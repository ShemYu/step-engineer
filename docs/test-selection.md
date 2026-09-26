# Test selection and cost reduction

[繁體中文](test-selection.zh-TW.md) · [Contributing](../CONTRIBUTING.md)

These are parent-reviewed engineering rules, not an automatic test selector.
Optimize measured feedback time or execution cost while preserving the behavior
contract. Fewer test cases, fewer assertions, or higher line coverage are not goals.
Step proposes a bounded change; the parent owns the oracle and acceptance.

For ordinary optimization jobs, the parent freezes `checks`, `benchmark`, and
`final_checks`; the candidate cannot select which checks apply to itself. When
optimizing tests themselves, use a separate protected evaluator for test quality.

## Classify each proposal

| Decision | Meaning and evidence required |
| --- | --- |
| `keep` | A required contract or fault has a distinct witness; retain it. |
| `lower-cost-layer` | Exercise the same pure behavior more cheaply; preserve inputs, observations, fault detection, and real integration anchors. |
| `skip-for-current-change` | Omit from this local feedback run because the reviewed change cannot affect its contract or dependencies; retain the test and final CI. |
| `remove-proven-duplicate` | Permanently remove only after the witness test or retained set satisfies the equivalence and fault-inclusion rule below. |
| `uncertain-keep` | Evidence is missing, conflicting, or too expensive to establish; retain it and record the uncertainty. |

Reducing one local run and deleting a test are separate decisions. Neither a slow
test nor many parameter combinations demonstrate redundancy. A repeated assertion
inside otherwise distinct tests does not make either complete test removable.

## Evidence for replacement or removal

Record the candidate's pytest node ID and its retained witness node IDs. Compare:

- The same requirement, input equivalence class, boundary, and allow/deny outcome.
- The same relevant state, transition order, reset behavior, and prior failures.
- The same observable outputs, side effects, errors, and prohibited actions.
- The required execution boundary: retain filesystem, subprocess, or service
  observations in real integration anchors when pure parsing moves to a unit test.
- A parent-owned fault set: every relevant fault detected by the old case must
  still be detected by the retained witnesses after the change.

For the declared fault set, require `kills(old) ⊆ kills(retained witnesses)`.
Include realistic regressions, not just mutations the proposed replacement finds.
A fault counts as detected only when the expected behavior assertion rejects it;
unrelated collection, import, setup, or syntax failures are not equivalent evidence.
Keep the unmodified program passing. Preserve distinct observations that fault
injection cannot adequately model, and explain any excluded or equivalent mutant.
Finite mutation evidence supports the stated contract; it does not prove universal
equivalence. The parent must review the fault catalog and semantic argument.

Shared names, source lines, coverage percentages, current execution traces, or
historical passes are insufficient. Two cases can take the same path today but
detect different future faults when an earlier guard is removed.

Preserve positive and negative cases, exact boundaries and meaningful neighbors,
security/privacy rules, resource and cost budgets, state transitions, reset logic,
and interactions between guards. Preserve actual integration and hidden final
checks. A fake clock or mocked subprocess cannot replace a real timeout, sandbox,
Git-index, filesystem, or process-lifecycle contract merely because both pass.

## Select local feedback from the actual change

These are conditional starting points, not filename-based permissions to skip.
Inspect changed functions, callers, fixtures, configuration, and dependencies first.

| Isolated change | Local feedback to retain |
| --- | --- |
| Documentation only | Relevant links, examples, public-tree audit, and documentation checks; runtime groups may wait for final CI if no executable inputs changed. |
| Public-tree pure parsing test bodies | All public-tree cases, protected parsing faults, and unchanged real Git/privacy anchors. |
| Improvement comparison only | Full numeric boundary group, golden-rules integration, and normal/final acceptance and rejection. |
| Stagnation counting or stop placement only | Stagnation allow/deny/reset cases, golden-rules integration, and deadline/batch-to-final transitions. |
| Exploration deadline or command reserve only | Validation-reserve group, golden-rules integration, and stop-then-final-failure behavior. |
| Independent example policy only | That example's protected correctness, benchmark, holdout, and applicable harness integration. |

