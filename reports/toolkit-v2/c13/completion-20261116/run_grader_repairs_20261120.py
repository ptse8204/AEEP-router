"""Verify the Locify fixture repair and capture the seven known EOS failures."""

import argparse
import asyncio
import re
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import check_eos_protected_pair as eos
import check_locify_protected_pair as locify
import execute_rebench_correction_group as prior
from stage_repository_transport import HERE, ROOT, WORK, encode, write

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore

NAME = "c13-grader-repairs-20261120"
TARGET = WORK / NAME
REVIEW = TARGET / "operation-review.json"
AUTHORITY = HERE / "c13-offline-approval-20261117.json"
DIAGNOSTICS = HERE / "pytest_failure_diagnostics.py"
NET_STORAGE_LIMIT = 768 * 2**20
runner = locify.runner
journal = prior.journal


def update_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError("reviewed observer insertion point changed")
    return text.replace(old, new)


def debug_observer(spec, *, git_identity=False):
    argv = list(spec.config["argv"])
    program = argv[-1]
    anchor = "\n# Only an exact operator-reviewed program may enable collection and failure logs."
    diagnostics = "\n" + DIAGNOSTICS.read_text() + "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
    program = update_once(program, anchor, "\nCAPTURE_SOURCE += " + repr(diagnostics) + anchor)
    program = update_once(
        program, "if not OPERATOR_REVIEW:\n            assert set(native) == {'statuses'}",
        "if not OPERATOR_REVIEW:\n            assert set(native) == {'statuses', 'failure_sites'}",
    )
    if git_identity:
        anchor = "'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1'"
        identity = "".join(f", 'GIT_{actor}_NAME': 'AEEP Fixture', 'GIT_{actor}_EMAIL': 'fixture@aeep.invalid'"
                           for actor in ("AUTHOR", "COMMITTER"))
        program = update_once(program, anchor, anchor + identity)
    compile(program, "<C13 reviewed observer>", "exec")
    return spec.model_copy(update={"config": dict(spec.config, argv=[*argv[:-1], program])})


def definitions():
    if Path(locify.aeep.__file__).resolve().parents[2] != locify.VERIFIED_SOURCE:
        raise ValueError("requires the frozen v7 evaluator")
    known = journal.doc(prior.TARGET / "locify" / "launcher.json")
    source = journal.doc(prior.TARGET / "locify-protected-review.json")
    if not known["observations"]["worker_import"] or source["environment"]["container_image"] != known["image"]["id"]:
        raise ValueError("Locify launcher predecessor changed")
    loc_env = AssessmentEnvironment.model_validate(source["environment"])
    native_record = eos.native.TARGET / "result.json"
    native = journal.doc(native_record)
    if not native["passed"]:
        raise ValueError("EOS retained runtime is unverified")
    eos_spec, eos_env, (eos_case,) = eos.definition(native)
    loc_case = locify.make_case()
    failed = journal.doc(prior.TARGET / "eos-failure-sites.json")["statuses"]
    if len(failed) != 7 or set(failed.values()) != {"FAILED"}:
        raise ValueError("the protected EOS diagnostic scope changed")
    return {
        "locify": (debug_observer(locify.spec(), git_identity=True), loc_env, loc_case, None),
        "eos": (debug_observer(eos_spec), eos_env, eos_case, sorted(failed)),
    }


