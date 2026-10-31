"""Draft canonical assessments through the existing operator setup service."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field

from aeep.assessment.models import (
    AssessmentPlan,
    AssessmentSetupRequest,
    AssessmentSubject,
    IntegrationCaseSet,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.onboarding import prepare_setup
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.models import StrictModel
from aeep.router import Router

from .benchmarks import BenchmarkPack, task_input
from .models import Digest
from .workflow import StackWorkflow, WorkflowFile, _read, prepare_stack


class TaskRightsReview(StrictModel):
    """An operator's exact asset-use determination, not an inferred license."""

    schema_version: Literal["aeep.toolkit.task-rights.v1"] = "aeep.toolkit.task-rights.v1"
    source_revision: str = Field(pattern=r"^[a-f0-9]{40}$")
    task_id: str = Field(min_length=1, max_length=200)
    assets: dict[str, Digest] = Field(min_length=4, max_length=4096)
    basis: list[str] = Field(min_length=1, max_length=32)
    local_execution_allowed: bool = Field(strict=True)
    provider_disclosure_allowed: bool = Field(strict=True)


class PreparationIntent(StrictModel):
    workflow_review: Digest
    configuration: str
    request_digest: Digest


class PreparedAssessment(StrictModel):
    workflow_review: Digest
    plan_id: str
    plan_digest: Digest
    status: Literal["plan_review_required"] = "plan_review_required"


def require_rights(
    repository: AssessmentRepository, pack: BenchmarkPack, tasks: tuple[str, ...]
) -> None:
    for identity in tasks:
        task = pack.task(identity)
        if task.rights_review_ref is None:
            raise ConfigurationError(
                "selected upstream task has no reviewed asset-use determination"
            )
        record = TaskRightsReview.model_validate(
            repository.get("toolkit_task_rights", task.rights_review_ref)
        )
        with repository.store._lock:
            review = repository.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (task.rights_review_ref,)
            ).fetchone()
        if (
            review is None
            or review[0]
            or content_digest(record) != task.rights_review_ref
            or record.source_revision != pack.source.revision
            or record.task_id != identity
            or record.assets != {asset.path: asset.sha256 for asset in task.assets}
            or not record.local_execution_allowed
            or not record.provider_disclosure_allowed
        ):
            raise ConfigurationError(
                "task asset-use review is missing, revoked, mismatched or insufficient"
            )


