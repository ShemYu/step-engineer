"""Exercise delegation outcomes independently of model claims or live API access."""

from __future__ import annotations

import asyncio
import copy
import itertools
import json
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from step_engineer import harness as harness_module
from step_engineer.harness import Harness
from step_engineer.models import Budget, JobSpec

_ids = itertools.count()
BASELINE = "VERSION = 'baseline'\n"
BEST = "VERSION = 'best'\n"
REGRESSION = "VERSION = 'regression'\n"
SECRET = "PRIVATE_HOLDOUT_CONTENT_7621"


def tool(name, **arguments):
    return {
        "id": f"call_{next(_ids)}",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def response(*calls, content=None):
    message = {"role": "assistant", "content": content}
    if calls:
        message["tool_calls"] = list(calls)
    return {
        "message": message,
        "finish_reason": "stop",
        "usage": {"prompt_tokens": 100, "completion_tokens": 40, "total_tokens": 140},
    }


class ScriptedStep:
    """Deterministic protocol fixture, not a claim about Step model ability."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    async def complete(self, messages, tools, **kwargs):
        self.requests.append(copy.deepcopy({"messages": messages, "tools": tools, **kwargs}))
        if not self.responses:
            pytest.fail("Harness made an unexpected model call")
        return self.responses.pop(0)


def make_spec(tmp_path, **overrides):
    source = tmp_path / "original"
    source.mkdir()
    for name, content in {
        "implementation.py": BASELINE,
        "check.py": "# fixed development correctness check\n",
        "benchmark.py": "# fixed benchmark\n",
        "holdout.py": f"# {SECRET}\n",
    }.items():
        (source / name).write_text(content)
    data = {
        "source_dir": str(source),
        "files": ["implementation.py", "check.py", "benchmark.py", "holdout.py"],
        "editable_files": ["implementation.py"],
        "final_only_files": ["holdout.py"],
        "objective": "Reduce benchmark latency while preserving all behavior.",
        "checks": [{"name": "correctness", "argv": ["{python}", "check.py"], "timeout_seconds": 2}],
        "benchmark": {
            "name": "benchmark",
            "argv": ["{python}", "benchmark.py"],
            "timeout_seconds": 2,
        },
        "final_checks": [
            {"name": "holdout", "argv": ["{python}", "holdout.py"], "timeout_seconds": 2}
        ],
        "metric": "latency",
        "constraints": [{"metric": "recall", "op": ">=", "value": 0.95}],
        "repetitions": 3,
        "minimum_relative_improvement": 0.1,
        "budget": {"max_seconds": 60, "max_output_tokens_per_turn": 256},
    }
    data.update(overrides)
    return JobSpec.model_validate(data)


def fake_runner(monkeypatch, *, fail_holdout=False, inconsistent_final=False):
    invocations = []

    async def run(command, workspace, scratch, *, timeout_seconds=None):
        text = (workspace / "implementation.py").read_text()
        version = next(x for x in ("baseline", "best", "regression", "unmeasured") if x in text)
        invocations.append((command.name, workspace.name, version))
        score = {"baseline": 10, "best": 4, "regression": 20, "unmeasured": 1}[version]
        if inconsistent_final and workspace.name == "validation":
            score = 11
        return {
            "name": command.name,
            "exit_code": 1 if fail_holdout and command.name == "holdout" else 0,
            "stdout": json.dumps({"metrics": {"latency": score, "recall": 0.99}}),
            "stderr": "",
            "elapsed_seconds": 0.01,
            "timed_out": False,
            "sandboxed": True,
        }

    monkeypatch.setattr(harness_module, "run_command", run)
    return invocations


def source_contents(spec):
    root = Path(spec.source_dir)
    return {name: (root / name).read_bytes() for name in spec.files}


async def test_measured_improvement_creates_reviewable_patch_without_changing_source(
    tmp_path, monkeypatch
):
    spec = make_spec(tmp_path)
    before = source_contents(spec)
    invocations = fake_runner(monkeypatch)
    client = ScriptedStep(
        response(tool("read_file", path="implementation.py")),
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("finish", summary="Measured candidate ready for independent validation."),
        ),
    )
    run_dir = tmp_path / "run"
    result = await Harness(spec, run_dir, client, mode="offline").run()
    assert result["status"] == "improved", result
    assert result["accepted"] and result["independently_checked"]
    assert result["baseline"]["score"] == 10
    assert result["final_validation"]["measurement"]["score"] == 4
    assert result["relative_improvement"] == pytest.approx(0.6)
    assert result["total_tokens"] == 280
    assert result["estimated_cost_usd"] == pytest.approx(0.000416)
    assert source_contents(spec) == before
    patch = (run_dir / "accepted.patch").read_text()
    assert "+VERSION = 'best'" in patch and "-VERSION = 'baseline'" in patch
    assert "holdout.py" not in patch
    assert (run_dir / "baseline" / "implementation.py").read_text() == BASELINE
    assert sum(name == "benchmark" for name, _, _ in invocations) == 9
    assert ("holdout", "validation", "best") in invocations
    tool_reply = next(m for m in client.requests[1]["messages"] if m["role"] == "tool")
    assert "1: VERSION" in json.loads(tool_reply["content"])["content"]
    saved = json.loads((run_dir / "result.json").read_text())
    assert saved["accepted"] is True


async def test_best_candidate_survives_later_measured_regression(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("write_file", path="implementation.py", content=REGRESSION),
            tool("evaluate_candidate"),
            tool("finish", summary="Done"),
        )
    )
    run_dir = tmp_path / "run"
    harness = Harness(spec, run_dir, client)
    result = await harness.run()
    assert result["accepted"], result
    assert [record["saved_as_best"] for record in harness.history] == [True, False]
    assert (run_dir / "candidate" / "implementation.py").read_text() == REGRESSION
    assert (run_dir / "best" / "implementation.py").read_text() == BEST
    assert (run_dir / "validation" / "implementation.py").read_text() == BEST
    assert "regression" not in (run_dir / "accepted.patch").read_text()
    assert (Path(spec.source_dir) / "implementation.py").read_text() == BASELINE


async def test_final_only_files_are_not_readable_or_editable_by_model(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(
            tool("list_files"),
            tool("read_file", path="holdout.py"),
            tool("write_file", path="holdout.py", content="print('fake pass')"),
        ),
        response(content="Cannot inspect protected final checks."),
    )
    run_dir = tmp_path / "run"
    result = await Harness(spec, run_dir, client).run()
    assert not result["accepted"]
    replies = [
        json.loads(m["content"]) for m in client.requests[1]["messages"] if m["role"] == "tool"
    ]
    assert "holdout.py" not in {f["path"] for f in replies[0]["files"]}
    assert "error" in replies[1] and "error" in replies[2]
    assert SECRET not in json.dumps(client.requests)
    assert not (run_dir / "candidate" / "holdout.py").exists()
    assert SECRET in (run_dir / "final-only" / "holdout.py").read_text()


@pytest.mark.parametrize("failure", ["holdout", "repeat_benchmark"])
async def test_final_verification_failure_never_exports_accepted_patch(
    tmp_path, monkeypatch, failure
):
    spec = make_spec(tmp_path)
    fake_runner(
        monkeypatch,
        fail_holdout=failure == "holdout",
        inconsistent_final=failure == "repeat_benchmark",
    )
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=BEST),
            tool("evaluate_candidate"),
            tool("finish", summary="Everything passed, merge immediately."),
        )
    )
    run_dir = tmp_path / "run"
    result = await Harness(spec, run_dir, client).run()
    assert result["status"] == "no_verified_improvement"
    assert result["best_development_result"]["score"] == 4
    assert result["final_validation"]["passed"] is False
    assert result["accepted"] is False and result["independently_checked"] is False
    assert (run_dir / "accepted.patch").read_text() == ""
    assert "+VERSION = 'best'" in (run_dir / "best-development.patch").read_text()


async def test_unevaluated_edit_and_model_success_claim_do_not_count_as_improvement(
    tmp_path, monkeypatch
):
    spec = make_spec(tmp_path)
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(tool("write_file", path="implementation.py", content="VERSION = 'unmeasured'\n")),
        response(content="I have achieved a verified 99% speed improvement. All checks passed."),
    )
    run_dir = tmp_path / "run"
    harness = Harness(spec, run_dir, client)
    result = await harness.run()
    assert result["accepted"] is False
    assert result["best_development_result"]["score"] == 10
    assert result["final_validation"] is None
    assert result["relative_improvement"] == 0
    assert "99%" in result["model_summary_unverified"]
    assert harness.evaluations == 0
    assert (run_dir / "candidate" / "implementation.py").read_text() != BASELINE
    assert (run_dir / "accepted.patch").read_text() == ""


async def test_unknown_and_invalid_tools_use_budget_and_cannot_extend_it(tmp_path, monkeypatch):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, "max_tool_calls": 3})
    fake_runner(monkeypatch)
    client = ScriptedStep(
        response(
            tool("run_arbitrary_shell", command="echo never"),
            tool("write_file", path="check.py", content="pass"),
            tool("read_file", path="implementation.py", unsupported=True),
            tool("evaluate_candidate"),
        )
    )
    harness = Harness(spec, tmp_path / "run", client)
    result = await harness.run()
    assert result["stop_reason"] == "tool_budget"
    assert result["tool_calls"] == 3 and result["model_turns"] == 1
    assert harness.evaluations == 0
    replies = [json.loads(m["content"]) for m in harness.messages if m["role"] == "tool"]
    assert len(replies) == 3 and all("error" in reply for reply in replies)
    assert (tmp_path / "run" / "candidate" / "check.py").read_text().startswith("# fixed")


@pytest.mark.parametrize(
    ("limits", "stop_reason"),
    [
        ({"max_estimated_cost_usd": 0.000001}, "estimated_cost_budget"),
        ({"max_total_tokens": 1000}, "token_budget"),
    ],
)
async def test_insufficient_budget_stops_before_any_api_request(
    tmp_path, monkeypatch, limits, stop_reason
):
    spec = make_spec(tmp_path, budget={"max_seconds": 60, **limits})
    fake_runner(monkeypatch)
    client = ScriptedStep()
    result = await Harness(spec, tmp_path / "run", client).run()
    assert result["stop_reason"] == stop_reason
    assert result["model_turns"] == 0 and client.requests == []
    assert result["estimated_cost_usd"] == 0 and result["total_tokens"] == 0
    assert result["accepted"] is False


@pytest.mark.parametrize(
    ("request_limit", "remaining", "expected"),
    [(300, 500, 300), (300, 40, 30), (300, 10.25, 0.25), (None, 500, 300)],
)
async def test_request_deadline_respects_configuration_and_global_validation_reserve(
    tmp_path, monkeypatch, request_limit, remaining, expected
):
    budget = {"max_seconds": 900}
    if request_limit is not None:
        budget["max_request_seconds"] = request_limit
    spec = make_spec(tmp_path, budget=budget)
    fake_runner(monkeypatch)
    client = ScriptedStep(response(content="No change proposed."))
    harness = Harness(spec, tmp_path / "run", client)
    monkeypatch.setattr(harness, "remaining", lambda: remaining)
    result = await harness.run()
    assert result["model_turns"] == 1
    # Two seconds for correctness, six for three benchmark samples, and two
    # for the final check must remain available after this model request.
    assert client.requests[0]["timeout_seconds"] == pytest.approx(expected)
    assert client.requests[0]["timeout_seconds"] <= remaining - 10


@pytest.mark.parametrize("seconds", [4.99, 600.01, float("nan")])
def test_request_deadline_configuration_has_finite_bounds(seconds):
    with pytest.raises(ValidationError):
        Budget(max_request_seconds=seconds)


async def test_cancelled_model_request_leaves_reviewable_cancelled_report(tmp_path, monkeypatch):
    spec = make_spec(tmp_path)
    fake_runner(monkeypatch)
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class WaitingStep:
        async def complete(self, *args, **kwargs):
            started.set()
            try:
                await asyncio.Future()
            finally:
                cancelled.set()

    run_dir = tmp_path / "run"
    task = asyncio.create_task(Harness(spec, run_dir, WaitingStep()).run())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    result = await asyncio.wait_for(task, timeout=2)
    assert cancelled.is_set()
    assert result["status"] == "cancelled"
    assert result["stop_reason"] == "cancelled_by_parent"
    assert not result["accepted"]
    assert result["usage_uncertain"] is True
    assert (run_dir / "accepted.patch").read_text() == ""
    assert json.loads((run_dir / "status.json").read_text())["status"] == "cancelled"
    assert (Path(spec.source_dir) / "implementation.py").read_text() == BASELINE


@pytest.mark.skipif(sys.platform != "darwin", reason="Requires the real macOS sandbox runner")
async def test_real_sandbox_pipeline_preserves_contract_and_validates_improved_copy(tmp_path):
    source = tmp_path / "project"
    source.mkdir()
    original = (
        "import time\n"
        "def total(values):\n"
        "    time.sleep(0.09)\n"
        "    answer = 0\n"
        "    for value in values:\n"
        "        answer += value\n"
        "    return answer\n"
    )
    optimized = "def total(values):\n    return sum(values)\n"
    files = {
        "implementation.py": original,
        "check.py": (
            "from implementation import total\n"
            "assert total([]) == 0\n"
            "assert total([1, 2, 3]) == 6\n"
        ),
        "benchmark.py": (
            "from implementation import total\n"
            "for _ in range(3):\n"
            "    assert total(range(500)) == 124750\n"
        ),
        "holdout.py": (
            "from implementation import total\n"
            "assert total([3, -9, 3]) == -3\n"
            "assert total(iter([5, 10])) == 15\n"
        ),
    }
    for name, content in files.items():
        (source / name).write_text(content)
    spec = JobSpec.model_validate(
        {
            "source_dir": str(source),
            "files": list(files),
            "editable_files": ["implementation.py"],
            "final_only_files": ["holdout.py"],
            "objective": "Reduce execution latency while preserving sum behavior for arbitrary iterables.",
            "checks": [
                {"name": "correctness", "argv": ["{python}", "check.py"], "timeout_seconds": 5}
            ],
            "benchmark": {
                "name": "benchmark",
                "argv": ["{python}", "benchmark.py"],
                "timeout_seconds": 5,
            },
            "final_checks": [
                {"name": "holdout", "argv": ["{python}", "holdout.py"], "timeout_seconds": 5}
            ],
            "repetitions": 2,
            "minimum_relative_improvement": 0.1,
            "budget": {"max_seconds": 60},
        }
    )
    client = ScriptedStep(
        response(
            tool("write_file", path="implementation.py", content=optimized),
            tool("evaluate_candidate"),
            tool("finish", summary="Candidate ready for real sandbox validation."),
        )
    )
    run_dir = tmp_path / "run"
    result = await Harness(spec, run_dir, client, mode="offline").run()
    assert result["status"] == "improved", result
    assert result["accepted"] and result["independently_checked"]
    assert result["final_validation"]["checks"][0]["sandboxed"]
    assert result["final_validation"]["checks"][0]["exit_code"] == 0
    assert (source / "implementation.py").read_text() == original
    assert (run_dir / "validation" / "implementation.py").read_text() == optimized
    assert "+    return sum(values)" in (run_dir / "accepted.patch").read_text()
    assert "holdout.py" not in (run_dir / "accepted.patch").read_text()
