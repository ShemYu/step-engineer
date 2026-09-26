# Step-assisted guard repairs: contributions and failed attempts

On 2026-09-26, four development agents worked in separate Git worktrees on four
reproduced guard defects. A parent agent running `gpt-6-astra` with `ultra`
reasoning reviewed the changes and added tests of interactions between them.
Each development agent made one live Step Engineer attempt before completing
the repair. This was a development exercise, not a controlled model benchmark.

The target source started at `094fb1644381538db8efcb9194cc338de1e93ee7`.
The integration branch accumulated reviewed changes during the exercise; the
runtime driving the jobs was therefore not held identical across all attempts.

## Explicit contracts

Step could edit only the relevant Python implementation file. Evaluators and
checks were protected. Existing valid behavior had to keep passing; the
benchmark score counted passing regression cases, and final checks required all
target cases. A partial baseline score made the defect a measurable optimization
task without pretending the original code already passed the new requirements.

| Task | Required behavior | Developer-agent repair |
| --- | --- | --- |
| Scratch storage | Below/equal limits allowed; excess bytes or entries rejected for both fast and slow completion | Check retained scratch after process cleanup, preserving an earlier violation |
| Final-validation reserve | Development checks and batched tools cannot spend the time reserved for validating saved best | Bound exploration commands and dispatch; transfer normally to final validation |
| Improvement threshold | Accept equal thresholds despite floating-point roundoff; reject real shortfalls and non-improvements | Compare gains in score units with an input-scale ULP allowance at both acceptance gates |
| Stagnation | The same completed evaluations stop at the same boundary regardless of response batching | Check the no-improvement count after each completed tool call, before further work |

All jobs used Step-5-Preview, `medium`, a 16,384-token output ceiling, a 180-second
request ceiling, a 420-second job budget, and a conservative US$0.30 cost ceiling.
Scratch/reserve allowed six model turns; threshold/stagnation allowed twelve.
The first three used a 120,000 total-token limit. Stagnation used 250,000 after
earlier attempts exposed the cost of the conservative input reservation. These
are different configurations, not an A/B comparison.

## What Step actually produced

| Task | Requests | Tokens | Estimated cost (USD) | Step job result | Code adoption |
| --- | ---: | ---: | ---: | --- | --- |
| Scratch | 6 | 48,917 | 0.052817 | Turn limit; wrote then restored; no candidate evaluation | None; development agent authored the repair |
| Final reserve | 3 | 30,363 | 0.041998 | Token admission stopped further requests; read-only tool activity | None; development agent authored the repair |
| Threshold | 6 | 37,410 | 0.049420 | Token admission stopped further requests; read-only tool activity | None; development agent authored the repair |
| Stagnation | 8 | 116,136 | 0.131640 | Candidate failed protected correctness checks; later token stop | Only the five-line post-tool guard was extracted and reviewed |
| **Total** | **23** | **232,826** | **0.275875** | **All four Step jobs had `accepted=false`** | **No complete Step patch was adopted** |

The stagnation attempt first supplied a short fragment to `write_file`, whose
contract is whole-file replacement. It later restored a complete implementation
and proposed the desired stopping logic, but also damaged the tool-schema
builder. The evaluator rejected that candidate. The development agent extracted
only the stopping logic; the parent reviewed that small diff and the regression
tests. The rejected schema changes were not integrated.

Costs are the harness's conservative token-based estimates, ignoring cache
discounts; they are not reconciled charges. `token_budget` here includes an
admission decision using the next request's UTF-8 byte bound and output reserve.
It does not mean the reported actual token count reached the configured limit.
There were no automatic retries or second live attempts for these tasks.

The private run identifiers, useful for local audit, are:

- Scratch: `b034227dabff4da5a7a4c9b90c654ba6`
- Reserve: `8318fa382f2a47f2a17e02578872d830`
- Threshold: `e67e7edde828429dac72a03d671535fa`
- Stagnation: `fa503b3bc96d4586a914874fda16594f`

Private run directories, credentials and raw continuation state are not included
in the repository. The committed regression tests make the repaired behavior
inspectable; the table alone is not sufficient to reproduce a live model run.

## Review and verification

The integrated local suite passed **307 tests**, including real macOS sandbox
and MCP integration checks. Ruff and the staged public-tree audit are separate
release checks; model success is not inferred from the test count.

- [Storage boundaries](../tests/test_runner.py): real macOS sandbox execution,
  byte/entry boundaries, and observations after cleanup.
- [Validation reserve](../tests/test_validation_reserve.py): deterministic phase
  deadlines, exhausted tool batches, and saved-best final checks.
- [Thresholds](../tests/test_improvement_threshold.py): minimize/maximize,
  positive/negative/zero/near-zero scores, strict improvement, and an independent
  high-precision Decimal boundary reference.
- [Stagnation](../tests/test_stagnation_boundary.py): batching, counter resets,
  tool errors, failed candidates, other budgets, and failed final checks.
- [Parent review integration tests](../tests/test_golden_rules_integration.py):
  an exactly qualifying candidate must still be delivered after stagnation or
  exploration-time exhaustion. These three tests failed on the original code.

Storage monitoring is not an instantaneous filesystem quota. The validation
reserve retains its 40% job-time cap and cannot eliminate cleanup/I/O overhead.
Numerical roundoff tolerance does not handle timing noise or establish statistical
significance. Successful regression tests establish these runtime behaviors, not
Step's effectiveness on other tasks.

This exercise points to request-reservation diagnostics and editing-tool
ergonomics as candidates for later investigation. It does not establish that
changing either one will increase model success, nor that the four failed
attempts measure the model's general coding ability.
