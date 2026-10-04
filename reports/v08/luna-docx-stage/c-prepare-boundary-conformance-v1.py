"""Prepare inert C conformance proposals from exact completed evidence.

This report-local helper performs no worker/model work and never writes to the
canonical assessment database. It refuses to run until every pinned C result
and proxy bracket exists and agrees with the frozen profile/source.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sqlite3
import threading
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from aeep.assessment.boundary import (
    BoundaryConformance,
    BoundaryProbe,
    DifferentialConformance,
    require_candidate_access,
    require_conformance,
    require_differential,
)
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentOperation,
    AssessmentPlanningRequest,
    DifferentialEnvironment,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.workers import binding_from_config

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
SOURCE = "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7"
PROFILE = OUT / "c-current-profile-v1.json"
PROFILE_SHA256 = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
WORKER_RESULT = OUT / "c-worker-components-result-v1.json"
WORKER_REVIEW = OUT / "c-worker-components-execution-review-v1.json"
WORKER_PROXY = OUT / "c-worker-components-v3-proxy-result.json"
WORKER_PROXY_REVIEW = OUT / "c-worker-components-v3-proxy-review.json"
PROXY_RUNNER = OUT / "c-proxy-bracket.py"
NATIVE_PATHS = {
    role: {
        "result": OUT / f"c-native-components-{role}-result-v1.json",
        "review": OUT / f"c-native-components-{role}-review-v1.json",
    }
    for role in ("control", "treatment")
}
CALLBACK_PATHS = {
    role: {
        "result": OUT
        / (
            "c-control-callback-result-v1.json"
            if role == "control"
            else "c-current-callback-result-v1.json"
        ),
        "review": OUT
        / (
            "c-control-callback-execution-review-v1.json"
            if role == "control"
            else "c-current-callback-execution-review-v1.json"
        ),
        "proxy": OUT / f"c-{role}-callback-proxy-result.json",
        "proxy_review": OUT / f"c-{role}-callback-proxy-review.json",
    }
    for role in ("control", "treatment")
}
CAPACITY_PATHS = {
    role: {
        "result": OUT / f"c-{role}-capacity-result.json",
        "review": OUT / f"c-{role}-capacity-review.json",
        "parent_review": OUT / f"c-{role}-capacity-parent-execution-review.json",
    }
    for role in ("control", "treatment")
}
CAPACITY_PROXY_PATHS = {
    role: OUT / f"c-{role}-capacity-proxy-result.json" for role in ("control", "treatment")
}
CAPACITY_PROXY_REVIEW_PATHS = {
    role: OUT / f"c-{role}-capacity-proxy-review.json" for role in ("control", "treatment")
}
OUTPUT = OUT / "c-boundary-conformance-proposal-v1.json"

IMPLEMENTATION_PATHS = (
    "src/aeep/assessment/boundary.py",
    "src/aeep/assessment/conformance.py",
    "src/aeep/assessment/identity.py",
    "src/aeep/assessment/models.py",
    "src/aeep/assessment/repository.py",
    "src/aeep/execution.py",
    "src/aeep/executors/managed_host.py",
    "src/aeep/hosts/codex_app_server.py",
    "src/aeep/hosts/codex_dynamic_tools.py",
    "src/aeep/hosts/codex_invocation.py",
    "src/aeep/hosts/codex_pair_inspection.py",
    "src/aeep/hosts/codex_sandbox.py",
    "src/aeep/hosts/workers.py",
    "src/aeep/router.py",
    "src/aeep/tasks.py",
)
REQUIRED_NAMES = {
    "allowed_tool",
    "denied_tool",
    "cross_worker",
    "answers",
    "configuration",
    "candidate_network",
    "credential_canary",
    "resource_limits",
    "cleanup",
    "events",
    "candidate_access",
    "native_boundary",
    "callback_lifecycle",
    "protected_state",
    "callback_authority",
}
ROLE_IDS = {"control": "b.luna.discovery", "treatment": "b.luna.aeep"}


def sha256(path: Path) -> str:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"expected regular non-symlink input: {path.name}")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"invalid JSON object: {path.name}")
    return value


def regular_inputs() -> tuple[dict[str, Any], dict[str, str]]:
    require(verification_source_digest(ROOT) == SOURCE, "frozen source digest changed")
    require(sha256(PROFILE) == PROFILE_SHA256, "C profile bytes changed")
    require(sha256(MANIFEST) == MANIFEST_SHA256, "canonical manifest bytes changed")
    require(not DATABASE.is_symlink() and DATABASE.is_file(), "canonical database target changed")
    profile = read_json(PROFILE)
    require(profile.get("source_digest") == SOURCE, "profile source differs")
    require(
        profile.get("component_digest")
        == "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d",
        "C component definition differs",
    )
    require(
        profile.get("differential_digest")
        == "57af9b71f05881d4109f1c4b44594433816228df3fe368aaf65c7588b7cb4dbe",
        "C differential definition differs",
    )

    paths = [PROFILE, WORKER_RESULT, WORKER_REVIEW, WORKER_PROXY, WORKER_PROXY_REVIEW, PROXY_RUNNER]
    for role in ("control", "treatment"):
        paths.extend(NATIVE_PATHS[role].values())
        paths.extend(CALLBACK_PATHS[role].values())
        paths.extend(CAPACITY_PATHS[role].values())
        paths.extend(
            (
                CALLBACK_PATHS[role]["proxy_review"],
                CAPACITY_PROXY_PATHS[role],
                CAPACITY_PROXY_REVIEW_PATHS[role],
            )
        )
    pins = {str(path.relative_to(ROOT)): sha256(path) for path in paths}
    worker_result = read_json(WORKER_RESULT)
    worker_review = read_json(WORKER_REVIEW)
    require(
        worker_result.get("source_digest") == SOURCE
        and worker_result.get("component_probes_match") is True
        and worker_result.get("model_turns") == 0
        and worker_result.get("review_sha256") == pins[str(WORKER_REVIEW.relative_to(ROOT))],
        "C worker component result is not a completed zero-turn result",
    )
    require(
        worker_review.get("execution_authorized") is True
        and worker_review.get("source_digest") == SOURCE,
        "C worker execution review is not current and authorized",
    )
    require(
        len(worker_result.get("workers", {})) == 2
        and set(worker_result["workers"]) == {"control", "treatment"},
        "C worker result does not contain both roles",
    )
    worker_proxy = read_json(WORKER_PROXY)
    require_proxy(
        worker_proxy, WORKER_RESULT, WORKER_PROXY_REVIEW, "worker", role="pair", purpose="worker"
    )

    for role in ("control", "treatment"):
        native = read_json(NATIVE_PATHS[role]["result"])
        native_review = read_json(NATIVE_PATHS[role]["review"])
        require(
            native.get("source_digest") == SOURCE
            and native.get("result_status") == "pass"
            and native.get("operation_settled") is True
            and native.get("cleanup_confirmed") is True
            and native.get("source_unchanged") is True
            and native.get("boundary_probes_complete") is True
            and native.get("model_turns") == 0
            and set(native.get("supervisor_probe_digests", {}))
            == {"native_boundary", "protected_state", "callback_lifecycle"},
            f"C {role} native result is incomplete",
        )
        require(
            native.get("review_sha256") == pins[str(NATIVE_PATHS[role]["review"].relative_to(ROOT))]
            and native_review.get("execution_authorized") is True
            and native_review.get("source_digest") == SOURCE,
            f"C {role} native review/result binding differs",
        )

        callback = read_json(CALLBACK_PATHS[role]["result"])
        callback_review = read_json(CALLBACK_PATHS[role]["review"])
        require(
            callback.get("source_digest") == SOURCE
            and callback.get("stage") == "callback_probe_recorded"
            and callback.get("result_status") == "passed"
            and callback.get("cleanup_confirmed") is True
            and callback.get("source_unchanged") is True
            and callback.get("operation_settled") is True
            and callback.get("model_turn_count_observed") == 1
            and callback.get("review_sha256")
            == pins[str(CALLBACK_PATHS[role]["review"].relative_to(ROOT))]
            and callback_review.get("execution_authorized") is True
            and callback_review.get("source_digest") == SOURCE,
            f"C {role} callback result/review is not a fresh successful one-turn result",
        )
        callback_proxy = read_json(CALLBACK_PATHS[role]["proxy"])
        require_proxy(
            callback_proxy,
            CALLBACK_PATHS[role]["result"],
            CALLBACK_PATHS[role]["proxy_review"],
            f"{role} callback",
            role=role,
            purpose="callback",
        )
        capacity_proxy = read_json(CAPACITY_PROXY_PATHS[role])
        capacity_path = CAPACITY_PATHS[role]["result"]
        capacity_review_path = CAPACITY_PATHS[role]["review"]
        capacity_result = read_json(capacity_path)
        capacity_review = read_json(capacity_review_path)
        capacity_parent_review = read_json(CAPACITY_PATHS[role]["parent_review"])
        require(
            callback_review.get("capacity_result_path") == str(capacity_path)
            and callback_review.get("capacity_review_path") == str(capacity_review_path)
            and callback_review.get("capacity_result_sha256") == sha256(capacity_path)
            and callback_review.get("capacity_review_sha256") == sha256(capacity_review_path)
            and callback.get("capacity_result_sha256") == sha256(capacity_path),
            f"C {role} callback does not bind its fresh capacity observation",
        )
        require(
            capacity_proxy.get("status") == "passed"
            and capacity_proxy.get("source_digest") == SOURCE
            and capacity_proxy.get("proxy_restored_stopped") is True
            and capacity_proxy.get("cleanup_operation_settled") is True,
            f"C {role} capacity proxy bracket is incomplete",
        )
        require_proxy(
            capacity_proxy,
            capacity_path,
            CAPACITY_PROXY_REVIEW_PATHS[role],
            f"{role} capacity",
            role=role,
            purpose="capacity",
            expected_worker=capacity_result.get("worker_digest"),
        )
        require(
            capacity_result.get("source_digest") == SOURCE
            and capacity_result.get("worker_digest") == callback.get("worker_digest")
            and capacity_result.get("cleanup_confirmed") is True
            and capacity_result.get("stage") == "capacity_introspection"
            and capacity_result.get("status") == "passed"
            and capacity_result.get("operation_id") == capacity_review.get("operation_id")
            and capacity_result.get("plan_id") == capacity_review.get("request_id")
            and capacity_result.get("request_digest") == capacity_review.get("request_digest")
            and isinstance(capacity_result.get("operation_start_digest"), str)
            and isinstance(capacity_result.get("operation_measurement_digest"), str)
            and capacity_result.get("max_model_turns_reserved") == 0
            and capacity_review.get("execution_authorized") is False
            and capacity_review.get("source_digest") == SOURCE
            and capacity_review.get("worker_digest") == callback.get("worker_digest"),
            f"C {role} capacity observation is not current for its callback worker",
        )
        require(
            capacity_parent_review.get("execution_authorized") is True
            and capacity_parent_review.get("source_digest") == SOURCE
            and capacity_parent_review.get("wrapper_review_sha256")
            == sha256(CAPACITY_PROXY_REVIEW_PATHS[role])
            and capacity_parent_review.get("wrapper_runner_sha256") == sha256(PROXY_RUNNER)
            and capacity_parent_review.get("inner_review_sha256") == sha256(capacity_review_path)
            and capacity_parent_review.get("maximum_operations_including_capacity") == 4
            and capacity_parent_review.get("maximum_reserved_seconds_including_capacity") == 210
            and capacity_parent_review.get("maximum_model_turns") == 0
            and capacity_parent_review.get("cash_usd") == 0,
            f"C {role} parent review does not authorize its bounded capacity bracket",
        )
        age = callback.get("capacity_age_seconds_at_start")
        max_age = capacity_review.get("max_age_seconds")
        require(
            isinstance(age, (int, float))
            and not isinstance(age, bool)
            and math.isfinite(age)
            and isinstance(max_age, (int, float))
            and not isinstance(max_age, bool)
            and math.isfinite(max_age)
            and 0 <= age <= max_age,
            f"C {role} callback did not consume a fresh reviewed capacity observation",
        )
        pins[str(capacity_path.relative_to(ROOT))] = sha256(capacity_path)
        pins[str(CAPACITY_PATHS[role]["parent_review"].relative_to(ROOT))] = sha256(
            CAPACITY_PATHS[role]["parent_review"]
        )
        pins[str(CALLBACK_PATHS[role]["review"].relative_to(ROOT))] = sha256(
            CALLBACK_PATHS[role]["review"]
        )
    require(
        not OUTPUT.exists() and not OUTPUT.is_symlink(),
        "proposal already exists; preserve and inspect",
    )
    return profile, pins


def require_proxy(
    record: dict[str, Any],
    inner_path: Path,
    review_path: Path,
    label: str,
    *,
    role: str,
    purpose: str,
    expected_worker: str | None = None,
) -> None:
    review = read_json(review_path)
    definition = review.get("definition", {})
    runner_name = definition.get("runner")
    inner_review_name = definition.get("inner_review")
    require(
        isinstance(runner_name, str)
        and Path(runner_name).name == runner_name
        and isinstance(inner_review_name, str)
        and Path(inner_review_name).name == inner_review_name,
        f"C {label} proxy names are not report-local",
    )
    inner_review_path = OUT / inner_review_name
    runner_path = OUT / runner_name
    require(
        record.get("status") == "passed"
        and record.get("source_digest") == SOURCE
        and record.get("review_sha256") == sha256(review_path)
        and record.get("role") == role
        and record.get("model_turns") == 0
        and record.get("inner_returned") is True
        and record.get("inner_result_sha256") == sha256(inner_path)
        and record.get("proxy_restored_stopped") is True
        and record.get("cleanup_operation_settled") is True
        and record.get("coordinator_closed") is True,
        f"C {label} proxy bracket is incomplete",
    )
    require(
        review.get("source_digest") == SOURCE
        and review.get("prepared_only") is True
        and review.get("role") == role
        and review.get("runner_sha256") == sha256(PROXY_RUNNER)
        and definition.get("runner_sha256") == sha256(runner_path)
        and definition.get("inner_review_sha256") == sha256(inner_review_path)
        and definition.get("purpose") == purpose
        and definition.get("inner_result") == inner_path.name
        and (expected_worker is None or definition.get("worker_digest") == expected_worker)
        and definition.get("operations") == 3
        and definition.get("reserved_seconds") == 150
        and definition.get("model_turns") == 0
        and definition.get("cash_usd") == 0,
        f"C {label} proxy review scope differs",
    )


def require_capacity_operation(
    repository: AssessmentRepository, role: str, result: dict[str, Any], review: dict[str, Any]
) -> None:
    """Join capacity output digests to the exact completed onboarding operation."""
    operation_id = result.get("operation_id")
    require(
        isinstance(operation_id, str)
        and operation_id == review.get("operation_id")
        and result.get("plan_id") == review.get("request_id"),
        f"C {role} capacity operation/request identity differs",
    )
    start_payload = repository.get("operation_start", operation_id)
    measured_payload = repository.get("operation_measurement", operation_id)
    start = AssessmentOperation.model_validate(start_payload)
    measured = AssessmentOperation.model_validate(measured_payload)
    start_digest = content_digest(start_payload)
    measured_digest = content_digest(measured_payload)
    require(
        start_digest == result.get("operation_start_digest")
        and measured_digest == result.get("operation_measurement_digest")
        and start.operation_id == operation_id
        and start.plan_id == result.get("plan_id")
        and start.stage == "capacity_introspection"
        and start.reserved.max_operations == 1
        and start.reserved.max_model_turns == 0
        and start.reserved.max_elapsed_seconds == 60
        and start.reserved.max_cash_usd == 0
        and measured.operation_id == operation_id
        and measured.plan_id == start.plan_id
        and measured.stage == start.stage
        and measured.reserved == start.reserved
        and measured.elapsed_seconds is not None
        and math.isfinite(measured.elapsed_seconds)
        and 0 <= measured.elapsed_seconds <= 60
        and result.get("elapsed_seconds") == measured.elapsed_seconds,
        f"C {role} capacity operation start/measurement digests or limits differ",
    )
    state = repository.store._connection.execute(
        "SELECT grant_id, state FROM assessment_operations WHERE id=?", (operation_id,)
    ).fetchone()
    require(
        state is not None and tuple(state) == ("onboarding", "complete"),
        f"C {role} capacity operation is not complete under the onboarding grant",
    )
    request_payload = repository.get("planning_request", start.plan_id)
    request = AssessmentPlanningRequest.model_validate(request_payload)
    expected_executor = ROLE_IDS[role]
    require(
        content_digest(request_payload) == result.get("request_digest")
        and result.get("request_digest") == review.get("request_digest")
        and request.plan_id == start.plan_id
        and request.authorization_id == "onboarding"
        and request.mapping_digest == review.get("definition_digest")
        and request.planner.id == expected_executor,
        f"C {role} capacity operation is detached from its exact reviewed same-grant request",
    )


def insert_memory_documents(
    connection: sqlite3.Connection, documents: dict[str, Any], created_by_proposal: set[str]
) -> None:
    """Add temporary validator inputs without silently ignoring collisions."""
    for digest, item in documents.items():
        document = item["document"]
        kind = item["kind"]
        identity = document.get("conformance_id", digest)
        require(content_digest(document) == digest, "proposal document digest differs")
        rows = connection.execute(
            "SELECT kind,id,digest,payload_json FROM assessment_records "
            "WHERE digest=? OR (kind=? AND id=?)",
            (digest, kind, identity),
        ).fetchall()
        review = connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
        ).fetchone()
        if rows:
            exact_row = (
                len(rows) == 1
                and rows[0][0] == kind
                and rows[0][1] == identity
                and rows[0][2] == digest
                and json.loads(rows[0][3]) == document
            )
            active_review = review is not None and review[0] == 0
            if digest in created_by_proposal:
                require(exact_row and active_review, "proposal-shared document changed in memory")
                continue
            require(
                kind == "reviewed_inventory" and exact_row and active_review,
                "only an exact active-reviewed canonical inventory may be reused",
            )
            created_by_proposal.add(digest)
            continue
        require(review is None, "review exists without its exact canonical document")
        connection.execute(
            "INSERT INTO assessment_records VALUES (?,?,?,?)",
            (kind, identity, digest, json.dumps(document, sort_keys=True)),
        )
        connection.execute(
            "INSERT INTO assessment_reviews VALUES (?,?,0)",
            (digest, "proposal-memory-only"),
        )
        created_by_proposal.add(digest)


class MappingProjection:
    def __init__(self, repository: AssessmentRepository, mapping: ReviewedMapping):
        self.repository, self.mapping = repository, mapping

    def __getattr__(self, name: str) -> Any:
        return getattr(self.repository, name)

    def get(self, kind: str, key: str) -> Any:
        if kind == "mapping" and key == content_digest(self.mapping):
            return self.mapping.model_dump(mode="json")
        return self.repository.get(kind, key)


def _probe_set(
    repository: AssessmentRepository,
    profile: dict[str, Any],
    role: str,
    worker_item: dict[str, Any],
    native_result: dict[str, Any],
    callback_result: dict[str, Any],
) -> tuple[dict[str, BoundaryProbe], dict[str, str]]:
    request_id = worker_item.get("request_id")
    require(isinstance(request_id, str) and request_id, f"C {role} worker request id missing")
    operation_ids = {
        "worker": "pair-inspection:" + request_id,
        "native": native_result.get("operation_id"),
        "callback": callback_result.get("operation_id"),
    }
    require(
        all(isinstance(value, str) and value for value in operation_ids.values()),
        f"C {role} operation lineage missing",
    )
    operations = {
        name: content_digest(repository.get("operation_start", operation_id))
        for name, operation_id in operation_ids.items()
    }
    digests: dict[str, str] = {}
    worker_digests = worker_item.get("probe_digests", [])
    require(len(worker_digests) == 11, f"C {role} must have exactly 11 worker probes")
    for digest in worker_digests:
        probe = BoundaryProbe.model_validate(repository.get("boundary_probe", digest))
        require(
            probe.name not in digests and probe.charged_operation_digest == operations["worker"],
            f"C {role} worker probe duplicate or parent mismatch",
        )
        digests[probe.name] = digest
    native_digests = native_result.get("supervisor_probe_digests", {})
    require(len(native_digests) == 3, f"C {role} must have exactly three native probes")
    for name, digest in native_digests.items():
        probe = BoundaryProbe.model_validate(repository.get("boundary_probe", digest))
        require(
            probe.name == name
            and name not in digests
            and probe.charged_operation_digest == operations["native"],
            f"C {role} native probe duplicate or parent mismatch",
        )
        digests[name] = digest
    callback_digest = callback_result.get("probe_digest")
    require(isinstance(callback_digest, str), f"C {role} callback probe missing")
    callback_probe = BoundaryProbe.model_validate(repository.get("boundary_probe", callback_digest))
    require(
        callback_probe.name == "callback_authority"
        and callback_probe.name not in digests
        and callback_probe.charged_operation_digest == operations["callback"],
        f"C {role} callback probe name or parent mismatch",
    )
    digests[callback_probe.name] = callback_digest
    require(
        set(digests) == REQUIRED_NAMES, f"C {role} probe set differs from the composed contract"
    )

    expected_worker = profile["callback_documents_by_role"][role]["identity"]["worker_digest"]
    probes: dict[str, BoundaryProbe] = {}
    for name, digest in digests.items():
        probe = BoundaryProbe.model_validate(repository.get("boundary_probe", digest))
        require(
            content_digest(probe) == digest
            and probe.schema_version == "assessment.boundary-probe.v2"
            and probe.worker_digest == expected_worker,
            f"C {role} probe digest/version/worker differs",
        )
        probes[name] = probe
    return probes, digests


def _role_proposal(
    repository: AssessmentRepository,
    profile: dict[str, Any],
    pins: dict[str, str],
    role: str,
    worker_item: dict[str, Any],
    native_result: dict[str, Any],
    callback_result: dict[str, Any],
    created_by_proposal: set[str],
) -> dict[str, Any]:
    composed = ComposedPairDefinition.model_validate(profile["component"]["composed"])
    differential = DifferentialEnvironment.model_validate(profile["differential"])
    spec = getattr(composed, role)
    config = spec.managed_host_config()
    worker = binding_from_config(config.managed_worker)
    require(worker is not None and spec.id == ROLE_IDS[role], f"C {role} worker profile differs")
    worker_digest = worker.digest()
    require(
        profile["callback_documents_by_role"][role]["identity"]["worker_digest"] == worker_digest,
        f"C {role} callback/profile worker differs",
    )
    require(
        worker_item.get("worker_digest") == worker_digest
        and worker_item.get("cleanup_confirmed") is True
        and worker_item.get("component_probes_match") is True
        and worker_item.get("model_turns") == 0,
        f"C {role} worker observation result differs",
    )
    require(
        callback_result.get("worker_digest") == worker_digest
        and callback_result.get("callback_binding_digest")
        == composed.callback_bindings[worker_digest],
        f"C {role} callback worker or binding differs",
    )
    require(
        native_result.get(
            "worker_digest", native_result.get("selected_worker_digest", worker_digest)
        )
        == worker_digest,
        f"C {role} native worker differs",
    )
    probes, probe_digests = _probe_set(
        repository, profile, role, worker_item, native_result, callback_result
    )
    identity_digest = worker_item.get("identity_digest")
    require(
        isinstance(identity_digest, str) and len(identity_digest) == 64,
        f"C {role} actual worker identity missing",
    )
    inventory = (
        differential.control_inventory if role == "control" else differential.treatment_inventory
    )
    callback_binding = composed.callback_bindings[worker_digest]
    native_backend = composed.native_backends[worker_digest]
    composed_digest = content_digest(composed)
    inventory_digest = content_digest(inventory)
    image_digest = (
        worker.image
        if worker.image.startswith("sha256:")
        else "sha256:" + worker.image.rsplit("sha256:", 1)[-1]
    )
    adapter = config.adapter_id

    effective_policy = {
        "definition": {
            "schema_version": "assessment.c-effective-policy-evidence.v1",
            "source_digest": SOURCE,
            "role": role,
            "executor_id": spec.id,
            "adapter": adapter,
            "adapter_version": "1",
            "worker_digest": worker_digest,
            "identity_digest": identity_digest,
            "binary_digest": worker.binary_sha256,
            "image_digest": image_digest,
            "configuration_digest": worker.configuration_digest,
            "effective_inventory_digest": inventory_digest,
            "callback_binding_digest": callback_binding,
            "native_backend_digest": native_backend,
            "composed_definition_digest": composed_digest,
            "invocation": config.invocation.model_dump(mode="json") if config.invocation else None,
            "configuration_probe_digest": probe_digests["configuration"],
            "candidate_access_probe_digest": probe_digests["candidate_access"],
            "callback_evidence_digest": callback_result.get("evidence_digest"),
            "host_receipt_digest": callback_result.get("host_receipt_digest"),
            "model_turn_count_observed": callback_result.get("model_turn_count_observed"),
            "unknowns": [
                "model-facing advertised tool inventory is not asserted by this record",
                "task-level tool use is not inferred from profile declarations",
            ],
        }
    }
    effective_policy_digest = content_digest(effective_policy)
    enforcement = {
        "definition": {
            "schema_version": "assessment.c-enforcement-evidence.v1",
            "purpose": f"C {role} composed-worker enforcement evidence; inert proposal only",
            "source_digest": SOURCE,
            "worker_digest": worker_digest,
            "identity_digest": identity_digest,
            "configuration_digest": worker.configuration_digest,
            "implementation_sha256": {path: sha256(ROOT / path) for path in IMPLEMENTATION_PATHS},
            "probe_digests_by_name": dict(sorted(probe_digests.items())),
            "operation_start_digests": {
                name: probes[name].charged_operation_digest for name in sorted(probes)
            },
            "component_result_sha256": pins[str(WORKER_RESULT.relative_to(ROOT))],
            "native_result_sha256": sha256(NATIVE_PATHS[role]["result"]),
            "callback_result_sha256": sha256(CALLBACK_PATHS[role]["result"]),
            "unknowns": ["bounded C probes do not establish qualification, admission, or value"],
        }
    }
    enforcement_digest = content_digest(enforcement)
    inventory_doc = dict(inventory)
    record = BoundaryConformance(
        schema_version="assessment.boundary-conformance.v3",
        conformance_id=f"c-{role}-boundary-conformance-20261003-50de",
        source_digest=SOURCE,
        worker_digest=worker_digest,
        image_digest=image_digest,
        binary_digest=worker.binary_sha256,
        adapter=adapter,
        adapter_version="1",
        effective_policy_digest=effective_policy_digest,
        reviewed_inventory_digest=inventory_digest,
        identity_digest=identity_digest,
        enforcement_definition_digest=enforcement_digest,
        advertised_tools=[],
        permitted_tools=[],
        used_tools=[],
        probe_digests=[probe_digests[name] for name in sorted(probe_digests)],
        configuration_digest=worker.configuration_digest,
        effective_inventory=inventory,
        callback_binding_digest=callback_binding,
        native_backend_digest=native_backend,
        composed_definition_digest=composed_digest,
    )
    record_digest = content_digest(record)
    boundary_doc = record.model_dump(mode="json")
    documents = {
        effective_policy_digest: {
            "kind": "effective_policy_definition",
            "document": effective_policy,
        },
        enforcement_digest: {"kind": "enforcement_definition", "document": enforcement},
        inventory_digest: {"kind": "reviewed_inventory", "document": inventory_doc},
        record_digest: {"kind": "boundary_conformance", "document": boundary_doc},
    }
    # Validate each role with a complete, temporary evidence view. The
    # canonical connection below is read-only; these proposed review marks
    # exist only in SQLite :memory:.
    insert_memory_documents(repository.store._connection, documents, created_by_proposal)
    actual = require_conformance(
        repository,
        record_digest,
        source_digest=SOURCE,
        worker_digest=worker_digest,
        identity_digest=identity_digest,
    )
    require_candidate_access(repository, actual, differential, available=role == "treatment")
    return {
        "canonical_references": {
            "worker_digest": worker_digest,
            "identity_digest": identity_digest,
            "callback_binding_digest": callback_binding,
            "native_backend_digest": native_backend,
            "composed_definition_digest": composed_digest,
            "component_digest": profile["component_digest"],
            "callback_probe_digest": probe_digests["callback_authority"],
            "callback_evidence_digest": callback_result.get("evidence_digest"),
            "host_receipt_digest": callback_result.get("host_receipt_digest"),
            "probe_digests_by_name": dict(sorted(probe_digests.items())),
        },
        "conformance_record": {"digest": record_digest, "document": boundary_doc},
        "review_documents": documents,
        "simulation_preflight": {
            "status": "passed",
            "verified_probe_count": len(actual.probe_digests),
            "verified_probe_names": sorted(REQUIRED_NAMES),
            "require_conformance": "passed_in_memory_only",
            "require_candidate_access": "passed_in_memory_only",
            "candidate_available": role == "treatment",
            "canonical_database_writes": 0,
            "qualification": False,
            "admission": False,
            "value_trial": False,
        },
    }


def prepare() -> dict[str, Any]:
    profile, pins = regular_inputs()
    before_source = verification_source_digest(ROOT)
    before_manifest = sha256(MANIFEST)
    stat = DATABASE.stat()
    canonical = sqlite3.connect(f"file:{DATABASE.as_posix()}?mode=ro", uri=True)
    memory = sqlite3.connect(":memory:")
    try:
        canonical.backup(memory)
        repository = AssessmentRepository(
            SimpleNamespace(_connection=memory, _lock=threading.RLock())
        )
        for role in ("control", "treatment"):
            require_capacity_operation(
                repository,
                role,
                read_json(CAPACITY_PATHS[role]["result"]),
                read_json(CAPACITY_PATHS[role]["review"]),
            )
        composed = ComposedPairDefinition.model_validate(profile["component"]["composed"])
        differential = DifferentialEnvironment.model_validate(profile["differential"])
        composed_digest = content_digest(composed)
        require(
            content_digest(repository.get("composed_pair_definition", composed_digest))
            == composed_digest,
            "profile composed definition is not the exact canonical definition",
        )
        created_by_proposal: set[str] = set()
        control = _role_proposal(
            repository,
            profile,
            pins,
            "control",
            read_json(WORKER_RESULT)["workers"]["control"],
            read_json(NATIVE_PATHS["control"]["result"]),
            read_json(CALLBACK_PATHS["control"]["result"]),
            created_by_proposal,
        )
        treatment = _role_proposal(
            repository,
            profile,
            pins,
            "treatment",
            read_json(WORKER_RESULT)["workers"]["treatment"],
            read_json(NATIVE_PATHS["treatment"]["result"]),
            read_json(CALLBACK_PATHS["treatment"]["result"]),
            created_by_proposal,
        )
        control_digest = control["conformance_record"]["digest"]
        treatment_digest = treatment["conformance_record"]["digest"]
        differential_record = DifferentialConformance(
            definition=differential,
            control_conformance_digest=control_digest,
            treatment_conformance_digest=treatment_digest,
        )
        differential_digest = content_digest(differential_record)
        insert_memory_documents(
            memory,
            {
                differential_digest: {
                    "kind": "differential_conformance",
                    "document": differential_record.model_dump(mode="json"),
                }
            },
            created_by_proposal,
        )
        mapping = ReviewedMapping(candidate=composed.treatment, baseline=composed.control)
        environment = AssessmentEnvironment(
            environment_id="c-conformance-proposal-memory-only",
            kind="trusted_local",
            identity={"purpose": "inert differential-validator projection"},
            conformance_digests={
                composed.control.id: control_digest,
                composed.treatment.id: treatment_digest,
            },
            differential_conformance_digest=differential_digest,
        )
        plan = SimpleNamespace(
            candidate_id=composed.treatment.id,
            baseline_id=composed.control.id,
            mapping_digest=content_digest(mapping),
            comparison=SimpleNamespace(
                experiment=SimpleNamespace(environment=differential, stage="qualification")
            ),
        )
        require_differential(MappingProjection(repository, mapping), environment, plan)
        proposal = {
            "schema_version": "assessment.c-boundary-conformance-proposal.v1",
            "status": "inert_proposal_unreviewed",
            "source_digest": SOURCE,
            "profile_sha256": PROFILE_SHA256,
            "input_pins": dict(sorted(pins.items())),
            "canonical_database_snapshot": {
                "path": str(DATABASE.relative_to(ROOT)),
                "read_only": True,
                "canonical_writes": 0,
                "simulation": "SQLite backup to :memory:; proposed review rows inserted there only",
            },
            "control": control,
            "treatment": treatment,
            "differential_conformance": {
                "digest": differential_digest,
                "document": differential_record.model_dump(mode="json"),
                "require_differential": "passed_in_memory_only",
            },
            "simulation_preflight": {
                "status": "passed",
                "role_count": 2,
                "probe_count_per_role": 15,
                "differential_definition_digest": content_digest(differential),
                "canonical_database_writes": 0,
                "model_turns": 0,
                "qualification": False,
                "admission": False,
                "value_trial": False,
            },
            "limitations": [
                "Proposal only; exact review under standing operator delegation and a separate "
                "apply step remain required.",
                "Probe evidence is bounded to the exact C worker, native and callback operations.",
                "Model-facing advertised tools and broader task-level tool use are not inferred.",
                "This record does not qualify, admit or establish value for any candidate.",
            ],
        }
        require(
            verification_source_digest(ROOT) == before_source == SOURCE
            and before_manifest == sha256(MANIFEST)
            and (DATABASE.stat().st_dev, DATABASE.stat().st_ino) == (stat.st_dev, stat.st_ino),
            "source, manifest or canonical database identity changed during preparation",
        )
        require(
            not OUTPUT.exists() and not OUTPUT.is_symlink(), "proposal appeared during preparation"
        )
        with OUTPUT.open("x", encoding="utf-8") as stream:
            json.dump(proposal, stream, indent=2, sort_keys=True, allow_nan=False)
            stream.write("\n")
        return {
            "status": "proposal_written",
            "path": str(OUTPUT),
            "sha256": sha256(OUTPUT),
            "source_digest": SOURCE,
            "canonical_database_writes": 0,
        }
    finally:
        memory.close()
        canonical.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prepare-inert",
        action="store_true",
        required=True,
        help="validate completed C evidence and write one unreviewed proposal file",
    )
    args = parser.parse_args()
    if args.prepare_inert:
        print(json.dumps(prepare(), sort_keys=True))


if __name__ == "__main__":
    main()
