"""Validated task contracts owned by the parent agent, never rewritten by Step."""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


def relative_file(value: str) -> str:
    p = PurePosixPath(value)
    if (
        not value
        or any(ord(c) < 32 for c in value)
        or p.is_absolute()
        or ".." in p.parts
        or "\\" in value
        or str(p) != value
    ):
        raise ValueError("Use canonical relative file paths without traversal")
    if any(part.startswith(".") for part in p.parts):
        raise ValueError("Hidden files, secrets, and repository metadata are not accepted")
    if p.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}:
        raise ValueError("Credential files are not accepted")
    return value


class CommandSpec(StrictModel):
    name: str = Field(min_length=1, max_length=80, pattern=r"^[a-zA-Z0-9_-]+$")
    argv: list[str] = Field(min_length=1, max_length=64)
    timeout_seconds: float = Field(default=30, gt=0, le=300)

    @field_validator("argv")
    @classmethod
    def clean_argv(cls, values: list[str]) -> list[str]:
        if any("\0" in v for v in values):
            raise ValueError("NUL in command")
        return values


class MetricConstraint(StrictModel):
    metric: str
    op: Literal[">=", "<="]
    value: float


class Budget(StrictModel):
    max_model_turns: int = Field(default=12, ge=1, le=100)
    max_tool_calls: int = Field(default=40, ge=1, le=300)
    max_seconds: float = Field(default=600, ge=5, le=7200)
    max_request_seconds: float = Field(default=300, ge=5, le=600)
    max_output_tokens_per_turn: int = Field(default=16384, ge=256, le=16384)
    max_total_tokens: int = Field(default=250000, ge=1000, le=2000000)
    max_estimated_cost_usd: float = Field(default=1.0, gt=0, le=100)
    max_no_improvement: int = Field(default=4, ge=1, le=20)


class JobSpec(StrictModel):
    source_dir: str
    files: list[str] = Field(min_length=1, max_length=300)
    editable_files: list[str] = Field(min_length=1, max_length=100)
    final_only_files: list[str] = Field(default_factory=list, max_length=100)
    objective: str = Field(min_length=10, max_length=12000)
    checks: list[CommandSpec] = Field(min_length=1, max_length=20)
    benchmark: CommandSpec
    final_checks: list[CommandSpec] = Field(default_factory=list, max_length=20)
    metric: str = Field(default="elapsed_seconds", min_length=1)
    direction: Literal["minimize", "maximize"] = "minimize"
    constraints: list[MetricConstraint] = Field(default_factory=list, max_length=20)
    repetitions: int = Field(default=3, ge=1, le=9)
    minimum_relative_improvement: float = Field(default=0.03, ge=0, lt=1)
    budget: Budget = Field(default_factory=Budget)
    reasoning_effort: Literal["low", "medium", "high"] = "medium"

    @field_validator("files", "editable_files", "final_only_files")
    @classmethod
    def check_paths(cls, values: list[str]) -> list[str]:
        if len(values) != len(set(values)):
            raise ValueError("Duplicate file paths")
        return [relative_file(v) for v in values]

    @model_validator(mode="after")
    def consistent(self) -> JobSpec:
        if not set(self.editable_files) <= set(self.files):
            raise ValueError("editable_files must be a subset of files")
        if not set(self.final_only_files) <= set(self.files) or set(self.final_only_files) & set(
            self.editable_files
        ):
            raise ValueError("final_only_files must be non-editable members of files")
        names = [x.name for x in [*self.checks, self.benchmark, *self.final_checks]]
        if len(names) != len(set(names)):
            raise ValueError("Command names must be unique")
        return self
