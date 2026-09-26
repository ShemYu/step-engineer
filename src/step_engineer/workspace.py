"""Explicit, bounded source snapshots; optimization never writes the original project."""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
from pathlib import Path

from .models import JobSpec, relative_file

MAX_FILE_BYTES = 1_000_000
MAX_SOURCE_BYTES = 12_000_000


def write_json(path: Path, value: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    os.replace(temp, path)


def source_file(root: Path, name: str) -> Path:
    relative_file(name)
    p = root
    for part in Path(name).parts:
        p = p / part
        if p.is_symlink():
            raise ValueError(f"Symlinks are not allowed: {name}")
    if not p.is_file() or not p.resolve().is_relative_to(root):
        raise ValueError(f"Not a regular source file: {name}")
    return p


def copy_tree(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)


class Workspace:
    def __init__(self, spec: JobSpec, run_dir: Path):
        self.spec = spec
        self.run_dir = run_dir
        self.root = run_dir / "candidate"
        self.baseline = run_dir / "baseline"
        self.best = run_dir / "best"
        self.private = run_dir / "final-only"
        self.visible = sorted(set(spec.files) - set(spec.final_only_files))
        self.protected_hashes: dict[str, str] = {}
        self.source_hashes: dict[str, str] = {}

    def prepare(self) -> None:
        source = Path(self.spec.source_dir).expanduser().resolve(strict=True)
        if not source.is_dir():
            raise ValueError("source_dir must be a directory")
        self.root.mkdir(parents=True)
        self.private.mkdir()
        total = 0
        for name in self.spec.files:
            p = source_file(source, name)
            if p.stat().st_size > MAX_FILE_BYTES:
                raise ValueError(f"File exceeds 1 MB: {name}")
            with p.open("rb") as f:
                raw = f.read(MAX_FILE_BYTES + 1)
            total += len(raw)
            if len(raw) > MAX_FILE_BYTES or total > MAX_SOURCE_BYTES:
                raise ValueError("Source snapshot exceeds size limit")
            raw.decode("utf-8")
            if b"\0" in raw:
                raise ValueError(f"Binary file not supported: {name}")
            destination = (self.private if name in self.spec.final_only_files else self.root) / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(raw)
            digest = hashlib.sha256(raw).hexdigest()
            self.source_hashes[name] = digest
            if name in self.visible and name not in self.spec.editable_files:
                self.protected_hashes[name] = digest
        copy_tree(self.root, self.baseline)
        copy_tree(self.root, self.best)
        write_json(self.run_dir / "source-manifest.json", self.source_hashes)

    def path(self, name: str, *, writable: bool = False) -> Path:
        relative_file(name)
        if name not in (self.spec.editable_files if writable else self.visible):
            raise ValueError("File is not in the permitted file list")
        return source_file(self.root, name)

    def read(self, path: str, start_line: int = 1, max_lines: int = 160) -> dict:
        name = path
        if isinstance(start_line, bool) or not isinstance(start_line, int) or start_line < 1:
            raise ValueError("start_line must be a positive integer")
        if (
            isinstance(max_lines, bool)
            or not isinstance(max_lines, int)
            or not 1 <= max_lines <= 300
        ):
            raise ValueError("max_lines must be 1..300")
        lines = self.path(name).read_text().splitlines()
        text = "\n".join(
            f"{i + 1}: {lines[i]}"
            for i in range(start_line - 1, min(len(lines), start_line - 1 + max_lines))
        )
        return {"path": name, "total_lines": len(lines), "content": text[:24000]}

    def write(self, path: str, content: str) -> dict:
        name = path
        if (
            not isinstance(content, str)
            or len(content.encode()) > MAX_FILE_BYTES
            or "\0" in content
        ):
            raise ValueError("Content must be UTF-8 text under 1 MB")
        p = self.path(name, writable=True)
        p.write_text(content)
        return {"path": name, "bytes": p.stat().st_size}

    def integrity(self, root: Path | None = None) -> bool:
        root = root or self.root
        try:
            return all(
                hashlib.sha256(source_file(root, name).read_bytes()).hexdigest() == digest
                for name, digest in self.protected_hashes.items()
            )
        except (OSError, ValueError):
            return False

    def save_best(self) -> None:
        copy_tree(self.root, self.best)

    def restore_best(self) -> None:
        copy_tree(self.best, self.root)

    def validation_workspace(self, source: Path) -> Path:
        target = self.run_dir / "validation"
        copy_tree(source, target)
        for name in self.spec.final_only_files:
            p = target / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes((self.private / name).read_bytes())
        return target

    def patch(self, use_best: bool) -> str:
        chunks = []
        selected = self.best if use_best else self.baseline
        for name in sorted(self.spec.editable_files):
            before = (self.baseline / name).read_text().splitlines(keepends=True)
            after = (selected / name).read_text().splitlines(keepends=True)
            # Unified patches require explicit markers for unterminated final lines.
            for line in difflib.unified_diff(
                before, after, fromfile="a/" + name, tofile="b/" + name
            ):
                if line.endswith("\n"):
                    chunks.append(line)
                else:
                    chunks.append(line + "\n\\ No newline at end of file\n")
        return "".join(chunks)
