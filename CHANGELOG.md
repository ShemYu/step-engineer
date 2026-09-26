# Changelog

## Unreleased

- Check aggregate scratch limits after command cleanup as well as during execution.
- Apply the final-validation time reserve to development commands and batched tool
  dispatch, then validate saved best when exploration time runs out.
- Accept exact improvement thresholds despite score-scale floating-point roundoff,
  without relaxing strict improvement or metric constraints.
- Enforce the no-improvement limit within a response's tool batch, before further
  edits or model requests; add cross-guard integration coverage.
- Document four Step-assisted repair attempts, including rejected candidates,
  reviewed partial adoption, and conservative costs.
- Clarify the project as a reusable Step-5-Preview harness with ready-made and
  customizable MCP, CLI, and orchestrator tool interfaces.
- Add English and Traditional Chinese capability evidence, sourced comparison
  figures, an architecture diagram, and an official-documentation directory.
- Add custom CLI and MCP wrapper examples using the existing Python components.

## 0.1.1 — 2026-09-26

- Support macOS framework-based Python installations, including GitHub Actions
  `setup-python`, by allowing reads of the active interpreter's exact framework
  library. Network access and unrelated filesystem reads remain denied.
- Version 0.1.0 worked with the locally tested uv standalone Python, but its
  sandbox blocked the framework library used by the hosted macOS CI interpreter.

## 0.1.0 — 2026-09-26

- Initial public release of the bounded Step optimization worker, CLI, MCP stdio
  service, and provider-neutral tool adapters.
- Added explicit file snapshots, immutable checks, repeated benchmarks, saved
  best candidates, independent final validation, budgets and local reports.
- Included a scripted offline example, English and Traditional Chinese guides,
  sanitized live case study, MIT license and public-tree publication checks.
- Included text-only wheel demo resources and explicit distribution allowlists.
