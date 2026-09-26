"""Audit tracked publication content without inspecting untracked local data.

Both staged blobs and tracked working copies are checked. Forbidden paths are
rejected before their contents are read. Findings never include matched values.
This is a release guardrail, not a complete replacement for human secret review.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import stat
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import NamedTuple

MAX_FILE_BYTES = 2 * 1024 * 1024
MAX_TRACKED_FILES = 5000
LOCAL_PARTS = {
    "runs", "experiments", "work", "cache", ".cache", ".venv", "venv",
    "__pycache__", ".pytest_cache", ".ruff_cache", ".mypy_cache", ".tox", ".nox",
    "node_modules", "dist", "build", ".coverage", "htmlcov",
}
BINARY_SUFFIXES = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".heic", ".tiff", ".ico",
    ".mp4", ".mov", ".mkv", ".avi", ".mp3", ".wav", ".m4a", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z", ".rar", ".whl",
    ".pdf", ".dmg", ".pkg", ".exe", ".dll", ".so", ".dylib", ".pyc",
    ".sqlite", ".sqlite3", ".db", ".pkl", ".pickle", ".npy", ".npz",
}
PRIVATE_PATH_PATTERNS = [
    re.compile(r"/(?:Users|home)/[^\s/<>\"']+"),
    re.compile(r"\b[A-Za-z]:[\\/](?:Users|Documents and Settings)[\\/]"),
    re.compile(r"~[/\\]"),
    re.compile(r"/private/var/(?:folders|root)/"),
]
CREDENTIAL_PATTERNS = [
    re.compile(r"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?<![A-Za-z0-9])xai-[A-Za-z0-9_-]{16,}"),
    re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}"),
    re.compile(r"(?<![A-Za-z0-9])github_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}\.[A-Za-z0-9_-]{12,}"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.-]{24,}"),
]
ASSIGNMENT = re.compile(
    r"(?im)\b(?:[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|CLIENT_SECRET|PASSWORD))"
    r"[\"']?[ \t]*[:=][ \t]*[\"']?([^\s\"'`,;#}]+)"
)
SECRET_NAME = re.compile(
    r"(?i)[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|CLIENT_SECRET|PASSWORD)"
)


class Finding(NamedTuple):
    path: str
    category: str


class AuditError(RuntimeError):
    """A safe, categorical error without subprocess output or file contents."""


def _git(root: Path, *args: str) -> bytes:
    result = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, check=False
    )
    if result.returncode:
        raise AuditError("git-read-failed")
    return result.stdout


def _path_category(name: str) -> str | None:
    path = PurePosixPath(name)
    parts = tuple(part.lower() for part in path.parts)
    base = path.name.lower()
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        return "unsafe-path"
    if name != ".env.example" and any(
        part == ".env" or part.startswith(".env.") or part == ".envrc" for part in parts
    ):
        return "environment-file"
    if set(parts) & LOCAL_PARTS or any(part.endswith(".egg-info") for part in parts):
        return "local-artifact"
    if any(part.startswith(("api-check", "api_check", "verification")) for part in parts) or base == ".ds_store":
        return "local-verification-artifact"
    if base in {"credentials", "credentials.json", "secrets.json", "id_rsa", "id_ed25519"}:
        return "credential-file"
    if path.suffix.lower() in {".pem", ".key", ".p12", ".pfx", ".keystore"}:
        return "credential-file"
    if path.suffix.lower() in BINARY_SUFFIXES:
        return "binary-media-or-archive"
    return None


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        value.startswith(("${", "$", "<"))
        or lowered in {"none", "null", "false", "true"}
        or lowered.startswith(("your_", "your-", "replace_", "replace-", "example_", "example-"))
    )


def _empty_example_value(value: str) -> bool:
    value = value.strip()
    if not value or value.startswith("#"):
        return True
    for empty_quote in ('""', "''"):
        if value.startswith(empty_quote):
            remainder = value[len(empty_quote):].lstrip()
            return not remainder or remainder.startswith("#")
    return False


def _literal_credential_values(text: str, name: str) -> list[str]:
    """Python names/calls are expressions, not credential values stored in source."""
    if PurePosixPath(name).suffix != ".py":
        return [match.group(1) for match in ASSIGNMENT.finditer(text)]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        # A broken Python file must not make secret scanning fail open.
        return [match.group(1) for match in ASSIGNMENT.finditer(text)]
    values = []

    def inspect(key: str | None, value: ast.expr) -> None:
        if (key and SECRET_NAME.fullmatch(key) and isinstance(value, ast.Constant)
                and isinstance(value.value, str)):
            values.append(value.value)

    for node in ast.walk(tree):
        if isinstance(node, ast.keyword):
            inspect(node.arg, node.value)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if node.value is not None:
                for target in targets:
                    key = target.id if isinstance(target, ast.Name) else (
                        target.attr if isinstance(target, ast.Attribute) else None
                    )
                    inspect(key, node.value)
        elif isinstance(node, ast.Dict):
            for key, value in zip(node.keys, node.values):
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    inspect(key.value, value)
    return values


def _content_categories(raw: bytes, name: str = "") -> set[str]:
    if len(raw) > MAX_FILE_BYTES:
        return {"oversized-file"}
    if b"\0" in raw:
        return {"binary-content"}
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        return {"non-utf8-content"}
    categories = set()
    if name == ".env.example":
        for line in text.splitlines():
            key, separator, value = line.partition("=")
            if separator and re.fullmatch(
                r"\s*(?:export\s+)?[A-Z0-9_]*(?:API_KEY|ACCESS_TOKEN|SECRET_KEY|CLIENT_SECRET|PASSWORD)\s*",
                key,
            ) and not _empty_example_value(value):
                categories.add("example-secret-must-be-empty")
    if any(pattern.search(text) for pattern in PRIVATE_PATH_PATTERNS):
        categories.add("private-home-path")
    if any(pattern.search(text) for pattern in CREDENTIAL_PATTERNS):
        categories.add("credential-pattern")
    for value in _literal_credential_values(text, name):
        if len(value) >= 8 and not _is_placeholder(value):
            categories.add("credential-assignment")
    return categories


def _working_copy(root: Path, name: str) -> bytes | None:
    target = root
    for part in PurePosixPath(name).parts:
        target /= part
        if target.is_symlink():
            raise AuditError("symlink-in-working-tree")
    try:
        metadata = target.stat()
    except FileNotFoundError:
        return None  # The staged blob is still audited for an unstaged deletion.
    if not stat.S_ISREG(metadata.st_mode):
        raise AuditError("non-regular-working-file")
    if metadata.st_size > MAX_FILE_BYTES:
        raise AuditError("oversized-file")
    with target.open("rb") as handle:
        return handle.read(MAX_FILE_BYTES + 1)


def audit(root: Path) -> list[Finding]:
    """Return safe findings for the index and tracked files; never scan untracked files."""
    root = root.resolve(strict=True)
    git_root = Path(_git(root, "rev-parse", "--show-toplevel").decode().strip()).resolve()
    if root != git_root:
        raise AuditError("run-at-git-root")
    entries = _git(root, "ls-files", "--stage", "-z").split(b"\0")
    if len(entries) - 1 > MAX_TRACKED_FILES:
        raise AuditError("too-many-tracked-files")
    if not any(entries):
        raise AuditError("empty-index")
    findings: set[Finding] = set()
    for entry in entries:
        if not entry:
            continue
        metadata, name_bytes = entry.split(b"\t", 1)
        mode, object_id, stage = metadata.decode("ascii").split()
        name = name_bytes.decode("utf-8", errors="surrogateescape")
        category = _path_category(name)
        if category:
            findings.add(Finding(name, category))
            continue  # Especially: never open a forbidden environment/credential file.
        if stage != "0":
            findings.add(Finding(name, "unmerged-index"))
            continue
        if mode not in {"100644", "100755"}:
            findings.add(Finding(name, "symlink-or-submodule"))
            continue
        size = int(_git(root, "cat-file", "-s", object_id))
        if size > MAX_FILE_BYTES:
            findings.add(Finding(name, "oversized-file"))
            continue
        staged = _git(root, "cat-file", "blob", object_id)
        for category in _content_categories(staged, name):
            findings.add(Finding(name, category))
        try:
            working = _working_copy(root, name)
        except AuditError as exc:
            findings.add(Finding(name, str(exc)))
            continue
        if working is not None and working != staged:
            for category in _content_categories(working, name):
                findings.add(Finding(name, category))
    return sorted(findings)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    arguments = parser.parse_args(argv)
    try:
        findings = audit(arguments.root)
    except (AuditError, OSError, ValueError):
        print("Public-tree audit could not read a valid Git index.", file=sys.stderr)
        return 2
    for finding in findings:
        print(f"{json.dumps(finding.path, ensure_ascii=True)}: {finding.category}")
    if findings:
        return 1
    print("Public-tree audit passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
