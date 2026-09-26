"""Run fixed parent-owned commands inside a restricted macOS process sandbox.

This is a local engineering guardrail, not a hostile multi-tenant compute service.
Output is bounded in memory; scratch has a monitored aggregate limit and a hard
per-file limit. Unsupported platforms fail closed instead of running unsandboxed.
"""

from __future__ import annotations

import asyncio
import json
import math
import os
import shutil
import signal
import stat
import sys
import sysconfig
import time
from pathlib import Path

from .models import CommandSpec

MAX_OUTPUT_BYTES = 16 * 1024
MAX_SCRATCH_BYTES = 64 * 1024 * 1024
MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SCRATCH_ENTRIES = 4096
SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")


def _quote(path: Path | str) -> str:
    return json.dumps(str(path), ensure_ascii=True)


def _runtime_paths() -> tuple[set[Path], set[Path]]:
    """Permit installed runtime libraries, not arbitrary cwd/PYTHONPATH entries."""
    trees = {
        Path("/System/Library"),
        Path("/usr/lib"),
        Path("/usr/bin"),
        Path("/usr/share"),
        Path("/bin"),
        Path("/System/Volumes/Preboot/Cryptexes/OS/System/Library"),
        Path("/System/Volumes/Preboot/Cryptexes/OS/usr/lib"),
    }
    exact = {Path("/"), Path("/dev/null"), Path("/dev/random"), Path("/dev/urandom")}
    for prefix_string in {sys.prefix, sys.base_prefix}:
        prefix = Path(prefix_string).resolve()
        # A misconfigured interpreter prefix must not turn into a home read grant.
        if (prefix == Path.home() or prefix in Path.home().parents) and prefix not in {
            Path("/usr"),
            Path("/usr/local"),
        }:
            raise RuntimeError("Unsafe Python runtime prefix; refusing sandbox setup")
        for relative in ("lib", "bin", "share"):
            trees.add(prefix / relative)
        exact.add(prefix / "pyvenv.cfg")
    for key in ("stdlib", "platstdlib", "purelib", "platlib"):
        trees.add(Path(sysconfig.get_paths()[key]).resolve())
    for entry in sys.path:
        if not entry:
            continue
        p = Path(entry).absolute()
        # Narrow dependency paths only; never expose an editable checkout or home.
        if p.name in {"site-packages", "dist-packages", "lib-dynload"}:
            trees.add(p)
            trees.add(p.resolve())
        elif p.name.startswith("python") and p.suffix == ".zip":
            exact.add(p)
    exact.add(Path(sys.executable).absolute())
    exact.add(Path(sys.executable).resolve())
    exact.add(Path(getattr(sys, "_base_executable", sys.executable)).absolute())
    framework = sysconfig.get_config_var("PYTHONFRAMEWORK")
    if isinstance(framework, str) and framework and Path(framework).name == framework:
        # Framework builds place libpython beside lib/, not within it. Use the
        # running interpreter's version prefix: build-time framework prefixes can
        # be stale after relocation. Keep this an exact-file grant, including the
        # alias and resolved path, rather than exposing the framework directory.
        shared_library = Path(sys.base_prefix) / framework
        exact.add(shared_library.absolute())
        exact.add(shared_library.resolve())
    return trees, exact


def _profile(workspace: Path, scratch: Path, executable: Path) -> str:
    trees, exact = _runtime_paths()
    trees.update({workspace, scratch})
    exact.add(executable)
    exact.add(executable.resolve())
    metadata = set()
    for path in trees | exact:
        metadata.update(path.parents)
    read_rules = [f"(subpath {_quote(p)})" for p in sorted(trees)]
    read_rules += [f"(literal {_quote(p)})" for p in sorted(exact)]
    metadata_rules = [f"(literal {_quote(p)})" for p in sorted(metadata)]
    return "\n".join(
        [
            "(version 1)",
            "(deny default)",
            "(allow process-exec)",
            "(allow process-fork)",
            "(allow sysctl-read)",
            "(allow file-read* " + " ".join(read_rules) + ")",
            "(allow file-read-metadata " + " ".join(metadata_rules) + ")",
            f"(allow file-write* (subpath {_quote(scratch)}))",
            '(allow file-write-data (literal "/dev/null"))',
            "(deny network*)",
        ]
    )


def _environment(scratch: Path) -> dict[str, str]:
    home = scratch / "home"
    tmp = scratch / "tmp"
    home.mkdir(exist_ok=True)
    tmp.mkdir(exist_ok=True)
    # Construct from scratch: no API keys, SSH agent, proxy, DYLD_*, or PYTHONPATH.
    return {
        "PATH": f"{Path(sys.executable).parent}:/usr/bin:/bin",
        "HOME": str(home),
        "TMPDIR": str(tmp),
        "TMP": str(tmp),
        "TEMP": str(tmp),
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "TZ": "UTC",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "PYTHONUNBUFFERED": "1",
        "NO_COLOR": "1",
    }


def _scratch_over_limit(scratch: Path) -> bool:
    total = count = 0
    for root, directories, files in os.walk(scratch, followlinks=False):
        for name in [*directories, *files]:
            count += 1
            if count > MAX_SCRATCH_ENTRIES:
                return True
            try:
                item = (Path(root) / name).lstat()
            except FileNotFoundError:
                continue
            if stat.S_ISREG(item.st_mode):
                total += item.st_size
                if total > MAX_SCRATCH_BYTES:
                    return True
    return False


