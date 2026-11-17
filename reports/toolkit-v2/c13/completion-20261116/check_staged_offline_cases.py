"""Review three source-bound protected pairs on the ordinary repository grader."""

import argparse
import asyncio
import json
from contextlib import closing
from pathlib import Path

import check_migrated_graders as native
from audit_staged_repository_graders import bind, index_paths, wheel_probe_assets
from check_linux_install import DOCKER, HERE, ROOT, SOCKET, WORK, docker, get, put
from plan_repository_expansion import previous_repositories, repository
from repository_offline_pair_batch import asset, context, verify_probe
from stage_repository_transport import digest, read

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import invoke
from aeep.assessment.models import AssessmentEnvironment, AssessmentSubject, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import archive_files, grade_suite_output
from aeep.errors import ConfigurationError
from aeep.models import utc_now
from aeep.router import Router
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.workflow_evidence import open_store

NAME = "c13-first-staged-protected-pairs-20261116"
PRIVATE = WORK / NAME
REVIEW = PRIVATE / "operation-review.json"
APPROVAL = PRIVATE / "approval.json"
RUN = PRIVATE / "execution"
TARGETS = (
    "open-spaced-repetition__py-fsrs-127-aeep-contract-audit",
    "simonw__files-to-prompt-44",
    "ultrabug__py3status-2286",
)
CLICK_REVIEW = HERE.parent / "repository-supported-suites-20261027/runtime-install-review.json"
SETUPTOOLS_REVIEW = HERE.parent / "repository-workload-expansion-20261022/image-runtime-wheel-review.json"
CARRIER_RECORD = HERE.parent / "repository-test-roots-20261027/build-result.json"
CARRIER = "sha256:2a057881ffe70b7a83639d24612b3c579b5892615542452e52324f1389c4abb9"
REBOUND = HERE / "cached-repository-rebinding.json"
RETAINED = HERE / "staged-repository-grader-bindings.json"


def cases():
    _, base = wheel_probe_assets()
    click = next(row for row in get(CLICK_REVIEW)["pins"] if row["project"] == "click")
    additional = {TARGETS[1]: [asset(ROOT / click["private_cache"], click["sha256"])]}
    origins = get(REBOUND)
    source_review = json.loads(read(WORK / "cached-source-tree-rebinding/source-results.json",
                                   origins["private_source_results_sha256"]))
    notices = {item["case_id"]: item for item in source_review if item["status"] == "archive_tree_and_notice_bound"}
    staged = {item["case"]: item for item in get(RETAINED)["cases"]}
    _, _, exposed = previous_repositories()
    prepared = {}
    for index, pin in index_paths():
        for row in json.loads(read(index, pin)):
            name = row["input"]["task_id"]
            if name not in TARGETS:
                continue
            if name in prepared or repository(row["source_repository"]) in exposed:
                raise ValueError("duplicate or development-exposed source")
            task, truth, reference, original, metadata = bind(row, index.parent, base + additional.get(name, []))
            if metadata.get("admits_python_3_13_0", True) is not True:
                raise ValueError("published runtime excludes Python 3.13")
            source_binding = notices.get(name, row)
            source = archive_files(truth.source.read(), large=True)
            license_records = source_binding["license_notices"]
            if (source_binding["source_revision"] != row["source_revision"] or not license_records
                    or any(digest(source[record["file"]]) != record["sha256"]
                           for record in license_records)):
                raise ValueError("source or notice changed since review")
            tests = truth.fail_to_pass + truth.pass_to_pass
            failures = [row["protected_guard"]] if "protected_guard" in row else truth.fail_to_pass
            if not failures or not set(failures) <= set(tests) or len(tests) != staged[name]["test_identities"]:
                raise ValueError("missing independent counterexample or changed test identities")
            prepared[name] = {
                "task": task, "truth": truth, "revision": row["source_revision"], "notices": license_records,
                "reference": reference, "original": original, "failures": failures, "source_index": pin,
                "archives": tuple(staged[name][f"{role}_transport"]["archive_sha256"] for role in ("reference", "original")),
            }
    if set(prepared) != set(TARGETS):
        raise ValueError("protected case inventory changed")
    return prepared


def expected_reply(payload, case, role):
    truth = case["truth"]
    statuses = dict.fromkeys(truth.fail_to_pass + truth.pass_to_pass, "PASSED")
    if role == "original":
        statuses.update(dict.fromkeys(case["failures"], "FAILED"))
    return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
        "exit_code": int(role == "original"), "statuses": statuses,
    }


async def grade(case, role, probe):
    return await grade_suite_output(case["task"].model_dump(mode="json"), case["truth"].model_dump(mode="json"),
                                    case[role], probe)


