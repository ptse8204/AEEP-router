"""Rerun only CANopen and Xsdata with bounded test and tool observations."""

import argparse
import asyncio
import json
import runpy
import sqlite3
import sys
import time
from pathlib import Path

import resume_dispatch as repaired
import run_dispatch as prior
from check_software_observer import checks
from freeze_study import DATABASE
from prepare_renewal import snapshot
from prepare_runtime import WORK, docker, read, sha, write
from software_observer import HELPER, PREFIX, observe_grader, positive_calls, watch_software_workers
from software_observer_preflight import DIR as OFFLINE

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.models import ExecutionReceipt, utc_now
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_stack_complete
from aeep_toolkit.telemetry import bound_journal
from aeep_toolkit.worker_readiness import _Document

HERE = Path(__file__).resolve().parent
REVIEW = HERE / "software-observation-review.json"
RUN = WORK / "software-observation-dispatch"
AUDIT = HERE / "sales-window-audit.json"
HELPER_FILE = HERE / "libcst_reviewed_helper.py"
ENVELOPE = {
    "maximum_operations": 78,
    "maximum_model_turns": 15,
    "maximum_reserved_seconds": 6800,
    "maximum_cash_usd": "0",
}
AUTHORITY = "Operator explicitly requested per-test reporting, real LibCST tracking and fresh paired runs on the same two software tasks."
TOOL = " ".join(PREFIX)
HINT = (
    "The usual local editing and Python tools remain available. If the optional reviewed LibCST "
    "helper exists and is useful, run a single direct command from /workspace, setting "
    "'login' to false if the command tool exposes it and avoiding shell composition. "
    f"To check syntax, run: {TOOL} check relative/file.py . For a qualified symbol rename, syntax is "
    f"{TOOL} rename relative/file.py old.symbol new.symbol . The helper prints a read-only "
    "preview; you choose which edits to make. Use ordinary tools whenever preferable. "
)


def entries_and_bindings():
    images = read(OFFLINE / "images.json")
    bindings = {}
    entries = []
    for (
        task,
        recipe,
        environment,
        value,
        truth,
        pair,
        shared,
        suite,
    ) in repaired.bind_continuation()[2:]:
        raw = pair.model_dump(mode="json")
        role_routes = {}
        for role in ("control", "treatment"):
            spec = raw[role]
            config = spec["config"]
            worker = config["managed_worker"]
            spec["id"] = spec["id"].replace("sol-pilot-", "sol-observed-")
            config["adapter_id"] = "codex-app-server:" + spec["id"]
            worker["worker_id"] = spec["id"].replace(".", "-")
            config["instructions"] = HINT + config["instructions"]
            assert config["timeout_seconds"] == 300.0
            if role == "treatment":
                worker["image"] = images[role]["id"]
                worker["reviewed_files"][HELPER] = sha(HELPER_FILE)
                worker["dependencies_digest"] = content_digest(
                    {"image": worker["image"], "helper": sha(HELPER_FILE)}
                )
            else:
                assert (
                    worker["image"] == images[role]["id"] and HELPER not in worker["reviewed_files"]
                )
            role_routes[getattr(pair, role).id] = spec["id"]
        assert (
            raw["control"]["config"]["instructions"] == raw["treatment"]["config"]["instructions"]
        )
        shared |= {
            "observer_sha256": sha(HERE / "software_observer.py"),
            "shared_prompt_hint": content_digest(HINT),
        }
        difference = raw["differential"]
        difference["shared_definition_digest"] = content_digest(shared)
        inventory = {"capable_local_tools": difference["shared_definition_digest"]}
        difference["control_inventory"] = inventory
        difference["treatment_inventory"] = inventory | difference["candidate_inventory"]
        pair = type(pair).model_validate(raw)
        suite = suite.model_copy(
            update={
                "suite_id": suite.suite_id.replace("-repair-", "-instrumented-"),
                "routes": [
                    route.model_copy(
                        update={
                            "route_id": role_routes[route.route_id],
                            "executor_id": role_routes[route.executor_id],
                        }
                    )
                    for route in suite.routes
                ],
                "baseline_route_id": pair.control.id,
            }
        )
        for role in ("control", "treatment"):
            config = getattr(pair, role).managed_host_config()
            worker = prior.binding_from_config(config.managed_worker)
            bindings[config.adapter_id] = {
                "worker_digest": worker.digest(),
                "helper_sha256": (worker.reviewed_files or {}).get(HELPER),
            }
        entries.append((task, recipe, environment, value, truth, pair, shared, suite))
    assert len(entries) == 2
    return entries, bindings


