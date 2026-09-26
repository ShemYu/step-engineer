import asyncio
import copy
import json

import httpx
import pytest

from step_engineer.provider import ProviderError, StepClient, estimate_cost


def completion(message=None, **overrides):
    result = {
        "choices": [
            {
                "message": message or {"role": "assistant", "content": "Done"},
                "finish_reason": "stop",
            }
        ],
        "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
    }
    return result | overrides


async def call(client, **kwargs):
    return await client.complete(
        [{"role": "user", "content": "Optimize"}],
        [],
        **({"reasoning_effort": "high", "max_tokens": 512, "timeout_seconds": 1} | kwargs),
    )


async def test_tool_round_trip_keeps_reasoning_in_memory_and_uses_step_endpoint():
    requests = []
    tool_message = {
        "role": "assistant",
        "content": None,
        "reasoning_content": "private continuation state",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "evaluate", "arguments": '{"label":"candidate"}'},
            }
        ],
    }

    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=completion(tool_message if len(requests) == 1 else None))

    client = StepClient(api_key='example_test_secret', transport=httpx.MockTransport(handler))
    messages = [{"role": "user", "content": "Optimize"}]
    tools = [
        {"type": "function", "function": {"name": "evaluate", "parameters": {"type": "object"}}}
    ]
    first = await client.complete(
        messages, tools, reasoning_effort="high", max_tokens=512, timeout_seconds=1
    )
    assert first["message"] == tool_message
    # The official tool-call example uses finish_reason=stop with tool_calls.
    assert first["finish_reason"] == "stop"
    messages += [
        first["message"],
        {"role": "tool", "tool_call_id": "call_1", "content": '{"passed":true}'},
    ]
    await client.complete(
        messages, tools, reasoning_effort="high", max_tokens=512, timeout_seconds=1
    )
    await client.aclose()
    assert len(requests) == 2
    assert str(requests[0].url) == "https://api.stepfun.ai/v1/chat/completions"
    assert requests[0].headers["authorization"] == 'Bearer example_test_secret'
    body = json.loads(requests[1].content)
    assert body["messages"][1] == tool_message
    assert body["tools"] == tools
    assert body["reasoning_format"] == "deepseek-style"
    assert body["reasoning_effort"] == "high"
    assert body["max_tokens"] == 512
    assert body["stream"] is False and body["n"] == 1


async def test_general_reasoning_field_is_preserved():
    msg = {"role": "assistant", "content": "Done", "reasoning": "opaque state"}
    client = StepClient(
        api_key="test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion(msg))),
    )
    assert (await call(client))["message"] == msg


@pytest.mark.parametrize(
    ("status", "code"),
    [
        (401, "authentication"),
        (403, "authentication"),
        (429, "rate_limit"),
        (503, "server"),
        (400, "request"),
        (307, "redirect"),
    ],
)
async def test_http_errors_do_not_retry_or_expose_body(status, code):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(
            status,
            text="test-secret sensitive server detail",
            headers={"Location": "https://example.com/stolen"},
        )

    client = StepClient(api_key='example_test_secret', transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await call(client)
    assert caught.value.code == code
    assert len(requests) == 1
    assert 'example_test_secret' not in str(caught.value)
    assert "sensitive" not in str(caught.value)
    assert caught.value.__cause__ is None


@pytest.mark.parametrize("kind", ["network", "http_timeout", "wall_timeout"])
async def test_transport_failure_is_bounded_and_safe(kind):
    requests = []

    async def handler(request):
        requests.append(request)
        if kind == "wall_timeout":
            await asyncio.sleep(1)
        if kind == "network":
            raise httpx.ConnectError('example_test_secret', request=request)
        raise httpx.ReadTimeout('example_test_secret', request=request)

    client = StepClient(api_key='example_test_secret', transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        await call(client, timeout_seconds=0.01)
    assert caught.value.code == ("connection" if kind == "network" else "timeout")
    assert caught.value.request_may_have_been_billed
    assert 'example_test_secret' not in str(caught.value)
    assert len(requests) == 1


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 3},
        {"prompt_tokens": True, "completion_tokens": 1, "total_tokens": 2},
        {"prompt_tokens": -1, "completion_tokens": 1, "total_tokens": 0},
        {"prompt_tokens": 1.0, "completion_tokens": 1, "total_tokens": 2},
    ],
)
async def test_missing_or_untrustworthy_usage_stops_run(usage):
    client = StepClient(
        api_key="test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion(usage=usage))),
    )
    with pytest.raises(ProviderError) as caught:
        await call(client)
    assert caught.value.code == "malformed_response"
    assert caught.value.request_may_have_been_billed
    assert caught.value.usage is None


