"""Contract and keyless real-harness checks for the synthetic allocation example."""

from __future__ import annotations

import copy
import importlib.util
import inspect
import json
import sys
from pathlib import Path

import pytest

from step_engineer.cli import load_job
from step_engineer.harness import Harness

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "resource_allocation"


# Hand-written test fixture, not a Step-generated policy or a live model result.
def select_jobs(jobs, cpu_budget, memory_budget):
    states = {(0, 0): (0, [])}
    for job in jobs:
        updated = dict(states)
        for (cpu, memory), (value, selected) in states.items():
            key = (cpu + job["cpu"], memory + job["memory"])
            if key[0] > cpu_budget or key[1] > memory_budget:
                continue
            reward = value + job["value"]
            if key not in updated or reward > updated[key][0]:
                updated[key] = (reward, selected + [job["id"]])
        states = updated
    return max(states.values(), key=lambda item: item[0])[1]


DP_SOURCE = inspect.getsource(select_jobs)


def load_example(name):
    # Load only import-independent modules; never overwrite global "policy" or
    # "evaluator" modules used by other examples or tests.
    spec = importlib.util.spec_from_file_location(
        f"allocation_example_{name}", EXAMPLE / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def evaluator():
    return load_example("evaluator")


@pytest.fixture
def dp_policy():
    return select_jobs


@pytest.mark.parametrize(
    ("cpu_budget", "memory_budget", "allowed"),
    [(3, 4, True), (4, 5, True), (2, 4, False), (3, 3, False), (0, 0, False)],
)
def test_inclusive_capacity_boundaries(evaluator, cpu_budget, memory_budget, allowed):
    jobs = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    policy = lambda *_: ["one"]
    if allowed:
        assert evaluator.evaluate_selection(policy, jobs, cpu_budget, memory_budget) == {
            "reward": 7,
            "cpu_used": 3,
            "memory_used": 4,
        }
    else:
        with pytest.raises(evaluator.ContractViolation, match="capacity"):
            evaluator.evaluate_selection(policy, jobs, cpu_budget, memory_budget)


@pytest.mark.parametrize("selected", [["one", "one"], ["unknown"], [1], "one", {"reward": 999}])
def test_invalid_selection_cannot_supply_reward(evaluator, selected):
    jobs = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    with pytest.raises(evaluator.ContractViolation):
        evaluator.evaluate_selection(lambda *_: selected, jobs, 100, 100)


def test_empty_and_feasible_nonoptimal_policies_are_allowed(evaluator):
    assert evaluator.evaluate_selection(lambda *_: [], [], 0, 0)["reward"] == 0
    jobs, cpu, memory = evaluator.tradeoff_cases()[0]
    assert evaluator.evaluate_selection(lambda *_: [], jobs, cpu, memory)["reward"] == 0
    assert evaluator.evaluate_selection(lambda *_: ["large"], jobs, cpu, memory)["reward"] == 9


def test_input_mutation_is_rejected_even_if_selection_fits(evaluator):
    jobs = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    before = copy.deepcopy(jobs)

    def mutate(candidate_jobs, *_):
        candidate_jobs[0]["value"] = 999
        return ["one"]

    with pytest.raises(evaluator.ContractViolation, match="modified"):
        evaluator.evaluate_selection(mutate, jobs, 3, 4)
    assert jobs == before


@pytest.mark.parametrize(("field", "replacement"), [("cpu", 3.0), ("value", True)])
def test_equal_numeric_values_with_changed_types_are_input_mutations(evaluator, field, replacement):
    jobs = [{"id": "one", "cpu": 3, "memory": 4, "value": 1}]
    assert jobs[0][field] == replacement
    assert type(jobs[0][field]) is not type(replacement)

    def mutate(candidate_jobs, *_):
        candidate_jobs[0][field] = replacement
        return ["one"]

    with pytest.raises(evaluator.ContractViolation, match="modified"):
        evaluator.evaluate_selection(mutate, jobs, 3, 4)
    assert type(jobs[0][field]) is int


def test_aggregate_reward_never_hides_a_single_capacity_violation(evaluator):
    job = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    cases = [(job, 3, 4), (job, 2, 4)]
    with pytest.raises(evaluator.ContractViolation, match="capacity"):
        evaluator.score_suite(lambda *_: ["one"], cases)


def test_slack_metrics_use_each_resources_minimum_unused_units(evaluator):
    jobs = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    cases = [(jobs, 5, 8), (jobs, 9, 5)]
    assert evaluator.score_suite(lambda *_: ["one"], cases) == {
        "reward": 14,
        "resource_violations": 0,
        "cases": 2,
        "min_cpu_slack": 2,
        "min_memory_slack": 1,
        "mean_cpu_slack": 4,
        "mean_memory_slack": 2.5,
    }


@pytest.mark.parametrize("cases", [[], [([], 0, 0)]])
def test_empty_suite_and_zero_capacity_have_defined_slack(evaluator, cases):
    metrics = evaluator.score_suite(lambda *_: [], cases)
    assert metrics["reward"] == metrics["min_cpu_slack"] == metrics["min_memory_slack"] == 0
    assert metrics["mean_cpu_slack"] == metrics["mean_memory_slack"] == 0
    assert metrics["cases"] == len(cases)


def test_small_tradeoffs_and_development_suite_leave_feasible_improvement(evaluator, dp_policy):
    baseline = load_example("policy").select_jobs
    for case, optimum in zip(evaluator.tradeoff_cases(), [12, 16], strict=True):
        assert evaluator.evaluate_selection(baseline, *case)["reward"] == 9
        assert evaluator.evaluate_selection(dp_policy, *case)["reward"] == optimum
    cases = evaluator.development_cases()
    before = copy.deepcopy(cases)
    baseline_result = evaluator.score_suite(baseline, cases)
    candidate_result = evaluator.score_suite(dp_policy, cases)
    assert baseline_result["resource_violations"] == candidate_result["resource_violations"] == 0
    assert candidate_result["reward"] > baseline_result["reward"]
    assert cases == before


def test_shifted_cases_share_rules_and_remain_inside_small_envelope(evaluator, dp_policy):
    cases = evaluator.generated_cases(
        range(2001, 2011), [(1, 35), (35, 1), (17, 29)], job_count=22, max_resource=15
    )
    baseline = evaluator.score_suite(evaluator.first_fit, cases)
    candidate = evaluator.score_suite(dp_policy, cases)
    assert candidate["reward"] >= baseline["reward"]
    for jobs, cpu, memory in cases:
        assert 0 <= cpu <= 35 and 0 <= memory <= 35 and len(jobs) <= 22
        assert all(1 <= job[key] <= 15 for job in jobs for key in ("cpu", "memory"))
        assert all(1 <= job["value"] <= 30 for job in jobs)
        assert len({job["id"] for job in jobs}) == len(jobs)


class ScriptedAllocationClient:
    def __init__(self, source=DP_SOURCE):
        self.source = source

    async def complete(self, messages, tools, **kwargs):
        calls = [
            ("read_file", {"path": "final_verify.py"}),
            ("write_file", {"path": "policy.py", "content": self.source}),
            ("evaluate_candidate", {}),
            ("finish", {"summary": "Hand-written fixture; no model or API was used."}),
        ]
        return {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"allocation-{i}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(arguments)},
                    }
                    for i, (name, arguments) in enumerate(calls)
                ],
            },
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "finish_reason": "tool_calls",
        }


