"""Resolve a fresh launcher boundary observation for a retained ASE run."""

from __future__ import annotations

import json
from pathlib import Path

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import SchedulerDefinition
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence
from aeep.models import ExecutorSpec, StrictModel

from .install_runtime import snapshot
from .models import Digest
from .stack_readiness import _resolve
from .workflow import WorkflowFile
from .workflow_evidence import OperationLink, _file, _receipt

SANDBOX = "/usr/bin/sandbox-exec"
REQUIRED_OBSERVATIONS = {
    "outside_read_denied",
    "outside_write_denied",
    "response_write_denied",
    "candidate_write_denied",
    "network_denied",
    "local_git_initialization",
}


class SchedulerBoundaryEvidence(StrictModel):
    review: WorkflowFile
    definition_ref: Digest
    receipt: OperationLink


def require_ase_boundary(
    repo: AssessmentRepository,
    scheduler_ref: str,
    evidence: SchedulerBoundaryEvidence,
) -> SchedulerDefinition:
    """Validate historical receipt compatibility without changing live scheduler validation."""
    scheduler = _resolve(repo, "scheduler", scheduler_ref, SchedulerDefinition, reviewed=True)
    review = json.loads(_file(evidence.review))
    entry = review["agent_skill_eval"]
    if (
        review["schema_version"] != "aeep.operator.toolkit-ase-native-repeat.v1"
        or review["model_turns"] != 0
        or review["maximum_cash_usd"] != 0
        or review["maximum_additional_operations"] != 1
        or entry["historical_definition_ref"] != scheduler_ref
        or entry["operation_id"] != evidence.receipt.operation_id
        or entry["runtime_tree_sha256"] != scheduler.runtime_tree_digest
        or set(entry["executable_change"]) != {SANDBOX}
    ):
        raise ConfigurationError("native boundary review does not bind the historical scheduler")
    change = entry["executable_change"][SANDBOX]
    dependencies = scheduler.executable_dependencies
    if (
        scheduler.adapter_id != "agent-skill-eval.controlled.v1"
        or dependencies.get(SANDBOX) != change["original"]
        or change["current"] == change["original"]
    ):
        raise ConfigurationError("native boundary review must bind the changed sandbox launcher")
    verify_dependencies(dependencies | {SANDBOX: change["current"]})
    if snapshot(Path(scheduler.runtime_root)) != scheduler.runtime_tree_digest:
        raise ConfigurationError("retained scheduler runtime changed")

    spec = _resolve(
        repo,
        "toolkit_ase_native_compatibility",
        evidence.definition_ref,
        ExecutorSpec,
        reviewed=True,
    )
    bindings = {
        key: WorkflowFile.model_validate(entry[key])
        for key in ("historical_git", "current_profile", "probe", "git", "outside_canary")
    }
    for binding in bindings.values():
        _file(binding)
    if (
        dependencies.get(bindings["historical_git"].path) != bindings["historical_git"].sha256
        or entry["stdin"]["git"] != bindings["git"].path
        or entry["stdin"]["outside"] != bindings["outside_canary"].path
        or entry["command"]
        != [
            SANDBOX,
            "-f",
            bindings["current_profile"].path,
            str(Path(scheduler.runtime_root) / "bin/python"),
            "-I",
            "-B",
            bindings["probe"].path,
        ]
        or spec.id != "toolkit.ase-native-compatibility"
        or spec.kind != "command"
        or spec.side_effect != "write"
        or spec.requires_network
        or spec.config
        != {
            "argv": entry["command"],
            "argv_literal": True,
            "inherit_env": False,
            "env": entry["environment"],
            "cwd": entry["workspace"],
            "stdin_json": True,
            "max_stdin_bytes": 16384,
            "max_output_bytes": 8192,
            "timeout_seconds": 25,
            "output": {"type": "json"},
        }
    ):
        raise ConfigurationError("native launcher proof differs from its reviewed command")

    request = ConformanceProbeRequest.model_validate(entry["request"])
    stored = repo.get("conformance_request", request.plan_id)
    receipt, charge = _receipt(repo, evidence.receipt)
    facts = receipt.metadata
    observed = facts.get("observed_checks")
    journal = ExecutionEvidence.model_validate(facts.get("execution_evidence"))
    if (
        content_digest(stored) != content_digest(request)
        or receipt.executor_id != spec.id
        or receipt.executor_kind != spec.kind
        or facts.get("review_sha256") != evidence.review.sha256
        or facts.get("exit_code") != 0
        or facts.get("model_turns") != 0
        or not isinstance(observed, dict)
        or set(observed) != REQUIRED_OBSERVATIONS
        or any(passed is not True for passed in observed.values())
        or journal.attempt_id != evidence.receipt.operation_id
        or journal.digest() != facts.get("execution_evidence_digest")
        or not journal.complete
        or journal.events[-1].kind != "execution.completed"
        or charge.stage != "ase_current_native_boundary"
        or charge.plan_id != request.plan_id
        or charge.reserved.max_operations != 1
        or charge.reserved.max_model_turns != 0
        or charge.reserved.max_cash_usd != 0
        or charge.reserved.max_elapsed_seconds != review["maximum_reserved_seconds"]
        or charge.resources != receipt.actual_resources
    ):
        raise ConfigurationError("native launcher proof lacks its settled successful receipt")
    if journal.journal_id is None or any(
        repo.get("execution_event", f"{journal.journal_id}:{event.sequence}")
        != event.model_dump(mode="json")
        for event in journal.events
    ):
        raise ConfigurationError("native launcher journal differs from canonical events")
    return scheduler
