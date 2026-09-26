"""Provider-neutral local MCP stdio interface. No port is opened."""

from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .models import JobSpec
from .service import JobService


def build_server(service: JobService) -> FastMCP:
    @asynccontextmanager
    async def lifespan(server):
        try:
            yield service
        finally:
            await service.close()

    server = FastMCP(
        "Step Engineering Optimizer",
        lifespan=lifespan,
        instructions="Keep the parent model and reasoning settings unchanged. Delegate only bounded engineering optimization tasks. Review accepted.patch and verification evidence before applying changes. Selected source and check feedback are sent to StepFun. Run directories are local; this server does not edit the original source.",
    )

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=True)
    )
    async def submit_optimization(job: JobSpec) -> dict:
        """Start a Step API optimization job in an isolated copy. Requires an allowed source_dir, explicit files, correctness checks, benchmark, and budget. Returns promptly with a run_id; poll status. Sends selected code to StepFun and may incur API charges. Never changes the parent model or original source."""
        return await service.submit(job)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    async def get_optimization_status(run_id: str) -> dict:
        """Read local job progress and estimated API cost. Poll at reasonable intervals."""
        return service.status(run_id)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=True, idempotentHint=True, openWorldHint=False)
    )
    async def get_optimization_result(run_id: str) -> dict:
        """Read measured results, final validation, and local patch/report paths. accepted=false means no changes are approved by the harness. Parent review is still required."""
        return service.result(run_id)

    @server.tool(
        annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
    )
    async def cancel_optimization(run_id: str) -> dict:
        """Cancel a local active job and its current check. A provider request already sent may still be billed."""
        return await service.cancel(run_id)

    return server
