"""Prepare one exact ordinary workbook qualification proposal; never execute it."""
from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
SOURCE = "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
DATABASE_DEVICE = 16777231
DATABASE_INODE = 166293865
COMPONENT_DIGEST = "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d"
DIFFERENTIAL_DIGEST = "57af9b71f05881d4109f1c4b44594433816228df3fe368aaf65c7588b7cb4dbe"
CALLBACK_IMPLEMENTATION_DIGEST = "b55e60d7db97fd842922da6790656222d776467dab5216ca52acb046309683fb"
CAPACITY_BOOTSTRAP = {
    "b-control": {
        "request": "b-control-capacity-request.json",
        "result": "b-control-capacity-result.json",
        "request_id": "planning_b_control_capacity_449b_e15b7ee0",
        "operation_id": "capacity:planning_b_control_capacity_449b_e15b7ee0",
        "source_digest": "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad",
    },
    "b-treatment": {
        "request": "b-treatment-capacity-request.json",
        "result": "b-treatment-capacity-result.json",
        "request_id": "planning_b_treatment_capacity_449b_19027f56",
        "operation_id": "capacity:planning_b_treatment_capacity_449b_19027f56",
        "source_digest": "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad",
    },
    "c-control": {
        "request": "c-control-capacity-request.json",
        "result": "c-control-capacity-result.json",
        "request_id": "planning_c_control_capacity_50de_e15b7ee0_20261003",
        "operation_id": "capacity:planning_c_control_capacity_50de_e15b7ee0_20261003",
        "source_digest": "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7",
    },
    "c-treatment": {
        "request": "c-treatment-capacity-request.json",
        "result": "c-treatment-capacity-result.json",
        "request_id": "planning_c_treatment_capacity_50de_19027f56_20261003",
        "operation_id": "capacity:planning_c_treatment_capacity_50de_19027f56_20261003",
        "source_digest": "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7",
    },
}
CONFORMANCE_DIGESTS = {
    "control_conformance_digest": "1b7fe4c370e3850fea06128308487ab91a93e54687d5b05660b189faae47bf6f",
    "treatment_conformance_digest": "227f3be41eda52ce6dec78564118dec997aaf92870fe877d5d29a40d96cef9ad",
    "differential_conformance_digest": "48f91fe4d9ea37cecd385fa095bba560db7a0b74944a1a049bbe43034bae67f0",
}
PINS = {
    "profile": ("c-current-profile-v1.json", "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"),
    "conformance_proposal": ("c-boundary-conformance-proposal-v1.json", "d6b7fcf91f285e28465b5286dfcdbcd7575fe5e331bdd33424ec60967dd5fb93"),
    "conformance_apply_result": ("c-boundary-conformance-apply-result-v1.json", "b5dcb07fa9db864b1f421322541441a8bb20584d7f6658889d24ebb75f0cdc40"),
    "paired_conformance_milestone": ("c-paired-conformance-milestone.json", "26678f1e0940f03fa51813c5656b890f3ca98ace88db5e95187714a766ad57bc"),
    "parent_cost_audit": ("c-all-probes-parent-cost-audit.json", "649af87a116e5dee11404e0cc351b29337015bb50db6bf593b8930a604bbda8a"),
    "callback_composition": (
        "c-qualification-callback-composition.py",
        "11cd96ce19c11019482664c46461ab7f96ca575539de6f3ee3ad835c20fea060",
    ),
    "workbook_producer": (
        "b-native-workbook-producer-final.py",
        "4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d",
    ),
    "materializer": (
        "c-workbook-qualification-materialize-20261003.py",
        "4513d7d7299c04205fd7924c75277f12091412342d475d2773a5d6f61ff0978b",
    ),
}
DERIVED_INPUTS = {
    "materialization_plan_review": "c-workbook-qualification-materialization-plan-review-v2.json",
    "materialization_request_review": "c-workbook-qualification-materialization-request-review-v2.json",
    "materialization_result": "c-workbook-qualification-materialization-result.json",
    **{f"{role}_{suffix}": item[suffix] for role, item in CAPACITY_BOOTSTRAP.items()
       for suffix in ("request", "result")},
}
OUTPUT = STAGE / "c-workbook-qualification-plan-proposal.json"
STARTED = STAGE / "c-workbook-qualification-plan-proposal-started.json"
RESULT = STAGE / "c-workbook-qualification-plan-proposal-result.json"


