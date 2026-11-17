"""Bind and verify four retained references and faults on the ordinary native observer."""

import argparse
import asyncio
import json
import shutil
from contextlib import closing
from pathlib import Path

from check_linux_install import DOCKER, HERE, ROOT, SOCKET, WORK, docker, get, put
from reconcile_repository_grader_evidence import bound_json, index, require, verify_receipt
from repository_offline_pair_batch import context, verify_probe

import aeep
from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.extensions import invoke
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentScopeAmendment,
    AssessmentSubject,
    RecipeMaterializationRequest,
    RecipeRuntimeBinding,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import (
    RepositorySuiteCase,
    grade_suite_output,
    repository_suite_recipe,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt
from aeep.router import Router
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_evidence import open_store

NAME = "c13-gzip-migrated-graders-20261116"
FROZEN = WORK / "transport-grader-current-source"
SOURCE = "9710ea4f129d21affc0dcbe85e2d0bc432a41e5ec9ee8899b68df8a834959786"
HISTORICAL = HERE.parent / "repository-screening-curation-20261022"
BASE = ROOT.parent / "aeep-agent-router/.aeep/live-review-v3"
DATABASE = BASE / "aeep.sqlite3"
OPERATIONS = BASE / ".aeep/assessments"
REVIEW = HERE / "migrated-grader-operation-review.json"
APPROVAL = WORK / "migrated-grader-approval.json"
RUN = WORK / NAME
CARRIER = "sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7"
HISTORICAL_REVIEW = "4cfc412d5a08b93220bc318e55b85167c870d049f2350c983eda68a1cf18bb0b"
TARGETS = {
    "fox-it__dissect.cstruct-120-single-file-scope": ("fox-it__dissect.cstruct-120", "dissect"),
    "kaste__mockito-python-93-single-file-scope": ("kaste__mockito-python-93", "mockito"),
}
SHAPE_FIXTURE = "collective__icalendar-880-native-identity-audit"
DISK_FLOOR = 50 * 1024**3


def settled_receipt(directory, spec, request, ledger, operation, payload):
    path = directory / request["plan_id"] / "recipe-operations" / (operation + ".sqlite3")
    with closing(open_store(str(path))) as store:
        with store._lock:
            row = store._connection.execute("SELECT payload_json FROM receipts").fetchall()
        require(len(row) == 1, "expected a single ordinary execution receipt")
        receipt = ExecutionReceipt.model_validate_json(row[0][0])
    name = container_name(receipt.metadata["attempt_id"])
    require(not docker("ps", "-aq", "--filter", f"name=^/{name}$"), "container cleanup uncertain")
    return verify_receipt(ledger, directory, request, {
        "operation_id": operation,
        "receipt_id": receipt.receipt_id,
        "receipt_ref": content_digest(receipt),
        "container_name": name,
        "container_removed": True,
        "environment_digest": request["environment_digest"],
    }, spec, payload)


async def bind_observations(cases, ledger, old_review, old_result, spec, environment):
    assets = old_review["assets"]
    variants_path = ROOT / old_review["variants_file"]
    variants = bound_json(variants_path, assets[str(variants_path)])
    observations = index(old_result["observations"], "name")
    receipts = index(old_result["receipts"], "name")
    grade_rows = index(old_result["results"], "case_id")
    old_request = old_review["request"]
    old_recipe = ledger.get("recipe", old_request["recipe_digest"])
    old_spec = type(spec).model_validate(old_recipe["extension"]["grader"])
    executor = ContainerExecutor(environment)
    bindings = []
    roles = {}
    for case_id, (legacy_id, module) in TARGETS.items():
        case = cases[case_id]
        truth = case.truth.model_dump(mode="json")
        grades = index(grade_rows[legacy_id]["variants"], "variant")
        require(grade_rows[legacy_id]["reproduction_eligible"], "historical case was not reproduced")
        require(len(case.fault_outputs) == 1, "changed fault inventory")
        for role, artifact in (("reference", json.loads(case.reference.read())), ("counterexample", case.fault_outputs[0])):
            name = legacy_id + "-" + role
            observation = observations[name]
            raw = bound_json(HISTORICAL / observation["raw_file"], observation["raw_sha256"])
            require(
                raw["name"] == name and raw["operation_id"] == observation["operation_id"] == receipts[name]["operation_id"]
                and raw["execution_error_type"] is None and grades[role]["passed"],
                "retained observation differs or did not complete",
            )
            expected = raw["output"]
            require(
                set(expected["statuses"]) == set(truth["fail_to_pass"] + truth["pass_to_pass"])
                and set(expected["statuses"].values()) <= {"PASSED", "FAILED"},
                "historical observation lacks complete test dispositions",
            )
            legacy = next(row for row in variants if row["case"] == legacy_id and row["variant"] == role)
            legacy_path = ROOT / legacy["payload"]
            require(assets[str(legacy_path)] == legacy["sha256"], "historical payload was not reviewed")
            payload = bound_json(legacy_path, legacy["sha256"])
            retained = verify_receipt(ledger, OPERATIONS, old_request, receipts[name], old_spec, payload)
            operation = f"{NAME}:{legacy_id}:{role}"

            captured = []

            async def observe(current, captured=captured, expected=expected):
                captured.append(current)
                return expected

            score = await grade_suite_output(case.input.model_dump(mode="json"), truth, artifact, observe)
            require(score.model_dump(mode="json") == grades[role]["grade"] and len(captured) == 1, "retained score did not transfer")
            current = captured[0]
            require(
                current == {**payload, "pytest_plugins": [], "source_modules": [module]}
                and verify_probe(expected, current, expected["statuses"], expected["exit_code"]),
                "migration changed protected source, wheel inputs, required test outcomes or import guards",
            )
            argv, container = executor.command(context(spec, operation, current))
            require(
                {arg for arg in argv if arg.startswith("type=bind,")}
                == {f"type=bind,src={FROZEN / 'src'},dst={FROZEN / 'src'},readonly"}
                and argv[argv.index("--network") + 1] == "none" and argv[argv.index("--user") + 1] == "65534:65534"
                and {"--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i"} <= set(argv),
                "ordinary observer containment changed",
            )
            bindings.append({
                "operation_id": operation, "case_id": case_id, "role": role,
                "source_revision": case.source_revision, "preflight_argv_sha256": content_digest({"argv": argv}),
                "preflight_container": container, "archive_sha256": current["archive_sha256"],
                "payload_sha256": content_digest(current), "payload_bytes": len(json.dumps(current).encode()),
                "historical_observation_sha256": observation["raw_sha256"],
                "historical_receipt": retained, "expected_outcome_sha256": content_digest(expected),
                "required_test_count": len(expected["statuses"]), "source_modules": [module],
            })
            roles[operation] = (case, artifact, expected, score)
    return bindings, roles


def project_source():
    # The entire imported coordinator source and the ordinary observer assets are pinned.
    require(Path(aeep.__file__).resolve().parents[2] == FROZEN, "load the frozen source via PYTHONPATH")
    require(verification_source_digest(FROZEN) == SOURCE, "frozen assessment source changed")
    require(shutil.disk_usage(WORK).free >= DISK_FLOOR, "host storage reserve reached")


async def prepare(ledger):
    project_source()
    image = json.loads(docker("image", "inspect", "--format", "{{json .}}", CARRIER))
    cfg = image["Config"]
    require(
        image["Id"] == CARRIER and (image["Os"], image["Architecture"], cfg["User"]) == ("linux", "arm64", "65534:65534")
        and not cfg.get("Volumes") and not cfg.get("Healthcheck"),
        "retained image boundary changed",
    )
    preparation = get(HERE / "formal-transport-preparation.json")
    pool = bound_json(ROOT / preparation["prepared_pool_relative_path"], preparation["prepared_pool_sha256"])
    by_id = index(pool, "independent_case_id")
    cases = {case_id: RepositorySuiteCase.model_validate(by_id[case_id]) for case_id in (*TARGETS, SHAPE_FIXTURE)}
    # The third literal selects the native observer. It receives no operation.
    recipe = repository_suite_recipe([
        case.model_copy(update={"split": "development", "used_for_development": True}) for case in cases.values()
    ])
    spec = recipe.extension.grader
    compile(spec.config["argv"][-1], "<frozen ordinary native grader>", "exec")
    environment = AssessmentEnvironment(
        environment_id=NAME, identity={"source": SOURCE}, kind="container", container_image=CARRIER,
        container_runtime=DOCKER, container_socket=SOCKET, container_tmpfs_mb=64, memory_mb=512, process_limit=96,
    )
    historical_review = bound_json(HISTORICAL / "operation-review.json", HISTORICAL_REVIEW)
    old_result = get(HISTORICAL / "execution-result.json")
    require(
        old_result["review_sha256"] == HISTORICAL_REVIEW
        and all(old_result[key] is True for key in ("batch_completed", "elapsed_complete", "source_unchanged", "containers_removed")),
        "historical batch binding did not close",
    )
    calls, roles = await bind_observations(cases, ledger, historical_review, old_result, spec, environment)
    require(len(calls) == 4, "exact four-operation limit changed")
    subject = AssessmentSubject(
        subject_id=NAME, kind="command", location=str(FROZEN),
        dependency_digests={"src/aeep/assessment/repository_suites.py": file_digest(FROZEN / "src/aeep/assessment/repository_suites.py")},
        description="Offline verification of two migrated prospective repository graders.",
    )
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    request = RecipeMaterializationRequest(
        schema_version="assessment.recipe-materialization.v2", plan_id=NAME,
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
        environment_digest=content_digest(environment), authorization_id="onboarding",
        definition_digests=[content_digest(v) for v in (recipe, environment, runtime)], seed=0,
        runtime_dependencies=runtime.dependencies,
    )
    root_grant = ledger.get("authorization", request.authorization_id)
    grant = ledger.current_grant(request.authorization_id)
    disclosure = {
        "schema_version": "aeep.c13.migrated-graders-review.v1",
        "authority_required": "Exact approval for four protected repeats on the current observer.",
        "source": SOURCE, "docker_sha256": file_digest(Path(DOCKER)), "image": CARRIER, "layers": image["RootFS"]["Layers"],
        "operation_root": str(OPERATIONS), "ledger": str(DATABASE),
        "driver_files": {p.name: file_digest(p) for p in (
            Path(__file__), HERE / "check_linux_install.py", HERE / "reconcile_repository_grader_evidence.py",
            HERE / "audit_formal_inputs.py", HERE / "repository_offline_pair_batch.py", HERE / "stage_repository_transport.py",
        )},
        "pool_sha256": preparation["prepared_pool_sha256"], "historical_review_sha256": HISTORICAL_REVIEW,
        "historical_execution_result_sha256": file_digest(HISTORICAL / "execution-result.json"),
        "root_grant_sha256": content_digest(root_grant), "expires_at": grant.expires_at.isoformat(),
        "grant_limits": grant.limits.model_dump(mode="json"), "request_sha256": content_digest(request),
        "spec_sha256": content_digest(spec), "environment": environment.model_dump(mode="json"),
        "maximum_operations": len(calls), "maximum_reserved_seconds": len(calls) * (spec.config["timeout_seconds"] + 5),
        "dispatches": calls, "inert_native_fixture": SHAPE_FIXTURE, "required_free_bytes": DISK_FLOOR,
        "models": 0, "cash_usd": 0, "provider_disclosure": False, "network": False,
        "downloads": 0, "builds": 0, "retries": 0, "formal_cases_adopted": 0,
    }
    documents = {"recipe": recipe, "environment": environment, "subject": subject, "recipe_runtime": runtime}
    return disclosure, request, documents, roles


def approved(exact, review, approval, run):
    require(not run.exists(), "terminal or interrupted attempt exists; recover from its receipts")
    require(
        review.is_file() and file_digest(review) == exact and approval.is_file()
        and get(approval) == {"approved": True, "review_sha256": exact}
        and get(approval)["approved"] is True,
        "exact review approval is required",
    )


def approve_definitions(repo, disclosure, request, documents):
    grant = repo.current_grant(request.authorization_id)
    with repo.store._lock:
        operations, seconds = repo.store._connection.execute(
            "SELECT operations,elapsed_seconds FROM assessment_grants WHERE id=?", (request.authorization_id,),
        ).fetchone()
        planned = repo.store._connection.execute(
            "SELECT 1 FROM assessment_records WHERE kind='operation_start' AND json_extract(payload_json, '$.plan_id')=?",
            (request.plan_id,),
        ).fetchone()
    require(
        planned is None and operations + disclosure["maximum_operations"] <= grant.limits.max_operations
        and seconds + disclosure["maximum_reserved_seconds"] <= grant.limits.max_elapsed_seconds,
        "previous dispatch exists or existing grant capacity is insufficient",
    )
    for kind, document in documents.items():
        repo.put(kind, content_digest(document), document)
    definitions = {content_digest(doc): doc.model_dump(mode="json") for doc in documents.values()}
    repo.approve_bundle(AssessmentScopeAmendment(
        authorization_id=request.authorization_id, authorization_digest=disclosure["root_grant_sha256"],
        subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(definitions),
    ), definitions)
    repo.authorize(request)


async def execute(ledger, exact):
    approved(exact, REVIEW, APPROVAL, RUN)
    disclosure, request, documents, roles = await prepare(ledger)
    require(disclosure == get(REVIEW), "exact scope changed")
    RUN.mkdir(mode=0o700)
    put(RUN / "started.json", {"review_sha256": exact, "automatic_retry": False})
    router = Router.from_manifest(BASE / "aeep.json")
    try:
        service = AssessmentService(router, OPERATIONS)
        repo = service.repository
        require(router.store.path == str(DATABASE), "operational ledger binding changed")
        approve_definitions(repo, disclosure, request, documents)
        spec = documents["recipe"].extension.grader
        results = []
        for position, binding in enumerate(disclosure["dispatches"]):
            operation = binding["operation_id"]
            case, artifact, expected, score = roles[operation]

            async def probe(payload, binding=binding, expected=expected, operation=operation, position=position):
                project_source()
                require(file_digest(REVIEW) == exact and content_digest(payload) == binding["payload_sha256"], "execution input drift")
                output, _ = await invoke(service, request, spec, payload, stage="migrated_repository_grader", operation_id=operation)
                put(RUN / f"{position}-raw.json", output)
                receipt = settled_receipt(OPERATIONS, spec, request.model_dump(mode="json"), repo, operation, payload)
                put(RUN / f"{position}-receipt.json", receipt)
                require(verify_probe(output, payload, expected["statuses"], expected["exit_code"]), "actual protected outcome differs")
                return output

            observed = await grade_suite_output(case.input.model_dump(mode="json"), case.truth.model_dump(mode="json"), artifact, probe)
            require(observed == score, "actual protected grade differs")
            results.append({"operation_id": operation, "grade": observed.model_dump(mode="json")})
        put(RUN / "completed.json", {"review_sha256": exact, "results": results, "models": 0, "formal_cases_adopted": 0})
    finally:
        await router.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_mutually_exclusive_group(required=True)
    commands.add_argument("--prepare", action="store_true")
    commands.add_argument("--verify", action="store_true")
    commands.add_argument("--execute-approved")
    args = parser.parse_args()
    with closing(open_store(str(DATABASE))) as store:
        ledger = AssessmentRepository(store)
        if args.execute_approved:
            await execute(ledger, args.execute_approved)
            return
        disclosure, _, _, _ = await prepare(ledger)
        if args.prepare:
            put(REVIEW, disclosure)
        require(disclosure == get(REVIEW), "exact standard observer review does not reproduce")
        print(file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
