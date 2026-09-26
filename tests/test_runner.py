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


def scratch_payload(kind: str, amount: int) -> str:
    if kind == "bytes":
        # Aggregate two files, each within the separate hard per-file limit.
        return (
            "from pathlib import Path; root=Path('{scratch}'); "
            f"(root/'a').write_bytes(b'x'*{amount // 2}); "
            f"(root/'b').write_bytes(b'x'*{amount - amount // 2}); "
        )
    # HOME and TMP are two entries created by the runner before command execution.
    return (
        "from pathlib import Path; root=Path('{scratch}'); "
        f"[(root/str(i)).touch() for i in range({amount - 2})]; "
    )


@pytest.mark.parametrize("kind,limit", [("bytes", 1024), ("entries", 8)])
@pytest.mark.parametrize("offset", [-1, 0, 1])
@pytest.mark.parametrize("delayed", [False, True], ids=["fast", "running"])
async def test_aggregate_storage_boundaries(tmp_path, monkeypatch, kind, limit, offset, delayed):
    workspace, scratch = paths(tmp_path)
    setting = "MAX_SCRATCH_BYTES" if kind == "bytes" else "MAX_SCRATCH_ENTRIES"
    monkeypatch.setattr(runner, setting, limit)
    code = scratch_payload(kind, limit + offset)
    if delayed:
        code += "import time; time.sleep(0.15)"

    result = await runner.run_command(command(code), workspace, scratch)

    assert result["storage_limit_exceeded"] is (offset > 0), result
    assert not result["timed_out"], result
    assert not result["output_limit_exceeded"], result
    if offset <= 0:
        assert result["exit_code"] == 0, result
        assert "Scratch storage limit exceeded" not in result["stderr"]
    else:
        assert "Scratch storage limit exceeded" in result["stderr"]


@pytest.mark.parametrize("kind,limit", [("bytes", 1024), ("entries", 8)])
async def test_completed_command_is_checked_after_cleanup(tmp_path, monkeypatch, kind, limit):
    workspace, scratch = paths(tmp_path)
    setting = "MAX_SCRATCH_BYTES" if kind == "bytes" else "MAX_SCRATCH_ENTRIES"
    monkeypatch.setattr(runner, setting, limit)
    inspect_scratch = runner._scratch_over_limit
    kill_group = runner._kill_group
    cleaned = False

    def cleanup(process):
        nonlocal cleaned
        kill_group(process)
        cleaned = True

    def inspect_after_cleanup(root):
        # Deterministically model writes landing between the final running poll
        # and process completion, independent of host scheduling speed. The
        # actual child still runs under the real macOS sandbox and writes files.
        return inspect_scratch(root) if cleaned else False

    monkeypatch.setattr(runner, "_kill_group", cleanup)
    monkeypatch.setattr(runner, "_scratch_over_limit", inspect_after_cleanup)

    result = await runner.run_command(command(scratch_payload(kind, limit + 1)), workspace, scratch)

    assert cleaned
    assert result["exit_code"] == 0, result
    assert not result["timed_out"], result
    assert result["storage_limit_exceeded"], result
    assert "Scratch storage limit exceeded" in result["stderr"]


async def test_no_unsandboxed_fallback(tmp_path, monkeypatch):
    workspace, scratch = paths(tmp_path)
    monkeypatch.setattr(runner, "SANDBOX_EXEC", tmp_path / "missing-sandbox-exec")
    with pytest.raises(RuntimeError, match="refusing unsandboxed"):
        await runner.run_command(command("print('never')"), workspace, scratch)


@pytest.mark.parametrize("use_alias", [False, True])
def test_framework_runtime_allows_exact_shared_library_without_broadening(
    tmp_path, monkeypatch, use_alias
):
    framework_root = tmp_path / "Library" / "Frameworks"
    version = framework_root / "Python.framework" / "Versions" / "3.12"
    version.mkdir(parents=True)
    (version / "Python").write_bytes(b"synthetic shared library")
    prefix = version
    if use_alias:
        prefix = version.parent / "Current"
        prefix.symlink_to(version, target_is_directory=True)
    monkeypatch.setattr(runner.sys, "base_prefix", str(prefix))
    monkeypatch.setattr(
        runner.sysconfig, "get_config_var",
        lambda key: "Python" if key == "PYTHONFRAMEWORK" else None,
    )

    trees, exact = runner._runtime_paths()

    assert prefix / "Python" in exact
    assert version / "Python" in exact
    assert not any((version / "Python").is_relative_to(tree) for tree in trees)
    assert framework_root not in trees
    assert framework_root.parent not in trees
    assert Path.home() not in trees
    profile = runner._profile(tmp_path / "workspace", tmp_path / "scratch", Path(sys.executable))
    assert f'(literal "{version / "Python"}")' in profile
    assert f'(subpath "{framework_root}")' not in profile


def test_standalone_runtime_does_not_grant_framework_library(tmp_path, monkeypatch):
    monkeypatch.setattr(runner.sys, "base_prefix", str(tmp_path / "standalone"))
    monkeypatch.setattr(runner.sysconfig, "get_config_var", lambda _: "")
    _, exact = runner._runtime_paths()
    assert tmp_path / "standalone" / "Python" not in exact
