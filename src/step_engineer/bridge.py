"""Tool schemas and local dispatch for an existing parent model's API loop.

This adapter does not call OpenAI, xAI, or Anthropic, select a parent model, or
change its reasoning setting. The host application decodes tool arguments and
passes the returned result back using its provider's tool-result envelope.
"""

from __future__ import annotations

import copy
import re
from typing import Literal

from pydantic import ValidationError

from .models import JobSpec
from .service import JobService

Provider = Literal["openai", "grok", "claude"]
_RUN_ID = re.compile(r"[a-f0-9]{32}\Z")
_DESCRIPTIONS = {
    "submit_optimization": (
        "Start a bounded engineering optimization in an isolated local copy. "
        "Provide an allowed source_dir, explicit files, protected checks, benchmark, "
        "and budget. Selected code and check feedback are sent to StepFun and may "
        "incur charges. Returns a run_id promptly. Does not change the parent model "
        "or original source; parent review of the resulting patch is required."
    ),
    "get_optimization_status": (
        "Read local job progress and estimated API cost by run_id. Poll at reasonable intervals."
    ),
    "get_optimization_result": (
        "Read measured results, final validation, and local patch/report paths. "
        "accepted=false means the harness did not approve changes. "
        "Parent review is still required before applying an accepted patch."
    ),
    "cancel_optimization": (
        "Cancel an active local job and its current check. A provider request "
        "already sent may still be billed."
    ),
}


def _schemas() -> dict[str, dict]:
    job_schema = JobSpec.model_json_schema()
    # Pydantic's references are document-root-relative. Once JobSpec is nested
    # under properties.job, its definitions must stay at the outer schema root.
    definitions = job_schema.pop("$defs", {})
    submit = {
        "type": "object",
        "properties": {"job": job_schema},
        "required": ["job"],
        "additionalProperties": False,
    }
    if definitions:
        submit["$defs"] = definitions
    run = {
        "type": "object",
        "properties": {"run_id": {"type": "string", "pattern": "^[a-f0-9]{32}$"}},
        "required": ["run_id"],
        "additionalProperties": False,
    }
    return {
        "submit_optimization": submit,
        **{name: run for name in _DESCRIPTIONS if name != "submit_optimization"},
    }


def _error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


class ToolBridge:
    """Expose the same four local service tools in each parent's tool format."""

    def __init__(self, service: JobService):
        self.service = service

    def tools(self, provider: Provider) -> list[dict]:
        """Return fresh tool schemas without making any provider request.

        OpenAI uses the Responses API's flat function format. Grok uses the
        Chat Completions function wrapper. Claude uses input_schema. OpenAI
        strict mode is explicitly disabled because JobSpec has optional fields
        with defaults; dispatch still enforces the full Pydantic contract.
        """
        if provider not in ("openai", "grok", "claude"):
            raise ValueError("Supported tool formats are openai, grok, and claude.")
        output = []
        for name, schema in _schemas().items():
            function = {
                "name": name,
                "description": _DESCRIPTIONS[name],
                "parameters": copy.deepcopy(schema),
            }
            if provider == "openai":
                output.append({"type": "function", **function, "strict": False})
            elif provider == "grok":
                output.append({"type": "function", "function": function})
            else:
                output.append(
                    {
                        "name": name,
                        "description": _DESCRIPTIONS[name],
                        "input_schema": function["parameters"],
                    }
                )
        return output

    async def dispatch(self, name: str, arguments: dict) -> dict:
        """Validate and execute one local call; never echo exception payloads.

        The caller is responsible for binding arguments to the exact tool call
        ID from its parent provider. Cancellation propagates normally.
        """
        if not isinstance(name, str) or name not in _DESCRIPTIONS:
            return _error("unknown_tool", "The requested optimization tool does not exist.")
        expected = "job" if name == "submit_optimization" else "run_id"
        if not isinstance(arguments, dict) or set(arguments) != {expected}:
            return _error("invalid_arguments", "Tool arguments do not match the declared schema.")
        if name == "submit_optimization":
            if not isinstance(arguments["job"], dict):
                return _error("invalid_arguments", "job must be an object matching JobSpec.")
            try:
                job = JobSpec.model_validate(arguments["job"])
            except (ValidationError, TypeError, ValueError):
                return _error("invalid_arguments", "job did not pass JobSpec validation.")
        else:
            run_id = arguments["run_id"]
            if not isinstance(run_id, str) or _RUN_ID.fullmatch(run_id) is None:
                return _error(
                    "invalid_arguments", "run_id must be a 32-character lowercase hex ID."
                )
        try:
            if name == "submit_optimization":
                return await self.service.submit(job)
            if name == "get_optimization_status":
                return self.service.status(run_id)
            if name == "get_optimization_result":
                return self.service.result(run_id)
            return await self.service.cancel(run_id)
        except Exception:  # noqa: BLE001 - sanitize every service exception at the tool boundary
            # Exception messages may include keys, source fragments, file names,
            # or provider response bodies. Do not serialize or log them.
            return _error(
                "service_error",
                "The local job service could not complete this request. "
                "Check the server configuration and local job status.",
            )
