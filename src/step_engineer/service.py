"""Async MCP job service; status calls are short even for long optimization runs."""

from __future__ import annotations

import asyncio
import json
import re
import uuid
from pathlib import Path

from .demo import EXAMPLE, DemoClient
from .harness import Harness
from .models import JobSpec
from .provider import StepClient
from .workspace import write_json


class JobService:
    def __init__(self, runs_dir: Path, allowed_roots: list[Path], *, offline_demo: bool = False):
        self.runs_dir = runs_dir.resolve()
        self.allowed_roots = [p.expanduser().resolve(strict=True) for p in allowed_roots]
        self.offline_demo = offline_demo
        self.tasks: dict[str, asyncio.Task] = {}

    def directory(self, run_id: str) -> Path:
        if not re.fullmatch(r"[a-f0-9]{32}", run_id):
            raise ValueError("Invalid run ID")
        p = self.runs_dir / run_id
        if p.is_symlink() or not p.is_dir():
            raise ValueError("Unknown run ID")
        return p

    async def submit(self, job: JobSpec) -> dict:
        if not Path(job.source_dir).is_absolute():
            raise ValueError("MCP source_dir must be absolute")
        source = Path(job.source_dir).expanduser().resolve(strict=True)
        if not any(source.is_relative_to(root) for root in self.allowed_roots):
            raise ValueError("source_dir is outside server --allow-root configuration")
        if self.offline_demo and source != EXAMPLE.resolve():
            raise ValueError("Offline demo only supports the bundled example")
        active = sum(not t.done() for t in self.tasks.values())
        if active >= 2:
            raise ValueError("Two optimization jobs are already active")
        client = DemoClient() if self.offline_demo else StepClient()
        job = job.model_copy(update={"source_dir": str(source)})
        run_id = uuid.uuid4().hex
        run_dir = self.runs_dir / run_id
        run_dir.mkdir(parents=True, mode=0o700)
        write_json(run_dir / "job.json", job.model_dump())
        write_json(
            run_dir / "status.json",
            {
                "run_id": run_id,
                "status": "queued",
                "mode": "offline-demo" if self.offline_demo else "live",
            },
        )
        harness = Harness(
            job, run_dir, client, mode="offline-demo" if self.offline_demo else "live"
        )
        task = asyncio.create_task(harness.run(), name=f"step-engineer-{run_id}")
        self.tasks[run_id] = task
        # Bound in-memory references while keeping all completed artifacts on disk.
        if len(self.tasks) > 200:
            self.tasks = {
                key: value for key, value in self.tasks.items() if not value.done() or key == run_id
            }
        return {
            "run_id": run_id,
            "status": "queued",
            "mode": harness.mode,
            "next_tool": "get_optimization_status",
            "artifact_dir": str(run_dir),
        }

    def status(self, run_id: str) -> dict:
        result = json.loads((self.directory(run_id) / "status.json").read_text())
        if result["status"] in {"running", "queued"} and run_id not in self.tasks:
            result["status"] = "interrupted"
            result["note"] = "The server restarted; this job is not being resumed or billed."
        task = self.tasks.get(run_id)
        if task and task.done() and task.cancelled():
            result["status"] = "cancelled"
        elif task and task.done() and task.exception():
            result = {
                "run_id": run_id,
                "status": "failed",
                "error": type(task.exception()).__name__,
            }
        return result

    async def cancel(self, run_id: str) -> dict:
        self.directory(run_id)
        task = self.tasks.get(run_id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return self.status(run_id)

    def result(self, run_id: str) -> dict:
        root = self.directory(run_id)
        result = root / "result.json"
        if not result.is_file():
            return {"available": False, **self.status(run_id)}
        return {"available": True, **json.loads(result.read_text())}

    async def close(self) -> None:
        pending = [t for t in self.tasks.values() if not t.done()]
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
