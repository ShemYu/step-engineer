# Resource allocation under two hard limits

This small synthetic example demonstrates a constrained search contract. It is a
pipeline example, **not evidence of Step model capability**; no model-generated
results are provided.

Implement `select_jobs(jobs, cpu_budget, memory_budget) -> list[str]` in `policy.py`.
Each job contains `id` (a unique string), `cpu`, `memory`, and `value` (positive
integers). Capacities are nonnegative integers. Select each job at most once,
using only input IDs, without modifying the input. CPU and memory totals must
each be **less than or equal to** their capacity. Returning no jobs, leaving
capacity unused, and any output order are allowed. Maximize total selected value.

CPU and memory are **simulated integer capacity units**, not measurements of host
CPU usage or resident memory. The example's environment envelope is 0–22 jobs,
1–15 units of each resource per job, values from 1–30, and each capacity from
0–35. Development and final cases both stay inside that envelope; final cases
shift the sizes and capacity balances within it.

The initial policy uses first-fit in input order. Larger individual value is not
always better:

| Case (CPU and memory budgets both 6) | First listed choice | Better combination |
| --- | --- | --- |
| Large `(6,6,value=9)`; two small `(3,3,value=6)` jobs | Large: value 9 | Two small: value 12 |
| Balanced `(3,3,value=9)`; CPU-heavy `(5,1,value=8)`; memory-heavy `(1,5,value=8)` | Balanced: value 9 | CPU-heavy + memory-heavy: value 16 |

These are hand-constructed arithmetic examples, not measured model results.

## What is fixed

- `evaluator.py` checks IDs, input preservation and both capacities, then computes
  reward from the original jobs. The candidate only returns IDs; it does not
  supply a score. Every scenario must satisfy the hard limits independently;
  aggregate reward cannot hide a violation. Violations fail the command instead
  of earning a penalized score.
- `verify.py` checks feasibility, including empty and insufficient-capacity inputs.
  It does not require an optimal answer.
- `bench.py` evaluates two illustrative cases and 16 deterministically generated
  cases. The metric is total `reward`, not runtime. One repetition is used because
  the cases and integer scoring are deterministic.
- `min_cpu_slack` and `min_memory_slack` report the smallest unused capacity for
  each resource across the scenarios, in integer simulation units.
  `mean_cpu_slack` and `mean_memory_slack` report average unused units so policies
  can be compared even when some scenarios fill capacity exactly. These are
  diagnostics, not objectives or constraints. An empty suite reports all four as
  zero with `cases=0`. Means divide by scenario count, never by capacity, so
  zero-capacity scenarios are valid.
- `final_verify.py` uses different seeds, capacity balances and case sizes with
  unchanged rules. It checks feasibility and requires aggregate reward at least
  as high as first-fit on those held-out cases; it does not require optimality.
- `job.json` permits editing only `policy.py`. The final verifier is excluded from
  the model's readable snapshot and restored for final validation. It is still
  public repository content, not a secret independent test set.

## Run without an API key

From a git checkout's root, these standard-library commands validate and measure
the checked-in baseline, including its final checks:

```sh
python3 examples/resource_allocation/verify.py
python3 examples/resource_allocation/bench.py
python3 examples/resource_allocation/final_verify.py
```

The repository also tests a hand-written dynamic-programming candidate through a
scripted client and the actual harness, including final validation. From the repo
root, `uv run pytest tests/test_resource_allocation.py -q` runs those keyless tests;
the real sandbox smoke test requires macOS.

## Optional live run

After installing step-engineer and configuring your local key, run from a git
checkout's root on supported macOS:

```sh
step-engineer --env-file .env.local --runs-dir runs run examples/resource_allocation/job.json
```

This calls the paid Step API. The example caps the conservative estimated cost at
$0.50, with 150,000 total tokens and 300 seconds. Each fixed evaluation command has
a 10-second timeout. `--offline-demo` only supports `batch_aggregation`; it is not
a simulator for this example.

## Trade-offs and limits

Exact search can improve reward at the cost of CPU and memory; a two-dimensional
dynamic program scales with both capacities and is reasonable only for small
integer capacities like these. Greedy policies are cheaper but may leave reward
behind. A candidate must finish inside command timeouts, and passing finite
holdouts does not prove generalization or optimality. These jobs have no duration,
dependencies, fairness, arrivals or scheduling uncertainty, so this is not a
production scheduler benchmark. Protected files and the local process sandbox
are engineering guardrails, not a hostile-code proof against evaluator tampering.