def preconditions():
    assert not RUN.exists()
    old, sales = read(prior.REVIEW), read(AUDIT)
    assert sales["cumulative_accounting"]["operations"] == 57
    assert sales["cumulative_accounting"]["model_turns"] == 11
    assert float(sales["cumulative_accounting"]["cash_usd"]) == 0
    prior.verify_assets(old)
    original, effective, counters, amendment, pending = snapshot()
    start = old["grant"]["unchanged_counters"]
    assert (counters[1] - start[0], counters[2] - start[1]) == (57, 11)
    assert abs(counters[3] - start[2] - sales["cumulative_accounting"]["operation_seconds"]) < 1e-7
    assert float(counters[4]) == 0
    assert amendment == old["grant"]["canonical_amendment_digest"]
    assert content_digest(pending) == old["grant"]["prior_reservations_sha256"]
    assert (
        utc_now() < effective.expires_at and prior.proxy_state(old["proxy"]["Id"]) == old["proxy"]
    )
    with ReceiptStore(DATABASE, read_only=True) as store:
        require_stack_complete(
            AssessmentRepository(store),
            old["stack_completion_ref"],
            source_digest=old["implementation_source"],
        )
    return old, original, effective, list(counters[1:]), {row[0] for row in pending}


async def freeze():
    old, _, effective, counters, _ = preconditions()
    assert checks()
    proof = read(OFFLINE / "result.json")
    assert proof["review_sha256"] == sha(OFFLINE / "review.json") and proof["model_turns"] == 0
    assert proof["workers"]["treatment"]["import_parse_and_changed_transform_controls_passed"]
    assert proof["workers"]["treatment"]["non_transform_and_path_escape_controls_passed"]
    assert not proof["workers"]["control"]["expected_helper_available"]
    assert all(row["owned_worker_removed"] for row in proof["workers"].values())
    assert read(OFFLINE / "review.json")["source_sha256"] == sha(HELPER_FILE)
    schema = read(OFFLINE / "app-server-event-schema-verified.json")
    assert schema["worker_cleanup_confirmed"] and schema["model_turns"] == 0
    [command_fields] = schema["command_schema"]
    assert command_fields["command"]["type"] == "string"
    assert command_fields["exitCode"]["type"] == ["integer", "null"]
    assert {"inProgress", "completed"} <= set(schema["status_enums"]["status"])
    shell = read(OFFLINE / "non-login-shell-boundary.json")
    assert shell["model_turns"] == 0 and set(shell["workers"]) == {"control", "treatment"}
    images = read(OFFLINE / "images.json")
    for role, evidence in shell["workers"].items():
        assert evidence["image"] == images[role]["id"]
        assert evidence["no_env_inheritance"] and evidence["no_shell_startup_env"]
        assert evidence["worker_cleanup_confirmed"]
    entries, bindings = entries_and_bindings()
    tasks = await repaired.bound_tasks(entries)
    for before, after in zip(read(repaired.REVIEW)["tasks"][2:], tasks, strict=True):
        assert [
            before[key] for key in ("task_id", "recipe_digest", "protected_environment_digest")
        ] == [after[key] for key in ("task_id", "recipe_digest", "protected_environment_digest")]
    operations = 2 * (2 + 3 + 2 + 2 + 1) + 1
    seconds = (
        4 * 240
        + 6 * 30
        + 4 * 305
        + 2 * 30
        + 120
        + sum(2 * (entry[1].extension.grader.config["timeout_seconds"] + 5) for entry in entries)
    )
    runpy.run_path(str(prior.BUDGET))["require_room"](
        counters,
        old["grant"]["unchanged_counters"],
        AssessmentLimits(max_operations=operations, max_model_turns=4, max_elapsed_seconds=seconds),
        ENVELOPE,
    )
    pins = [prior.REVIEW, repaired.REVIEW, AUDIT, Path(__file__), HELPER_FILE]
    pins.extend(
        HERE / file
        for file in (
            "software_observer.py",
            "software_observer_preflight.py",
            "check_software_observer.py",
        )
    )
    pins.extend(
        OFFLINE / file
        for file in (
            "review.json",
            "result.json",
            "images.json",
            "app-server-event-schema-verified.json",
            "non-login-shell-boundary.json",
        )
    )
    review = {
        "operator_authority": AUTHORITY,
        "opening_counters": counters,
        "grant_expiry": effective.expires_at.isoformat(),
        "model": "gpt-6.1-sol",
        "reasoning_effort": "medium",
        "destination": "existing managed Codex proxy",
        "tasks": tasks,
        "observer_bindings": bindings,
        "cumulative_ceiling": ENVELOPE,
        "maximum_new_operations": operations,
        "maximum_new_model_turns": 4,
        "maximum_reserved_seconds": seconds,
        "automatic_retries": 0,
        "pins": {str(path.resolve()): sha(path) for path in pins},
    }
    write(REVIEW, review)
    print(sha(REVIEW))


