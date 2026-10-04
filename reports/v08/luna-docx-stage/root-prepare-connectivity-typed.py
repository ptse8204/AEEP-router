"""Prepare exact one-turn Luna/xhigh connectivity definitions; never execute them."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    RecipeRuntimeBinding,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, ManagedHostExecutorConfig, ManagedHostInvocation, SideEffect
from aeep.router import Router


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "eaad5bc7b30f3671284b1d7291a4483ff0d87399c2ea13a298be4006bc717ee1"
PAIR_REVIEW = OUT / "pair-review.json"
PAIR_RESULT = OUT / "pair-result.json"
REVIEW = OUT / "root-connectivity-typed-review.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if REVIEW.exists():
    raise RuntimeError("preserve an existing connectivity review")
if verification_source_digest(ROOT) != SOURCE:
    raise RuntimeError("frozen source digest differs")
pair_bytes = PAIR_REVIEW.read_bytes()
pair = json.loads(pair_bytes)
result_bytes = PAIR_RESULT.read_bytes()
pair_result = json.loads(result_bytes)
if not pair_result.get("paired_checks_passed") or not pair_result.get("proxy_restored_stopped"):
    raise RuntimeError("fresh paired inspection evidence is not passing and cleaned up")
if pair.get("source_digest") != "060fbefd55ff1c73256520a0c1e3d0de0e029755b75437cf7a93d7b68335e293":
    raise RuntimeError("historical pair review source differs from its recorded binding")
if len(pair.get("requests", [])) != 2 or len(pair.get("request_ids", [])) != 2:
    raise RuntimeError("exactly two paired task profiles are required")

router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
repo = AssessmentRepository(router.store)
try:
    definitions: dict[str, dict] = {}

    def put(kind: str, value, identity: str | None = None) -> str:
        digest = content_digest(value)
        repo.put(kind, identity or digest, value)
        definitions[digest] = value.model_dump(mode="json")
        return digest

    original = [ConformanceProbeRequest.model_validate(value) for value in pair["requests"]]
    pair_digest = pair["pair_definition_digest"]
    definitions[pair_digest] = pair["definitions"][pair_digest]
    definitions[original[0].subject_digest] = pair["definitions"][original[0].subject_digest]
    definitions[original[0].recipe_digest] = pair["definitions"][original[0].recipe_digest]

    dependencies = runtime_dependencies()
    runtime_digest = put("probe_runtime", RecipeRuntimeBinding(dependencies=dependencies))
    requests = []
    workers = {}
    environments = []

    for role, source in zip(("control", "treatment"), original, strict=True):
        old = BoundaryProbeDefinition.model_validate(pair["definitions"][source.mapping_digest])
        task_spec = old.executor
        task_config = task_spec.managed_host_config()
        worker = binding_from_config(task_config.managed_worker)
        if worker is None or worker.digest() != source.worker_digest:
            raise RuntimeError(f"{role} worker binding differs from the fresh pair request")

        # Preserve the exact role-specific image, binary, network, and credential
        # volume. This probe does not pass the task input or enable the candidate.
        invocation = ManagedHostInvocation(mode="turn")
        config_data = task_config.model_dump(mode="json")
        config_data.update({
            "instructions": (
                "This is a connectivity check only. Do not read local files. Do not use, "
                "invoke, search for, or describe skills, tools, apps, or external services. "
                'Return exactly this JSON object: {"connected":true}.'
            ),
            "model_constraints": {"allowed_model_ids": ["gpt-6-luna"]},
            "reasoning_efforts": ("xhigh",),
            "timeout_seconds": 60,
            "approval_ceiling": SideEffect.READ,
            "store_prompt": False,
            "store_output": False,
            "invocation": invocation,
            "artifact": None,
            "input_tree": None,
            "worker_workspace": None,
            "assessment_adapter": None,
        })
        config = ManagedHostExecutorConfig.model_validate(config_data)
        spec_data = task_spec.model_dump(mode="json")
        spec_data.update(
            id=f"skillsbench.docx.connectivity.{role}",
            capability="aeep.conformance.connectivity@1",
            description=f"Fresh Luna/xhigh connectivity-only probe for DOCX {role} worker",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
            output_schema={
                "type": "object",
                "properties": {"connected": {"type": "boolean"}},
                "required": ["connected"],
                "additionalProperties": False,
            },
            side_effect="read",
            requires_network=False,
            config=config.model_dump(mode="json"),
        )
        spec = ExecutorSpec.model_validate(spec_data)
        exact_worker = binding_from_config(spec.managed_host_config().managed_worker)
        if exact_worker is None or exact_worker.digest() != source.worker_digest:
            raise RuntimeError(f"{role} connectivity definition changed the worker binding")
        if (spec.managed_host_config().invocation != ManagedHostInvocation(mode="turn")
                or spec.managed_host_config().artifact is not None
                or spec.managed_host_config().input_tree is not None
                or spec.managed_host_config().store_prompt
                or spec.managed_host_config().store_output):
            raise RuntimeError(f"{role} connectivity definition exposes task or candidate inputs")

        environment = AssessmentEnvironment(
            environment_id=f"skillsbench-docx-connectivity-{role}",
            kind="codex_sandbox",
            identity={
                "purpose": "one-turn Luna/xhigh connectivity only; no task input or completion claim",
                "worker_digest": exact_worker.digest(),
                "task_pair_review_sha256": sha256(PAIR_REVIEW),
                "task_pair_definition_digest": pair_digest,
                "role": role,
                "candidate_profile": "plain turn; local_profile absent; isolated skills.config disables all catalog entries",
                "source_digest": SOURCE,
            },
        )
        environment_digest = put("environment", environment)
        environments.append(environment_digest)
        probe = BoundaryProbeDefinition(name="model_connectivity", executor=spec, expected={"connected": True})
        mapping_digest = put("boundary_probe_definition", probe)
        request = ConformanceProbeRequest(
            subject_digest=source.subject_digest,
            recipe_digest=source.recipe_digest,
            mapping_digest=mapping_digest,
            environment_digest=environment_digest,
            authorization_id=source.authorization_id,
            definition_digests=[pair_digest, mapping_digest, environment_digest, runtime_digest, source.recipe_digest],
            worker_digest=exact_worker.digest(),
            executable_dependencies=dependencies,
        )
        request_digest = repo.put("conformance_request", request.plan_id, request)
        definitions[request_digest] = request.model_dump(mode="json")
        definitions[request.recipe_digest] = pair["definitions"][request.recipe_digest]
        requests.append(request)
        workers[role] = {
            "executor_id": spec.id,
            "worker_digest": exact_worker.digest(),
            "image": exact_worker.image,
            "credential_volume": exact_worker.credential_volume,
            "adapter_id": spec.managed_host_config().adapter_id,
            "invocation": spec.managed_host_config().invocation.model_dump(mode="json"),
            "candidate_skill_sha256": (exact_worker.reviewed_files or {}).get(
                "/opt/dependencies/plugin/skills/docx/SKILL.md"
            ),
            "candidate_selected": False,
        }

    pair_amendment = AssessmentScopeAmendment.model_validate(pair["amendment"])
    amendment = AssessmentScopeAmendment(
        authorization_id=pair_amendment.authorization_id,
        authorization_digest=pair_amendment.authorization_digest,
        subject_digests=[requests[0].subject_digest],
        recipe_digests=[requests[0].recipe_digest],
        environment_digests=environments,
        reviewed_digests=sorted(definitions),
    )

    review = {
        "authority": "Standing September 25/27 finite conformance-definition delegation; operator-selected Luna/xhigh",
        "source_digest": SOURCE,
        "historical_pair_source_digest": pair["source_digest"],
        "pair_review_sha256": sha256(PAIR_REVIEW),
        "pair_result_sha256": sha256(PAIR_RESULT),
        "pair_definition_digest": pair_digest,
        "pair_check_passed": True,
        "request_ids": [item.plan_id for item in requests],
        "requests": [item.model_dump(mode="json") for item in requests],
        "definitions": definitions,
        "amendment": amendment.model_dump(mode="json"),
        "workers": workers,
        "scope": {
            "probe": "connectivity only",
            "model": "gpt-6-luna",
            "reasoning_effort": "xhigh",
            "model_turns": 1,
            "timeout_seconds_per_worker": 60,
            "task_input": False,
            "skill_invocation": False,
            "candidate_enabled_in_effective_config": False,
            "prompt_or_output_persistence": False,
            "qualification_or_admission": False,
            "review_committed": False,
            "grant_reserved": False,
            "model_started": False,
        },
        "maximum_operations": 2,
        "maximum_model_turns": 2,
        "maximum_reserved_seconds": 130,
        "maximum_cash_usd": 0,
        "no_authentication_state_access": True,
        "no_task_case_or_oracle_in_worker": True,
    }
    REVIEW.write_text(json.dumps(review, indent=2) + "\n")
    print(json.dumps({
        "review_path": str(REVIEW),
        "review_sha256": sha256(REVIEW),
        "request_ids": review["request_ids"],
        "worker_digests": {key: value["worker_digest"] for key, value in workers.items()},
        "source_digest": SOURCE,
        "model_started": False,
        "grant_reserved": False,
        "review_committed": False,
    }))
finally:
    router.store.close()
