# Task brief for constrained optimization

[README](../README.md) · [Use cases](use-cases.md) · [Delegation instructions](parent-agent-instructions.md) · [Job schema](../src/step_engineer/models.py)

Complete this brief before creating a job. These are planning notes mapped to the **existing `JobSpec`**, not additional schema fields. The orchestrator owns the contract, evaluator, and adoption decision; Step searches within them.

## Copy and fill in

```text
TASK AND OPERATING ENVELOPE
Improve [specific policy/function] for [supported inputs, sizes, distributions,
runtime, hardware, and conditions]. The observable user benefit is [benefit].
Decisions may use [available information]; they may not use [future/hidden data].
Out of scope: [cases this contract does not claim to cover].

CONTROLLABLE SURFACE
Source directory: [path].
Files required by the job: [explicit files].
Editable files and permitted choices: [smallest implementation subset].
Implementation may change [algorithm/policy/parameters], but must preserve [API].

IMMUTABLE RULES AND BASELINE
Required behavior: [rules, input/output semantics, edge cases].
Protected evaluation files/commands: [checks, benchmark, fixtures].
Baseline: [existing implementation and its measured feasible result].
Established algorithm/solver checked: [candidate and why further search is useful].
If the baseline fails a mandatory rule: stop and resolve the contract or baseline.

ONE SCORE
Metric and direction: [name; minimize or maximize].
Units and timing scope: [e.g. reward points; milliseconds inside the function].
Within one benchmark run: [scenario aggregation, weights, denominator, failures].
Across repetitions: [count; the harness uses the median].
Minimum accepted relative improvement over baseline: [fraction].

HARD LIMITS AND EXPLICIT MARGINS
For each limit: [rule/metric, >= or <= threshold, units, per-case/group scope,
measurement method, and margin beyond the operational requirement].
Margin choice: [reason and holdout conditions used to justify it, or explicit zero].
Allowed exchanges: [what may worsen, by how much, and why that is acceptable].
Forbidden exchanges: [what cannot be traded for score or omitted from accounting].

FEEDBACK FOR EACH TRIAL
Return [score, resource use, failed constraint, and useful diagnostic breakdown].
Keep diagnostics bounded and distinguish valid-but-worse from invalid candidates.
Measure through the protected evaluator; candidate claims are not measurements.

HOLDOUT AND FINAL ACCEPTANCE
Withheld files: [separate cases/oracle; excluded from editable files].
Final commands: [checks on new inputs and boundary conditions].
Required holdout behavior and numeric limits: [explicit pass/fail assertions].
Unmeasured production requirements for parent review: [remaining risks].

FIXED SEARCH BUDGET
reasoning_effort: [low/medium/high].
max_model_turns: [n]; max_tool_calls: [n]; max_no_improvement: [n].
max_seconds: [seconds]; max_request_seconds: [seconds].
max_total_tokens: [n]; max_output_tokens_per_turn: [n].
max_estimated_cost_usd: [USD estimate, not a provider billing guarantee].

STOP AND REVIEW
Stop at configured limits or lack of improvement. A failed candidate is feedback;
an unreliable evaluator or contradictory contract requires parent review.
Review the saved accepted patch, final results, cost/usage, and stop reason.
Revisit this brief when [workload/rule/runtime change or observed regression].
Do not weaken rules or margins after seeing candidate results; changes require a
new reviewed contract. State whether the original goal remains unmet.
```

## Map the brief to the current job

| Brief content | Existing `JobSpec` fields and behavior |
| --- | --- |
| Envelope, permitted choices, invariant behavior, legal tradeoffs | `objective`; keep executable rules in protected checks and fixtures. Prose alone is not enforcement. |
| Source and action boundary | `source_dir`, `files`, `editable_files`. CLI source paths resolve beside the job JSON; MCP requires an absolute source path. |
| Baseline correctness | `checks`, `benchmark`, `constraints`. The unchanged snapshot must be feasible before optimization begins. |
| Score and repeated measurement | `metric`, `direction`, `benchmark`, `repetitions`, `minimum_relative_improvement`. The benchmark defines units and within-run aggregation; the harness compares repeated medians. |
| Numeric limits and margin | `constraints` with `metric`, `op`, `value`; nonnumeric invariants belong in `checks`. Encode the selected margin in the threshold and explain it in `objective`. |
| Trial feedback | Protected commands produce bounded stdout/stderr and benchmark metrics. Design the evaluator's diagnostics; there is no separate feedback-schema field. |
| Holdout | Put final-only files in both `files` and `final_only_files`, never `editable_files`; register their commands in `final_checks`. |
| Search limits and worker setting | `budget` and `reasoning_effort`. Use `step-engineer schema` for accepted ranges; model-level limits are not this harness's configured limits. |
| Stop/review policy | Configured budget limits plus orchestrator decisions. There is no automatic contract-renewal or cross-job memory field. |

The harness tests numeric constraints on **each benchmark repetition**, not on every scenario hidden inside a benchmark. If every instance must stay within a resource cap, enforce that in the evaluator or emit the worst violation. A passing average must not conceal an invalid instance.

Final checks are pass/fail commands. A holdout script must exit unsuccessfully when its required quality or resource limit fails; merely printing a bad metric does not reject the candidate. Final validation also reruns the normal checks and benchmark. Without separate `final_checks`, the result reports `independently_checked=false`.

## Example of a precise exchange

For a resource-allocation policy: maximize reward over the fixed development instances; never exceed either instance's CPU or memory cap; allow skipping jobs; return only unique IDs from the input. Test new combinations and capacities in final checks. The relevant operating envelope is a known batch with no future arrivals, not a live scheduler. See the [synthetic example](../examples/resource_allocation/README.md); it is not a live Step result.

For a quality-constrained search task, an operational recall requirement of 0.95 might be encoded as a development threshold of 0.965 **only if the owner chooses and justifies that 0.015 margin**. This is an example of an explicit choice, not a recommended universal margin or an automatically computed guarantee. Holdout checks must enforce their own agreed requirement.

Review successful and unsuccessful trials. A higher score from this contract establishes a measured result on this workload; a claim that Step or the harness outperforms an alternative requires a controlled comparison with repeated runs.
