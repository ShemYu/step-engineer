"""Final-only cases use new seeds and capacities, with the same selection rules."""

import json

from evaluator import first_fit, generated_cases, score_suite
from policy import select_jobs


def main():
    cases = generated_cases(
        range(1001, 1021),
        [(9, 31), (31, 9), (27, 35), (35, 27)],
        job_count=22,
        max_resource=15,
    )
    actual = score_suite(select_jobs, cases)
    baseline = score_suite(first_fit, cases)
    if actual["reward"] < baseline["reward"]:
        raise ValueError("Held-out total reward regressed below the first-fit baseline")
    print(json.dumps({"passed": True, "cases": len(cases), "non_regression": True}))


if __name__ == "__main__":
    main()