def launch(component, role, environment, spec, payload):
    identity = f"{NAME}:{component}:{role}"
    executor = runner.ContainerExecutor(environment)
    trial = runner.context(spec, identity, payload)
    argv, owned = executor.command(trial)
    mount = locify.VERIFIED_SOURCE / "src"
    if (argv[argv.index("--network") + 1] != "none"
            or argv[argv.index("--user") + 1] != "65534:65534"
            or {arg for arg in argv if arg.startswith("type=bind,")} != {f"type=bind,src={mount},dst={mount},readonly"}
            or not {"--pull=never", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges"} <= set(argv)):
        raise ValueError("protected container boundary changed")
    pin = {"container": owned, "argv_sha256": content_digest({"argv": argv}),
           "payload_sha256": content_digest(payload), "archive_sha256": payload["archive_sha256"]}
    return executor, trial, pin


async def scope_fields():
    operations = {}
    docker, env = journal.docker_settings()
    for component, (spec, environment, case, selectors) in definitions().items():
        image = journal.inspect(docker, env, environment.container_image)
        if image["id"] != environment.container_image:
            raise ValueError("retained carrier identity changed")
        roles = ("reference", "original") if selectors is None else ("diagnostic",)
        for role in roles:
            expected = runner.expected_statuses(case["truth"], role)

            async def project(payload, component=component, role=role, expected=expected, selectors=selectors,
                              spec=spec, environment=environment, case=case, image=image):
                projected = dict(payload, test_paths=selectors) if selectors else payload
                if role != "original" and projected["archive_sha256"] != case["reference_archive_sha256"]:
                    raise ValueError("published reference bytes changed")
                _, _, pin = launch(component, role, environment, spec, projected)
                operations[f"{component}:{role}"] = pin | {
                    "image": image, "observer_sha256": content_digest(spec), "case_sha256": content_digest(case)}
                return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                    "exit_code": int(role == "original"), "statuses": expected}

            await ordinary(case, role, project)
    bound = [Path(__file__), DIAGNOSTICS, AUTHORITY, Path(locify.__file__), Path(eos.__file__),
             Path(runner.__file__), Path(journal.__file__), prior.TARGET / "result.json",
             prior.TARGET / "locify-protected" / "ledger.json", prior.TARGET / "eos-ledger.json"]
    return {
        "schema_version": "aeep.c13.grader-repairs.v1",
        "frozen_source": verification_source_digest(locify.VERIFIED_SOURCE),
        "inputs": {str(path.relative_to(ROOT)): journal.fingerprint(path) for path in bound},
        "operations": operations, "maximum_operations": 3, "maximum_reserved_seconds": 165,
        "scope": "Locify reference and conditional original, plus the seven prior EOS failures for diagnostics.",
        "operator_authority": "C13 bounded correction delegation and November 20 direction to continue at current usable space.",
        "models": 0, "cash_usd": 0, "downloads": 0, "builds": 0, "retries": 0, "formal_adoption": False,
    }


async def ordinary(case, role, probe):
    return await grade_suite_output(case["input"], case["truth"],
                                    case["roles"]["original" if role == "original" else "reference"], probe)


def parse_response(reply, payload, allowed):
    if not isinstance(reply, dict) or set(reply) != {"archive_sha256", "python", "pytest", "exit_code", "statuses", "failure_sites"}:
        raise ConfigurationError("structured grader response has the wrong shape")
    clean = {key: value for key, value in reply.items() if key != "failure_sites"}
    if (any(reply[key] != payload[key] for key in ("archive_sha256", "python", "pytest"))
            or type(reply["exit_code"]) is not int or reply["exit_code"] not in {0, 1, 2, 3, 4, 5}
            or not isinstance(reply["statuses"], dict) or len(reply["statuses"]) > 10000
            or any(not isinstance(value, str) or value not in {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}
                   for value in reply["statuses"].values())):
        raise ConfigurationError("structured grader response changed identity or status vocabulary")
    sites = reply["failure_sites"]
    if not isinstance(sites, list) or len(sites) > 64:
        raise ConfigurationError("failure location collection exceeded its bound")
    for site in sites:
        if (not isinstance(site, dict) or set(site) != {"test", "phase", "category", "file", "line"}
                or not isinstance(site["test"], str) or site["test"] not in allowed
                or clean["statuses"].get(site["test"]) not in {"FAILED", "ERROR"}
                or site["phase"] not in {"setup", "call", "teardown"}
                or not isinstance(site["category"], str)
                or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]{0,79}", site["category"])
                or (site["file"] is None) != (site["line"] is None)
                or (site["file"] is not None and
                    (not isinstance(site["file"], str) or not re.fullmatch(r"[A-Za-z0-9_./-]{1,300}\.py", site["file"])
                     or Path(site["file"]).is_absolute() or ".." in Path(site["file"]).parts
                     or type(site["line"]) is not int or site["line"] <= 0))):
            raise ConfigurationError("failure location escaped the allowed diagnostic fields")
    return clean, sites


