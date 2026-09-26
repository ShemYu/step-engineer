"""Bounded, non-streaming StepFun client; no model SDK or implicit retries.

Protocol checked against the official Chat Completions and reasoning docs on
2026-09-26. Assistant reasoning is retained only for continuation in memory;
callers must not put it into user reports or persistent transcripts.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import re
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.stepfun.ai/v1"
ALLOWED_BASE_URLS = frozenset({DEFAULT_BASE_URL})
MAX_OUTPUT_TOKENS = 64_000
MAX_RESPONSE_BYTES = 8 * 1024 * 1024
INPUT_USD_PER_MILLION = 1.0
OUTPUT_USD_PER_MILLION = 2.7
_FUNCTION_NAME = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")


class ProviderError(RuntimeError):
    """Safe error with no raw response, request body, or credential attached."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        usage: dict[str, int] | None = None,
        request_may_have_been_billed: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.usage = usage
        self.request_may_have_been_billed = request_may_have_been_billed


def _reject_nonfinite(value: str) -> None:
    raise ValueError("Non-finite JSON value")


def _validate_usage(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        raise TypeError("Missing token usage")
    usage = {}
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        count = value.get(key)
        if type(count) is not int or count < 0 or count > 2**53:
            raise ValueError("Invalid token usage")
        usage[key] = count
    if usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]:
        raise ValueError("Inconsistent token usage")
    return usage


def estimate_cost(usage: dict[str, int]) -> float:
    """Step 5 Preview estimate in USD; conservatively ignore cache discounts.

    Published prices verified 2026-09-26. This is an estimate, not an invoice.
    Other models or future prices require a different pricing configuration.
    """
    clean = _validate_usage(usage)
    return (
        clean["prompt_tokens"] * INPUT_USD_PER_MILLION
        + clean["completion_tokens"] * OUTPUT_USD_PER_MILLION
    ) / 1_000_000


def _validate_message(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict) or value.get("role") != "assistant":
        raise ValueError("Missing assistant message")
    content = value.get("content")
    if content is not None and not isinstance(content, str):
        raise ValueError("Invalid assistant content")
    message: dict[str, Any] = {"role": "assistant", "content": content}
    for field in ("reasoning_content", "reasoning"):
        if field in value:
            if value[field] is not None and not isinstance(value[field], str):
                raise ValueError("Invalid assistant reasoning")
            message[field] = value[field]
    calls = value.get("tool_calls")
    if calls is not None:
        if not isinstance(calls, list) or len(calls) > 128:
            raise ValueError("Invalid tool calls")
        clean_calls = []
        seen_ids: set[str] = set()
        for call in calls:
            if not isinstance(call, dict):
                raise TypeError("Invalid tool call")
            call_id = call.get("id")
            function = call.get("function")
            if (
                not isinstance(call_id, str)
                or not call_id
                or len(call_id) > 256
                or call_id in seen_ids
                or call.get("type") != "function"
                or not isinstance(function, dict)
            ):
                raise ValueError("Invalid tool call")
            name = function.get("name")
            arguments = function.get("arguments")
            if (
                not isinstance(name, str)
                or _FUNCTION_NAME.fullmatch(name) is None
                or not isinstance(arguments, str)
                or not isinstance(json.loads(arguments, parse_constant=_reject_nonfinite), dict)
            ):
                raise ValueError("Invalid tool function")
            seen_ids.add(call_id)
            clean_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": arguments},
                }
            )
        message["tool_calls"] = clean_calls
    if content is None and not calls:
        raise ValueError("Empty assistant message")
    return message


