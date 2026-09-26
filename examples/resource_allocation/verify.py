"""Protected feasibility checks: a valid policy does not have to be optimal."""

import json

from evaluator import development_cases, evaluate_selection
from policy import select_jobs


def main():
    one = [{"id": "one", "cpu": 3, "memory": 4, "value": 7}]
    cases = [([], 0, 0), (one, 3, 4), (one, 2, 4), (one, 3, 3), (one, 0, 0)]
    cases += development_cases()
    for case in cases:
        evaluate_selection(select_jobs, *case)
    print(json.dumps({"passed": True, "cases": len(cases)}))


if __name__ == "__main__":
    main()