def diagnostics(entry, folder, task_result, review, repository):
    task, recipe, _, _, truth, _, _, _ = entry
    required = truth["fail_to_pass"] + truth["pass_to_pass"]
    refs = {row["receipt_ref"]: row["arm"] for row in task_result["arms"]}
    records = {}
    for index in (1, 2):
        trial_file = folder / f"trial-{index}.json"
        trial = read(trial_file)
        receipt = ExecutionReceipt.model_validate(trial["receipt"])
        arm = refs[content_digest(receipt)]
        sidecar_file = (
            RUN / "observers" / (content_digest(receipt.metadata["attempt_id"]) + ".json")
        )
        sidecar = read(sidecar_file)
        binding = review["observer_bindings"][receipt.metadata["adapter_id"]]
        assert sidecar["helper_sha256"] == binding["helper_sha256"]
        assert sidecar["worker_digest"] == binding["worker_digest"]
        with sqlite3.connect(
            (folder / "campaign.sqlite3").as_uri() + "?mode=ro", uri=True
        ) as campaign:
            [(database, trial_payload)] = campaign.execute(
                "SELECT s.database_path, t.payload_json FROM trial_stores s JOIN trials t USING(trial_id) WHERE trial_id=?",
                (trial["trial_id"],),
            ).fetchall()
        assert Path(database).resolve().parent == (folder / "attempts").resolve()
        with sqlite3.connect(Path(database).as_uri() + "?mode=ro", uri=True) as attempt:
            [(payload,)] = attempt.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
                (receipt.metadata["execution_evidence_digest"],),
            ).fetchall()
        journal = bound_journal(receipt, json.loads(payload))
        calls = positive_calls(sidecar, receipt, journal)
        event = json.loads(trial_payload)
        [grade] = event["case_validation"]
        detail = grade["detail"]
        outcomes = None
        grade_path = folder / "grades" / ("per-test-" + content_digest(trial["trial_id"]) + ".json")
        if grade_path.is_file():
            [grader] = list((folder / "grades").glob(f"*-{trial['trial_id']}.json"))
            outcomes = read(grade_path)
            assert outcomes == repository.get("protected_test_diagnostics", trial["trial_id"])
            grader_receipt = read(grader)
            assert outcomes["trial_id"] == trial["trial_id"] and outcomes["task"] == task["id"]
            assert outcomes["grader_receipt_sha256"] == sha(grader)
            assert (
                grader_receipt["metadata"]["task_id"] == task["id"]
                and grader_receipt["metadata"]["stage"] == trial["trial_id"]
            )
            assert (
                grader_receipt["metadata"]["cleanup_confirmed"]
                and grader_receipt["status"] == "success"
            )
            assert grader_receipt["metadata"]["executor_digest"] == content_digest(
                recipe.extension.grader
            )
            assert outcomes["grader_request_digest"] == grader_receipt["metadata"]["request_digest"]
            assert outcomes["protected_test_identity_digest"] == content_digest(required)
            statuses = outcomes["required_statuses"]
            assert set(statuses) == set(required)
            if "NOT_REPORTED" in statuses.values():
                assert detail == "missing_test"
            elif outcomes["pytest_exit"] or set(statuses.values()) != {"PASSED"}:
                assert detail == "test_failure"
            else:
                assert grade["valid"] is True
        else:
            assert detail in {"input_binding", "patch_contract"}
        records[arm] = {
            "receipt_ref": trial["receipt_ref"],
            "grade_detail": detail,
            "per_test": outcomes,
            "positive_helper_calls": calls,
            "observed_helper_import_count": len(calls),
            "observed_helper_rename_preview_count": sum(
                row["transformation_observed"] for row in calls
            ),
            "observed_changed_preview_count": sum(row["changed_preview_observed"] for row in calls),
            "other_libcst_use": "unknown",
            "observation_overflow": sidecar["overflow"],
        }
    assert set(records) == {"control", "treatment"}
    return records