async def run_role(repo, store, request, review, exact, component, role, row):
    spec, environment, case, selectors = row
    expected = runner.expected_statuses(case["truth"], role)
    selected = selectors or list(expected)
    key = f"{component}:{role}"
    observation = {}

    async def probe(payload):
        projected = dict(payload, test_paths=selectors) if selectors else payload
        executor, trial, pin = launch(component, role, environment, spec, projected)
        reviewed = review["operations"][key]
        owned = pin["container"]
        if (any(reviewed[k] != v for k, v in pin.items()) or journal.fingerprint(REVIEW) != exact
                or shutil.disk_usage(ROOT).free < review["minimum_free_bytes"]
                or runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$")):
            raise RuntimeError("reviewed launch, storage or owned-container check failed")
        seconds = 95 if selectors else 35
        name = trial.attempt_id
        repo.reserve(request, name, AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds), stage=role)
        clock, started = time.monotonic(), utc_now()
        raw = await executor.execute(trial)
        if runner.docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
            raise RuntimeError("owned container cleanup is uncertain")
        error = raw.error_type
        clean = None
        if raw.status.value == "success":
            try:
                clean, sites = parse_response(raw.output, payload, selected)
            except ConfigurationError:
                error = "INCOMPLETE_DIAGNOSTICS"
            else:
                observation.update(exit_code=clean["exit_code"], failure_sites=sites,
                                   statuses={test: clean["statuses"].get(test, "MISSING") for test in selected},
                                   protected_response_sha256=content_digest(raw.output))
        accepted = clean is not None and (selectors is not None or runner.verify_probe(clean, payload, expected, int(role == "original")))
        receipt = ExecutionReceipt(
            decision_id=name, action_id=name, capability=spec.capability, executor_id=spec.id, executor_kind=spec.kind,
            status="success" if accepted else "failed", started_at=started, ended_at=utc_now(), estimated=trial.estimate,
            actual_resources=raw.resources, execution_success=accepted,
            error_type=(error or "OBSERVATION_MISMATCH") if not accepted else None,
            metadata={"review_sha256": exact, "container_absent": True},
        )
        store.save_receipt(receipt)
        repo.finish_operation(name, elapsed_seconds=time.monotonic()-clock, resources=raw.resources)
        observation.update(receipt=receipt.receipt_id, accepted=accepted, score=None)
        write(TARGET / f"{component}-{role}-receipt.json", encode(receipt.model_dump(mode="json")))
        if not accepted:
            raise ConfigurationError("protected observation did not match the reviewed result")
        return clean

    try:
        grade = await ordinary(case, role, probe)
    except ConfigurationError:
        observation.setdefault("reason", "protected observation did not qualify")
    else:
        if selectors is None:
            observation["score"] = grade.quality_score
    write(TARGET / f"{component}-{role}.json", encode(observation))
    return observation


async def prepare():
    scope = await scope_fields()
    free = shutil.disk_usage(ROOT).free
    if free <= NET_STORAGE_LIMIT:
        raise ValueError("insufficient free capacity for the bounded local operations")
    write(REVIEW, encode(scope | {
        "initial_free_bytes": free, "minimum_free_bytes": free - NET_STORAGE_LIMIT,
        "expires_at": (utc_now() + timedelta(hours=2)).isoformat(),
    }))
    print(journal.fingerprint(REVIEW))


async def execute(exact):
    review = journal.doc(REVIEW)
    dynamic = {k: review[k] for k in ("initial_free_bytes", "minimum_free_bytes", "expires_at")}
    expiry = datetime.fromisoformat(review["expires_at"])
    if (journal.fingerprint(REVIEW) != exact or review != await scope_fields() | dynamic
            or utc_now() >= expiry or review["minimum_free_bytes"] != review["initial_free_bytes"] - NET_STORAGE_LIMIT
            or shutil.disk_usage(ROOT).free < review["minimum_free_bytes"]):
        raise ValueError("prepared scope, expiry or capacity changed")
    rows = definitions()
    write(TARGET / "started.json", encode({"review_sha256": exact}))
    definition, auth, request = prior.grant(NAME, exact, expiry, 3, 165)
    result = {}
    with ReceiptStore(TARGET / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_grader_repair_scope", content_digest(definition), definition)
        repo.approve_bundle(auth, {content_digest(definition): definition.model_dump(mode="json")})
        try:
            result["locify_reference"] = await run_role(repo, store, request, review, exact, "locify", "reference", rows["locify"])
            if result["locify_reference"].get("score") == 1.0:
                result["locify_original"] = await run_role(repo, store, request, review, exact, "locify", "original", rows["locify"])
            result["eos_diagnostic"] = await run_role(repo, store, request, review, exact, "eos", "diagnostic", rows["eos"])
        finally:
            write(TARGET / "ledger.json", encode(repo.operation_ledger(auth.authorization_id).model_dump(mode="json")))
            write(TARGET / "result.json", encode(result))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    asyncio.run(prepare() if args.prepare else execute(args.execute))


if __name__ == "__main__":
    main()