async def _read_bounded(stream: asyncio.StreamReader, output: bytearray) -> bool:
    truncated = False
    while chunk := await stream.read(8192):
        remaining = MAX_OUTPUT_BYTES - len(output)
        truncated |= len(chunk) > remaining
        if remaining > 0:
            output.extend(chunk[:remaining])
        # Continue draining excess bytes to avoid backpressure deadlocks, never spool.
    return truncated


def _text(output: bytearray) -> str:
    # Replacement characters must not expand invalid UTF-8 beyond the byte cap.
    return (
        bytes(output)
        .decode("utf-8", errors="replace")
        .encode("utf-8")[:MAX_OUTPUT_BYTES]
        .decode("utf-8", errors="ignore")
    )


def _kill_group(process: asyncio.subprocess.Process) -> None:
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


async def run_command(
    command: CommandSpec,
    workspace: Path,
    scratch: Path,
    *,
    timeout_seconds: float | None = None,
) -> dict:
    """Execute a fixed argv with restricted reads/writes, network off, and a deadline."""
    if sys.platform != "darwin" or not SANDBOX_EXEC.is_file():
        raise RuntimeError("macOS sandbox-exec is required; refusing unsandboxed execution")
    workspace = workspace.resolve(strict=True)
    scratch.mkdir(parents=True, exist_ok=True)
    scratch = scratch.resolve(strict=True)
    if not workspace.is_dir() or not scratch.is_dir():
        raise RuntimeError("Command workspace and scratch must be directories")
    if workspace == scratch or workspace in scratch.parents or scratch in workspace.parents:
        raise RuntimeError("Command workspace and scratch must be separate, nonoverlapping paths")
    if any(scratch.iterdir()):
        raise RuntimeError("Each command requires a fresh, empty scratch directory")
    timeout = (
        command.timeout_seconds
        if timeout_seconds is None
        else min(timeout_seconds, command.timeout_seconds)
    )
    if not math.isfinite(timeout) or timeout <= 0:
        raise RuntimeError("Command deadline has already expired")
    environment = _environment(scratch)
    argv = [
        v.replace("{workspace}", str(workspace)).replace("{scratch}", str(scratch))
        for v in command.argv
    ]
    if argv[0] in {"{python}", "python"}:
        argv[0] = sys.executable
    executable_string = shutil.which(argv[0], path=environment["PATH"])
    if executable_string is None:
        raise RuntimeError("Command executable was not found in the restricted runtime PATH")
    executable = Path(executable_string).absolute()
    argv[0] = str(executable)
    profile = _profile(workspace, scratch, executable)
    # Apply hard limits inside the child, avoiding preexec_fn in threaded MCP hosts.
    bootstrap = (
        "import os,resource,sys;"
        f"resource.setrlimit(resource.RLIMIT_FSIZE,({MAX_FILE_BYTES},{MAX_FILE_BYTES}));"
        "resource.setrlimit(resource.RLIMIT_CORE,(0,0));"
        "resource.setrlimit(resource.RLIMIT_NOFILE,(128,128));"
        "os.execv(sys.argv[1],sys.argv[1:])"
    )
    started = time.monotonic()
    process = await asyncio.create_subprocess_exec(
        str(SANDBOX_EXEC),
        "-p",
        profile,
        sys.executable,
        "-I",
        "-c",
        bootstrap,
        *argv,
        cwd=workspace,
        env=environment,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
        limit=MAX_OUTPUT_BYTES,
    )
    stdout, stderr = bytearray(), bytearray()
    readers = [
        asyncio.create_task(_read_bounded(process.stdout, stdout)),
        asyncio.create_task(_read_bounded(process.stderr, stderr)),
    ]
    wait_task = asyncio.create_task(process.wait())
    timed_out = disk_limit_exceeded = False
    try:
        # A child retaining the pipe after the direct process exits is also bounded.
        while not (wait_task.done() and all(reader.done() for reader in readers)):
            if time.monotonic() - started >= timeout:
                timed_out = True
                break
            if _scratch_over_limit(scratch):
                disk_limit_exceeded = True
                break
            # Wake immediately on completion, preserving sub-50ms timing precision.
            pending_tasks = [task for task in [wait_task, *readers] if not task.done()]
            await asyncio.wait(
                pending_tasks,
                return_when=asyncio.FIRST_COMPLETED,
                timeout=min(0.05, max(0.001, timeout - (time.monotonic() - started))),
            )
    finally:
        # Always remove remaining descendants, including after a successful parent exit.
        _kill_group(process)
        _, pending = await asyncio.wait([wait_task, *readers], timeout=1)
        if pending:
            # A deliberately detached session can keep inherited pipes open. Do not
            # allow that to hang the host; this sandbox is not a hostile-code VM.
            for task in pending:
                task.cancel()
            process._transport.close()
        await asyncio.gather(wait_task, *readers, return_exceptions=True)
    if disk_limit_exceeded:
        message = b"\nScratch storage limit exceeded."
        stderr[-len(message) :] = message
    stderr_text = _text(stderr)
    if "sandbox-exec:" in stderr_text and (
        "sandbox_init" in stderr_text or "profile" in stderr_text
    ):
        raise RuntimeError("macOS sandbox initialization failed; command was not run")
    return {
        "name": command.name,
        "exit_code": process.returncode,
        "stdout": _text(stdout),
        "stderr": stderr_text,
        "elapsed_seconds": time.monotonic() - started,
        "timed_out": timed_out,
        "sandboxed": True,
        "storage_limit_exceeded": disk_limit_exceeded,
        "output_limit_exceeded": any(
            reader.cancelled() or (reader.exception() is None and reader.result())
            for reader in readers
        ),
    }
