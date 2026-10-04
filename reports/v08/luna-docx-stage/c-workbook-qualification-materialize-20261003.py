"""Prepare, approve, or execute one fresh offline workbook case materialization.

This report-local helper has no import-time effects. `prepare` stores an inert
request, `approve` commits only its exact reviewed scope bundle, and `execute`
uses that request once. It never starts an agent worker or makes a model call.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from aeep.assessment.extensions import materialize
from aeep.assessment.extensions import prepare as prepare_materialization
from aeep.assessment.identity import verify_subject
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentScopeAmendment,
    AssessmentSubject,
    RecipeDefinition,
    RecipeMaterializationRequest,
    RecipeRuntimeBinding,
    content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
DATABASE = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
PROFILE = OUT / "c-current-profile-v1.json"
CONFORMANCE_PROPOSAL = OUT / "c-boundary-conformance-proposal-v1.json"
CONFORMANCE_RESULT = OUT / "c-boundary-conformance-apply-result-v1.json"
PLAN_REVIEW = OUT / "c-workbook-qualification-materialization-plan-review.json"
REQUEST_REVIEW = OUT / "c-workbook-qualification-materialization-request-review.json"
PREPARE_MARKER = OUT / "c-workbook-qualification-materialization-prepare-started.json"
APPROVAL_MARKER = OUT / "c-workbook-qualification-materialization-approved.json"
APPROVAL_MARKER_START = OUT / "c-workbook-qualification-materialization-approval-started.json"
EXECUTION_MARKER = OUT / "c-workbook-qualification-materialization-started.json"
RESULT_PATH = OUT / "c-workbook-qualification-materialization-result.json"

SOURCE = "50de999eb8fcd15ffef056c6b67db9f1dc0e491a3b32a3f236bbd81cd52651f7"
PROFILE_SHA256 = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
CONFORMANCE_PROPOSAL_SHA256 = "d6b7fcf91f285e28465b5286dfcdbcd7575fe5e331bdd33424ec60967dd5fb93"
RECIPE_DIGEST = "a3e6a7a2954118ff1034fb53f65bc0ef6e61a94cfe9df082fdb7df4c0cbd9599"
SEED = 2026100302
SUBJECT_ID = "c-workbook-aeep-native-qualification-20261003"
WORKBOOK_IMAGE = "sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228"
CONTROL_WORKER_ID = "b.luna.discovery"
CONTROL_WORKER_DIGEST = "e15b7ee0ecabb077cc64ba80f724c739bc51bda8dc71d4038efc92f7678df345"
TREATMENT_WORKER_ID = "b.luna.aeep"
TREATMENT_WORKER_DIGEST = "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
MAX_OPERATIONS = 1
MAX_SECONDS = 35
MAX_MODEL_TURNS = 0
MAX_CASH_USD = 0
HOST_FREE_RESERVE_BYTES = 50 * 1024**3
SPLIT_COUNTS = {"qualification": 8, "training": 28, "holdout": 105}


def load_c_conformance() -> dict[str, Any]:
    for path in (CONFORMANCE_PROPOSAL, CONFORMANCE_RESULT):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("fresh C composed conformance proposal and apply result are required")
    proposal = json.loads(CONFORMANCE_PROPOSAL.read_text(encoding="utf-8"))
    result = json.loads(CONFORMANCE_RESULT.read_text(encoding="utf-8"))
    if (sha256_file(CONFORMANCE_PROPOSAL) != CONFORMANCE_PROPOSAL_SHA256
            or proposal.get("status") != "inert_proposal_unreviewed"
            or proposal.get("source_digest") != SOURCE
            or proposal.get("profile_sha256") != PROFILE_SHA256):
        raise RuntimeError("C composed conformance proposal differs from the reviewed frozen input")
    if (result.get("status") != "passed" or result.get("source_digest") != SOURCE
            or result.get("atomic_commit") is not True
            or result.get("grant_counters_unchanged") is not True
            or result.get("model_turns") != 0
            or result.get("qualification") is not False
            or result.get("admission") is not False
            or result.get("value_trial") is not False):
        raise RuntimeError("C composed conformance has not passed on the frozen source")
    if result.get("proposal_sha256") != sha256_file(CONFORMANCE_PROPOSAL):
        raise RuntimeError("C conformance apply result does not bind its exact proposal")
    digests = {
        "control_conformance_digest": result.get("control_conformance_digest"),
        "treatment_conformance_digest": result.get("treatment_conformance_digest"),
        "differential_conformance_digest": result.get("differential_conformance_digest"),
    }
    if any(not isinstance(value, str) or len(value) != 64
           or any(char not in "0123456789abcdef" for char in value)
           for value in digests.values()):
        raise RuntimeError("C conformance result is missing exact applied record digests")
    expected = {
        "control_conformance_digest": proposal["control"]["conformance_record"]["digest"],
        "treatment_conformance_digest": proposal["treatment"]["conformance_record"]["digest"],
        "differential_conformance_digest": proposal["differential_conformance"]["digest"],
    }
    if digests != expected:
        raise RuntimeError("C apply result digests differ from the exact composed proposal")
    return {
        "proposal_path": str(CONFORMANCE_PROPOSAL.relative_to(ROOT)),
        "proposal_sha256": sha256_file(CONFORMANCE_PROPOSAL),
        "result_path": str(CONFORMANCE_RESULT.relative_to(ROOT)),
        "result_sha256": sha256_file(CONFORMANCE_RESULT),
        "digests": digests,
    }


def verify_c_conformance(review: dict[str, Any]) -> None:
    observed = load_c_conformance()
    if observed != review.get("c_conformance"):
        raise RuntimeError("C composed conformance inputs changed after materialization review")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1_048_576):
            digest.update(chunk)
    return digest.hexdigest()


def require_source_and_profile() -> dict[str, Any]:
    if verification_source_digest(ROOT) != SOURCE:
        raise RuntimeError("frozen source digest changed")
    if (sha256_file(MANIFEST) != "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
            or DATABASE.is_symlink()
            or (DATABASE.stat().st_dev, DATABASE.stat().st_ino) != (16777231, 166293865)):
        raise RuntimeError("canonical manifest or database identity changed")
    if PROFILE.is_symlink() or sha256_file(PROFILE) != PROFILE_SHA256:
        raise RuntimeError("frozen current profile changed")
    profile = json.loads(PROFILE.read_text())
    if profile.get("source_digest") != SOURCE:
        raise RuntimeError("current profile is not bound to the frozen source")
    if profile.get("component_digest") != "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d":
        raise RuntimeError("composed worker component drift")
    if profile.get("differential_digest") != "57af9b71f05881d4109f1c4b44594433816228df3fe368aaf65c7588b7cb4dbe":
        raise RuntimeError("composed differential definition drift")
    if profile.get("callback_implementation_digest") != "b55e60d7db97fd842922da6790656222d776467dab5216ca52acb046309683fb":
        raise RuntimeError("callback implementation drift")
    if profile.get("qualification_exposure") != "required":
        raise RuntimeError("qualification invocation must remain required")
    composed = profile["component"]["composed"]
    if composed["control"].get("id") != CONTROL_WORKER_ID or composed["treatment"].get("id") != TREATMENT_WORKER_ID:
        raise RuntimeError("current worker roles changed")
    if set(composed.get("callback_bindings", {})) != {CONTROL_WORKER_DIGEST, TREATMENT_WORKER_DIGEST}:
        raise RuntimeError("callback bindings are incomplete")
    if set(composed.get("native_backends", {})) != {CONTROL_WORKER_DIGEST, TREATMENT_WORKER_DIGEST}:
        raise RuntimeError("native backend bindings are incomplete")
    return profile


def require_c_inputs_frozen() -> dict[str, Any]:
    profile = require_source_and_profile()
    load_c_conformance()
    return profile


def canonical_database_bytes() -> int:
    total = DATABASE.stat().st_size
    for suffix in ("-wal", "-shm"):
        path = Path(str(DATABASE) + suffix)
        if path.exists():
            total += path.stat().st_size
    return total


def _sqlite_file_components(path: Path) -> dict[str, int]:
    components: dict[str, int] = {}
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.is_symlink():
            raise RuntimeError("SQLite storage measurement encountered a symbolic link")
        components[candidate.name] = candidate.stat().st_size if candidate.exists() else 0
    return components


def _materialization_storage_bounds(
    router: Router, service: AssessmentService, request: RecipeMaterializationRequest,
    recipe: RecipeDefinition, amendment: AssessmentScopeAmendment,
    definitions: dict[str, Any],
) -> dict[str, Any]:
    """Measure the post-approval scoped copy and derive persisted-output bounds."""
    from aeep.assessment.models import RecipeCaseSet
    from aeep.benchmarking import BenchmarkCase, BenchmarkSplit
    from aeep.models import ActionRequest, ValidationKind, ValidationSpec

    if recipe.extension is None:
        raise RuntimeError("materialization recipe has no bounded generator")
    generator_limit = recipe.extension.generator.config.get("max_output_bytes")
    if isinstance(generator_limit, bool) or not isinstance(generator_limit, int) or generator_limit <= 0:
        raise RuntimeError("recipe generator has no finite declared output limit")

    raw_cases: list[dict[str, Any]] = []
    bound_cases: list[BenchmarkCase] = []
    variations = recipe.variations
    for split, count in ((BenchmarkSplit.QUALIFICATION, 8),
                         (BenchmarkSplit.TRAINING, 28),
                         (BenchmarkSplit.HOLDOUT, 105)):
        for index in range(count):
            variation = variations[index % len(variations)]
            family = f"workbook:{variation}"
            raw_cases.append({"input": {}, "output": {}, "variation": variation,
                              "template_family": family})
            bound_cases.append(BenchmarkCase(
                case_id=f"{request.plan_id}-{split.value}-{index}",
                split=split,
                variation=variation,
                template_family=family,
                action=ActionRequest(
                    action_id="act_" + "0" * 32,
                    capability=recipe.capability,
                    input={},
                ),
                validators=[ValidationSpec(
                    kind=ValidationKind.CALLBACK,
                    config={"name": "contained_recipe_" + "0" * 64, "expected": {}},
                )],
            ))
    raw_skeleton_bytes = len(json.dumps({"cases": raw_cases}).encode("utf-8"))
    case_set_skeleton = RecipeCaseSet(
        request_id=request.plan_id,
        recipe_digest=request.recipe_digest,
        environment_digest=request.environment_digest,
        seed=request.seed,
        cases=bound_cases,
    )
    stored_skeleton_bytes = len(case_set_skeleton.model_dump_json().encode("utf-8"))
    wrapper_bytes_upper = max(0, stored_skeleton_bytes - raw_skeleton_bytes)
    # One generator result is persisted in the scoped campaign receipt, and the
    # validated case set is persisted in the canonical assessment store. Each
    # is bounded by the declared generator output ceiling plus its measured
    # schema wrapper; the campaign database is one exact scoped snapshot copy.
    receipt_wrapper_bytes_upper = len(json.dumps({
        "request": {"seed": request.seed, "stages": [
            {"split": "qualification", "count": 8},
            {"split": "training", "count": 28},
            {"split": "holdout", "count": 105},
        ], "variations": recipe.variations},
        "operation_id": f"{request.plan_id}-generator",
        "stage": "recipe_generation",
    }).encode("utf-8"))
    campaign_receipt_bytes_upper = generator_limit + receipt_wrapper_bytes_upper
    canonical_receipt_bytes_upper = generator_limit + receipt_wrapper_bytes_upper
    # The case-set representation stores every generated input/output once and
    # validators retain the expected truth output once more. Thus the bounded
    # generator payload can appear at most twice in this canonical artifact.
    artifact_bytes_upper = 2 * generator_limit + wrapper_bytes_upper

    sample_path = OUT / "c-materialization-scoped-snapshot-sample.sqlite3"
    if sample_path.exists() or sample_path.is_symlink():
        raise RuntimeError("scoped storage sample already exists; preserve and inspect")
    original_authorization = AssessmentAuthorization.model_validate(
        service.repository.get("authorization", request.authorization_id)
    )
    bound = {
        content_digest(request), request.subject_digest, request.recipe_digest,
        request.mapping_digest, request.environment_digest, *request.definition_digests,
        content_digest(original_authorization), content_digest(amendment),
        *definitions.keys(),
    }
    snapshot = router.store.campaign_snapshot(sample_path, bound_digests=bound)
    try:
        # Model the exact reviewed rows that approve() will add, inside the
        # disposable scoped database. This captures their page growth without
        # changing the canonical store or adding arbitrary headroom.
        from aeep.assessment.repository import AssessmentRepository

        AssessmentRepository(snapshot).approve_bundle(amendment, definitions)
        before_close = _sqlite_file_components(sample_path)
    except BaseException:
        snapshot.close()
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(sample_path) + suffix)
            if candidate.exists() and not candidate.is_symlink():
                candidate.unlink()
        raise
    else:
        snapshot.close()
    after_close = _sqlite_file_components(sample_path)
    snapshot_bytes = max(sum(before_close.values()), sum(after_close.values()))
    for suffix in ("", "-wal", "-shm"):
        sample_file = Path(str(sample_path) + suffix)
        if sample_file.is_symlink():
            raise RuntimeError("scoped storage sample produced a symbolic link")
        sample_file.unlink(missing_ok=True)
    return {
        "snapshot_bytes_upper": snapshot_bytes,
        "snapshot_file_components_before_close": before_close,
        "snapshot_file_components_after_close": after_close,
        "snapshot_bytes_measurement_basis": "max(main+wal+shm while open after proposed review rows, checkpointed main+wal+shm after close)",
        "snapshot_count_upper": 1,  # One _campaign_router call in extensions.materialize -> invoke.
        "snapshot_copy_count_basis": {
            "materialize_invocations": 1,
            "invoke_campaign_router_calls_per_invocation": 1,
            "derived_copy_count": 1,
        },
        "campaign_receipt_bytes_upper": campaign_receipt_bytes_upper,
        "canonical_receipt_bytes_upper": canonical_receipt_bytes_upper,
        "receipt_wrapper_bytes_upper": receipt_wrapper_bytes_upper,
        "artifact_bytes_upper": artifact_bytes_upper,
        "generator_output_limit_bytes": generator_limit,
        "case_set_wrapper_bytes_upper": wrapper_bytes_upper,
    }


def request_seed_metadata(*, allowed_request_id: str | None = None) -> dict[str, int]:
    """Read only materialization-request metadata; never query a case set."""
    connection = sqlite3.connect(f"file:{DATABASE}?mode=ro", uri=True, timeout=5)
    try:
        connection.execute("PRAGMA query_only=ON")
        rows = connection.execute(
            "SELECT id,payload_json FROM assessment_records WHERE kind='recipe_materialization_request'"
        ).fetchall()
        matching = [identity for identity, payload in rows if json.loads(payload).get("seed") == SEED]
        if allowed_request_id is None and matching:
            raise RuntimeError("fresh materialization seed already exists; do not replay")
        if allowed_request_id is not None and matching != [allowed_request_id]:
            raise RuntimeError("seed metadata does not match the single reviewed request")
        return {"existing_request_count": len(rows), "matching_seed_count": len(matching)}
    finally:
        connection.close()


def grant_counters(router: Router) -> dict[str, Any]:
    row = router.store._connection.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?",
        ("onboarding",),
    ).fetchone()
    if row is None:
        raise RuntimeError("canonical onboarding grant is unavailable")
    return {
        "operations": row[0],
        "model_turns": row[1],
        "elapsed_seconds": float(row[2]),
        "cash_usd": str(row[3]),
    }


def subject_for(profile: dict[str, Any], conformance: dict[str, Any]) -> AssessmentSubject:
    composed = profile["component"]["composed"]
    declarations = {
        "workflow": "operator-composed native workbook AEEP workflow",
        "source_digest": SOURCE,
        "profile_sha256": PROFILE_SHA256,
        "composed_worker_component_digest": profile["component_digest"],
        "composed_differential_definition_digest": profile["differential_digest"],
        "control_conformance_digest": conformance["digests"]["control_conformance_digest"],
        "treatment_conformance_digest": conformance["digests"]["treatment_conformance_digest"],
        "paired_differential_conformance_digest": conformance["digests"]["differential_conformance_digest"],
        "candidate_exposure": profile["qualification_exposure"],
        "shared_physical_spreadsheets_skill_sha256": profile["shared_physical_skill_inventory"]["aeep"]["/opt/dependencies/plugin/skills/spreadsheets/SKILL.md"],
        "candidate_dynamic_tool_digest": profile["differential"]["candidate_dynamic_tools"]["dynamic:workbook:aeep_recipe_f468b36bc594"],
        "callback_implementation_digest": profile["callback_implementation_digest"],
        "workers": {
            "discovery": {
                "worker_id": CONTROL_WORKER_ID,
                "worker_digest": CONTROL_WORKER_DIGEST,
                "callback_binding_digest": composed["callback_bindings"][CONTROL_WORKER_DIGEST],
                "native_backend_digest": composed["native_backends"][CONTROL_WORKER_DIGEST],
            },
            "aeep": {
                "worker_id": TREATMENT_WORKER_ID,
                "worker_digest": TREATMENT_WORKER_DIGEST,
                "callback_binding_digest": composed["callback_bindings"][TREATMENT_WORKER_DIGEST],
                "native_backend_digest": composed["native_backends"][TREATMENT_WORKER_DIGEST],
            },
        },
    }
    return AssessmentSubject(
        subject_id=SUBJECT_ID,
        kind="command",
        location=str(PROFILE.resolve()),
        dependency_digests={"profile": PROFILE_SHA256},
        description=(
            "Qualification of the operator-composed native workbook AEEP workflow. "
            "Both arms retain the same physical Spreadsheets support; the AEEP callback "
            "is the reviewed candidate increment."
        ),
        declarations=declarations,
    )


def environment(conformance: dict[str, Any]) -> AssessmentEnvironment:
    return AssessmentEnvironment(
        environment_id="c-workbook-qualification-20261003",
        kind="container",
        identity={
            "purpose": "Offline workbook generation and grading; Luna/xhigh AEEP native callback qualification"
        },
        network=False,
        container_image=WORKBOOK_IMAGE,
        cpu_count=1,
        memory_mb=512,
        process_limit=64,
        container_runtime="/usr/local/bin/docker",
        container_socket="/Users/edwintse/.docker/run/docker.sock",
        read_only_roots=[],
        conformance_digests={
            CONTROL_WORKER_ID: conformance["digests"]["control_conformance_digest"],
            TREATMENT_WORKER_ID: conformance["digests"]["treatment_conformance_digest"],
        },
        differential_conformance_digest=conformance["digests"]["differential_conformance_digest"],
    )


def exact_review(path: Path, expected_sha: str) -> dict[str, Any]:
    if not path.is_file() or sha256_file(path) != expected_sha:
        raise RuntimeError("exact reviewed materialization bundle hash required")
    review = json.loads(path.read_text())
    verify_c_conformance(review)
    if review.get("runner_sha256") != sha256_file(Path(__file__)):
        raise RuntimeError("materialization helper changed after review")
    if verification_source_digest(ROOT) != SOURCE or sha256_file(PROFILE) != PROFILE_SHA256:
        raise RuntimeError("frozen source or profile changed")
    require_source_and_profile()
    return review


async def prepare() -> None:
    if PLAN_REVIEW.exists() or REQUEST_REVIEW.exists() or PREPARE_MARKER.exists():
        raise RuntimeError("existing preparation evidence must be preserved")
    profile = require_source_and_profile()
    conformance = load_c_conformance()
    seed_metadata = request_seed_metadata()
    recipe = workbook_recipe()
    recipe_digest = content_digest(recipe)
    if recipe_digest != RECIPE_DIGEST:
        raise RuntimeError("current workbook_recipe definition changed")

    router = Router.from_manifest(MANIFEST)
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
    repo = service.repository
    before = grant_counters(router)
    try:
        stored_recipe = RecipeDefinition.model_validate(repo.get("recipe", RECIPE_DIGEST))
        if content_digest(stored_recipe) != RECIPE_DIGEST:
            raise RuntimeError("canonical workbook recipe differs from workbook_recipe()")
        subject = subject_for(profile, conformance)
        verify_subject(subject)
        # This marker makes partial canonical definition preparation non-replayable.
        with PREPARE_MARKER.open("x") as stream:
            stream.write(json.dumps({"source_digest": SOURCE, "seed": SEED}) + "\n")
        subject_digest = repo.put("subject", subject.subject_id, subject)
        env = environment(conformance)
        request = prepare_materialization(
            service,
            subject_id=subject.subject_id,
            recipe_id=RECIPE_DIGEST,
            authorization_id="onboarding",
            environment=env,
            seed=SEED,
        )
        runtime = RecipeRuntimeBinding(dependencies=request.runtime_dependencies or {})
        runtime_digest = content_digest(runtime)
        definitions: dict[str, Any] = {
            subject_digest: subject.model_dump(mode="json"),
            RECIPE_DIGEST: stored_recipe.model_dump(mode="json"),
            content_digest(env): env.model_dump(mode="json"),
            content_digest(request): request.model_dump(mode="json"),
            runtime_digest: repo.get("recipe_runtime", runtime_digest),
        }
        original = AssessmentAuthorization.model_validate(repo.get("authorization", "onboarding"))
        amendment = AssessmentScopeAmendment(
            authorization_id="onboarding",
            authorization_digest=content_digest(original),
            subject_digests=[subject_digest],
            recipe_digests=[RECIPE_DIGEST],
            environment_digests=[content_digest(env)],
            reviewed_digests=sorted(definitions),
        )
        database_bytes_at_prepare = canonical_database_bytes()
        storage = _materialization_storage_bounds(
            router, service, request, stored_recipe, amendment, definitions,
        )
        storage_allowance = (
            storage["snapshot_count_upper"] * storage["snapshot_bytes_upper"]
            + storage["campaign_receipt_bytes_upper"]
            + storage["canonical_receipt_bytes_upper"]
            + storage["artifact_bytes_upper"]
        )
        after_prepare = grant_counters(router)
        unchanged = before == after_prepare
        review = {
            "schema_version": "c.workbook-qualification-materialization-review.v1",
            "purpose": "Fresh offline workbook case materialization for AEEP native callback qualification only",
            "source_digest": SOURCE,
            "profile_sha256": PROFILE_SHA256,
            "c_conformance": conformance,
            "runner_sha256": sha256_file(Path(__file__)),
            "seed": SEED,
            "seed_uniqueness_metadata": seed_metadata,
            "subject_digest": subject_digest,
            "recipe_digest": RECIPE_DIGEST,
            "environment_digest": content_digest(env),
            "request": request.model_dump(mode="json"),
            "definitions": definitions,
            "amendment": amendment.model_dump(mode="json"),
            "maximum_operations": MAX_OPERATIONS,
            "maximum_reserved_seconds": MAX_SECONDS,
            "maximum_model_turns": MAX_MODEL_TURNS,
            "maximum_cash_usd": MAX_CASH_USD,
            "split_counts": SPLIT_COUNTS,
            "database_bytes_at_prepare": database_bytes_at_prepare,
            **storage,
            "storage_allowance_bytes": storage_allowance,
            "host_free_reserve_bytes": HOST_FREE_RESERVE_BYTES,
            "image_pins": [WORKBOOK_IMAGE],
            "image_presence": "must be inspected before any later execution; build and pull are forbidden",
            "no_docker_inspection_or_pull": True,
            "no_worker_or_model_execution": True,
            "no_case_values_emitted": True,
            "grant_counters_unchanged_during_prepare": unchanged,
            "grant_before_prepare": before,
            "grant_after_prepare": after_prepare,
            "approval_committed": False,
            "execution_authorized": False,
        }
        if not unchanged:
            review["preparation_status"] = "blocked_grant_counter_changed"
        else:
            review["preparation_status"] = "inert_request_prepared"
        REQUEST_REVIEW.open("x").write(json.dumps(review, indent=2) + "\n")
        PLAN_REVIEW.open("x").write(
            json.dumps(
                {
                    "schema_version": "c.workbook-qualification-materialization-plan-review.v1",
                    "runner_sha256": sha256_file(Path(__file__)),
                    "source_digest": SOURCE,
                    "profile_sha256": PROFILE_SHA256,
                    "c_conformance": conformance,
                    "workbook_recipe_digest": RECIPE_DIGEST,
                    "environment": env.model_dump(mode="json"),
                    "paired_conformance_digest": conformance["digests"]["differential_conformance_digest"],
                    "seed": SEED,
                    "seed_uniqueness_metadata": seed_metadata,
                    "maximum_operations": MAX_OPERATIONS,
                    "maximum_reserved_seconds": MAX_SECONDS,
                    "maximum_model_turns": MAX_MODEL_TURNS,
                    "maximum_cash_usd": MAX_CASH_USD,
                    "split_counts": SPLIT_COUNTS,
                    "database_bytes_at_prepare": database_bytes_at_prepare,
                    **storage,
                    "storage_allowance_bytes": storage_allowance,
                    "execution_authorized": False,
                    "canonical_request_prepared": True,
                },
                indent=2,
            )
            + "\n"
        )
        print(json.dumps({"request_id": request.plan_id, "request_review_sha256": sha256_file(REQUEST_REVIEW)}))
    finally:
        await router.close()


async def approve(review_sha: str) -> None:
    require_c_inputs_frozen()
    review = exact_review(REQUEST_REVIEW, review_sha)
    if review.get("preparation_status") != "inert_request_prepared":
        raise RuntimeError("request preparation did not pass its inert checks")
    if APPROVAL_MARKER.exists() or APPROVAL_MARKER_START.exists() or EXECUTION_MARKER.exists():
        raise RuntimeError("approval or execution evidence already exists")
    router = Router.from_manifest(MANIFEST)
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
    repo = service.repository
    before = grant_counters(router)
    try:
        request = RecipeMaterializationRequest.model_validate(review["request"])
        if content_digest(request) != content_digest(repo.get("recipe_materialization_request", request.plan_id)):
            raise RuntimeError("canonical request differs from exact reviewed request")
        if content_digest(workbook_recipe()) != RECIPE_DIGEST:
            raise RuntimeError("workbook recipe drift before approval")
        with APPROVAL_MARKER_START.open("x") as stream:
            stream.write(json.dumps({"review_sha256": review_sha}) + "\n")
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review["amendment"]), review["definitions"])
        repo.authorize(request)
        after = grant_counters(router)
        if before != after:
            raise RuntimeError("approval unexpectedly changed grant counters")
        with APPROVAL_MARKER.open("x") as stream:
            stream.write(json.dumps({"review_sha256": review_sha, "grant_before": before, "grant_after": after}) + "\n")
        print(json.dumps({"approval_committed": True, "grant_counters_unchanged": True}))
    finally:
        await router.close()


async def execute(review_sha: str) -> None:
    require_c_inputs_frozen()
    review = exact_review(REQUEST_REVIEW, review_sha)
    if not APPROVAL_MARKER.is_file() or json.loads(APPROVAL_MARKER.read_text()).get("review_sha256") != review_sha:
        raise RuntimeError("exact request bundle has not been approved")
    if EXECUTION_MARKER.exists() or RESULT_PATH.exists():
        raise RuntimeError("one-shot execution evidence already exists; preserve it")
    if shutil.disk_usage(ROOT).free < HOST_FREE_RESERVE_BYTES + review["storage_allowance_bytes"]:
        raise RuntimeError("host free-space reserve plus reviewed storage allowance is unavailable")
    require_source_and_profile()
    router = Router.from_manifest(MANIFEST)
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3/.aeep/assessments")
    repo = service.repository
    request = RecipeMaterializationRequest.model_validate(review["request"])
    current_database_bytes = canonical_database_bytes()
    try:
        current_storage = _materialization_storage_bounds(
            router, service, request, RecipeDefinition.model_validate(
                repo.get("recipe", request.recipe_digest)
            ), AssessmentScopeAmendment.model_validate(review["amendment"]),
            review["definitions"],
        )
        for key in ("snapshot_count_upper", "artifact_bytes_upper", "campaign_receipt_bytes_upper",
                    "canonical_receipt_bytes_upper", "case_set_wrapper_bytes_upper",
                    "receipt_wrapper_bytes_upper", "generator_output_limit_bytes",
                    "snapshot_copy_count_basis"):
            if current_storage[key] != review[key]:
                raise RuntimeError(f"materialization storage derivation changed before execution: {key}")
        if current_storage["snapshot_bytes_upper"] > review["snapshot_bytes_upper"]:
            raise RuntimeError("current scoped snapshot exceeds the reviewed measured basis")
        if shutil.disk_usage(ROOT).free < HOST_FREE_RESERVE_BYTES + review["storage_allowance_bytes"]:
            raise RuntimeError("host free-space reserve plus reviewed storage allowance is unavailable")
    except BaseException:
        await router.close()
        raise
    before = grant_counters(router)
    harness_start = time.perf_counter()
    materialize_start: float | None = None
    result: dict[str, Any] = {
        "schema_version": "c.workbook-qualification-materialization-result.v1",
        "request_id": request.plan_id,
        "request_review_sha256": review_sha,
        "source_digest": SOURCE,
        "seed": SEED,
        "model_turns": 0,
        "replay_allowed": False,
        "operation_id": f"{request.plan_id}-generator",
        "canonical_database_bytes_at_execute": current_database_bytes,
        "scoped_snapshot_bytes_at_execute": current_storage["snapshot_bytes_upper"],
    }
    try:
        repo.authorize(request)
        if content_digest(workbook_recipe()) != RECIPE_DIGEST:
            raise RuntimeError("workbook recipe drift before generation")
        if content_digest(repo.get("recipe_materialization_request", request.plan_id)) != content_digest(request):
            raise RuntimeError("canonical request changed after review")
        if router.store._connection.execute(
            "SELECT 1 FROM assessment_records WHERE kind='recipe_case_set' AND id=?",
            (request.plan_id,),
        ).fetchone():
            raise RuntimeError("case set already exists; do not replay")
        if router.store._connection.execute(
            "SELECT 1 FROM assessment_operations WHERE id=?", (result["operation_id"],)
        ).fetchone():
            raise RuntimeError("generator operation already exists; do not replay")
        if request_seed_metadata(allowed_request_id=request.plan_id).get("matching_seed_count") != 1:
            raise RuntimeError("seed metadata check did not confirm the unique reviewed request")
        with EXECUTION_MARKER.open("x") as stream:
            stream.write(json.dumps({"review_sha256": review_sha, "request_id": request.plan_id}) + "\n")
        materialize_start = time.perf_counter()
        cases = await materialize(service, request.plan_id)
        result["materializer_call_wall_seconds"] = time.perf_counter() - materialize_start
        counts = {name: sum(case.split.value == name for case in cases.cases) for name in SPLIT_COUNTS}
        distinct_inputs = len({content_digest(case.action.input) for case in cases.cases})
        if counts != SPLIT_COUNTS or len(cases.cases) != 141 or distinct_inputs != 141:
            raise RuntimeError("generated case-count/distinctness contract failed")
        result.update(
            status="passed",
            case_set_digest=content_digest(cases),
            case_count=len(cases.cases),
            split_counts=counts,
            distinct_inputs=distinct_inputs,
            environment_digest=request.environment_digest,
        )
    except BaseException as exc:
        result.update(status="failed", error_type=type(exc).__name__)
    finally:
        operation = router.store._connection.execute(
            "SELECT state FROM assessment_operations WHERE id=?", (result["operation_id"],)
        ).fetchone()
        result["operation_state"] = operation[0] if operation else "absent"
        if materialize_start is not None and "materializer_call_wall_seconds" not in result:
            result["materializer_call_wall_seconds"] = time.perf_counter() - materialize_start
        result["harness_wall_seconds"] = time.perf_counter() - harness_start
        result["source_unchanged"] = verification_source_digest(ROOT) == SOURCE
        result["profile_unchanged"] = sha256_file(PROFILE) == PROFILE_SHA256
        result["grant_before"] = before
        result["grant_after"] = grant_counters(router)
        result["operation_settled"] = result["operation_state"] in {"complete", "failed"}
        result["coordinator_closed"] = False
        result["container_cleanup_confirmation"] = "not independently observed by this helper"
        if (not result["source_unchanged"] or not result["profile_unchanged"]
                or not result["operation_settled"]
                or (result.get("status") == "passed" and result["operation_state"] != "complete")):
            result["status"] = "failed"
        try:
            await router.close()
            result["coordinator_closed"] = True
        except BaseException as exc:
            result["cleanup_error_type"] = type(exc).__name__
            result["status"] = "failed"
        result["whole_system_cost_complete"] = False
        result["accounting_note"] = "Grant and canonical operation accounting only; no claim of whole-system resource completeness."
        with RESULT_PATH.open("x") as stream:
            stream.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


def main() -> None:
    require_c_inputs_frozen()
    if len(sys.argv) == 2 and sys.argv[1] == "prepare":
        asyncio.run(prepare())
        return
    if len(sys.argv) == 3 and sys.argv[1] in {"approve", "execute"}:
        if len(sys.argv[2]) != 64 or any(char not in "0123456789abcdef" for char in sys.argv[2]):
            raise RuntimeError("pass the exact 64-character request-review SHA-256")
        asyncio.run(approve(sys.argv[2]) if sys.argv[1] == "approve" else execute(sys.argv[2]))
        return
    raise SystemExit("usage: script.py prepare | approve <request-review-sha256> | execute <request-review-sha256>")


if __name__ == "__main__":
    main()
