import pytest

from step_engineer.models import JobSpec, relative_file
from step_engineer.workspace import Workspace


def make_spec(root):
    return JobSpec(
        source_dir=str(root),
        files=["source.py", "check.py", "hidden.py"],
        editable_files=["source.py"],
        final_only_files=["hidden.py"],
        objective="Improve speed with equivalent output",
        checks=[{"name": "correct", "argv": ["{python}", "check.py"]}],
        benchmark={"name": "speed", "argv": ["{python}", "source.py"]},
    )


def test_snapshot_and_final_only(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for name in ["source.py", "check.py", "hidden.py"]:
        (src / name).write_text("original\n")
    ws = Workspace(make_spec(src), tmp_path / "run")
    ws.prepare()
    assert not (ws.root / "hidden.py").exists()
    with pytest.raises(ValueError):
        ws.read("hidden.py")
    with pytest.raises(ValueError):
        ws.write("check.py", "tampered")
    ws.write("source.py", "modified\n")
    ws.save_best()
    assert (src / "source.py").read_text() == "original\n"
    assert (ws.validation_workspace(ws.best) / "hidden.py").read_text() == "original\n"
    assert "+modified" in ws.patch(True)
    assert not ws.patch(False)


@pytest.mark.parametrize(
    "name", ["../x", "/tmp/x", ".env", "a/.git/config", "a/../b", "a\\b", "x.pem", "a\nb"]
)
def test_paths_rejected(name):
    with pytest.raises(ValueError):
        relative_file(name)


def test_symlink_rejected(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (tmp_path / "outside").write_text("private")
    (src / "source.py").symlink_to(tmp_path / "outside")
    (src / "check.py").write_text("")
    (src / "hidden.py").write_text("")
    with pytest.raises(ValueError):
        Workspace(make_spec(src), tmp_path / "run").prepare()