@pytest.mark.skipif(sys.platform != "darwin", reason="Real macOS sandbox smoke test")
async def test_keyless_harness_verifies_candidate_and_protects_holdout(tmp_path):
    spec = load_job(EXAMPLE / "job.json")
    original = {name: (EXAMPLE / name).read_bytes() for name in spec.files}
    harness = Harness(spec, tmp_path / "run", ScriptedAllocationClient(), mode="offline")
    result = await harness.run()
    assert result["accepted"] and result["independently_checked"], result
    assert result["total_tokens"] == result["estimated_cost_usd"] == 0
    assert result["final_validation"]["measurement"]["score"] > result["baseline"]["score"]
    assert spec.editable_files == ["policy.py"]
    assert spec.final_only_files == ["final_verify.py"]
    replies = [
        json.loads(message["content"]) for message in harness.messages if message["role"] == "tool"
    ]
    assert "error" in replies[0]
    assert not (harness.workspace.root / "final_verify.py").exists()
    assert (harness.run_dir / "validation" / "final_verify.py").exists()
    assert {name: (EXAMPLE / name).read_bytes() for name in spec.files} == original
    assert (harness.run_dir / "accepted.patch").read_text().startswith("--- a/policy.py\n")


@pytest.mark.skipif(sys.platform != "darwin", reason="Real macOS sandbox smoke test")
async def test_heldout_regression_rejects_an_improved_development_candidate(tmp_path):
    # Fault injection: a policy unnecessarily refuses larger capacities. It is
    # still feasible everywhere, so only holdout non-regression catches the loss.
    restricted = DP_SOURCE.replace(
        "    states =",
        "    if cpu_budget > 24 or memory_budget > 24:\n        return []\n    states =",
        1,
    )
    harness = Harness(
        load_job(EXAMPLE / "job.json"),
        tmp_path / "run",
        ScriptedAllocationClient(restricted),
        mode="offline",
    )
    result = await harness.run()
    assert result["best_development_result"]["score"] > result["baseline"]["score"]
    assert result["accepted"] is False
    assert result["final_validation"]["reason"] == "final_check_failed"
    assert (harness.run_dir / "accepted.patch").read_text() == ""
