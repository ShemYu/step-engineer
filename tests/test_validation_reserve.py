"""A development deadline must leave saved candidates time for final validation."""

from __future__ import annotations

import json

import pytest
from test_harness import BEST, REGRESSION, ScriptedStep, make_spec, response, tool

from step_engineer import harness as harness_module
from step_engineer.harness import BudgetExceeded, Harness


@pytest.mark.parametrize(
    ("phase", "remaining", "expected"),
    [
        ("optimizing", 60, 10),
        ("optimizing", 12, 2),
        ("optimizing", 10.1, 0.1),
        ("optimizing", 10, None),
        ("optimizing", 9, None),
        ("final_validation", 9, 9),
        ("final_validation", 0, None),
        ("baseline", 9, 9),
    ],
)
async def test_command_allow_deny_at_phase_deadline(
    tmp_path, monkeypatch, phase, remaining, expected
):
    spec = make_spec(tmp_path)
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    harness = Harness(spec, run_dir, ScriptedStep())
    harness.phase = phase
    monkeypatch.setattr(harness, "remaining", lambda: remaining)
    invocations = []

    async def runner(command, root, scratch, *, timeout_seconds):
        invocations.append(timeout_seconds)
        return {"exit_code": 0, "elapsed_seconds": 0, "sandboxed": True}

    monkeypatch.setattr(harness_module, "run_command", runner)
    command = spec.benchmark.model_copy(update={"timeout_seconds": 10})
    if expected is None:
        with pytest.raises(BudgetExceeded):
            await harness.command(command, harness.workspace.root)
        assert not invocations
    else:
        await harness.command(command, harness.workspace.root)
        assert invocations == [pytest.approx(expected)]


@pytest.mark.parametrize("development_check_finishes", [False, True])
async def test_exhausted_development_batch_still_validates_saved_best(
    tmp_path, monkeypatch, development_check_finishes
):
    spec = make_spec(tmp_path)
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content=REGRESSION),
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content="VERSION = 'unmeasured'\n"),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    remaining = [60.0]
    monkeypatch.setattr(harness, "remaining", lambda: remaining[0])
    invocations = []
    best_benchmarks = 0

    async def runner(command, root, scratch, *, timeout_seconds):
        nonlocal best_benchmarks
        content = (root / "implementation.py").read_text()
        version = (
            "best" if content == BEST else "regression" if content == REGRESSION else "baseline"
        )
        invocations.append((harness.phase, command.name, version, timeout_seconds))
        timed_out = False
        if harness.phase == "optimizing" and version == "best" and command.name == "benchmark":
            best_benchmarks += 1
            if best_benchmarks == spec.repetitions:
                remaining[0] = 11
        if harness.phase == "optimizing" and version == "regression":
            assert timeout_seconds == pytest.approx(1)
            remaining[0] -= timeout_seconds
            timed_out = not development_check_finishes
        return {
            "name": command.name,
            "exit_code": 1 if timed_out else 0,
            "stdout": json.dumps(
                {"metrics": {"latency": 4 if version == "best" else 10, "recall": 0.99}}
            ),
            "stderr": "",
            "elapsed_seconds": 0,
            "sandboxed": True,
            "timed_out": timed_out,
        }

    monkeypatch.setattr(harness_module, "run_command", runner)
    result = await harness.run()
    assert result["accepted"], result
    assert result["stop_reason"] == "wall_time_reserved_for_validation"
    assert result["tool_calls"] == 4
    assert len(client.requests) == 1
    assert harness.workspace.root.joinpath("implementation.py").read_text() == REGRESSION
    assert any(
        phase == "final_validation" and name == "holdout" for phase, name, _, _ in invocations
    )
    assert all(
        version == "best" for phase, _, version, _ in invocations if phase == "final_validation"
    )


async def test_request_using_exploration_time_does_not_start_tool_batch(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    remaining = [60.0]

    class Client(ScriptedStep):
        async def complete(self, *args, **kwargs):
            result = await super().complete(*args, **kwargs)
            remaining[0] = 10
            return result

    client = Client(response(tool("write_file", path="implementation.py", content=BEST)))
    harness = Harness(spec, tmp_path / "run", client)
    harness.run_dir.mkdir()
    harness.workspace.prepare()
    harness.baseline = harness.best = {"feasible": True, "score": 10}
    harness.phase = "optimizing"
    monkeypatch.setattr(harness, "remaining", lambda: remaining[0])
    await harness.optimize()
    assert harness.stop_reason == "wall_time_reserved_for_validation"
    assert harness.tool_calls == 0
    assert harness.workspace.root.joinpath("implementation.py").read_text() != BEST


async def test_reserve_cap_leaves_exploration_when_command_timeouts_are_large(
    tmp_path, monkeypatch
):
    spec = make_spec(tmp_path)
    spec.checks[0].timeout_seconds = 100
    spec.benchmark.timeout_seconds = 100
    spec.final_checks[0].timeout_seconds = 100
    client = ScriptedStep(response(content="Done"))
    harness = Harness(spec, tmp_path / "run", client)
    harness.run_dir.mkdir()
    harness.workspace.prepare()
    harness.baseline = harness.best = {"feasible": True, "score": 10}
    harness.phase = "optimizing"
    monkeypatch.setattr(harness, "remaining", lambda: 60)
    await harness.optimize()
    assert len(client.requests) == 1
    assert client.requests[0]["timeout_seconds"] == pytest.approx(36)
