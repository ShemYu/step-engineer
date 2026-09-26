# Parent-agent delegation instructions

[English README](../README.md) · [繁體中文](README.zh-TW.md) · [Integrations](integrations.md)

Step Engineer is a reusable **Step-5-Preview harness** that developers expose through their own CLI, MCP server, or API tool executor. GPT, Grok, or Claude is the orchestrator: choose a suitable task, set the constraints and evaluation, delegate iteration, then review the evidence. Keep the parent model and reasoning settings selected by the user, including Ultra when available.

Use the template below in a project or wrapper. It targets Step's intended strengths in tool-guided engineering iteration and explicit optimization constraints; it does not assume that the model is best for every task.

## Suggested instruction

```text
Use Step Engineer as a Step-5-Preview worker through the project's CLI/MCP/API
wrapper. Delegate bounded engineering optimization when a reproducible
baseline, protected correctness checks, and a measurable objective exist.
Own task selection and acceptance as the orchestrator; do not delegate an
unscoped request such as "make the whole project better."
Keep the parent's configured model and reasoning effort unchanged.

A job's reasoning_effort controls only the Step worker. It defaults to medium
and can be overridden per job. Starting limits are 16,384 output tokens and
300 seconds per request, and 250,000 total tokens. Respect the job's global
elapsed-time and estimated-cost limits. These settings do not guarantee an
improvement or establish that one reasoning level is generally better.

Before delegation:
- Inspect the actual bottleneck and behavior contract. Choose one concrete task.
- Prepare JobSpec with an explicit file list and the smallest editable subset.
- Respect the wrapper's allowed source roots. An allowed root is not approval
  for every command, file, objective, or cost within it; review the full job.
- Own correctness checks, benchmark, final checks, constraints, and budget.
- Put separate final-validation files in final_only_files and files, never in
  editable_files. The harness withholds these files and final-check commands
  from development tools and introduces them only for final validation.
- Cover realistic boundary cases and an independent workload. Do not lower
  acceptance thresholds in response to candidate results.
- For process timing, use externally measured elapsed_seconds. Set repetitions
  and minimum_relative_improvement before the run. Add measured quality or
  memory constraints when they are relevant.
- Set finite turn, tool, token, request-time, total-time, stagnation, and cost
  limits. Cost estimates are not an invoice or a hard provider billing cap.
- Send only task-related code and feedback that may be shared with StepFun.
  Keep credentials and unrelated private data out of every listed file.

Delegate through submit_optimization(job) or the CLI. Use absolute source_dir
for MCP. CLI relative source_dir resolves against the job JSON's directory.
A local host executes tools; a cloud model does not access this workstation's
localhost or filesystem directly.

Keep the local service and its async event loop alive while a job runs. MCP
wrappers must retain their session; API hosts must await service.close() on
shutdown, not after submission. Retain the run ID, poll status at
reasonable intervals, and cancel superseded work. Retrieve the final result
for unsuccessful runs too. Do not automatically retry a paid request.

Before adopting a patch:
- Inspect the diff and confirm only allowed implementation files changed.
- Compare repeated measurements under the same protected workload; do not
  select a single favorable timing or accept candidate-written benchmark claims.
- Confirm normal and independent final checks actually passed. If separate
  final_checks were not provided, report independently_checked=false.
- Review behavior, complexity, memory costs, failure modes, dependencies,
  cache invalidation, and unmeasured production requirements.
- Report stop_reason separately from acceptance. Budget exhaustion can leave
  an earlier measured best that passes final validation. Never use an
  unmeasured last edit in candidate/ instead of the accepted saved best.
- Treat best-development.patch as diagnostic. Use accepted.patch only when
  accepted=true and validation supports the intended use.
- Keep the original source intact until the parent decides to apply a reviewed
  patch under the user's authorization. Merging and publishing are separate
  parent-owned actions.

Report the change, measured benefit, correctness and final-validation evidence,
cost/usage, stop reason, and remaining limits. Label scripted offline demos as
such. Do not attribute their improvements to the Step model.
```

## Suitable tasks and limits

Good candidates include batch processing, query or index tuning, and data-structure changes with fixed inputs and measurable outcomes. Express the task as improving one metric while preserving behavior and explicit constraints. For example: reduce a batch processor's runtime while keeping exact output, input immutability, and a measured memory bound. An optimization metric without a correctness contract is not enough.

Document analysis or open-ended research may suit the model, but this repository currently implements a code-edit/check/benchmark loop. Reusing its lower-level pieces for other workflows requires your own tools and acceptance logic; the shipped harness does not supply that workflow automatically.

A subjective visual objective, an unclear product requirement, or an unrepresentative microbenchmark needs additional evaluation design before delegation. A faster local function does not establish higher application FPS or better production latency.

The bundled aggregation example exchanges additional index memory for expected time-complexity improvement. Its job does not measure memory, so acceptance cannot establish lower memory use. External process timing includes interpreter startup, input preparation, and validation.

Final-only files are hidden from development tools, not from the program during final verification. The local sandbox is not a hostile-code VM; inspect the implementation and evaluator together before trusting a result.

## Wrapper responsibilities

Use [`JobService`, `build_server`, or `ToolBridge`](integrations.md#build-your-own-cli-or-mcp) to add task templates, domain-specific tool names, or a custom CLI. The wrapper owns authentication setup, allowed roots, job review, and process lifetime. The harness owns the bounded iteration and saved-best verification. There is no scaffold generator or runtime plugin registry; changing worker tools or sandbox backends requires code changes. All existing entry points leave the original project unchanged.