async def test_malformed_message_preserves_valid_usage_for_accounting():
    client = StepClient(
        api_key="test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion(choices=[]))),
    )
    with pytest.raises(ProviderError) as caught:
        await call(client)
    assert caught.value.usage == {
        "prompt_tokens": 100,
        "completion_tokens": 20,
        "total_tokens": 120,
    }


@pytest.mark.parametrize("body", [b"not json test-secret", b"NaN", b'{"usage":Infinity}'])
async def test_invalid_json_does_not_leak_response(body):
    client = StepClient(
        api_key="test", transport=httpx.MockTransport(lambda _: httpx.Response(200, content=body))
    )
    with pytest.raises(ProviderError) as caught:
        await call(client)
    assert caught.value.code == "malformed_response"
    assert 'example_test_secret' not in str(caught.value)


@pytest.mark.parametrize("arguments", ['{"time":NaN}', "[]", "{bad json}"])
async def test_invalid_tool_arguments_are_rejected(arguments):
    msg = {
        "role": "assistant",
        "content": None,
        "tool_calls": [
            {
                "id": "c1",
                "type": "function",
                "function": {"name": "evaluate", "arguments": arguments},
            }
        ],
    }
    client = StepClient(
        api_key="test",
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=completion(msg))),
    )
    with pytest.raises(ProviderError):
        await call(client)


@pytest.mark.parametrize(
    "base_url",
    [
        "http://api.stepfun.ai/v1",
        "https://api.stepfun.ai.example.com/v1",
        "https://api.stepfun.ai@evil.example/v1",
        "https://api.stepfun.ai/v1?x=1",
        "https://api.stepfun.com/v1",
        "https://api.openai.com/v1",
        "http://localhost:8080/v1",
    ],
)
def test_only_verified_step_origin_is_allowed(base_url):
    with pytest.raises(ProviderError) as caught:
        StepClient(api_key="test", base_url=base_url)
    assert caught.value.code == "configuration"


def test_environment_key_precedence_and_base_url(monkeypatch):
    monkeypatch.setenv("STEP_API_KEY", "first-key")
    monkeypatch.setenv("STEPFUN_API_KEY", "second-key")
    monkeypatch.setenv("STEP_BASE_URL", "https://api.stepfun.ai/v1/")
    first = StepClient()
    assert first._api_key == "first-key"
    assert first.base_url == "https://api.stepfun.ai/v1"
    monkeypatch.delenv("STEP_API_KEY")
    assert StepClient()._api_key == "second-key"
    assert StepClient(api_key='example_explicit')._api_key == 'example_explicit'
    monkeypatch.delenv("STEPFUN_API_KEY")
    with pytest.raises(ProviderError):
        StepClient()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_tokens": 0},
        {"max_tokens": 64001},
        {"max_tokens": True},
        {"reasoning_effort": "ultra"},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": float("inf")},
        {"timeout_seconds": -1},
    ],
)
async def test_invalid_request_limits_fail_before_network(kwargs):
    requests = []
    client = StepClient(
        api_key="test", transport=httpx.MockTransport(lambda req: requests.append(req))
    )
    with pytest.raises(ProviderError) as caught:
        await call(client, **kwargs)
    assert caught.value.code == "configuration"
    assert requests == []


def test_cost_conservatively_ignores_cache_discount():
    usage = {
        "prompt_tokens": 1_000_000,
        "completion_tokens": 1_000_000,
        "total_tokens": 2_000_000,
        "cached_tokens": 900_000,
    }
    assert estimate_cost(copy.deepcopy(usage)) == pytest.approx(3.7)
