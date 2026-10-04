"""Prepare one exact ordinary workbook qualification proposal; never execute it."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
STAGE = Path(__file__).resolve().parent
SCRIPT = Path(__file__).resolve()
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
DATABASE_DEVICE = 16777231
DATABASE_INODE = 166293865
COMPONENT_DIGEST = "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d"
DIFFERENTIAL_DIGEST = "57af9b71f05881d4109f1c4b44594433816228df3fe368aaf65c7588b7cb4dbe"
CALLBACK_IMPLEMENTATION_DIGEST = "b55e60d7db97fd842922da6790656222d776467dab5216ca52acb046309683fb"
PINS = {
    "profile": ("b-current-profile-v2.json", "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"),
    "materialization_plan_review": (
        "b-workbook-qualification-materialization-plan-review.json",
        "3c43fa5414c96dfd787611a79498c88a10cadf9903424e9196884a4feb82ef93",
    ),
    "materialization_request_review": (
        "b-workbook-qualification-materialization-request-review.json",
        "d43a235e67026ea20ebfaa57fc18114a9d8d732751a8c2fd7d971cc69addaf12",
    ),
    "materialization_result": (
        "b-workbook-qualification-materialization-result.json",
        "8afdc3d94b0bcc8c34f801eaba6a6aeb0673511ffe7d3ffdde84586a0908b61e",
    ),
    "paired_conformance_milestone": (
        "b-paired-conformance-milestone.json",
        "62eb51f6d3ff65999309f7701917d2e37c5995061de3062e01a73a92b57a6c7f",
    ),
    "callback_composition": (
        "b-qualification-callback-composition.py",
        "82f602d92a19d8020931d344ad0ce05c7bcccdf9b64908b0723a786c250591e7",
    ),
    "workbook_producer": (
        "b-native-workbook-producer-final.py",
        "4d5db1fd761882f90bbaff5d1a6c392e2bab185a248f4a981399f95ee8aa539d",
    ),
    "materializer": (
        "b-workbook-qualification-materialize-20261003.py",
        "26adf6bd763230d83dc61194058f91aae2afdbfaeed3587d379dd08535ceaf75",
    ),
}
OUTPUT = STAGE / "b-workbook-qualification-plan-proposal.json"
STARTED = STAGE / "b-workbook-qualification-plan-proposal-started.json"
RESULT = STAGE / "b-workbook-qualification-plan-proposal-result.json"


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
        _require(actual[label] == expected, f"pinned input changed: {filename}")
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
    _require(verification_source_digest(ROOT) == SOURCE, "repository source differs from frozen B profile")
    profile = _json(STAGE / PINS["profile"][0])
    plan_review = _json(STAGE / PINS["materialization_plan_review"][0])
    request_review = _json(STAGE / PINS["materialization_request_review"][0])
    materialized = _json(STAGE / PINS["materialization_result"][0])
    milestone = _json(STAGE / PINS["paired_conformance_milestone"][0])

    _require(profile.get("source_digest") == SOURCE and plan_review.get("source_digest") == SOURCE,
             "source pin differs across reviewed inputs")
    _require(profile.get("component_digest") == COMPONENT_DIGEST
             and profile.get("differential_digest") == DIFFERENTIAL_DIGEST
             and profile.get("callback_implementation_digest") == CALLBACK_IMPLEMENTATION_DIGEST,
             "frozen component, differential or callback implementation differs")
    _require(profile.get("qualification_exposure") == "required"
             and profile.get("qualification_plan_created") is False,
             "profile is not a fresh required-exposure qualification profile")
    _require(milestone.get("status") == "paired_environment_conformance_passed"
             and milestone.get("source_digest") == SOURCE,
             "current paired conformance milestone is not passing")
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
    _require(materialized.get("seed") == plan_review.get("seed") == request_review.get("seed") == 2026100301,
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
             "executor identities differ from the frozen B roles")
    _require(control_raw["config"]["invocation"].get("mode") == "turn"
             and treatment_raw["config"]["invocation"].get("mode") == "dynamic_tool"
             and treatment_raw["config"]["invocation"].get("server") == "workbook"
             and treatment_raw["config"]["invocation"].get("tool") == "aeep_recipe_f468b36bc594"
             and treatment_raw["config"]["invocation"].get("exposure") == "required",
             "paired invocation contract differs from current B profile")

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
    _require(environment.differential_conformance_digest == milestone["differential_digest"],
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
            "schema_version": "b.workbook-qualification-plan-proposal-started.v1",
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
            "schema_version": "b.workbook-qualification-plan-proposal.v1",
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
            "schema_version": "b.workbook-qualification-plan-proposal-result.v1",
            "status": "passed" if not plan.blocked_reasons else "proposal_blocked",
            "source_digest": SOURCE,
            "runner_sha256": _sha(SCRIPT),
            "proposal_sha256": _sha(OUTPUT),
            "plan_id": plan.plan_id,
            "plan_digest": content_digest(plan),
            "case_set_digest": plan.recipe_case_set_digest,
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
                "schema_version": "b.workbook-qualification-plan-proposal-result.v1",
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
