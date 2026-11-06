"""Run a single diagnostic pair through the pinned SkillRank callback bridge."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from aeep.assessment.identity import protected_directory
from aeep.assessment.models import AssessmentSubject, ReviewedMapping, content_digest
from aeep.assessment.scheduling import SKILLRANK_DIAGNOSTIC
from aeep.benchmarking import BenchmarkTrial
from aeep.errors import ConfigurationError

from .ase_scheduler import ControlledScheduler
from .candidate import inspect
from .install_runtime import canonical

REVISION = "5216bae9149b4ff8a7f9e014b6889fb094cee8e1"
SANDBOX = "/usr/bin/sandbox-exec"
BINARY_NAME = "aeep-skillrank-bridge"
ARMS = ("control", "treatment")
CASE_SLOT = "aeep-case"


def boundary_profile(runtime: Path, workspace: Path) -> str:
    """Read only the pinned runtime and parent-issued certificates."""
    binary = runtime / "bin" / BINARY_NAME
    metadata = sorted({*runtime.parents, *workspace.parents, workspace})
    directories = ("/System", "/usr/lib", str(runtime), str(workspace / "responses"))
    return "\n".join([
        "(version 1)", "(allow default)", "(deny network*)",
        "(deny file-write*)", '(allow file-write* (literal "/dev/null"))',
        "(deny file-read*)",
        '(allow file-read-data (literal "/"))',  # macOS dyld bootstraps from the root entry.
        "(allow file-read* " + " ".join(f"(subpath {json.dumps(path)})" for path in directories) + ")",
        '(allow file-read* (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))',
        "(allow file-read-metadata "
        + " ".join(f"(literal {json.dumps(str(path))})" for path in metadata) + ")",
        "(deny process-exec)", f"(allow process-exec (literal {json.dumps(str(binary))}))",
        "",
    ])


class SkillRankCoordinator(ControlledScheduler):
    grading_semantics = "SkillRank verdict over the existing protected task-grade certificate"

    def validate_definition(self) -> None:
        definition = self.definition
        runtime = canonical(definition.runtime_root)
        workspace = canonical(definition.workspace)
        binary = str(runtime / "bin" / BINARY_NAME)
        config = definition.executor.config
        if (
            self.plan.schema_version != "assessment.plan.v9"
            or definition.adapter_id != SKILLRANK_DIAGNOSTIC
            or definition.source_revision != REVISION
            or definition.maximum_requests != 2
            or protected_directory(runtime)
            or protected_directory(workspace)
            or workspace == runtime
            or workspace.is_relative_to(runtime)
            or runtime.is_relative_to(workspace)
            or config["argv"] != [SANDBOX, "-f", definition.boundary_profile, binary]
            or definition.executable_dependencies.get(binary) != definition.artifact_sha256
            or SANDBOX not in definition.executable_dependencies
            or Path(definition.boundary_profile).read_text() != boundary_profile(runtime, workspace)
            or not 4 <= config["timeout_seconds"] <= 600
        ):
            raise ConfigurationError("scheduler differs from the bounded SkillRank diagnostic")

    def require_runtime(self) -> None:
        runtime = canonical(self.definition.runtime_root)
        bin_dir = runtime / "bin"
        if (not bin_dir.is_dir() or bin_dir.is_symlink()
                or {path.name for path in runtime.iterdir()} != {"bin"}
                or {path.name for path in bin_dir.iterdir()} != {BINARY_NAME}):
            raise ConfigurationError("SkillRank runtime must contain only the reviewed bridge")
        super().require_runtime()

    def prepare_payload(
        self, workspace: Path, trial_ids: tuple[str, ...], token: str
    ) -> dict[str, object]:
        if trial_ids != ("0", "1"):
            raise ConfigurationError("SkillRank requires a single control and treatment")
        subject = AssessmentSubject.model_validate(
            self.repository.get("subject", self.plan.subject_digest)
        )
        candidate = inspect(Path(subject.location))
        mapping = ReviewedMapping.model_validate(
            self.repository.get("mapping", self.plan.mapping_digest)
        )
        invocation = mapping.candidate.managed_host_config().invocation
        name = invocation.skill_name if invocation and invocation.mode == "skill" else None
        if (
            candidate.describe()["files"] != subject.dependency_digests
            or not name
            or re.fullmatch(r"[a-z0-9-]{1,80}", name) is None
        ):
            raise ConfigurationError("SkillRank requires the reviewed primary skill snapshot")
        return {
            "case_id": CASE_SLOT,
            "skill_slug": name,
            "skill_sha256": candidate.sha256,
            "run_token": token,
            "timeout_seconds": min(60, int(self.definition.executor.config["timeout_seconds"]) // 2),
        }

    def requested_slot(self, message: dict[str, Any], token: str) -> str:
        if (
            set(message) != {"kind", "case_id", "run_token", "arm"}
            or message["kind"] != "trial"
            or message["case_id"] != CASE_SLOT
            or message["run_token"] != token
            or message["arm"] not in ARMS
        ):
            raise ConfigurationError("SkillRank requested an unreviewed trial")
        return str(ARMS.index(message["arm"]))

    def certificate(self, slot: str, trial: BenchmarkTrial, token: str) -> tuple[str, dict[str, Any]]:
        position = int(slot)
        route = (self.plan.baseline_id, self.plan.candidate_id)[position]
        if (
            trial.route_id != route
            or trial.case_id != self.plan.suite.cases[0].case_id
            or trial.condition != self.plan.suite.conditions[0]
            or trial.repetition != 0
        ):
            raise ConfigurationError("SkillRank certificate differs from the canonical trial slot")
        arm = ARMS[position]
        return arm, {
            "case_id": CASE_SLOT,
            "arm": arm,
            "run_token": token,
            "trial_ref": content_digest(trial),
            "canonical_valid": trial.valid,
        }

    def validate_completion(
        self, output: object, trials: dict[str, BenchmarkTrial], token: str
    ) -> dict[str, dict[str, int | float]]:
        expected = {
            "kind": "done",
            "run_token": token,
            "harness": "skillrank-runner",
            "harness_version": "0.1.0",
            "upstream_numeric_fields_excluded": True,
            "trials": [
                {"arm": arm, "trial_ref": content_digest(trials[str(index)]),
                 "canonical_valid": trials[str(index)].valid}
                for index, arm in enumerate(ARMS)
            ],
        }
        if (
            not isinstance(output, dict)
            or output != expected
            or output["upstream_numeric_fields_excluded"] is not True
            or any(type(row["canonical_valid"]) is not bool for row in output["trials"])
        ):
            raise ConfigurationError("SkillRank verdict differs from the protected grades")
        return {
            slot: {"passed": int(trial.valid is True), "failed": int(trial.valid is False),
                   "total": 1, "pass_rate": float(trial.valid is True), "skipped": 0}
            for slot, trial in trials.items()
        }
