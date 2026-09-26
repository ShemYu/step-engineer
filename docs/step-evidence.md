# Why Step 5 Preview, and what the evidence supports

[English README](../README.md) · [繁體中文證據說明](step-evidence.zh-TW.md) · [Local case study](case-study.md)

**Sources checked: 2026-09-26.** This is the evidence behind Step Engineer's positioning as a Step-specific harness for engineering optimization under constraints, with measurable feedback. It separates provider demonstrations, documented API capabilities, and one local experiment. None establishes general superiority over other models.

The design hypothesis is straightforward: define the behavior that must remain correct, measure a candidate, retain the best qualifying version, and use execution feedback to choose the next change. The parent owns the evaluator and adoption decision. Whether this works for a new workload must be tested; clear rules alone do not guarantee useful optimization.

## Provider demonstration: GPU kernel optimization

StepFun reports the following experiment in its [official model introduction](https://www.stepfun.com/step-5-preview), with an [original result chart](https://www.stepfun.com/assets/inference-combined-7fkNnlSY.png).

| Condition | Provider-reported setup |
| --- | --- |
| Task | Optimize an MLA GPU kernel from an initial description |
| Hardware | One NVIDIA H100 |
| Fixed shape | Head dimension 512; batch size 1; 64 heads; 8,192 tokens |
| Budget | 24 hours per attempt |
| Selection | Four independent attempts per model; best run reported |
| Feedback | Run changes, measure throughput, discard regressions, continue from the best version |
| Metric | Achieved forward + backward TFLOPS; higher is better |

![Provider-reported MLA kernel results: Step 5 Preview High 508, Claude Opus 5 Max 493, Kimi K3 Max 307, GLM-5.3 Max 286 TFLOPS](assets/step-kernel-results.svg)

| Model and effort | Best reported TFLOPS |
| --- | ---: |
| Step 5 Preview — High | 508 |
| Claude Opus 5 — Max | 493 |
| Kimi K3 — Max | 307 |
| GLM-5.3 — Max | 286 |

These are **vendor measurements, best-of-four, at one fixed shape**, not this repository's measurements or a general ranking. The source does not disclose numerical precision, correctness tolerances, a baseline implementation, or run variance. The chart shows a running best despite unsuccessful candidates. Its Step peak appears around 17–18 hours, whereas the prose says roughly 22 hours; this document therefore claims only the **24-hour budget**, not an exact time to peak.

The same [official introduction](https://www.stepfun.com/step-5-preview) describes a separate 24-hour post-training data optimization experiment: Qwen3-30B-A3B's AIME24 accuracy rose from **53.3% to 60.0%, or 6.7 percentage points**. This is another provider example of measurable feedback, not a replication by this project.

## Local evidence: one sprite-composition workload

The [case study](case-study.md) records three sequential attempts: two `high` attempts exhausted their output allowance without producing a patch; the third, `medium`, retained an evaluated candidate that passed final validation. Output limits, deadlines, and remaining cost allowances differed, so this is not a controlled comparison of reasoning levels.

![Local sprite-composition results: 10.57 percent lower real-asset composition time and 21.05 percent lower synthetic process elapsed time, with different timing scopes](assets/local-case-results.svg)

| Measurement | Baseline | Accepted candidate | Time reduction |
| --- | ---: | ---: | ---: |
| Real assets: fresh nine-pose composition | 1.340068 ms | 1.198424 ms | 10.57% |
| Synthetic batch: external process elapsed time | 1.088911 s | 0.859693 s | 21.05% |

Reduction is `(baseline − candidate) / baseline`; it is not an FPS gain. The synthetic measurement includes process startup, input preparation, composition, and cleanup. The real-asset follow-up alternated baseline and candidate runs. These timing scopes are different and their percentages must not be combined.

Both charts use the checked-in [numeric source data](data/step-evidence.json). They can be regenerated with `uv run --no-project --with matplotlib==3.10.8 python tools/render_documentation_charts.py` from the repository root. Regenerating a chart does not reproduce either experiment.

The accepted run used **126,365 tokens over 292.522 seconds**, with eight model requests and eleven tool calls. These usage and runtime totals cover that run, not all three attempts. It stopped at its total-token budget; an unmeasured later edit was excluded, and the saved best passed independent final validation. The case study also reports the failures and an estimated US$0.25212 across all attempts; that estimate is not a reconciled provider invoice.

Correctness checks covered 160 development cases, 2,016 real-asset cases, 63 reference frames, and 5,500 independent synthetic full-RGBA comparisons. They support the tested candidate and contract. Private application assets are omitted, so the exact real-asset result is not publicly reproducible. The public offline demo uses a handwritten scripted solution and is **not model-performance evidence**. No cross-model comparison, statistical confidence interval, or production-wide speedup is claimed.

## Documented capabilities and the harness boundary

The following are provider capabilities, not evidence that Step Engineer exercises every capability or achieves its maximum scale.

| Official capability | Relevance to an optimization loop | This package's boundary |
| --- | --- | --- |
| [1M context; 64K maximum output](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview) | Capacity for selected code and prior feedback | Text worker; job output capped at 16,384 tokens per request; no million-token workload demonstrated |
| [Function tool calls](https://platform.stepfun.ai/docs/en/api-reference/tool-call) | Request edits and measurements through host tools | The local host executes protected commands; the model has no direct local access |
| [`low` / `medium` / `high`](https://platform.stepfun.ai/docs/en/guides/developer/reasoning) | Tune worker reasoning within a budget | Defaults to `medium`; the local trials do not prove it is generally best |
| [Prompt caching](https://platform.stepfun.ai/docs/en/guides/developer/prompt-cache) | Repeated prefixes may cost less | Cache hits are not guaranteed; local estimates ignore discounts |
| [JSON Mode and JSON Schema](https://platform.stepfun.ai/docs/en/guides/developer/json-mode) | Can constrain structured replies | Current worker uses tool calls and does not request `response_format` schema output |
| [US$1 input / US$0.05 cached input / US$2.70 output per million tokens](https://platform.stepfun.ai/docs/en/guides/pricing/details) | Makes bounded trials and cost estimates practical | Reasoning tokens are billed as output; an estimate is not a billing cap |

Defaults are **600 seconds per job**, **300 seconds per request**, and **250,000 total tokens**, subject to earlier budget stops. The provider's 64K output ceiling, multimodal support, and 24-hour demonstrations are not this package's operating configuration. See [the job schema](../src/step_engineer/models.py), [provider client](../src/step_engineer/provider.py), and [example job](../examples/batch_aggregation/job.json).

The implementation is Step-specific in its worker integration and defaults. Its evaluation pattern is applicable more broadly; no ablation here shows that the pattern benefits Step more than another model. Treat query tuning, scheduling, or simulation optimization as candidate applications requiring their own representative evaluators, not capabilities established by these examples.

## Official documentation map

These direct sources were checked on **2026-09-26**. Start with the [official documentation index](https://platform.stepfun.ai/docs/llms.txt); the model page also links the caching and structured-output guides.

| Source | What to verify before integration |
| --- | --- |
| [Step 5 Preview model](https://platform.stepfun.ai/docs/en/guides/models/step-5-preview) | Model ID, modalities, context, output limits |
| [Quickstart](https://platform.stepfun.ai/docs/en/quickstart/overview) | Endpoint and basic request examples |
| [Chat Completions API](https://platform.stepfun.ai/docs/en/api-reference/chat/chat-completion-create) | Request fields, finish reasons, token usage |
| [Tool Call](https://platform.stepfun.ai/docs/en/api-reference/tool-call) | Tool schemas and host integration |
| [Reasoning best practices](https://platform.stepfun.ai/docs/en/guides/developer/reasoning) | Reasoning effort and response fields |
| [Prompt cache](https://platform.stepfun.ai/docs/en/guides/developer/prompt-cache) | Prefix reuse, cache accounting, eviction |
| [JSON Mode and JSON Schema](https://platform.stepfun.ai/docs/en/guides/developer/json-mode) | Format constraints versus semantic correctness |
| [Pricing and rate limits](https://platform.stepfun.ai/docs/en/guides/pricing/details) | Current rates and account limits |

The official launch page is client-rendered. Its explanatory text was checked through the page's [loaded public JavaScript asset](https://www.stepfun.com/assets/index-DqYLKNXj.js), alongside the original chart. Asset URLs can change as the site is rebuilt. No paid inference or independent reproduction of the provider experiments was performed for this document.
