"""Stagnation is an evaluation limit, independent of model response batching."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from test_harness import (
    BASELINE,
    BEST,
    REGRESSION,
    ScriptedStep,
    fake_runner,
    make_spec,
    response,
    tool,
)

from step_engineer import harness as harness_module
from step_engineer.harness import Harness


@pytest.mark.parametrize("limit", [1, 2, 4])
@pytest.mark.parametrize("batched", [True, False])
async def test_threshold_stops_next_write_and_evaluation_without_extra_request(
    tmp_path, monkeypatch, limit, batched
):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": limit})
    invocations = fake_runner(monkeypatch)
    improve = [
        tool("write_file", path="implementation.py", content=BEST),
        tool("evaluate_candidate"),
    ]
    stagnant = [tool("evaluate_candidate") for _ in range(limit)]
    forbidden_after_limit = [
        tool("write_file", path="implementation.py", content=REGRESSION),
        tool("evaluate_candidate"),
        tool("finish", summary="This must not run after the limit."),
    ]
    responses = (
        [response(*improve, *stagnant, *forbidden_after_limit)]
        if batched
        else [
            response(*improve),
            *(response(call) for call in stagnant),
            response(*forbidden_after_limit),
        ]
    )
    client = ScriptedStep(*responses)
    run_dir = tmp_path / "run"
    harness = Harness(spec, run_dir, client)
    result = await harness.run()

    assert result["stop_reason"] == "no_improvement_limit"
    assert len(client.requests) == (1 if batched else 1 + limit)
    assert result["tool_calls"] == 2 + limit
    assert harness.evaluations == 1 + limit
    assert harness.no_improvement == limit
    assert [record["saved_as_best"] for record in harness.history] == [True] + [False] * limit
    assert result["accepted"] and result["independently_checked"]
    assert result["final_validation"]["measurement"]["score"] == 4
    assert ("holdout", "validation", "best") in invocations
    assert (run_dir / "candidate" / "implementation.py").read_text() == BEST
    assert "+VERSION = 'best'" in (run_dir / "accepted.patch").read_text()
    assert (Path(spec.source_dir) / "implementation.py").read_text() == BASELINE


async def test_positive_improvement_resets_counter_before_next_boundary(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": 2})
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("evaluate_candidate"),
            tool("restore_best"),
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content=REGRESSION),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    result = await harness.run()

    assert result["accepted"] and result["stop_reason"] == "no_improvement_limit"
    assert [record["saved_as_best"] for record in harness.history] == [False, True, False, False]
    assert harness.no_improvement == 2 and harness.evaluations == 4
    assert result["tool_calls"] == 6
    assert (tmp_path / "run" / "candidate" / "implementation.py").read_text() == BEST


async def test_read_write_restore_and_tool_errors_do_not_count_as_evaluations(
    tmp_path, monkeypatch
):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": 1})
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(
            tool("list_files"),
            tool("read_file", path="implementation.py"),
            tool("unknown_tool"),
            tool("evaluate_candidate", unsupported=True),
            tool("write_file", path="check.py", content="Must be rejected."),
            tool("write_file", path="implementation.py", content=REGRESSION),
            tool("restore_best"),
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("finish", summary="Measured improvement."),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    result = await harness.run()

    assert result["accepted"] and result["stop_reason"] == "model_finished"
    assert harness.evaluations == 1 and harness.no_improvement == 0
    assert result["tool_calls"] == 10
    replies = [
        json.loads(message["content"]) for message in harness.messages if message["role"] == "tool"
    ]
    assert sum("error" in reply for reply in replies) == 3


async def test_failed_correctness_evaluation_counts_and_stops_later_writes(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": 1})
    fake_runner(monkeypatch)
    successful_runner = harness_module.run_command

    async def fail_regression(command, workspace, scratch, *, timeout_seconds=None):
        result = await successful_runner(
            command, workspace, scratch, timeout_seconds=timeout_seconds
        )
        if (
            command.name == "correctness"
            and (workspace / "implementation.py").read_text() == REGRESSION
        ):
            result["exit_code"] = 1
        return result

    monkeypatch.setattr(harness_module, "run_command", fail_regression)
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=REGRESSION),
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    result = await harness.run()

    assert result["stop_reason"] == "no_improvement_limit" and not result["accepted"]
    assert harness.evaluations == harness.no_improvement == 1
    assert result["tool_calls"] == 2 and len(client.requests) == 1
    assert harness.history[0]["feasible"] is False
    assert (tmp_path / "run" / "candidate" / "implementation.py").read_text() == REGRESSION
    assert (tmp_path / "run" / "accepted.patch").read_text() == ""


async def test_stagnation_stop_does_not_bypass_failed_final_validation(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": 1})
    fake_runner(monkeypatch, fail_holdout=True)
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("evaluate_candidate"),
            tool("finish", summary="Must not substitute for final validation."),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    result = await harness.run()

    assert result["stop_reason"] == "no_improvement_limit"
    assert not result["accepted"] and result["final_validation"]["passed"] is False
    assert result["final_validation"]["reason"] == "final_check_failed"
    assert harness.evaluations == 2 and result["tool_calls"] == 3
    assert (tmp_path / "run" / "accepted.patch").read_text() == ""
    assert "+VERSION = 'best'" in (tmp_path / "run" / "best-development.patch").read_text()


@pytest.mark.parametrize("limit", ["max_tool_calls", "max_model_turns"])
async def test_other_limits_still_stop_when_stagnation_threshold_is_not_reached(
    tmp_path, monkeypatch, limit
):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_no_improvement": 2, limit: 1})
    fake_runner(monkeypatch)
    calls = [tool("evaluate_candidate")]
    if limit == "max_tool_calls":
        calls.append(tool("write_file", path="implementation.py", content=BEST))
    harness = Harness(spec, tmp_path / "run", ScriptedStep(response(*calls)))
    result = await harness.run()

    assert result["stop_reason"] == (
        "tool_budget" if limit == "max_tool_calls" else "model_turn_budget"
    )
    assert harness.no_improvement == harness.evaluations == result["tool_calls"] == 1
    assert result["model_turns"] == 1 and not result["accepted"]
