"""Explicit scripted fixture for pipeline testing; it never impersonates a model run."""

import json
from pathlib import Path

_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_SOURCE_EXAMPLE = _SOURCE_ROOT / "examples" / "batch_aggregation"
_PACKAGED_EXAMPLE = Path(__file__).resolve().parent / "_examples" / "batch_aggregation"
# Editable checkouts use their reviewable source fixture; wheels carry an
# explicit, text-only copy inside the package.
EXAMPLE = (
    _SOURCE_EXAMPLE
    if (_SOURCE_ROOT / "pyproject.toml").is_file() and _SOURCE_EXAMPLE.is_dir()
    else _PACKAGED_EXAMPLE
)


class DemoClient:
    def __init__(self):
        self.turn = 0

    async def complete(self, messages, tools, **kwargs):
        self.turn += 1
        if self.turn == 1:
            calls = [("read_file", {"path": "processor.py"})]
        elif self.turn == 2:
            calls = [
                (
                    "write_file",
                    {
                        "path": "processor.py",
                        "content": (EXAMPLE / "offline_solution.txt").read_text(),
                    },
                )
            ]
        elif self.turn == 3:
            calls = [("evaluate_candidate", {})]
        else:
            calls = [("finish", {"summary": "Scripted fixture completed; no model was invoked."})]
        return {
            "message": {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": f"demo-{self.turn}-{i}",
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(args)},
                    }
                    for i, (name, args) in enumerate(calls)
                ],
            },
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
            "finish_reason": "tool_calls",
        }
