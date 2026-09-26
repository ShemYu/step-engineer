"""Review checks for interactions between independently developed guard fixes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_harness import BEST, REGRESSION, ScriptedStep, make_spec, response, tool

from step_engineer import harness as harness_module
from step_engineer.harness import Harness


def decimal_runner(monkeypatch, clock=None):
    calls = []

    async def run(command, workspace, scratch, *, timeout_seconds=None):
        if clock is not None:
            assert timeout_seconds > 0
            clock[0] -= min(1.0, timeout_seconds)
        text = (workspace / "implementation.py").read_text()
        score = 0.27 if "best" in text else 0.3
        calls.append((workspace.name, command.name, text))
        return {
            "name": command.name,
            "exit_code": 0,
            "stdout": json.dumps({"metrics": {"latency": score, "recall": 0.99}}),
            "stderr": "",
            "elapsed_seconds": 1.0,
            "timed_out": False,
            "sandboxed": True,
        }

    monkeypatch.setattr(harness_module, "run_command", run)
    return calls


@pytest.mark.parametrize("split_batch", [False, True])
async def test_stagnation_stop_still_validates_exact_threshold_best(
    tmp_path, monkeypatch, split_batch
):
    spec = make_spec(
        tmp_path,
        budget={"max_seconds": 60, "max_no_improvement": 1},
    )
    calls = decimal_runner(monkeypatch)
    first = [
        tool("write_file", path="implementation.py", content=BEST),
        tool("evaluate_candidate"),
        tool("evaluate_candidate"),
    ]
    forbidden_after_stop = [
        tool("write_file", path="implementation.py", content=REGRESSION),
        tool("evaluate_candidate"),
        tool("finish", summary="Do not execute after the stop boundary."),
    ]
    replies = (
        [response(*first), response(*forbidden_after_stop)]
        if split_batch
        else [response(*first, *forbidden_after_stop)]
    )
    client = ScriptedStep(*replies)
    harness = Harness(spec, tmp_path / "run", client)

    result = await harness.run()

    assert result["accepted"], result
    assert result["stop_reason"] == "no_improvement_limit"
    assert harness.evaluations == 2
    assert len(client.requests) == 1
    assert [item["saved_as_best"] for item in harness.history] == [True, False]
    assert result["relative_improvement"] == pytest.approx(0.1)
    assert (harness.workspace.root / "implementation.py").read_text() == BEST
    assert any(root == "validation" and name == "holdout" for root, name, _ in calls)
    assert "regression" not in (harness.run_dir / "accepted.patch").read_text()


async def test_exploration_deadline_transfers_to_final_validation_of_threshold_best(
    tmp_path, monkeypatch
):
    spec = make_spec(tmp_path)
    clock = [60.0]
    calls = decimal_runner(monkeypatch, clock)

    class ClockedStep(ScriptedStep):
        async def complete(self, *args, **kwargs):
            answer = await super().complete(*args, **kwargs)
            # Four development commands fit before the ten-second final reserve.
            clock[0] = 14.0
            return answer

    client = ClockedStep(
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("evaluate_candidate"),
            tool("finish", summary="An extra evaluation must not consume final time."),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    monkeypatch.setattr(harness, "remaining", lambda: clock[0])

    result = await harness.run()

    assert result["accepted"], result
    assert result["stop_reason"] == "wall_time_reserved_for_validation"
    assert result["final_validation"]["passed"]
    assert result["relative_improvement"] == pytest.approx(0.1)
    assert len([item for item in calls if item[0] == "validation"]) == 5
    assert clock[0] >= 0
    assert (Path(spec.source_dir) / "implementation.py").read_text() != BEST
