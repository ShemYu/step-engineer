# Contributing

Use Python 3.12 and macOS for the full suite:

```sh
uv sync --frozen --python 3.12
uv run --frozen pytest -q
uv run --frozen ruff check src tests tools examples/resource_allocation
python3 tools/check_public_tree.py
```

Tests mock provider HTTP calls and use scripted offline fixtures. They must not
require a real API key or incur model charges. Tests requiring `sandbox-exec`
are skipped on other operating systems; passing that subset does not establish
that a live optimization can run there.

Keep changes focused. Explain the behavior contract, meaningful verification,
resource tradeoffs and any user-visible limitations in the pull request. Changes
to budgets, file boundaries, process isolation, credential handling or provider
parsing should include regression coverage. Never weaken isolation merely to make
a test pass.

Do not commit `.env.local`, `runs/`, `experiments/`, generated media or account
information. Use synthetic fixtures with clear provenance. The public-tree
checker examines Git's index as well as tracked working files, so stage the
intended changes before running the final check.

The code is MIT licensed. Only contribute code and fixtures you have permission
to distribute under that license.
