from __future__ import annotations

import json
import sys

import pytest

from step_engineer import cli


@pytest.mark.parametrize("explicit", [False, True])
def test_run_artifacts_use_cwd_or_explicit_directory(tmp_path, monkeypatch, capsys, explicit):
    """Installing a wheel must never make CLI artifacts default to site-packages."""
    monkeypatch.chdir(tmp_path)
    captured = {}

    async def fake_run(args):
        captured["runs_dir"] = args.runs_dir
        return {"status": "improved"}

    monkeypatch.setattr(cli, "run_job", fake_run)
    argv = ["step-engineer"]
    if explicit:
        argv += ["--runs-dir", str(tmp_path / "chosen-artifacts")]
    monkeypatch.setattr(sys, "argv", [*argv, "run", "job.json"])
    cli.main()
    expected = tmp_path / ("chosen-artifacts" if explicit else "runs")
    assert captured["runs_dir"] == str(expected)
    assert json.loads(capsys.readouterr().out) == {"status": "improved"}