def _sha(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _write_once(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())


def _atomic_json(path: Path, value: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, sort_keys=True, indent=2)
        stream.write("\n")
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"expected JSON object in {path.name}")
    return value


def _verify_files() -> dict[str, str]:
    actual: dict[str, str] = {}
    for label, (filename, expected) in PINS.items():
        path = STAGE / filename
        _require(path.resolve(strict=True).parent == STAGE, f"pinned input escaped stage: {filename}")
        actual[label] = _sha(path)
        if expected is not None:
            _require(actual[label] == expected, f"pinned input changed: {filename}")
    for label, filename in DERIVED_INPUTS.items():
        path = STAGE / filename
        _require(path.resolve(strict=True).parent == STAGE, f"derived input escaped stage: {filename}")
        actual[label] = _sha(path)
    return actual


def _verify_canonical_identity() -> dict[str, Any]:
    _require(MANIFEST.is_file() and not MANIFEST.is_symlink(), "canonical manifest identity changed")
    _require(_sha(MANIFEST) == MANIFEST_SHA256, "canonical manifest digest changed")
    _require(DATABASE.is_file() and not DATABASE.is_symlink(), "canonical database identity changed")
    stat = DATABASE.stat()
    _require((stat.st_dev, stat.st_ino) == (DATABASE_DEVICE, DATABASE_INODE),
             "canonical database device/inode changed")
    manifest = _json(MANIFEST)
    _require(manifest.get("database") == str(DATABASE), "manifest database target changed")
    return {
        "manifest_sha256": MANIFEST_SHA256,
        "database_device": DATABASE_DEVICE,
        "database_inode": DATABASE_INODE,
    }


