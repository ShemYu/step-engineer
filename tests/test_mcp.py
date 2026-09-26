"""Real stdio protocol tests; scripted fixture only, no external model requests."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from step_engineer.cli import load_job
from step_engineer.demo import EXAMPLE

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS sandbox integration")


@pytest.mark.asyncio
async def test_stdio_submit_poll_result(tmp_path):
    server = StdioServerParameters(
        command=sys.executable,
        args=[
            "-m",
            "step_engineer",
            "--runs-dir",
            str(tmp_path / "runs"),
            "serve",
            "--offline-demo",
            "--allow-root",
            str(EXAMPLE),
        ],
    )
    async with stdio_client(server) as (reader, writer):  # noqa: SIM117 - session uses transport streams
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            listing = await session.list_tools()
            assert {tool.name for tool in listing.tools} == {
                "submit_optimization",
                "get_optimization_status",
                "cancel_optimization",
                "get_optimization_result",
            }
            submit_tool = next(t for t in listing.tools if t.name == "submit_optimization")
            assert "job" in submit_tool.inputSchema["properties"]
            job = load_job(EXAMPLE / "job.json")
            job.budget.max_seconds = 240
            submission = await session.call_tool("submit_optimization", {"job": job.model_dump()})
            assert not submission.isError
            submitted = json.loads(submission.content[0].text)
            run_id = submitted["run_id"]
            for _ in range(100):
                response = await session.call_tool("get_optimization_status", {"run_id": run_id})
                state = json.loads(response.content[0].text)
                if state["status"] not in {"queued", "running"}:
                    break
                await asyncio.sleep(0.1)
            assert state["status"] == "improved", state
            response = await session.call_tool("get_optimization_result", {"run_id": run_id})
            result = json.loads(response.content[0].text)
            assert result["mode"] == "offline-demo"
            assert result["accepted"] and result["independently_checked"]
            assert Path(result["patch_path"]).read_text()
            assert result["total_tokens"] == 0
            bad = await session.call_tool("get_optimization_result", {"run_id": "../outside"})
            assert bad.isError
