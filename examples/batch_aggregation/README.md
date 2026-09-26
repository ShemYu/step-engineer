# Batch aggregation example

This example optimizes a real join-and-aggregate operation using only the Python standard library. The supplied baseline looks up each paid order's customer with a linear scan: O(orders × customers), plus result sorting. A hash index can reduce this to expected O(orders + customers), plus result sorting, while using additional memory for the index.

`processor.py` defines the complete behavior contract. In particular, duplicate customer IDs use the **first** customer, including when that customer is inactive. String and integer IDs remain distinct; unknown customers do not contribute; amounts are exact integers and may be negative. Results are sorted by region and inputs are preserved.

From the package root, run the bundled demonstration:

```sh
uv run step-engineer --runs-dir ./runs run examples/batch_aggregation/job.json --offline-demo
```

This is an **offline harness demonstration with a handwritten answer**, not a live Step-5-Preview result or evidence about that model's performance. `offline_solution.txt` provides the scripted answer and is deliberately absent from `job.json`'s file allowlist. Remove `--offline-demo` only when the Step provider has been configured for a live call. For a private dotenv file, explicitly pass the global `--env-file /absolute/path/to/step.env` option before `run`; see [integration instructions](../../docs/integrations.md).

The job accepts four explicitly listed source files, withholds `final_verify.py` from the development workspace, and permits changes only to `processor.py`. `verify.py` supplies deterministic randomized checks. `bench.py` builds 6,000 customers and 18,000 orders and checks basic output invariants. Timing comes from the external runner, including Python startup, input generation, aggregation, and validation; the program does not report its own timing metric. Compare repeated medians on the same machine, and do not treat a speedup from this one workload as a general benchmark result.

`final_verify.py` uses a separate oracle, additional seeds, larger cases, mixed ID types, Unicode regions, large signed integers, input-preservation checks, and an order-permutation check. It is listed in `final_only_files`, and its command appears only under `final_checks`. The harness keeps it outside the development workspace and Step's list/read tools, and restores it only in the final-validation workspace. Final check commands and file paths are withheld from Step's prompt. The example source remains reviewable by the parent engineer; file withholding is not a replacement for process isolation or a guarantee against malicious code.

CLI `source_dir: "."` is resolved relative to `job.json`, not your shell's working directory. When submitting the same job through MCP, replace `source_dir` with the example directory's absolute path because the MCP request has no job-file location.
