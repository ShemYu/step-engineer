"""Protected finite development suite; maximize total value of valid selections."""

import json

from evaluator import development_cases, score_suite
from policy import select_jobs

if __name__ == "__main__":
    print(json.dumps({"metrics": score_suite(select_jobs, development_cases())}))