For the isolated numeric change, unrelated counter arithmetic may be deferred;
for isolated counter/deadline changes, the pure numeric matrix may be deferred.
Document why the deferred contract is unaffected. A change to `run`, `verify_final`,
shared models, fixtures, defaults, configuration, global core behavior, or multiple
guards requires the full suite. Unknown dependency impact falls back to
the full suite, not a guessed subset. Final acceptance still requires full CI.

Do not repeat a passing check on the same code, inputs, configuration, and relevant
environment without a new change, failure, or unresolved concern. Planned benchmark
repetitions and predetermined fault checks are evidence collection, not redundant
reruns. Record the state tested so previous results are reusable only when valid.

## Measure and report

Establish a passing baseline and freeze the workload before optimization. Measure
wall time for the complete affected invocation, including collection, fixtures,
subprocess startup, and teardown; per-test durations help locate costs but do not
replace end-to-end timing. Keep hardware, dependencies, commands, cache policy,
repetitions, seeds, and measurement method fixed. Report distributions or repeated
medians and the number of runs; disclose noise or interference. Do not select only
the fastest run. Report model tokens, estimated model cost, and experiment time
separately from test-execution savings. Reject an unsupported speedup claim.

Deliver a decision table with node IDs, classification, reason, contract/input/state,
retained witness or replacement, evidence paths, before/after timings, and fault
kills/losses. Include the exact diff, commands, environment, collection counts,
failures, and uncertainties. The parent reviews semantics and the protected oracle;
final acceptance requires the complete existing CI checks, including supported-
platform sandbox integration. A faster selected run alone is not final acceptance.

## Initial assessment of this repository

At the reviewed baseline `72fab43`, no complete case has sufficient evidence for
permanent deletion. The public-tree suite has 51 collected cases; repeated Git
initialization in pure path/content cases is a candidate for cheaper execution.
Preserve real Git anchors for staged versus working-copy content, untracked files,
forbidden-file rejection before reads, symlinks, redacted reporting, and invalid
index handling. These test contracts extend beyond parsing.

The threshold, stagnation, validation-reserve, and golden-rules groups cover
different numerical, state, and interaction faults. Their parameter counts and
mocked timing are not evidence that real integration tests are redundant.
The [case study](test-selection-case-study.md) records the bounded Step attempt,
including its final-check rejection and the parent's review of partial adoption.

## Copyable Step instruction

```text
Reduce measured public-tree test runtime without weakening its contract.
Parent-provided inputs: exact baseline revision, allowed test-body names,
protected evaluator/fault catalog, timing command, fixed repetitions and seeds,
acceptance threshold, and finite model/tool/token/time/cost budgets.
If any required input is missing, report the gap before making dependent edits.

Only edit the explicitly allowlisted pure-parsing tests inside
tests/test_public_tree.py. Those tests may drop their unused repository fixture
argument and use simple aliases or helpers for the production classifiers.
Keep all 51 collected cases, node IDs, parameterized inputs and decorators,
existing fixture/helper definitions, and real Git/privacy integration anchors.
Use the existing production parser; preserve each input and expected outcome.
Do not replace the parser with a fake or copy its implementation into tests.
Do not change production code, evaluator, fault catalog, thresholds, assertions'
meaning, skip/xfail markers, repetition counts, random seeds, or hidden final
checks to obtain a faster result. Do not delete cases in this experiment.

Confirm the baseline passes. Propose lower-cost-layer changes only within the
allowlist, then evaluate promptly with the protected command. Preserve every
declared relevant fault kill and the real integration observations. Do not
inspect hidden final checks or optimize for recognizing benchmark fixtures.
Stop within the fixed budget; leave uncertain changes unadopted and report why.

Return changed node IDs, classification, reason, old/new layer, preserved contract
and state, witness evidence, repeated before/after timings, fault kills/losses,
collection counts, exact diff, failures, usage, and remaining uncertainty.
Passing the development evaluator is provisional. The parent owns independent
review, protected final validation, the complete existing CI, and adoption.
```
