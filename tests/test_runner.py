from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

import pytest

from step_engineer import runner
from step_engineer.models import CommandSpec

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="macOS sandbox integration")


def command(code: str, timeout: float = 5) -> CommandSpec:
    return CommandSpec(name="test", argv=["{python}", "-c", code], timeout_seconds=timeout)


def paths(tmp_path: Path) -> tuple[Path, Path]:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    return workspace, tmp_path / "scratch"


async def test_normal_command_and_sanitized_environment(tmp_path, monkeypatch):
    workspace, scratch = paths(tmp_path)
    (workspace / "input.txt").write_text("hello")
    monkeypatch.setenv("STEP_API_KEY", "must-not-reach-the-child")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-the-child")
    result = await runner.run_command(
        command(
            "import json,os,pathlib; "
            "assert 'STEP_API_KEY' not in os.environ and 'OPENAI_API_KEY' not in os.environ; "
            "pathlib.Path('{scratch}/result.txt').write_text('ok'); "
            "print(json.dumps({'input':pathlib.Path('input.txt').read_text(), 'cwd':os.getcwd()}))"
        ),
        workspace,
        scratch,
    )
    assert result["exit_code"] == 0, result
    assert result["sandboxed"] and not result["timed_out"]
    assert json.loads(result["stdout"])["input"] == "hello"
    assert (scratch / "result.txt").read_text() == "ok"


async def test_workspace_writes_and_private_reads_are_denied(tmp_path):
    workspace, scratch = paths(tmp_path)
    secret = tmp_path / "outside-secret.txt"
    secret.write_text("private-value")
    (workspace / "protected.txt").write_text("original")
    code = (
        "from pathlib import Path; import json; result={}; "
        f"outside=Path({str(secret)!r}); "
        "\nfor name,action in ["
        "('write_workspace',lambda:Path('protected.txt').write_text('changed')),"
        "('read_outside',lambda:outside.read_text()),"
        "('write_outside',lambda:outside.write_text('changed'))]:"
        "\n try: action(); result[name]='allowed'"
        "\n except PermissionError: result[name]='denied'"
        "\nprint(json.dumps(result))"
    )
    result = await runner.run_command(command(code), workspace, scratch)
    assert result["exit_code"] == 0, result
    assert set(json.loads(result["stdout"]).values()) == {"denied"}
    assert (workspace / "protected.txt").read_text() == "original"
    assert secret.read_text() == "private-value"


async def test_network_is_denied(tmp_path):
    workspace, scratch = paths(tmp_path)
    result = await runner.run_command(
        command("import socket; s=socket.socket(); s.settimeout(1); s.connect(('127.0.0.1',9))"),
        workspace,
        scratch,
    )
    assert result["exit_code"] != 0
    assert "PermissionError" in result["stderr"] or "Operation not permitted" in result["stderr"]


async def test_output_is_bounded_without_deadlock(tmp_path):
    workspace, scratch = paths(tmp_path)
    result = await runner.run_command(
        command("import os; os.write(1,b'x'*2000000); os.write(2,b'y'*2000000)"), workspace, scratch
    )
    assert result["exit_code"] == 0, result
    assert len(result["stdout"].encode()) == runner.MAX_OUTPUT_BYTES
    assert len(result["stderr"].encode()) == runner.MAX_OUTPUT_BYTES
    assert result["output_limit_exceeded"]


async def test_timeout_kills_child_process_group(tmp_path):
    workspace, scratch = paths(tmp_path)
    marker = scratch / "child-survived.txt"
    child = f"import time,pathlib; time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    code = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(10)"
    start = time.monotonic()
    result = await runner.run_command(command(code, timeout=0.25), workspace, scratch)
    assert result["timed_out"]
    assert time.monotonic() - start < 2
    await asyncio.sleep(1.1)
    assert not marker.exists()


async def test_cancellation_kills_child_process_group(tmp_path):
    workspace, scratch = paths(tmp_path)
    marker = scratch / "child-survived.txt"
    child = f"import time,pathlib; time.sleep(1); pathlib.Path({str(marker)!r}).touch()"
    code = f"import subprocess,sys,time; subprocess.Popen([sys.executable,'-c',{child!r}]); time.sleep(10)"
    task = asyncio.create_task(runner.run_command(command(code), workspace, scratch))
    await asyncio.sleep(0.25)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.sleep(1.1)
    assert not marker.exists()


async def test_per_file_limit(tmp_path):
    workspace, scratch = paths(tmp_path)
    result = await runner.run_command(
        command(
            "from pathlib import Path; "
            "f=Path('{scratch}/too-large').open('wb'); "
            "\nfor i in range(32): f.write(b'x'*1024*1024); f.flush()"
        ),
        workspace,
        scratch,
    )
    assert result["exit_code"] != 0
    assert (scratch / "too-large").stat().st_size <= runner.MAX_FILE_BYTES


async def test_no_unsandboxed_fallback(tmp_path, monkeypatch):
    workspace, scratch = paths(tmp_path)
    monkeypatch.setattr(runner, "SANDBOX_EXEC", tmp_path / "missing-sandbox-exec")
    with pytest.raises(RuntimeError, match="refusing unsandboxed"):
        await runner.run_command(command("print('never')"), workspace, scratch)
