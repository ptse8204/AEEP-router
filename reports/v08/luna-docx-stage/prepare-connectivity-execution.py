"""Bind a one-shot connectivity runner and proxy lifecycle; do not approve or run."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aeep.assessment.models import (
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import StrictModel
from aeep.router import Router


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "eaad5bc7b30f3671284b1d7291a4483ff0d87399c2ea13a298be4006bc717ee1"
BASE_REVIEW = OUT / "connectivity-review.json"
PAIR_REVIEW = OUT / "pair-review.json"
PAIR_RESULT = OUT / "pair-result.json"
PAIR_EXECUTION = OUT / "pair-execution-review.json"
RUNNER = OUT / "run-connectivity.py"
REVIEW = OUT / "connectivity-execution-review-v2.json"


class Definition(StrictModel):
    values: dict


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if REVIEW.exists():
    raise RuntimeError("preserve an existing connectivity execution review")
if verification_source_digest(ROOT) != SOURCE:
    raise RuntimeError("frozen source digest differs")
base = json.loads(BASE_REVIEW.read_text())
pair = json.loads(PAIR_REVIEW.read_text())
pair_result = json.loads(PAIR_RESULT.read_text())
old_execution = json.loads(PAIR_EXECUTION.read_text())
if not pair_result.get("paired_checks_passed") or not pair_result.get("proxy_restored_stopped"):
    raise RuntimeError("fresh paired inspection evidence is not passing and cleaned up")
if base.get("source_digest") != SOURCE:
    raise RuntimeError("fresh connectivity request source pin differs")

first = ConformanceProbeRequest.model_validate(base["requests"][0])
pair_definition = pair["definitions"][base["pair_definition_digest"]]
control = pair_definition["control"]
control_spec = control
control_worker = binding_from_config(control_spec["config"]["managed_worker"])
if control_worker is None or control_worker.digest() != first.worker_digest:
    raise RuntimeError("proxy lifecycle must bind the exact control worker")

proxy = {
    "proxy_name": old_execution["proxy_name"],
    "proxy_id_prefix": old_execution["proxy_id_prefix"],
    "proxy_image": old_execution["proxy_image"],
    "network_id": control_worker.network_id,
    "runner_sha256": sha256(RUNNER),
    "connectivity_review_sha256": sha256(BASE_REVIEW),
    "pair_review_sha256": sha256(PAIR_REVIEW),
    "pair_result_sha256": sha256(PAIR_RESULT),
    "source_digest": SOURCE,
    "maximum_proxy_seconds": 600,
    "maximum_outer_seconds": 420,
    "restore_prior_state": True,
    "start_only_when_stopped": True,
}

router = Router.from_manifest(ROOT / ".aeep/live-review-v3/aeep.json")
repo = AssessmentRepository(router.store)
try:
    definitions = dict(base["definitions"])
    lifecycle_definition = Definition(values=proxy)
    lifecycle_digest = repo.put(
        "proxy_lifecycle_definition", content_digest(lifecycle_definition), lifecycle_definition
    )
    definitions[lifecycle_digest] = lifecycle_definition.model_dump(mode="json")

    runtime_digest = next(
        digest for digest, value in definitions.items()
        if isinstance(value, dict) and "dependencies" in value
        and len(value["dependencies"]) > 20
    )
    lifecycle_request = ConformanceProbeRequest(
        schema_version="assessment.conformance-request.v2",
        operation="worker_inspection",
        subject_digest=first.subject_digest,
        recipe_digest=first.recipe_digest,
        mapping_digest=lifecycle_digest,
        environment_digest=first.environment_digest,
        authorization_id=first.authorization_id,
        definition_digests=[
            base["pair_definition_digest"], lifecycle_digest,
            first.environment_digest, runtime_digest, first.recipe_digest,
        ],
        worker_digest=control_worker.digest(),
        executable_dependencies=first.executable_dependencies,
    )
    lifecycle_request_digest = repo.put(
        "conformance_request", lifecycle_request.plan_id, lifecycle_request
    )
    definitions[lifecycle_request_digest] = lifecycle_request.model_dump(mode="json")

    old_amendment = AssessmentScopeAmendment.model_validate(base["amendment"])
    amendment = AssessmentScopeAmendment(
        authorization_id=old_amendment.authorization_id,
        authorization_digest=old_amendment.authorization_digest,
        subject_digests=old_amendment.subject_digests,
        recipe_digests=old_amendment.recipe_digests,
        environment_digests=old_amendment.environment_digests,
        reviewed_digests=sorted(definitions),
    )
    review = {
        "authority": "Standing September 25/27 finite conformance-definition delegation; root reviewed connectivity request settings",
        "source_digest": SOURCE,
        "connectivity_review_sha256": sha256(BASE_REVIEW),
        "pair_review_sha256": sha256(PAIR_REVIEW),
        "pair_result_sha256": sha256(PAIR_RESULT),
        "runner_sha256": sha256(RUNNER),
        "pair_definition_digest": base["pair_definition_digest"],
        "connectivity_request_ids": {
            "control": base["request_ids"][0],
            "treatment": base["request_ids"][1],
        },
        "task_images": {
            role: details["image"] for role, details in base["workers"].items()
        },
        "proxy_name": proxy["proxy_name"],
        "proxy_id_prefix": proxy["proxy_id_prefix"],
        "proxy_image": proxy["proxy_image"],
        "network_id": proxy["network_id"],
        "proxy_request": lifecycle_request.model_dump(mode="json"),
        "definitions": definitions,
        "amendment": amendment.model_dump(mode="json"),
        "maximum_operations": 3,
        "maximum_model_turns": 2,
        "maximum_reserved_seconds": 730,
        "maximum_cash_usd": 0,
        "maximum_outer_seconds": 420,
        "accounting": "One proxy lifecycle operation is capped at 600 seconds and includes proxy startup, paired wait, and restoration; each worker bootstrap is separately capped at 65 seconds. No task timing or economic-cost claim.",
        "stop_if_control_fails": True,
        "restore_prior_proxy_state": True,
        "no_authentication_state_access": True,
        "no_case_template_or_oracle": True,
        "review_committed": False,
        "grant_reserved": False,
        "model_started": False,
    }
    REVIEW.write_text(json.dumps(review, indent=2) + "\n")
    print(json.dumps({
        "review_path": str(REVIEW),
        "review_sha256": sha256(REVIEW),
        "runner_sha256": review["runner_sha256"],
        "request_ids": review["connectivity_request_ids"],
        "proxy_lifecycle_request_id": lifecycle_request.plan_id,
        "source_digest": SOURCE,
        "approval_committed": False,
        "grant_reserved": False,
        "model_started": False,
    }))
finally:
    router.store.close()
