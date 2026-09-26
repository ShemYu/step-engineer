# Changelog

## Unreleased

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
