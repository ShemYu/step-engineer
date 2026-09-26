# Test-cost audit: preserve cases, remove repeated Git setup

[Selection rules](test-selection.md) · [繁體中文規則](test-selection.zh-TW.md)

This audit starts from `72fab4343ca3f267e51338cb1787cefc2e602370`.
The parent agents identified the contracts and eligible scope; Step received a
bounded implementation task. This is not evidence that Step independently chose
which tests to delete, or a comparison of models.

## What the initial inventory showed

One complete local baseline passed **334 tests in 18.90 seconds**. JUnit case
durations located the costs below; they exclude some invocation overhead and are
not end-to-end benchmark results.

| Group | Cases | Recorded case seconds | Decision |
| --- | ---: | ---: | --- |
| Runner | 30 | 6.444 | Keep: real timeout, cancellation, sandbox and cleanup observations are distinct. |
| Public-tree audit | 51 | 4.534 | Up to 35 cases eligible for lowering; at least 16 real Git cases locked. |
| MCP | 1 | 4.278 | Keep: a real stdio client/server round trip. |
| Harness | 18 | 1.408 | Keep: integration and acceptance behavior. |
| Allocation example | 22 | 0.831 | Keep: correctness, types, protected evaluation and holdout. |
| Improvement thresholds | 114 | 0.176 | Keep: cheap numerical boundaries, signs, directions and scales. |
| Stagnation, validation reserve and golden integration | 27 | 0.355 | Keep: state, reset, phase and cross-guard contracts. |
| Bridge, CLI, provider and workspace | 71 | 0.099 | Keep: no complete redundant case established. |

No whole test case had sufficient evidence for permanent deletion. Parameter
count would have been a poor optimization target: the 114 numerical cases were
much cheaper than a single MCP integration case.

## Allowed changes and retained observations

Each row lists candidates for lowering, not an accepted result. A case remains
at the integration layer if lowering loses any protected observation. Each row
covers every original parameterized node of the named function. All
parameter values, decorators and node IDs are fixed. Content tests must send the
original bytes **and filename** to the real production classifier.

| Test function | Cases | Decision and preserved observation |
| --- | ---: | --- |
| `test_environment_example_allows_only_empty_secret_values` | 4 | Lower to content classifier; allowed empty values still produce no findings. |
| `test_forbidden_staged_paths` | 15 | Lower to path classifier; each original forbidden path is rejected. |
| `test_private_home_paths` | 4 | Lower to content classifier; each path syntax is still detected. |
| `test_credential_signatures` | 6 | Lower to content classifier; each signature or assignment is still detected. |
| `test_python_credential_literals_still_fail` | 5 | Lower to content classifier; every original Python literal form is rejected. |
| `test_python_placeholder_never_masks_provider_token_signature` | 1 | Lower to content classifier; a placeholder prefix cannot hide the signature. |

The other 16 nodes retain their original bodies and real Git fixture. They cover
clean files, filename-sensitive environment rejection and Python-expression
allowance, forbidden-file rejection before reads, untracked files, index versus
working-copy content, binary/non-UTF8 blobs, both symlink states, redaction,
scanner self-audit and an empty index. Helpers, fixtures and production code are
also frozen. Only the six listed functions may remove the unused repository
fixture argument and use simple production-classifier aliases or helpers.

## Protected fault evidence

Before any model edit, the parent froze these scanner faults and the original
assertion-failure node set for each. A candidate must retain **each original
failure node for each fault**, not merely fail somewhere. All 35 editable nodes
have at least one such witness. Collection, setup, runtime and teardown errors,
timeouts, skips and xfails do not count as detection.

| Injected fault | Original assertion-failure nodes |
| --- | ---: |
| Allow all paths | 16 |
| Allow all content | 24 |
| Reject empty environment examples | 5 |
| Ignore Python credential literals | 5 |
| Inspect only the index | 1 |
| Inspect only the working copy | 1 |
| Drop filenames when routing content | 6 |
| Remove NUL bytes when routing blobs | 1 |

Normal runs must also pass the original 51 nodes, exercise their original
classifier inputs and preserve the frozen production hash and test AST outside
the allowlist. Final fault checks remain unavailable during Step's exploration.
These eight faults support the declared contract; they do not prove equivalence
against every possible future bug.

## Measurement protocol

