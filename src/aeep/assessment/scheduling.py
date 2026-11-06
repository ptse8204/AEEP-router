"""Reviewed scheduling adapters cannot replace canonical trial execution."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Literal, Protocol

from pydantic import Field, model_validator

from ..benchmarking import BenchmarkTrial
from ..errors import ConfigurationError
from ..models import ExecutorSpec, SideEffect, StrictModel
from .identity import verify_dependencies
from .models import Digest, content_digest
from .repository import AssessmentRepository

SKILLRANK_DIAGNOSTIC = "skillrank.controlled-diagnostic.v1"


class SchedulerDefinition(StrictModel):
    schema_version: Literal["assessment.scheduler.v1"] = "assessment.scheduler.v1"
    adapter_id: str = Field(min_length=1, max_length=100)
    source_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    artifact_sha256: Digest
    executable_dependencies: dict[str, Digest] = Field(min_length=1, max_length=2048)
    executor: ExecutorSpec
    workspace: str = Field(min_length=1, max_length=4096)
    runtime_root: str = Field(min_length=1, max_length=4096)
    runtime_tree_digest: Digest
    boundary_profile: str = Field(min_length=1, max_length=4096)
    overhead_seconds: int = Field(strict=True, ge=1, le=600)
    maximum_requests: int = Field(strict=True, ge=1, le=6)

    @model_validator(mode="after")
    def bounded_command(self) -> SchedulerDefinition:
        from pathlib import Path

        config = self.executor.config
        env = config.get("env", {})
        if (
            self.executor.kind.value != "command"
            or config.get("shell")
            or config.get("inherit_env")
            or config.get("argv_literal") is not True
            or config.get("stdin_json") is not True
            or config.get("cwd") != self.workspace
            or config.get("output") != {"type": "jsonl", "match": {"kind": "done"}}
            or Path(self.workspace).is_absolute() is False
            or self.boundary_profile not in self.executable_dependencies
            or not isinstance(config.get("argv"), list)
            or config["argv"][:3] != ["/usr/bin/sandbox-exec", "-f", self.boundary_profile]
            or type(config.get("max_output_bytes")) is not int
            or not 1 <= config["max_output_bytes"] <= 1048576
            or self.executor.side_effect.rank > SideEffect.WRITE.rank
            or self.executor.requires_network
            or not isinstance(env, dict)
            or set(env)
            - {
                "PATH",
                "HOME",
                "TMPDIR",
                "PYTHONDONTWRITEBYTECODE",
                "PYTHONNOUSERSITE",
                "LC_ALL",
                "LANG",
            }
            or any(not isinstance(value, str) or "${" in value for value in env.values())
            or env.get("HOME") != str(Path(self.workspace) / "home")
            or env.get("TMPDIR") != str(Path(self.workspace) / "tmp")
            or not isinstance(config.get("timeout_seconds"), (float, int))
            or not 0 < float(config["timeout_seconds"]) <= 86400
        ):
            raise ValueError(
                "scheduler requires a finite reviewed sandbox command and owned workspace"
            )
        if self.adapter_id == SKILLRANK_DIAGNOSTIC and self.maximum_requests != 2:
            raise ValueError("SkillRank requires exactly two diagnostic slots")
        return self


class TrialCoordinator(Protocol):
    definition_digest: str

    async def coordinate(
        self, trial_ids: tuple[str, ...], execute: Callable[[str], Awaitable[BenchmarkTrial | None]]
    ) -> None: ...


def require_scheduler(repository: AssessmentRepository, reference: str) -> SchedulerDefinition:
    definition = SchedulerDefinition.model_validate(repository.get("scheduler", reference))
    with repository.store._lock:
        row = repository.store._connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (reference,)
        ).fetchone()
    if content_digest(definition) != reference or row is None or row[0]:
        raise ConfigurationError("scheduler definition is changed, unreviewed or revoked")
    verify_dependencies(definition.executable_dependencies)
    return definition
