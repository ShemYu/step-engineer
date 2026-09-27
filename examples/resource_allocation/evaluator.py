"""Protected input generation and scoring; candidates return IDs, never scores."""

import copy
import json
import random


class ContractViolation(ValueError):
    pass


def evaluate_selection(policy, jobs, cpu_budget, memory_budget):
    original = json.dumps(jobs, sort_keys=True, allow_nan=False)
    working = copy.deepcopy(jobs)
    selected = policy(working, cpu_budget, memory_budget)
    try:
        # Python equality treats 3 == 3.0 and 1 == True. Canonical JSON preserves
        # those distinctions for this example's plain string/integer job data.
        unchanged = json.dumps(working, sort_keys=True, allow_nan=False) == original
    except (TypeError, ValueError):
        unchanged = False
    if not unchanged:
        raise ContractViolation("Input jobs were modified")
    if not isinstance(selected, list) or any(not isinstance(item, str) for item in selected):
        raise ContractViolation("Return a list of string job IDs")
    if len(selected) != len(set(selected)):
        raise ContractViolation("Duplicate selected ID")
    by_id = {job["id"]: job for job in jobs}
    if any(item not in by_id for item in selected):
        raise ContractViolation("Unknown selected ID")
    cpu = sum(by_id[item]["cpu"] for item in selected)
    memory = sum(by_id[item]["memory"] for item in selected)
    if cpu > cpu_budget or memory > memory_budget:
        raise ContractViolation("CPU or memory capacity exceeded")
    return {
        "reward": sum(by_id[item]["value"] for item in selected),
        "cpu_used": cpu,
        "memory_used": memory,
    }


def first_fit(jobs, cpu_budget, memory_budget):
    """Protected reference for a non-regression floor; this is not an optimum."""
    selected = []
    for job in jobs:
        if job["cpu"] <= cpu_budget and job["memory"] <= memory_budget:
            selected.append(job["id"])
            cpu_budget -= job["cpu"]
            memory_budget -= job["memory"]
    return selected


def tradeoff_cases():
    return [
        (
            [
                {"id": "large", "cpu": 6, "memory": 6, "value": 9},
                {"id": "small-a", "cpu": 3, "memory": 3, "value": 6},
                {"id": "small-b", "cpu": 3, "memory": 3, "value": 6},
            ],
            6,
            6,
        ),
        (
            [
                {"id": "balanced", "cpu": 3, "memory": 3, "value": 9},
                {"id": "cpu-heavy", "cpu": 5, "memory": 1, "value": 8},
                {"id": "memory-heavy", "cpu": 1, "memory": 5, "value": 8},
            ],
            6,
            6,
        ),
    ]


def generated_cases(seeds, capacities, *, job_count=18, max_resource=12):
    """Finite deterministic cases, with independent CPU and memory pressure."""
    cases = []
    for index, seed in enumerate(seeds):
        rng = random.Random(seed)
        jobs = [
            {
                "id": f"job-{seed}-{i}",
                "cpu": rng.randint(1, max_resource),
                "memory": rng.randint(1, max_resource),
                "value": rng.randint(1, 30),
            }
            for i in range(job_count)
        ]
        cpu_budget, memory_budget = capacities[index % len(capacities)]
        cases.append((jobs, cpu_budget, memory_budget))
    return cases


def development_cases():
    return tradeoff_cases() + generated_cases(range(16), [(20, 20), (24, 14), (14, 24)])


def score_suite(policy, cases):
    results = [evaluate_selection(policy, *case) for case in cases]
    cpu_slacks = [case[1] - result["cpu_used"] for case, result in zip(cases, results)]
    memory_slacks = [case[2] - result["memory_used"] for case, result in zip(cases, results)]
    # Violations raise above and make the command fail; they cannot buy more reward.
    # An empty suite has no observed slack; report zero alongside cases=0.
    return {
        "reward": sum(result["reward"] for result in results),
        "resource_violations": 0,
        "cases": len(cases),
        "min_cpu_slack": min(cpu_slacks, default=0),
        "min_memory_slack": min(memory_slacks, default=0),
        "mean_cpu_slack": sum(cpu_slacks) / len(cases) if cases else 0,
        "mean_memory_slack": sum(memory_slacks) / len(cases) if cases else 0,
    }