def launch_binding(spec, executor, operation, payload):
    argv, _ = executor.command(context(spec, operation, payload))
    if (
        {arg for arg in argv if arg.startswith("type=bind,")}
        != {f"type=bind,src={native.FROZEN / 'src'},dst={native.FROZEN / 'src'},readonly"}
        or argv[argv.index("--network") + 1] != "none" or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges", "-i"} <= set(argv)
    ):
        raise ValueError("ordinary protected observer boundary changed")
    return content_digest({"argv": argv})


def image_layers():
    retained = get(CARRIER_RECORD)
    image = json.loads(docker("image", "inspect", "--format", "{{json .}}", CARRIER))
    config = image["Config"]
    setuptools, = get(SETUPTOOLS_REVIEW)
    history = docker("image", "history", "--no-trunc", "--format", "{{.CreatedBy}}", CARRIER)
    if (
        retained["image_id"] != image["Id"] or image["Id"] != CARRIER
        or not retained["passed"] or not retained["parent_layers_verified"]
        or not retained["inherited_config_verified"] or setuptools["filename"] not in history
        or (image["Os"], image["Architecture"], config["User"]) != ("linux", "arm64", "65534:65534")
        or config.get("Volumes") or config.get("Healthcheck")
    ):
        raise ValueError("retained runtime and its installed setuptools binding changed")
    return image["RootFS"]["Layers"]


async def prepare(ledger):
    native.project_source()
    # Reuse the existing native observer and inert recipe shape. No staged
    # subjects enter that recipe's development fixtures or a materialized set.
    prior, previous_request, definitions, _ = await native.prepare(ledger)
    cases_by_id = cases()
    environment = AssessmentEnvironment(
        environment_id=NAME, identity={"source": native.SOURCE}, kind="container", container_image=CARRIER,
        container_runtime=DOCKER, container_socket=SOCKET, container_tmpfs_mb=64, memory_mb=512, process_limit=96,
    )
    subject = AssessmentSubject(subject_id=NAME, kind="command", location=str(native.FROZEN),
                               dependency_digests=definitions["subject"].dependency_digests,
                               description="Three first protected pairs on retained source and runtime.")
    documents = {**definitions, "environment": environment, "subject": subject}
    request = previous_request.model_copy(update={
        "plan_id": NAME, "subject_digest": content_digest(subject), "environment_digest": content_digest(environment),
        "definition_digests": [content_digest(documents[k]) for k in ("recipe", "environment", "recipe_runtime")],
    })
    spec = documents["recipe"].extension.grader
    executor = ContainerExecutor(environment)
    calls = []
    for name in TARGETS:
        case = cases_by_id[name]
        for role, archive in zip(("reference", "original"), case["archives"], strict=True):
            operation = f"{NAME}:{name}:{role}"

            async def substitute(payload, *, operation=operation, case=case, role=role, archive=archive):
                if payload["archive_sha256"] != archive:
                    raise ValueError("protected task archive differs from its staged binding")
                response = expected_reply(payload, case, role)
                calls.append({
                    "case": case["task"].task_id, "role": role, "operation_id": operation,
                    "payload_sha256": content_digest(payload), "archive_sha256": archive,
                    "expected_sha256": content_digest(response), "expected_required_tests": len(response["statuses"]),
                    "argv_sha256": launch_binding(spec, executor, operation, payload),
                })
                return response

            score = await grade(case, role, substitute)
            if score.valid is not (role == "reference") or score.detail != ("" if role == "reference" else "test_failure"):
                raise ValueError("ordinary callback contract changed")
    record = {
        "schema_version": "aeep.c13.first-staged-protected-pairs.v1",
        "purpose": "Observe exact published reference and original-source outcomes on three staged tasks.",
        "driver_files": {path.name: file_digest(path) for path in (
            Path(__file__), HERE / "audit_staged_repository_graders.py", HERE / "plan_repository_expansion.py",
        )} | prior["driver_files"],
        "files": {str(path.relative_to(ROOT)): file_digest(path) for path in (
            CLICK_REVIEW, SETUPTOOLS_REVIEW, CARRIER_RECORD, REBOUND, RETAINED,
        )},
        "source": native.SOURCE, "image": CARRIER, "layers": image_layers(), "docker_sha256": prior["docker_sha256"],
        "ledger": str(native.DATABASE), "operation_root": str(native.OPERATIONS), "root_grant_sha256": prior["root_grant_sha256"],
        "expires_at": prior["expires_at"], "grant_limits": prior["grant_limits"], "request_sha256": content_digest(request),
        "observer_sha256": content_digest(spec), "environment": environment.model_dump(mode="json"),
        "maximum_operations": len(calls), "maximum_reserved_seconds": len(calls) * (spec.config["timeout_seconds"] + 5),
        "required_free_bytes": native.DISK_FLOOR, "dispatches": calls,
        "cases": {name: {"source_revision": case["revision"], "source_index_sha256": case["source_index"],
                         "notices": case["notices"], "wheel_sha256": {Path(w.path).name: w.sha256 for w in case["truth"].wheels}}
                  for name, case in cases_by_id.items()},
        "downloads": 0, "builds": 0, "retries": 0, "models": 0, "cash_usd": 0, "network": False,
        "provider_disclosure": False, "formal_cases_adopted": 0,
        "stop_policy": "Stop on an indeterminate operation. A settled reference mismatch skips only its original-source control.",
    }
    if len(calls) != 2 * len(TARGETS) or len({call["operation_id"] for call in calls}) != len(calls):
        raise ValueError("missing or repeated reviewed dispatch")
    return record, request, documents, cases_by_id