def _capacity_bootstrap_audit(repository: Any, pins: dict[str, str]) -> dict[str, Any]:
    """Resolve historical capacity observations without charging them again."""
    from aeep.assessment.models import AssessmentOperation, content_digest

    operations: list[dict[str, Any]] = []
    for role, expected in CAPACITY_BOOTSTRAP.items():
        wrapper = _json(STAGE / expected["request"])
        result = _json(STAGE / expected["result"])
        request = wrapper.get("request")
        _require(isinstance(request, dict)
                 and request.get("plan_id") == expected["request_id"]
                 and request.get("authorization_id") == "onboarding"
                 and wrapper.get("operation_id") == expected["operation_id"],
                 f"{role} capacity request identity differs")
        _require(result.get("status") == "passed"
                 and result.get("source_digest") == expected["source_digest"]
                 and result.get("plan_id") == expected["request_id"]
                 and result.get("operation_id") == expected["operation_id"]
                 and result.get("request_digest") == content_digest(request)
                 and result.get("model_turns") == 0
                 and result.get("cash_ceiling_usd") == 0
                 and result.get("cleanup_confirmed") is True
                 and result.get("replay_allowed") is False,
                 f"{role} capacity result does not pass its exact report-local request")

        stored_request = repository.get("planning_request", expected["request_id"])
        _require(content_digest(stored_request) == content_digest(request),
                 f"{role} capacity planning request differs from canonical storage")
        start = AssessmentOperation.model_validate(
            repository.get("operation_start", expected["operation_id"])
        )
        measurement = AssessmentOperation.model_validate(
            repository.get("operation_measurement", expected["operation_id"])
        )
        _require(start.plan_id == measurement.plan_id == expected["request_id"]
                 and measurement.operation_id == expected["operation_id"]
                 and measurement.stage == "capacity_introspection"
                 and measurement.elapsed_seconds is not None
                 and math.isfinite(measurement.elapsed_seconds)
                 and measurement.elapsed_seconds >= 0
                 and content_digest(measurement) == result.get("operation_measurement_digest"),
                 f"{role} capacity operation measurement differs from canonical evidence")
        with repository.store._lock:
            state = repository.store._connection.execute(
                "SELECT grant_id,state FROM assessment_operations WHERE id=?",
                (expected["operation_id"],),
            ).fetchone()
        _require(state is not None and state[0] == "onboarding" and state[1] == "complete",
                 f"{role} capacity operation is not complete on the shared onboarding grant")
        operations.append({
            "role": role,
            "request_path": expected["request"],
            "request_sha256": pins[f"{role}_request"],
            "request_id": expected["request_id"],
            "result_path": expected["result"],
            "result_sha256": pins[f"{role}_result"],
            "operation_id": expected["operation_id"],
            "operation_measurement_digest": content_digest(measurement),
            "elapsed_seconds": measurement.elapsed_seconds,
            "cpu_ms": measurement.resources.cpu_ms if measurement.resources is not None else None,
            "cpu_measurement_status": "measured" if measurement.resources is not None
            and measurement.resources.cpu_ms is not None else "unavailable",
            "grant_id": state[0],
            "operation_state": state[1],
            "already_charged": True,
        })
    return {
        "schema_version": "c.workbook-qualification-capacity-bootstrap-cost-audit.v1",
        "status": "passed",
        "source_digest": SOURCE,
        "ordinary_plan_ledger_inclusion": False,
        "ordinary_campaign_allowance_addition": False,
        "same_grant": "onboarding",
        "operations": operations,
        "already_charged_elapsed_seconds": sum(
            item["elapsed_seconds"] for item in operations
        ),
        "already_charged_cpu_ms": sum(
            item["cpu_ms"] for item in operations
        ) if all(item["cpu_ms"] is not None for item in operations) else None,
        "resource_coverage_limitation": (
            "CPU measurement remains unavailable for operations whose canonical "
            "operation_measurement has no ResourceVector."
        ),
        "whole_system_cost_complete": False,
    }


def _safe_spec(router: Any, value: dict[str, Any]) -> Any:
    from aeep.models import ExecutorSpec
    from aeep.qualification import behavior_fingerprint

    spec = ExecutorSpec.model_validate(value)
    if router.registry.contains(spec.id):
        existing = router.registry.get(spec.id)
        _require(behavior_fingerprint(existing) == behavior_fingerprint(spec),
                 f"registered executor differs from reviewed profile: {spec.id}")
    else:
        router.register(spec)
    return spec