def prepare_canonical(
    definition: Path,
    configuration: str,
    *,
    reviewed_digest: str | None,
    destination: Path,
    directory: Path | None = None,
) -> dict[str, Any]:
    """Create an inert plan draft, never review definitions, install, enqueue or run."""
    from .cli import read_json
    from .install_runtime import canonical

    preview = prepare_stack(definition, configuration)
    workflow = StackWorkflow.model_validate(read_json(definition))
    selected = workflow.configurations[configuration]
    if (
        preview["review_sha256"] != reviewed_digest
        or selected.evaluator != "managed"
        or selected.preparation is None
        or preview["preparation"] is None
    ):
        raise ConfigurationError("exact managed workflow preparation review required")
    # A declaration can be previewed with blockers. Draft creation requires the
    # selected dependency/permission closure and asset rights to be resolved.
    permitted = "canonical plan preparation is selected but has not been performed"
    if any(reason != permitted for reason in preview["blockers"]):
        raise ConfigurationError("selected workflow has unresolved setup or asset-rights blockers")
    canonical(str(destination))
    if destination.exists() or not destination.parent.is_dir():
        raise ConfigurationError(
            "prepared workflow output requires a new directory in an existing parent"
        )
    root = definition.absolute().parent
    _, pack_raw = _read(selected.benchmark, root)
    pack = BenchmarkPack.model_validate_json(pack_raw)
    assert selected.benchmark_recipe is not None
    _, recipe_raw = _read(selected.benchmark_recipe, root)
    recipe = RecipeDefinition.model_validate_json(recipe_raw)
    request = AssessmentSetupRequest.model_validate(preview["preparation"]["request"])

    async def draft() -> tuple[AssessmentPlan, PreparedAssessment]:
        router = Router.from_manifest(Path(preview["preparation"]["manifest_path"]))
        try:
            service = AssessmentService(
                router,
                directory
                or Path(preview["preparation"]["manifest_path"]).parent / ".aeep" / "assessments",
            )
            repository = service.repository
            subject = AssessmentSubject.model_validate(
                repository.get("subject", request.subject_id)
            )
            if subject.dependency_digests != preview["candidate"]["files"] or content_digest(
                RecipeDefinition.model_validate(repository.get("recipe", request.recipe_id))
            ) != content_digest(recipe):
                raise ConfigurationError(
                    "canonical candidate or grader recipe differs from the selected workflow"
                )
            require_rights(repository, pack, selected.task_ids)
            if request.integration_case_set_id is None:
                raise ConfigurationError(
                    "stack bootstrap preparation requires an explicit integration task set"
                )
            cases = IntegrationCaseSet.model_validate(
                repository.get("integration_case_set", request.integration_case_set_id)
            )
            if tuple(
                case.action.input.get("task_id") for case in cases.cases
            ) != selected.task_ids or cases.benchmark_pack_digest != content_digest(
                pack.model_dump(mode="json")
            ):
                raise ConfigurationError(
                    "canonical task selection differs from the exact upstream pack"
                )
            asset_root = Path(selected.asset_root)
            asset_root = asset_root if asset_root.is_absolute() else root / asset_root
            if any(
                case.action.input != task_input(pack, asset_root, task_id)
                for case, task_id in zip(cases.cases, selected.task_ids, strict=True)
            ):
                raise ConfigurationError(
                    "canonical case input differs from the original public task bytes"
                )
            intent = PreparationIntent(
                workflow_review=preview["review_sha256"],
                configuration=configuration,
                request_digest=content_digest(request),
            )
            identity = content_digest(intent)
            # Claim in the existing transaction boundary. A lost result is
            # uncertain preparation, never an excuse to make another plan.
            with router.store._immediate_transaction() as connection:
                prior = connection.execute(
                    "SELECT 1 FROM assessment_records WHERE kind='toolkit_workflow_preparation' AND id=?",
                    (identity,),
                ).fetchone()
                complete = connection.execute(
                    "SELECT payload_json FROM assessment_records WHERE kind='toolkit_workflow_prepared' AND id=?",
                    (identity,),
                ).fetchone()
                if complete is not None:
                    result = PreparedAssessment.model_validate_json(complete[0])
                elif prior is not None:
                    raise ConfigurationError(
                        "preparation was interrupted; inspect existing canonical records before recovery"
                    )
                else:
                    repository._put(connection, "toolkit_workflow_preparation", identity, intent)
                    result = None
            if result is None:
                setup = prepare_setup(service, request)
                if setup["status"] != "plan_review_required":
                    raise ConfigurationError(
                        "existing setup service did not produce a canonical plan draft"
                    )
                plan = AssessmentPlan.model_validate(repository.get("plan", setup["plan_id"]))
                result = PreparedAssessment(
                    workflow_review=preview["review_sha256"],
                    plan_id=plan.plan_id,
                    plan_digest=content_digest(plan),
                )
                repository.put("toolkit_workflow_prepared", identity, result)
            plan = AssessmentPlan.model_validate(repository.get("plan", result.plan_id))
            if content_digest(plan) != result.plan_digest:
                raise ConfigurationError("prepared canonical plan changed")
            return plan, result
        finally:
            await router.close()

    plan, result = asyncio.run(draft())
    # Recheck every external file/candidate before publishing bindings. If drift
    # occurred, the durable result remains recoverable and no execution occurs.
    if prepare_stack(definition, configuration)["review_sha256"] != reviewed_digest:
        raise ConfigurationError("workflow inputs changed while preparing its canonical plan")
    from .cli import INTEGRATION_PLAN_BYTES

    plan_text = plan.model_dump_json(indent=2) + "\n"
    if len(plan_text.encode('utf-8')) > INTEGRATION_PLAN_BYTES:
        raise ConfigurationError("canonical integration plan exceeds the bounded reader envelope")
    destination.mkdir(mode=0o700)
    plan_path = destination / "plan.json"
    plan_path.write_text(plan_text)
    source_path = Path(preview["preparation"]["source_path"])
    data = workflow.model_dump(mode="json")
    for name in ("registry", "policy"):
        data[name]["path"] = str(_read(WorkflowFile.model_validate(data[name]), root)[0])
    target = data["configurations"][configuration]
    target["candidate"]["path"] = str((root / selected.candidate.path).absolute())
    target["asset_root"] = str((root / selected.asset_root).absolute())
    for name in ("benchmark", "benchmark_recipe"):
        target[name]["path"] = str(_read(WorkflowFile.model_validate(target[name]), root)[0])
    target["preparation"] = None
    target["assessment"] = {
        name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        for name, path in (("plan", plan_path), ("source", source_path))
    }
    data["configurations"] = {configuration: target}
    prepared = StackWorkflow.model_validate(data)
    (destination / "workflow.json").write_text(prepared.model_dump_json(indent=2) + "\n")
    return {
        **result.model_dump(mode="json"),
        "workflow_path": str(destination / "workflow.json"),
        "definition_digests": plan.definition_digests,
        "blocked_reasons": plan.blocked_reasons,
        "execution_authorized": False,
        "models_started": 0,
        "notice": "Canonical plan draft only. Existing reviews, grant, current workers, protected grading and an exact engineering execution review remain required.",
    }