class StepClient:
    """Requests only the documented StepFun API origin.

    HTTP redirects, environment proxies, and automatic retries are disabled.
    Each completion owns its HTTP connection, so ``aclose`` is a no-op supplied
    for the same lifecycle interface as a persistent asynchronous client.
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str = "step-5-preview",
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        candidate_key = (
            api_key
            if api_key is not None
            else os.environ.get("STEP_API_KEY") or os.environ.get("STEPFUN_API_KEY")
        )
        if (
            not isinstance(candidate_key, str)
            or not candidate_key.strip()
            or any(ord(char) < 33 or ord(char) > 126 for char in candidate_key)
        ):
            raise ProviderError("configuration", "Set a valid STEP_API_KEY or STEPFUN_API_KEY.")
        candidate_url = (
            base_url if base_url is not None else os.environ.get("STEP_BASE_URL", DEFAULT_BASE_URL)
        )
        if not isinstance(candidate_url, str) or candidate_url.rstrip("/") not in ALLOWED_BASE_URLS:
            raise ProviderError(
                "configuration", "STEP_BASE_URL must use https://api.stepfun.ai/v1."
            )
        if not isinstance(model, str) or re.fullmatch(r"step-[A-Za-z0-9._-]+", model) is None:
            raise ProviderError("configuration", "A StepFun model identifier is required.")
        self._api_key = candidate_key
        self.base_url = candidate_url.rstrip("/")
        self.model = model
        self._transport = transport

    async def aclose(self) -> None:
        """No persistent HTTP resources are held between completions."""

    async def complete(
        self,
        messages: list[dict],
        tools: list[dict],
        *,
        reasoning_effort: str,
        max_tokens: int,
        timeout_seconds: float,
    ) -> dict:
        if reasoning_effort not in {"low", "medium", "high"}:
            raise ProviderError(
                "configuration", "Step reasoning effort must be low, medium, or high."
            )
        if type(max_tokens) is not int or not 1 <= max_tokens <= MAX_OUTPUT_TOKENS:
            raise ProviderError("configuration", "max_tokens must be an integer from 1 to 64000.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (float, int))
            or not math.isfinite(timeout_seconds)
            or timeout_seconds <= 0
        ):
            raise ProviderError("configuration", "timeout_seconds must be positive and finite.")
        if (
            not isinstance(messages, list)
            or not messages
            or not all(isinstance(message, dict) for message in messages)
            or not isinstance(tools, list)
            or not all(isinstance(tool, dict) for tool in tools)
        ):
            raise ProviderError("configuration", "messages and tools must be lists of objects.")
        payload = {
            "model": self.model,
            "messages": messages,
            "reasoning_effort": reasoning_effort,
            "reasoning_format": "deepseek-style",
            "max_tokens": max_tokens,
            "stream": False,
            "n": 1,
        }
        if tools:
            payload["tools"] = tools
        try:
            encoded = json.dumps(payload, allow_nan=False, ensure_ascii=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProviderError(
                "configuration", "Request must contain valid finite JSON."
            ) from None

        try:
            async with asyncio.timeout(timeout_seconds):
                async with (
                    httpx.AsyncClient(
                        transport=self._transport,
                        follow_redirects=False,
                        trust_env=False,
                        timeout=timeout_seconds,
                    ) as client,
                    client.stream(
                        "POST",
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self._api_key}",
                            "Content-Type": "application/json",
                        },
                        content=encoded,
                    ) as response,
                ):
                    if response.status_code != 200:
                        code, message = _status_error(response.status_code)
                        raise ProviderError(code, message)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > MAX_RESPONSE_BYTES:
                            raise ProviderError(
                                "malformed_response",
                                "StepFun response exceeded the local size limit; stopped.",
                                request_may_have_been_billed=True,
                            )
        except (httpx.TimeoutException, TimeoutError):
            raise ProviderError(
                "timeout",
                "StepFun request timed out; no retry was sent. Usage may have been billed.",
                request_may_have_been_billed=True,
            ) from None
        except httpx.HTTPError:
            raise ProviderError(
                "connection",
                "StepFun connection failed; no retry was sent. Usage may have been billed.",
                request_may_have_been_billed=True,
            ) from None

        usage = None
        try:
            result = json.loads(data, parse_constant=_reject_nonfinite)
            if not isinstance(result, dict):
                raise TypeError("Invalid response")
            usage = _validate_usage(result.get("usage"))
            choices = result.get("choices")
            if (
                not isinstance(choices, list)
                or len(choices) != 1
                or not isinstance(choices[0], dict)
            ):
                raise ValueError("Invalid choices")
            choice = choices[0]
            finish_reason = choice.get("finish_reason")
            if finish_reason not in ("stop", "tool_calls", "length", "content_filter"):
                raise ValueError("Invalid finish reason")
            message = _validate_message(choice.get("message"))
            return {"message": message, "usage": usage, "finish_reason": finish_reason}
        except (ValueError, TypeError, UnicodeError, RecursionError):
            raise ProviderError(
                "malformed_response",
                "StepFun returned an invalid completion or token usage; stopped without retry.",
                usage=usage,
                request_may_have_been_billed=True,
            ) from None


def _status_error(status: int) -> tuple[str, str]:
    if status in (401, 403):
        return "authentication", "StepFun rejected the API key or account access."
    if status == 429:
        return "rate_limit", "StepFun rate or quota limit reached; no retry was sent."
    if 300 <= status < 400:
        return "redirect", "StepFun redirect refused; no credential was forwarded."
    if status >= 500:
        return "server", "StepFun service error; no retry was sent."
    return "request", f"StepFun rejected the request (HTTP {status}); no retry was sent."