async def execute(identity):
    assert not sys.flags.optimize and sha(REVIEW) == identity
    review = read(REVIEW)
    assert review["operator_authority"] == AUTHORITY and review["cumulative_ceiling"] == ENVELOPE

    def check_pins():
        assert sha(REVIEW) == identity
        assert all(sha(Path(name)) == expected for name, expected in review["pins"].items())

    check_pins()
    old, original, effective, counters, before = preconditions()
    assert (
        counters == review["opening_counters"]
        and effective.expires_at.isoformat() == review["grant_expiry"]
    )
    entries, bindings = entries_and_bindings()
    assert (
        await repaired.bound_tasks(entries) == review["tasks"]
        and bindings == review["observer_bindings"]
    )
    router = Router.from_manifest(prior.BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    stamp = "sol-development-proxy-software-observation-20261116"
    operation = stamp + ":owned-start-stop"
    result = {"review_sha256": identity, "completed": False, "tasks": []}
    started = owned = False
    startup = 0.0
    try:
        RUN.mkdir(mode=0o700)
        started = True
        write(RUN / "started.json", {"review_sha256": identity, "retries": 0})
        observers = RUN / "observers"
        observers.mkdir(mode=0o700)
        runpy.run_path(str(prior.BUDGET))["install"](
            repo, router.store._connection, old["grant"]["unchanged_counters"], ENVELOPE
        )
        subject = prior.store_doc(
            repo, "subject", _Document(value={"exact_software_review": identity})
        )
        request = prior.request(
            repo,
            stamp,
            subject,
            prior.store_doc(repo, "recipe", entries[0][1]),
            AssessmentEnvironment(
                environment_id=stamp, kind="trusted_local", identity={"review": identity}
            ),
        )
        prior.scope(repo, original, [request], RUN, "proxy")
        repo.reserve(
            request,
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
            stage="retained_codex_proxy_control",
        )
        at = time.perf_counter()
        owned = True
        try:
            docker("start", old["proxy"]["Id"])
        finally:
            startup = time.perf_counter() - at

        def verify():
            check_pins()
            prior.verify_assets(old)
            assert utc_now() < effective.expires_at and before <= prior.reservations(repo)
            state = prior.proxy_state(old["proxy"]["Id"])
            assert state["Running"] and all(
                state[key] == old["proxy"][key] for key in ("Id", "Image", "Memory", "MemorySwap")
            )
            assert {name: row["NetworkID"] for name, row in state["Networks"].items()} == {
                name: row["NetworkID"] for name, row in old["proxy"]["Networks"].items()
            }
            assert state["Networks"]["aeep-reviewed-model-private"]["IPAddress"] == "172.18.0.2"

        async with asyncio.timeout(review["maximum_reserved_seconds"]):
            authenticated = []
            for task, recipe, _, _, _, pair, shared, _ in entries:
                folder = RUN / task["id"]
                folder.mkdir(mode=0o700)
                authenticated.append(
                    await prior.authenticate_pair(
                        service, original, task, recipe, pair, shared, subject, folder, verify
                    )
                )
            truth = {entry[0]["id"]: entry[4] for entry in entries}
            with watch_software_workers(observers, bindings), observe_grader(truth, repo):
                for entry, proof, refs in zip(entries, review["tasks"], authenticated, strict=True):
                    folder = RUN / entry[0]["id"]
                    task_result = await prior.run_task(
                        service, original, entry, proof, refs, subject, folder, verify
                    )
                    task_result["diagnostics"] = diagnostics(
                        entry, folder, task_result, review, repo
                    )
                    result["tasks"].append(task_result)
        result["completed"] = True
    except BaseException as error:
        result.update(completed=False, error_type=type(error).__name__)
        raise
    finally:
        if started:
            if owned:
                at = time.perf_counter()
                try:
                    if prior.proxy_state(old["proxy"]["Id"])["Running"]:
                        docker("stop", "--time", "5", old["proxy"]["Id"])
                    result["proxy_restored_stopped"] = (
                        prior.proxy_state(old["proxy"]["Id"]) == old["proxy"]
                    )
                    if result["proxy_restored_stopped"]:
                        repo.finish_operation(
                            operation, elapsed_seconds=startup + time.perf_counter() - at
                        )
                except BaseException as error:
                    result.update(completed=False, cleanup_error=type(error).__name__)
            result["new_unsettled_operations"] = sorted(prior.reservations(repo) - before)
            if result["new_unsettled_operations"]:
                result["completed"] = False
            write(RUN / "result.json", result)
            prior.render_result(result, RUN)
        await router.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    asyncio.run(freeze() if args.freeze else execute(args.execute))
