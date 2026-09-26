from __future__ import annotations

import asyncio
import copy
import json

import pytest
from jsonschema import Draft202012Validator

from step_engineer.bridge import ToolBridge
from step_engineer.models import JobSpec

RUN_ID = "0123456789abcdef" * 2
NAMES = {
    "submit_optimization",
    "get_optimization_status",
    "get_optimization_result",
    "cancel_optimization",
}


def job():
    return {
        "source_dir": "/approved/project",
        "files": ["kernel.py", "check.py", "bench.py"],
        "editable_files": ["kernel.py"],
        "objective": "Reduce latency while preserving exact output.",
        "checks": [{"name": "correctness", "argv": ["{python}", "check.py"]}],
        "benchmark": {"name": "benchmark", "argv": ["{python}", "bench.py"]},
        "constraints": [{"metric": "recall", "op": ">=", "value": 0.95}],
        "budget": {"max_estimated_cost_usd": 0.5, "max_model_turns": 4},
    }


class FakeService:
    def __init__(self):
        self.calls = []

    async def submit(self, spec):
        assert isinstance(spec, JobSpec)
        self.calls.append(("submit", spec))
        return {"run_id": RUN_ID, "status": "queued"}

    def status(self, run_id):
        self.calls.append(("status", run_id))
        return {"run_id": run_id, "status": "running"}

    def result(self, run_id):
        self.calls.append(("result", run_id))
        return {"run_id": run_id, "available": True, "accepted": False}

    async def cancel(self, run_id):
        self.calls.append(("cancel", run_id))
        return {"run_id": run_id, "status": "cancelled"}


def unpack(tool, provider):
    if provider == "openai":
        assert tool["type"] == "function"
        assert tool["strict"] is False
        assert "function" not in tool
        return tool["name"], tool["parameters"]
    if provider == "grok":
        assert tool["type"] == "function"
        assert "name" not in tool and "parameters" not in tool
        return tool["function"]["name"], tool["function"]["parameters"]
    assert "parameters" not in tool and "type" not in tool
    return tool["name"], tool["input_schema"]


@pytest.mark.parametrize("provider", ["openai", "grok", "claude"])
async def test_schema_and_dispatch_for_all_four_tools(provider):
    service = FakeService()
    bridge = ToolBridge(service)
    tools = bridge.tools(provider)
    assert len(tools) == 4
    unpacked = dict(unpack(tool, provider) for tool in tools)
    assert set(unpacked) == NAMES
    for name, schema in unpacked.items():
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        arguments = {"job": job()} if name == "submit_optimization" else {"run_id": RUN_ID}
        # This traverses every nested $ref; check_schema alone would miss broken
        # document-root references after embedding the JobSpec object.
        validator.validate(arguments)
        assert not validator.is_valid({**arguments, "unexpected": True})
        result = await bridge.dispatch(name, arguments)
        assert "error" not in result and result["run_id"] == RUN_ID
    assert {name for name, _ in service.calls} == {"submit", "status", "result", "cancel"}
    submitted = next(value for name, value in service.calls if name == "submit")
    assert submitted.reasoning_effort == "medium"
    assert submitted.budget.max_model_turns == 4
    assert submitted.constraints[0].value == 0.95


def test_provider_formats_share_the_exact_same_job_contract():
    bridge = ToolBridge(FakeService())
    schemas = [
        dict(unpack(t, provider) for t in bridge.tools(provider))
        for provider in ("openai", "grok", "claude")
    ]
    assert schemas[0] == schemas[1] == schemas[2]
    schema = schemas[0]["submit_optimization"]
    assert "$defs" in schema and "$defs" not in schema["properties"]["job"]
    expected = JobSpec.model_json_schema()
    definitions = expected.pop("$defs")
    assert schema["$defs"] == definitions
    assert schema["properties"]["job"] == expected


def test_returned_schemas_are_independent_mutable_copies():
    bridge = ToolBridge(FakeService())
    first = bridge.tools("openai")
    original = copy.deepcopy(first)
    first[0]["parameters"]["properties"]["job"]["properties"].clear()
    assert bridge.tools("openai") == original
    first[1]["parameters"]["properties"].clear()
    assert first[2]["parameters"]["properties"]


@pytest.mark.parametrize(
    ("name", "arguments", "code"),
    [
        ("shell", {"secret": "do-not-echo"}, "unknown_tool"),
        ("submit_optimization", {}, "invalid_arguments"),
        ("submit_optimization", {"job": "do-not-echo"}, "invalid_arguments"),
        ("submit_optimization", {"job": {"source_dir": "do-not-echo"}}, "invalid_arguments"),
        ("get_optimization_status", {"run_id": "../../do-not-echo"}, "invalid_arguments"),
        (
            "get_optimization_result",
            {"run_id": RUN_ID, "extra": "do-not-echo"},
            "invalid_arguments",
        ),
        ("cancel_optimization", {"run_id": True}, "invalid_arguments"),
        ("cancel_optimization", None, "invalid_arguments"),
    ],
)
async def test_invalid_calls_are_rejected_before_service_without_echoing_values(
    name, arguments, code
):
    service = FakeService()
    result = await ToolBridge(service).dispatch(name, arguments)
    assert result["error"]["code"] == code
    assert "do-not-echo" not in json.dumps(result)
    assert service.calls == []


@pytest.mark.parametrize("name", sorted(NAMES))
async def test_service_errors_do_not_expose_exception_data_or_logs(name, capsys, caplog):
    class BrokenService:
        def status(self, run_id):
            raise RuntimeError("secret-api-key and private source snippet")

        result = status

        async def submit(self, spec):
            raise ValueError("secret-api-key and private source snippet")

        cancel = submit

    arguments = {"job": job()} if name == "submit_optimization" else {"run_id": RUN_ID}
    result = await ToolBridge(BrokenService()).dispatch(name, arguments)
    assert result["error"]["code"] == "service_error"
    captured = capsys.readouterr()
    assert "secret-api-key" not in json.dumps(result) + captured.out + captured.err + caplog.text


async def test_dispatch_does_not_swallow_cancellation():
    class CancelledService:
        async def submit(self, spec):
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await ToolBridge(CancelledService()).dispatch("submit_optimization", {"job": job()})


def test_unknown_provider_has_constant_error():
    with pytest.raises(ValueError, match="Supported tool formats"):
        ToolBridge(FakeService()).tools("secret-provider")