The private harness measures a complete protected 51-case invocation externally,
with three repetitions per evaluation and a minimum 10% median improvement. A
separate native measurement uses the same repository virtual environment in two
minimal source snapshots, the same command and six predetermined runs:
baseline, candidate, candidate, baseline, baseline, candidate. No warmup or
fastest-run selection is used. The native command is:

```sh
python -m pytest -q -p no:cacheprovider tests/test_public_tree.py
```

The private macOS sandbox needed the installed CommandLineTools Git binary in
its private runtime: Apple's Git launcher attempted a blocked developer-directory
lookup. System/global Git configuration and templates were isolated for that
experiment. No sandbox permissions or production code were relaxed. Native
measurements use the ordinary Git environment and are reported separately.

Model cost, fault-audit setup and optimization time are one-time expenses; they
are not included in the repeated test invocation's savings. Full CI remains
required, and no full-suite speedup is inferred from a single before/after run.

## Step attempt and the review decision

One live `step-5-preview` job used medium reasoning, up to 8 model turns,
24 tool calls, 250,000 tokens and 600 seconds, with an estimated US$0.35 cost cap.
It made 7 requests and 11 tool calls, used 104,918 reported tokens and finished in
195.776 seconds. The harness estimated **US$0.122851**, using its conservative
input/output rates without cache discounts; this is not an invoice. Usage was
reported without uncertainty. No second paid attempt was made.

The original Step candidate lowered all 35 eligible cases. Normal checks passed,
and the private benchmark median fell from 2.935337 seconds to 1.331153 seconds
(three runs each). But the final fault check **rejected the candidate**: the
annotated Python literal node stopped detecting missing filename routing. The
other retained tests still caught that fault, but this did not satisfy the
stricter precommitted requirement to retain each original failure node. The
eighth fault was not reached after that failure. These timings therefore describe
a rejected candidate, not an accepted quality-preserving speedup.

The run reports `no_verified_improvement`, `accepted: false`, with exploration
ending at `token_budget`; the budget includes conservative request reservations,
so it can stop before consuming the nominal token maximum. The parent did not
change the frozen oracle or repeat the API attempt to turn that result green.

For partial adoption, the parent retained the entire original five-case Python
literal family at the real Git layer and corrected two comments that still
described integration observations in pure tests. The resulting scope is **30
cases lowered, 21 real Git cases retained, zero cases deleted**. This revision
passed the same frozen normal-input and AST checks, all 51 normal cases, and all
eight faults with the exact original failure-node sets retained. No skips,
timeouts or unrelated errors counted as successes. The adopted test-file SHA-256
is `946f915ad22da5f67f0e394020a8232b3e756cf3415deef54c3f2552b3c68635`.

This is a parent-reviewed partial adoption of Step's output. The original live
job remains rejected; the subsequent offline repair is not relabeled as a
successful unmodified Step run.

## Adopted revision: native measurements

Measured on macOS 26.5 arm64, Python 3.12.14, Apple Git 2.50.1, with the same
locked dependencies for both snapshots. The `uv.lock` SHA-256 was
`7dc96c842b0d701e80a31473da8dd02a892fce476ce2c5944136ab448e0d0d9d`.
Every run below passed all 51 cases. These are external process wall times,
including Python startup, collection, fixtures and teardown.

| Run order | Version | Seconds |
| ---: | --- | ---: |
| 1 | Baseline | 4.310594 |
| 2 | Adopted revision | 2.248302 |
| 3 | Adopted revision | 2.051694 |
| 4 | Baseline | 4.108017 |
| 5 | Baseline | 4.039676 |
| 6 | Adopted revision | 2.013609 |

The median changed from **4.108017 to 2.051694 seconds**, a **50.1% reduction**
for this module on this machine, with three samples per version. The baseline
range was 4.040–4.311 seconds; the adopted revision's was 2.014–2.248 seconds.
This removes 30 repeated repository-fixture setups while retaining all 51 cases.
It is a small local sample, not a statistical performance guarantee or a 50%
reduction of the complete suite. No production runtime behavior changed.

The adopted checkout also passed the complete **334-test** local suite, Ruff,
the staged public-tree audit, whitespace checks and the changed documentation's
local links. Full macOS CI remains the final integration gate; local selective
feedback did not remove or skip any existing CI test.