async def _prepare() -> dict[str, Any]:
    sys.path.insert(0, str(ROOT / "src"))
    from aeep.assessment.boundary import require_differential, require_managed_boundaries
    from aeep.assessment.models import (
        AssessmentAuthorization,
        AssessmentEnvironment,
        AssessmentScopeAmendment,
        DifferentialEnvironment,
        IncrementalExperiment,
        RecipeCaseSet,
        UtilityPolicy,
        content_digest,
    )
    from aeep.assessment.service import AssessmentService
    from aeep.assessment.verification import verification_source_digest
    from aeep.router import Router

    pins = _verify_files()
    canonical_identity = _verify_canonical_identity()
    _require(verification_source_digest(ROOT) == SOURCE, "repository source differs from frozen C profile")
    profile = _json(STAGE / PINS["profile"][0])
    plan_review = _json(STAGE / DERIVED_INPUTS["materialization_plan_review"])
    request_review = _json(STAGE / DERIVED_INPUTS["materialization_request_review"])
    materialized = _json(STAGE / DERIVED_INPUTS["materialization_result"])
    milestone = _json(STAGE / PINS["paired_conformance_milestone"][0])
    conformance_proposal = _json(STAGE / PINS["conformance_proposal"][0])
    conformance_result = _json(STAGE / PINS["conformance_apply_result"][0])
    parent_cost_audit = _json(STAGE / PINS["parent_cost_audit"][0])

    _require(profile.get("source_digest") == SOURCE and plan_review.get("source_digest") == SOURCE,
             "source pin differs across reviewed inputs")
    _require(profile.get("component_digest") == COMPONENT_DIGEST
             and profile.get("differential_digest") == DIFFERENTIAL_DIGEST
             and profile.get("callback_implementation_digest") == CALLBACK_IMPLEMENTATION_DIGEST,
             "frozen component, differential or callback implementation differs")
    _require(profile.get("qualification_exposure") == "required"
             and profile.get("qualification_plan_created") is False,
             "profile is not a fresh required-exposure qualification profile")
    _require(milestone.get("status") == "paired_composed_conformance_passed"
             and milestone.get("source_digest") == SOURCE,
             "current paired conformance milestone is not passing")
    _require(conformance_result.get("status") == "passed"
             and conformance_result.get("source_digest") == SOURCE
             and conformance_result.get("proposal_sha256") == pins["conformance_proposal"]
             and conformance_result.get("atomic_commit") is True
             and conformance_result.get("grant_counters_unchanged") is True
             and conformance_result.get("model_turns") == 0
             and conformance_result.get("qualification") is False
             and conformance_result.get("admission") is False
             and conformance_result.get("value_trial") is False
             and conformance_proposal.get("source_digest") == SOURCE,
             "canonical composed conformance apply result is not bound to the pinned proposal")
    expected_conformance = {
        "control_conformance_digest": milestone["control_conformance_digest"],
        "treatment_conformance_digest": milestone["treatment_conformance_digest"],
        "differential_conformance_digest": milestone["paired_conformance_digest"],
    }
    _require(expected_conformance == CONFORMANCE_DIGESTS
             and all(conformance_result.get(key) == value
                     for key, value in expected_conformance.items()),
             "C milestone, apply result and frozen composed conformance digests differ")
    for review_doc in (plan_review, request_review):
        _require(review_doc.get("c_conformance") == {
            "proposal_path": "reports/v08/luna-docx-stage/c-boundary-conformance-proposal-v1.json",
            "proposal_sha256": pins["conformance_proposal"],
            "result_path": "reports/v08/luna-docx-stage/c-boundary-conformance-apply-result-v1.json",
            "result_sha256": pins["conformance_apply_result"],
            "digests": CONFORMANCE_DIGESTS,
        }, "materialization review does not bind the exact applied C conformance bundle")
    _require(parent_cost_audit.get("status") == "passed"
             and parent_cost_audit.get("source_digest") == SOURCE
             and parent_cost_audit.get("probe_count") == 30
             and parent_cost_audit.get("distinct_charged_requests") == 6,
             "C boundary parent-cost audit is incomplete")
    _require(materialized.get("status") == "passed"
             and materialized.get("source_unchanged") is True
             and materialized.get("profile_unchanged") is True
             and materialized.get("operation_settled") is True
             and materialized.get("model_turns") == 0
             and materialized.get("replay_allowed") is False,
             "fresh recipe materialization is not a settled one-shot result")
    _require(materialized.get("request_review_sha256") == pins["materialization_request_review"],
             "materialization result is not bound to the reviewed request")
    _require(materialized.get("request_id") == request_review.get("request", {}).get("plan_id")
             and request_review.get("runner_sha256") == pins["materializer"]
             and plan_review.get("runner_sha256") == pins["materializer"],
             "materialization request or producer helper differs from exact reviewed lineage")
    _require(materialized.get("seed") == plan_review.get("seed") == request_review.get("seed") == 2026100302,
             "materialization seed differs from its exact reviews")
    _require(materialized.get("case_count") == 141 and materialized.get("distinct_inputs") == 141
             and materialized.get("split_counts") == {"qualification": 8, "training": 28, "holdout": 105},
             "materialized case count or split contract differs")
    _require(materialized.get("environment_digest") == request_review.get("environment_digest"),
             "materialized environment differs from the exact request")
    _require(plan_review.get("profile_sha256") == pins["profile"]
             and request_review.get("profile_sha256") == pins["profile"],
             "materialization review does not bind the current profile")
    _require(plan_review.get("workbook_recipe_digest") == request_review.get("recipe_digest"),
             "workbook recipe differs between the reviewed requests")
    _require(request_review.get("subject_digest") == request_review.get("request", {}).get("subject_digest")
             and request_review.get("recipe_digest") == request_review.get("request", {}).get("recipe_digest"),
             "materialization subject or recipe binding is inconsistent")
    _require(request_review.get("environment_digest") == request_review.get("request", {}).get("environment_digest"),
             "materialization environment binding is inconsistent")

    composed = profile.get("component", {}).get("composed", {})
    _require(set(composed) >= {"control", "treatment"}, "profile omits a paired executor")
    control_raw = composed["control"]
    treatment_raw = composed["treatment"]
    for role, raw in (("control", control_raw), ("treatment", treatment_raw)):
        config = raw.get("config", {})
        constraints = config.get("model_constraints", {})
        invocation = config.get("invocation", {})
        _require(constraints.get("allowed_model_ids") == ["gpt-6-luna"]
                 and config.get("reasoning_efforts") == ["xhigh"],
                 f"{role} model or reasoning binding differs")
        _require(invocation.get("local_profile") == "capable_local",
                 f"{role} profile is not the reviewed capable-local environment")
    _require(control_raw.get("id") == "b.luna.discovery"
             and treatment_raw.get("id") == "b.luna.aeep",
             "executor identities differ from the frozen C roles")
    _require(control_raw["config"]["invocation"].get("mode") == "turn"
             and treatment_raw["config"]["invocation"].get("mode") == "dynamic_tool"
             and treatment_raw["config"]["invocation"].get("server") == "workbook"
             and treatment_raw["config"]["invocation"].get("tool") == "aeep_recipe_f468b36bc594"
             and treatment_raw["config"]["invocation"].get("exposure") == "required",
             "paired invocation contract differs from current C profile")

    differential = DifferentialEnvironment.model_validate(profile["differential"])
    _require(content_digest(differential) == profile.get("differential_digest"),
             "profile differential definition digest differs")
    environment = AssessmentEnvironment.model_validate(plan_review["environment"])
    _require(content_digest(environment) == materialized["environment_digest"],
             "reviewed campaign environment digest differs from materialization")
    _require(environment.conformance_digests == {
        control_raw["id"]: milestone["control_conformance_digest"],
        treatment_raw["id"]: milestone["treatment_conformance_digest"],
    }, "environment worker conformance digests differ from paired milestone")
    _require(environment.differential_conformance_digest == milestone["paired_conformance_digest"],
             "environment differential conformance differs from paired milestone")
    _require(profile.get("component_digest") == content_digest(profile.get("component"))
             and profile.get("differential_digest") == content_digest(profile.get("differential")),
             "profile component or differential digest binding is inconsistent")

    router = Router.from_manifest(MANIFEST)
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
    repository = service.repository
    plan: Any = None
    started = time.perf_counter()
    try:
        capacity_bootstrap_cost_audit = _capacity_bootstrap_audit(repository, pins)
        from aeep.assessment.models import AssessmentSubject

        control = _safe_spec(router, control_raw)
        treatment = _safe_spec(router, treatment_raw)
        from aeep.hosts.workers import binding_from_config

        control_binding = binding_from_config(control.managed_host_config().managed_worker)
        treatment_binding = binding_from_config(treatment.managed_host_config().managed_worker)
        _require(control_binding is not None and treatment_binding is not None,
                 "both profile roles must retain isolated managed-worker bindings")
        _require(treatment_binding.digest() == profile.get("selected_worker_digest"),
                 "selected treatment fingerprint differs from the frozen profile")
        _require(control_binding.digest() == "e15b7ee0ecabb077cc64ba80f724c739bc51bda8dc71d4038efc92f7678df345",
                 "control worker fingerprint differs from the frozen profile")
        specs = [control, treatment]
        env = AssessmentEnvironment.model_validate(
            repository.get("environment", materialized["environment_digest"])
        )
        _require(content_digest(env) == content_digest(environment),
                 "canonical environment differs from the reviewed campaign environment")
        if env.conformance_digests is None or env.differential_conformance_digest is None:
            raise RuntimeError("environment lacks current paired conformance bindings")
        identities = {
            spec.id: repository.get("boundary_conformance", env.conformance_digests[spec.id])["identity_digest"]
            for spec in specs
        }
        require_managed_boundaries(repository, env, specs, identities)

        subject = AssessmentSubject.model_validate(
            repository.get("subject", request_review["subject_digest"])
        )
        recipe = repository.get("recipe", request_review["recipe_digest"])
        case_set = RecipeCaseSet.model_validate(
            repository.get("recipe_case_set", materialized["request_id"])
        )
        _require(content_digest(case_set) == materialized["case_set_digest"]
                 and case_set.request_id == materialized["request_id"]
                 and case_set.seed == materialized["seed"]
                 and case_set.environment_digest == materialized["environment_digest"]
                 and case_set.recipe_digest == request_review["recipe_digest"],
                 "canonical recipe case set differs from its one-shot materialization result")
        _require(recipe.get("capability") == control.capability == treatment.capability
                 and request_review["recipe_digest"] == plan_review["workbook_recipe_digest"],
                 "reviewed workbook recipe and paired executor task contracts differ")

        router.managed_hosts.configure(
            specs, principal_salt=router.store.host_principal_key,
            manifest_directory=router.manifest_path.parent,
        )
        utility = UtilityPolicy(
            benefit_dimensions=["wall_time_ms"],
            guardrail_dimensions=["wall_time_ms"],
            minimum_resource_benefit=0.10,
            minimum_success_gain=0.05,
            maximum_resource_regression=0.10,
            family_error_rate=0.05,
        )
        experiment = IncrementalExperiment(
            stage="qualification", exposure="required",
            environment=differential, utility=utility,
        )
        from aeep.assessment.comparison import choices

        options = choices(subject, treatment, control, experiment=experiment)
        selected = options["recommended"]
        selected_option = next(item for item in options["choices"] if item["structure"] == selected)
        _require(selected_option["available"] is True,
                 "the current reviewed worker pair has no available comparison structure")
        _require(selected == "workflow",
                 "current managed-host required-exposure comparison no longer recommends workflow")

        with router.store._lock:
            existing = router.store._connection.execute(
                "SELECT 1 FROM assessment_records WHERE kind='plan' "
                "AND json_extract(payload_json, '$.recipe_case_set_digest')=? LIMIT 1",
                (materialized["case_set_digest"],),
            ).fetchone()
        _require(existing is None, "this exact case set already belongs to a plan; replay is forbidden")
        _require(not any(path.exists() for path in (OUTPUT, STARTED, RESULT)),
                 "proposal output or one-shot marker already exists; replay is forbidden")

        marker = {
            "schema_version": "c.workbook-qualification-plan-proposal-started.v1",
            "source_digest": SOURCE,
            "runner_sha256": _sha(SCRIPT),
            "materialization_result_sha256": pins["materialization_result"],
            "case_set_digest": materialized["case_set_digest"],
            "replay_allowed": False,
        }
        _write_once(STARTED, marker)

        plan = service.propose(
            subject_id=request_review["subject_digest"],
            family=request_review["recipe_digest"],
            candidate_id=treatment.id,
            baseline_id=control.id,
            authorization_id=request_review["request"]["authorization_id"],
            environment=env,
            seed=materialized["seed"],
            structure=selected,
            case_set_id=materialized["request_id"],
            experiment=experiment,
        )
        require_differential(repository, env, plan)
        _require(plan.recipe_case_set_digest == materialized["case_set_digest"],
                 "proposed plan references a different materialized case set")
        _require(plan.comparison is not None and plan.comparison.experiment is not None
                 and plan.comparison.experiment.stage == "qualification"
                 and plan.comparison.experiment.exposure == "required",
                 "proposed plan is not the required-exposure qualification")
        _require(len(plan.suite.cases) == 141
                 and sum(case.split.value == "qualification" for case in plan.suite.cases) == 8
                 and sum(case.split.value == "training" for case in plan.suite.cases) == 28
                 and sum(case.split.value == "holdout" for case in plan.suite.cases) == 105,
                 "proposed suite count or frozen split changed")

        preview = service.budget_preview(plan.plan_id)
        campaign_allowance = preview.get("campaign_allowance", {})
        _require(campaign_allowance.get("gaps") == []
                 and campaign_allowance.get("fits_remaining") is True,
                 "ordinary qualification budget preview has unresolved cost-lineage gaps or does not fit")
        upper_allowance = campaign_allowance.get("upper_allowance")
        _require(isinstance(upper_allowance, dict)
                 and all(isinstance(upper_allowance.get(field), (int, float))
                         and not isinstance(upper_allowance.get(field), bool)
                         and math.isfinite(float(upper_allowance[field]))
                         and float(upper_allowance[field]) >= 0
                         for field in ("operations", "model_turns", "elapsed_seconds"))
                 and str(upper_allowance.get("cash_usd")) in {"0", "0.0"},
                 "ordinary qualification budget preview lacks numeric zero-cash bounds")
        prior_operations = campaign_allowance.get("prior_operations")
        _require(isinstance(prior_operations, list)
                 and all(item.get("state") == "complete"
                         and item.get("elapsed_seconds") is not None
                         and math.isfinite(float(item["elapsed_seconds"]))
                         and float(item["elapsed_seconds"]) >= 0
                         for item in prior_operations),
                 "ordinary plan has an unresolved or unmeasured parent operation")
        digests = sorted({*plan.definition_digests, content_digest(plan), plan.subject_digest})
        grant = AssessmentAuthorization.model_validate(
            repository.get("authorization", plan.authorization_id)
        )
        amendment = AssessmentScopeAmendment(
            authorization_id=plan.authorization_id,
            authorization_digest=content_digest(grant),
            subject_digests=[plan.subject_digest],
            recipe_digests=[plan.recipe_digest],
            environment_digests=[plan.environment_digest],
            reviewed_digests=digests,
        )
        summary = {
            "schema_version": "c.workbook-qualification-plan-proposal.v1",
            "status": "proposal_prepared",
            "authority": "Delegated finite assessment-plan preparation; exact later review required before execution.",
            "source_digest": SOURCE,
            "runner_sha256": _sha(SCRIPT),
            "input_sha256": pins,
            "canonical_store": canonical_identity,
            "component_digest": profile["component_digest"],
            "selected_worker_digest": profile["selected_worker_digest"],
            "control_worker_digest": control_binding.digest(),
            "treatment_worker_digest": treatment_binding.digest(),
            "model": "gpt-6-luna",
            "reasoning_effort": "xhigh",
            "candidate_exposure": "required_for_qualification",
            "plan_id": plan.plan_id,
            "plan_digest": content_digest(plan),
            "subject_digest": plan.subject_digest,
            "recipe_digest": plan.recipe_digest,
            "environment_digest": plan.environment_digest,
            "case_set_digest": plan.recipe_case_set_digest,
            "materialization_request_id": materialized["request_id"],
            "seed": plan.suite.seed,
            "case_count": len(plan.suite.cases),
            "split_counts": {"qualification": 8, "training": 28, "holdout": 105},
            "structure": plan.comparison.structure if plan.comparison else None,
            "conformance_digests": env.conformance_digests,
            "differential_conformance_digest": env.differential_conformance_digest,
            "definition_digests": digests,
            "amendment": amendment.model_dump(mode="json"),
            "budget_preview": preview,
            "capacity_bootstrap_cost_audit": capacity_bootstrap_cost_audit,
            "boundary_parent_cost_audit": {
                "path": PINS["parent_cost_audit"][0],
                "sha256": pins["parent_cost_audit"],
                "status": parent_cost_audit["status"],
                "probe_count": parent_cost_audit["probe_count"],
                "distinct_charged_requests": parent_cost_audit["distinct_charged_requests"],
            },
            "blocked_reasons": plan.blocked_reasons,
            "boundary_and_differential_verified": True,
            "holdout_content_emitted": False,
            "case_definitions_embedded": False,
            "whole_system_cost_complete": False,
            "execution_authorized": False,
            "qualification": False,
            "admission": False,
            "not_enqueued": True,
            "preparation_elapsed_seconds": max(0.0, time.perf_counter() - started),
        }
        _atomic_json(OUTPUT, summary)
        _require(verification_source_digest(ROOT) == SOURCE, "repository source changed during plan preparation")
        _require(_sha(MANIFEST) == MANIFEST_SHA256, "canonical manifest changed during plan preparation")
        database_stat = DATABASE.stat()
        _require((database_stat.st_dev, database_stat.st_ino) == (DATABASE_DEVICE, DATABASE_INODE),
                 "canonical database identity changed during plan preparation")
        _require(_sha(STAGE / PINS["profile"][0]) == PINS["profile"][1],
                 "profile changed during plan preparation")
        _atomic_json(RESULT, {
            "schema_version": "c.workbook-qualification-plan-proposal-result.v1",
            "status": "passed" if not plan.blocked_reasons else "proposal_blocked",
            "source_digest": SOURCE,
            "runner_sha256": _sha(SCRIPT),
            "proposal_sha256": _sha(OUTPUT),
            "plan_id": plan.plan_id,
            "plan_digest": content_digest(plan),
            "case_set_digest": plan.recipe_case_set_digest,
            "budget_preview": preview,
            "capacity_bootstrap_cost_audit": capacity_bootstrap_cost_audit,
            "blocked_reasons": plan.blocked_reasons,
            "not_enqueued": True,
            "execution_authorized": False,
            "qualification": False,
            "admission": False,
            "replay_allowed": False,
        })
        return {key: summary[key] for key in (
            "status", "plan_id", "plan_digest", "case_set_digest", "case_count",
            "split_counts", "blocked_reasons", "not_enqueued", "admission",
        )}
    except BaseException as exc:
        if STARTED.exists() and not RESULT.exists():
            _atomic_json(RESULT, {
                "schema_version": "c.workbook-qualification-plan-proposal-result.v1",
                "status": "failed",
                "source_digest": SOURCE,
                "runner_sha256": _sha(SCRIPT),
                "exception_type": type(exc).__name__,
                "partial_plan_id": plan.plan_id if plan is not None else None,
                "replay_allowed": False,
            })
        raise
    finally:
        await router.close()


async def _main(argv: list[str]) -> None:
    _require(len(argv) == 2 and len(argv[1]) == 64
             and all(character in "0123456789abcdef" for character in argv[1]),
             "usage: prepare.py <exact-runner-sha256>")
    _require(_sha(SCRIPT) == argv[1], "runner bytes differ from supplied reviewed pin")
    result = await _prepare()
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    asyncio.run(_main(sys.argv))
