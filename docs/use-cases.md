# Choosing a task for Step Engineer

[README](../README.md) · [繁體中文](use-cases.zh-TW.md) · [Copyable task brief](task-brief.md) · [Evidence](step-evidence.md)

The product hypothesis is that Step can find valuable feasible solutions when rules are explicit, objectives compete, and experiments return useful feedback. For example, a policy might earn more reward by using spare memory, accepting a permitted delay, or spending less effort once a quality requirement is met. The evidence does **not** establish that Step is generally better than other models at these tasks.

The orchestrator defines which exchanges are allowed. Step explores implementations; the harness measures them and preserves qualifying improvements. A solution near a constraint boundary is a candidate, not automatically the best choice: uncertainty, workload changes, and recovery costs can make a solution with more margin preferable.

## Is the task ready?

| Requirement | A concrete answer before delegation |
| --- | --- |
| Controllable actions | Identify the function, policy, or configuration that Step can change in explicitly listed source files. |
| Fixed evaluation | Supply checks, fixtures, and a benchmark outside `editable_files`; freeze scoring rules before trials. |
| Hard constraints | State what must never be exchanged for score, how each condition is checked, and any required margin. |
| Objective and tradeoffs | Select one scalar objective; turn other requirements into limits or fixed terms in its scoring formula. |
| Useful freedom | Name at least one lawful tradeoff or alternative strategy. A fully prescribed solution leaves little to search. |
| Existing solutions | Try a suitable established algorithm or solver first. Use it as a baseline, or adopt it directly if it already solves the task adequately. Constraints alone do not justify an LLM. |
| Feasible baseline | The unchanged implementation passes development checks and all benchmark constraints. An invalid baseline stops the current harness before model exploration. |
| Bounded experiments | Fix representative workloads, feedback, holdouts, and time/token/cost limits. Trials must be practical within that budget. |

**Objective tension is different from infeasibility.** If latency and quality cannot both reach their preferred levels, the owner can specify a quality floor and optimize latency. If two mandatory rules demand mutually exclusive behavior, no valid optimization can satisfy them. Resolve the contract or establish feasibility first; this harness does not diagnose or solve arbitrary infeasible contracts.

**Permitted slack is different from cheating.** Using a documented grace period is legitimate only when the task owner accepts that delay. Altering the penalty calculation, recognizing fixture IDs, weakening tests, hiding dropped jobs, or inventing measurements changes the evaluation instead of improving the solution.

## 1. Select jobs under CPU and memory caps

| Part | Task contract |
| --- | --- |
| Environment | A known batch of jobs, each with reward and resource requirements; a CPU cap and a memory cap. |
| Action | Change the selection policy that returns a subset of the supplied jobs. |
| Objective | Maximize total reward over a fixed evaluation suite. |
| Hard limits | Respect both caps in every instance; use valid job IDs at most once; preserve input data. |
| Lawful tradeoff | Skip an individually attractive but expensive job if several other jobs yield more reward within the same caps. Unused capacity is allowed. |
| Holdout | Unseen job combinations and capacities, ties, dominant jobs, empty selections, and cases where a simple reward-per-resource heuristic fails. |
| Current support | The [resource-allocation example](../examples/resource_allocation/README.md) supplies a synthetic local task. Its fixtures and any scripted solution demonstrate the contract and harness, **not live Step performance**. It does not submit real compute jobs. |

Dynamic programming or an integer-programming solver may already solve this allocation problem well. The synthetic example does not establish an advantage over either; use an appropriate conventional solution as the comparison before adding model-driven search.

## 2. Search throughput subject to a quality floor

| Part | Task contract |
| --- | --- |
| Environment | A local corpus and query set, a fixed reference answer set, and a runnable search implementation. |
| Action | Change search effort, candidate selection, or an index-building strategy in the allowed implementation. |
| Objective | Maximize measured queries per second on the declared workload. |
| Hard limits | Meet the chosen recall floor and memory cap; retain required filters and output semantics. Specify whether recall must hold per query group as well as in aggregate. |
| Lawful tradeoff | Reduce excess search effort while retaining the required quality margin; use more permitted memory to reduce query work. |
| Holdout | New queries, rare categories, different corpus sizes, and harder query distributions. Check the required floor on holdouts explicitly. |
| Current support | A custom local `JobSpec` can wrap a suitable implementation and evaluator. No retrieval dataset, quality evaluator, index service, or memory instrumentation is supplied for this use case. |

## 3. Schedule work with deadlines and switching costs

| Part | Task contract |
| --- | --- |
| Environment | A local simulator with jobs, durations, resource limits, switching costs, and explicit deadline/penalty rules. |
| Action | Modify the scheduling policy's ordering, batching, or admission decisions using only information available at that decision. |
| Objective | Maximize completed reward minus the penalties defined before the run. |
| Hard limits | Respect resource capacity, dependencies, and any hard completion deadlines. Account for rejected or unfinished jobs according to the contract. |
| Lawful tradeoff | Use an allowed soft-deadline grace interval to complete more valuable work, or batch similar jobs to reduce switching overhead. A hard deadline has no implicit grace. |
| Holdout | New seeds and arrival patterns, bursts, scarce resources, and workloads where locally attractive choices harm later outcomes. |
| Current support | The harness can edit policy source evaluated by parent-provided local simulations. It does not provide a simulator, a live controller, or an executor for real-world schedules. |

## 4. Faster processing with exact output

| Part | Task contract |
| --- | --- |
| Environment | A batch processor or composition function with representative inputs and a trusted output reference. |
| Action | Change data structures, loop work, or batching inside the allowed implementation. |
| Objective | Minimize a precisely scoped elapsed-time metric. |
| Hard limits | Preserve required output, ordering, input immutability, and later input-mutation behavior. Add an explicitly measured memory cap if memory is constrained. |
| Lawful tradeoff | Spend permitted memory on an index, or avoid redundant calculations. Caching is allowed only where its invalidation and output-independence rules permit it. |
| Holdout | Different batch sizes, duplicates, edge values, repeated calls, mutated inputs, and distributions absent from development timing. |
| Current support | The [batch-aggregation example](../examples/batch_aggregation/README.md) and [local sprite case](case-study.md) exercise this pattern. The bundled aggregation job does not measure memory; a memory-bound variant needs an additional evaluator. Function timing does not establish application FPS or end-to-end latency. |

## What the current runtime can express

The shipped runtime edits selected local UTF-8 source files and runs fixed parent-owned commands in its macOS sandbox. A job has **one scalar objective**, numeric `>=`/`<=` constraints, and optional separate final checks. A benchmark can combine several objectives into a scalar only when the owner fixes that formula and its weights beforehand.

It does not maintain a Pareto frontier, automatically design evaluators, solve arbitrary infeasibility, control a live environment, or carry learned experience across jobs. Different policies and weights require explicit task design. Holdout coverage and robustness margins remain the orchestrator's responsibility; passing the development score is not evidence of generalization.
