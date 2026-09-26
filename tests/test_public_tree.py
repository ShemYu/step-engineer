from __future__ import annotations

import runpy
import subprocess
from pathlib import Path

import pytest

SCANNER = Path(__file__).resolve().parents[1] / "tools" / "check_public_tree.py"
MODULE = runpy.run_path(str(SCANNER))
audit = MODULE["audit"]


def git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    git(tmp_path, "init", "--quiet")
    return tmp_path


def stage(root: Path, name: str, text: str | bytes = "safe public fixture\n") -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode() if isinstance(text, str) else text)
    git(root, "add", "--force", "--", name)
    return path


def categories(root: Path) -> set[str]:
    return {finding.category for finding in audit(root)}


def synthetic_token() -> str:
    # Construct a clearly synthetic signature without embedding one in this source.
    return "sk" + "-" + "notARealCredential" * 3


def test_clean_public_files_and_exact_environment_example(repository):
    stage(repository, "README.md")
    stage(repository, ".env.example", "STEP_" + "API_KEY" + "=\nSTEP_BASE_URL=https://api.stepfun.ai/v1\n")
    stage(repository, "src/step_engineer/_examples/batch_aggregation/job.json", "{}\n")
    assert audit(repository) == []


@pytest.mark.parametrize("value", ["your_key_here", "x", "'#quoted-content'", '"x"'])
def test_environment_example_rejects_even_placeholder_key_values(repository, value):
    stage(repository, ".env.example", "STEP_" + "API_KEY" + "=" + value + "\n")
    assert "example-secret-must-be-empty" in categories(repository)


@pytest.mark.parametrize("value", ["", "# configure locally", '""', "'' # configure locally"])
def test_environment_example_allows_only_empty_secret_values(repository, value):
    stage(repository, ".env.example", "STEP_" + "API_KEY" + "=" + value + "\n")
    assert audit(repository) == []


@pytest.mark.parametrize("name", [
    ".env", ".env.local", "docs/.env.example", "runs/result.json",
    "experiments/source.py", ".venv/pyvenv.cfg", "cache/value.txt",
    "src/__pycache__/cache.pyc", "api-check.json", "verification.json",
    "verification/result.json",
    "docs/video.mov", "backup.tar.gz", "credentials.json", "private.key",
])
def test_forbidden_staged_paths(repository, name):
    stage(repository, name)
    assert audit(repository)


def test_forbidden_environment_is_rejected_before_read(repository, monkeypatch):
    stage(repository, ".env.local", synthetic_token())
    original = MODULE["_git"]

    def forbid_blob_reads(root, *args):
        assert "cat-file" not in args
        return original(root, *args)

    # The function's globals are the dictionary populated by run_path.
    monkeypatch.setitem(audit.__globals__, "_git", forbid_blob_reads)
    monkeypatch.setitem(audit.__globals__, "_working_copy", lambda *_: pytest.fail("read env"))
    assert categories(repository) == {"environment-file"}


def test_untracked_local_data_is_not_scanned(repository):
    stage(repository, "README.md")
    (repository / ".env.local").write_text(synthetic_token())
    (repository / "private.txt").write_text(synthetic_token())
    assert audit(repository) == []


def test_staged_secret_is_found_when_working_copy_is_sanitized(repository):
    path = stage(repository, "notes.txt", synthetic_token())
    path.write_text("safe after staging\n")
    assert "credential-pattern" in categories(repository)


def test_unstaged_secret_in_tracked_file_is_found(repository):
    path = stage(repository, "notes.txt")
    path.write_text(synthetic_token())
    assert "credential-pattern" in categories(repository)


@pytest.mark.parametrize("private_path", [
    "/" + "Users" + "/sample-person/project",
    "/" + "home" + "/sample-person/project",
    "~" + "/personal-project",
    "C:" + "\\Users\\sample-person\\project",
])
def test_private_home_paths(repository, private_path):
    stage(repository, "notes.txt", private_path)
    assert "private-home-path" in categories(repository)


@pytest.mark.parametrize("value", [
    "xai" + "-" + "synthetic" * 5,
    "gh" + "p_" + "synthetic" * 5,
    "github" + "_pat_" + "synthetic" * 5,
    "AK" + "IA" + "A" * 16,
    "-----BEGIN " + "PRIVATE KEY-----",
    "SERVICE_" + "API_KEY=" + "arbitrary-assignment-value",
])
def test_credential_signatures(repository, value):
    stage(repository, "notes.txt", value)
    assert categories(repository) & {"credential-pattern", "credential-assignment"}


def test_python_credential_expressions_are_not_literal_secrets(repository):
    key_name = "api" + "_key"
    source = (
        f"{key_name} = candidate_key\n"
        f"client({key_name}=candidate_key)\n"
        f"client({key_name}=os.getenv('SETTING'))\n"
        f"self._{key_name} = candidate_key\n"
        f"settings = {{'{key_name}': candidate_key}}\n"
    )
    stage(repository, "expressions.py", source)
    assert audit(repository) == []


@pytest.mark.parametrize("form", [
    "{key} = {value!r}",
    "{key}: str = {value!r}",
    "self._{key} = {value!r}",
    "client({key}={value!r})",
    "settings = {{'{key}': {value!r}}}",
])
def test_python_credential_literals_still_fail(repository, form):
    source = form.format(key="api" + "_key", value="synthetic-arbitrary-value") + "\n"
    stage(repository, "literals.py", source)
    assert "credential-assignment" in categories(repository)


def test_python_placeholder_never_masks_provider_token_signature(repository):
    value = "example_" + synthetic_token()
    stage(repository, "literals.py", "api" + f"_key = {value!r}\n")
    assert "credential-pattern" in categories(repository)


def test_binary_and_non_utf8_data(repository):
    stage(repository, "data.txt", b"public\x00binary")
    stage(repository, "other.txt", bytes([255, 254]))
    assert categories(repository) == {"binary-content", "non-utf8-content"}


def test_tracked_symlink_is_not_followed(repository):
    target = repository / "private-local.txt"
    target.write_text(synthetic_token())
    (repository / "reference.txt").symlink_to(target)
    git(repository, "add", "reference.txt")
    assert categories(repository) == {"symlink-or-submodule"}


def test_symlink_replacement_in_working_tree_is_not_followed(repository):
    path = stage(repository, "notes.txt")
    path.unlink()
    path.symlink_to(repository / "does-not-exist")
    assert categories(repository) == {"symlink-in-working-tree"}


def test_report_redacts_matched_values(repository, capsys):
    secret = synthetic_token()
    stage(repository, "notes.txt", secret)
    assert MODULE["main"](["--root", str(repository)]) == 1
    output = capsys.readouterr().out
    assert "notes.txt" in output and "credential-pattern" in output
    assert secret not in output


def test_scanner_source_and_tests_do_not_trigger_themselves(repository):
    stage(repository, "tools/check_public_tree.py", SCANNER.read_text())
    stage(repository, "tests/test_public_tree.py", Path(__file__).read_text())
    assert audit(repository) == []


def test_empty_index_fails_closed(repository, capsys):
    assert MODULE["main"](["--root", str(repository)]) == 2
    assert "valid Git index" in capsys.readouterr().err