def checked_reply(output, payload, expected):
    return verify_probe(output, payload, expected["statuses"], expected["exit_code"]) and not any(
        status == "ERROR" for status in output["statuses"].values()
    )


async def observe(service, request, spec, executor, case, binding, exact):
    operation = binding["operation_id"]
    role = binding["role"]
    observation = {}

    async def probe(payload):
        native.project_source()
        expected = expected_reply(payload, case, role)
        if (file_digest(REVIEW) != exact or content_digest(payload) != binding["payload_sha256"]
                or content_digest(expected) != binding["expected_sha256"]
                or launch_binding(spec, executor, operation, payload) != binding["argv_sha256"]):
            raise ValueError("reviewed payload, grade expectation or boundary changed")
        output, _ = await invoke(service, request, spec, payload, stage="staged_repository_reference_control", operation_id=operation)
        retained = native.settled_receipt(native.OPERATIONS, spec, request.model_dump(mode="json"),
                                          service.repository, operation, payload)
        matches = checked_reply(output, payload, expected)
        observation.update(receipt=retained, contract_matched=matches, reply_sha256=content_digest(output),
                           actual_exit_code=output.get("exit_code") if isinstance(output, dict) else None)
        if matches:
            put(RUN / f"{operation}.observation.json", output)
        return output

    try:
        result = await grade(case, role, probe)
    except ConfigurationError:
        if not observation:
            raise
        result = None
    if not observation:
        raise ValueError("ordinary grading did not invoke the reviewed observer")
    observation["grade"] = result.model_dump(mode="json") if result and observation["contract_matched"] else None
    if observation["contract_matched"] and (result is None or result.valid is not (role == "reference")):
        raise ValueError("observed callback score differs from the exact contract")
    return observation


async def execute(ledger, exact):
    native.approved(exact, REVIEW, APPROVAL, RUN)
    record, request, documents, collection = await prepare(ledger)
    if get(REVIEW) != record or ledger.current_grant(request.authorization_id).expires_at <= utc_now():
        raise ValueError("reviewed scope changed or expired")
    RUN.mkdir(mode=0o700)
    put(RUN / "started.json", {"review_sha256": exact, "automatic_retry": False})
    router = Router.from_manifest(native.BASE / "aeep.json")
    try:
        service = native.AssessmentService(router, native.OPERATIONS)
        if router.store.path != str(native.DATABASE):
            raise ValueError("operational ledger changed")
        native.approve_definitions(service.repository, record, request, documents)
        spec = documents["recipe"].extension.grader
        executor = ContainerExecutor(documents["environment"])
        results = []
        for binding in record["dispatches"]:
            name, role = binding["case"], binding["role"]
            if role == "original" and not results[-1]["contract_matched"]:
                results.append({"case": name, "role": role, "contract_matched": False, "skipped": "reference_not_reproduced"})
                continue
            observed = await observe(service, request, spec, executor, collection[name], binding, exact)
            summary = {"case": name, "role": role, **observed}
            put(RUN / f"{binding['operation_id']}.json", summary)
            results.append(summary)
        put(RUN / "completed.json", {"review_sha256": exact, "results": results, "formal_cases_adopted": 0})
    finally:
        await router.close()


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--prepare", action="store_true")
    actions.add_argument("--verify", action="store_true")
    actions.add_argument("--execute-approved")
    args = parser.parse_args()
    with closing(open_store(str(native.DATABASE))) as store:
        ledger = AssessmentRepository(store)
        if args.execute_approved:
            await execute(ledger, args.execute_approved)
            return
        record, *_ = await prepare(ledger)
        if args.prepare:
            PRIVATE.mkdir(mode=0o700)
            put(REVIEW, record)
        if get(REVIEW) != record:
            raise ValueError("review failed exact offline replay")
        print(file_digest(REVIEW))


if __name__ == "__main__":
    asyncio.run(main())
