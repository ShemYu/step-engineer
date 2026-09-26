"""CLI for local tool executors and MCP hosts; stdout is always machine-readable."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import shutil
import sys
import uuid
from pathlib import Path

from dotenv import load_dotenv

from .demo import EXAMPLE, DemoClient
from .harness import Harness
from .models import JobSpec
from .provider import DEFAULT_BASE_URL, ProviderError, StepClient
from .service import JobService
from .workspace import write_json


def load_job(path: Path) -> JobSpec:
    path = path.expanduser().resolve(strict=True)
    job = JobSpec.model_validate_json(path.read_text())
    source = Path(job.source_dir).expanduser()
    if not source.is_absolute():
        source = path.parent / source
    return job.model_copy(update={"source_dir": str(source.resolve(strict=True))})


def doctor() -> dict:
    key = bool(os.getenv("STEP_API_KEY") or os.getenv("STEPFUN_API_KEY"))
    sandbox = platform.system() == "Darwin" and bool(shutil.which("sandbox-exec"))
    return {
        "model": "step-5-preview",
        "api_key_present": key,
        "base_url": os.getenv("STEP_BASE_URL", DEFAULT_BASE_URL),
        "sandbox_available": sandbox,
        "platform": platform.system(),
        "configured_for_live_run": key and sandbox,
        "note": "Presence check only; authentication, quota, and model access are not verified.",
    }


async def run_job(args) -> dict:
    job = load_job(Path(args.job))
    if args.offline_demo and Path(job.source_dir) != EXAMPLE.resolve():
        raise ValueError("Offline demo only supports examples/batch_aggregation/job.json")
    client = DemoClient() if args.offline_demo else StepClient()
    root = Path(args.runs_dir).expanduser().resolve() / uuid.uuid4().hex
    root.mkdir(parents=True, mode=0o700)
    write_json(root / "job.json", job.model_dump())
    return await Harness(
        job, root, client, mode="offline-demo" if args.offline_demo else "live"
    ).run()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env-file", help="Explicit local dotenv file; existing environment values take precedence"
    )
    parser.add_argument(
        "--runs-dir",
        default=str(Path.cwd() / "runs"),
        help="Local artifacts directory (default: ./runs in the current directory)",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("schema")
    run = sub.add_parser("run")
    run.add_argument("job")
    run.add_argument(
        "--offline-demo", action="store_true", help="Scripted fixture, no Step API request"
    )
    serve = sub.add_parser("serve")
    serve.add_argument(
        "--allow-root",
        action="append",
        default=[],
        help="Allowed source directory; repeat for multiple projects",
    )
    serve.add_argument(
        "--offline-demo", action="store_true", help="Only for local integration tests"
    )
    report = sub.add_parser("report")
    report.add_argument("run_id")
    args = parser.parse_args()
    try:
        if args.env_file:
            env_file = Path(args.env_file).expanduser()
            if env_file.is_symlink() or not env_file.is_file():
                raise ValueError("--env-file must be a regular existing file")
            load_dotenv(env_file, override=False, interpolate=False)
        if args.command == "doctor":
            result = doctor()
        elif args.command == "schema":
            result = JobSpec.model_json_schema()
        elif args.command == "run":
            result = asyncio.run(run_job(args))
        elif args.command == "report":
            result = JobService(Path(args.runs_dir), []).result(args.run_id)
        else:
            from .server import build_server

            roots = [Path(p) for p in args.allow_root] or [EXAMPLE]
            service = JobService(Path(args.runs_dir), roots, offline_demo=args.offline_demo)
            build_server(service).run(transport="stdio")
            return
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        if args.command == "run" and result["status"] in {"failed", "cancelled"}:
            raise SystemExit(1)
    except KeyboardInterrupt:
        print(json.dumps({"status": "cancelled"}))
        raise SystemExit(130)
    except (ValueError, OSError, ProviderError) as exc:
        # Pydantic errors can contain user input; do not echo them or dotenv content.
        message = (
            str(exc)
            if isinstance(exc, ProviderError)
            else "Invalid local configuration or job; check paths and the job schema."
        )
        print(
            json.dumps({"status": "error", "type": type(exc).__name__, "message": message}),
            file=sys.stderr,
        )
        raise SystemExit(2)
