"""Run the two reviewed software pairs with direct and helper LibCST observations."""

import argparse
import asyncio
import json
import runpy
import sqlite3
import sys
import time
from pathlib import Path
from unittest.mock import patch

import resume_dispatch as repaired
import run_dispatch as prior
import software_rerun as software
from check_libcst_direct import OFFLINE, REVIEW as OFFLINE_REVIEW, RESULT as OFFLINE_RESULT, checks
from freeze_study import DATABASE
from libcst_direct_observer import PACKAGE_ROOT, validate_direct_calls, watch_direct_workers
from prepare_renewal import snapshot
from prepare_runtime import WORK, docker, read, sha, write
from software_observer import observe_grader, watch_software_workers

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
REVIEW = HERE / "libcst-direct-review.json"
RUN = WORK / "libcst-direct-dispatch"
LAST_AUDIT = HERE / "software-observation-audit.json"
LAST_RESULT = HERE / "software-observation-result.json"
AUTHORITY = (
    "Operator explicitly requested tracking actual direct LibCST imports and transforms as well "
    "as reviewed helper calls, then rerunning both software pairs with LibCST optional."
)
ENVELOPE = software.ENVELOPE | {"maximum_operations": 99, "maximum_model_turns": 19}
DIRECT_HINT = (
    "If you choose to use installed LibCST directly, the observer recognizes simple inline "
    "Python commands using /usr/local/bin/python3 -I -S -B -c or a quoted heredoc. "
    f"For these commands, start with import sys; sys.path.insert(0, '{PACKAGE_ROOT}'); "
    "import libcst. Set login to false for the inline command if applicable. "
    "Use your normal tools and workflow if you prefer. "
)


def study_entries():
    old_entries, old_bindings = software.entries_and_bindings()
    runtime = read(OFFLINE_RESULT)
    assert set(runtime["workers"]) == {"control", "treatment"}
    entries, bindings = [], {}
    for task, recipe, environment, value, truth, previous_pair, shared, suite in old_entries:
        raw = previous_pair.model_dump(mode="json")
        routes = {}
        for role in ("control", "treatment"):
            previous_config = getattr(previous_pair, role).managed_host_config()
            spec = raw[role]
            routes[spec["id"]] = identifier = spec["id"].replace("sol-observed-", "sol-direct-")
            assert identifier != spec["id"]
            spec["id"] = identifier
            config = spec["config"]
            config["adapter_id"] = "codex-app-server:" + identifier
            config["managed_worker"]["worker_id"] = identifier.replace(".", "-")
            config["instructions"] = DIRECT_HINT + config["instructions"]
            assert config["timeout_seconds"] == 300.0
            assert config["invocation"]["mode"] == ("turn" if role == "control" else "skill")
            if role == "treatment":
                assert config["invocation"]["exposure"] == "optional"
            worker = prior.binding_from_config(config["managed_worker"])
            evidence = runtime["workers"][role]
            assert evidence["worker_image"] == worker.image and evidence["worker_cleanup_confirmed"]
            facts = evidence["facts"]
            assert facts["package_present"] == (role == "treatment")
            assert facts["read_only_package_root"] == (role == "treatment")
            bindings[config["adapter_id"]] = {
                "worker_digest": worker.digest(),
                "helper_sha256": old_bindings[previous_config.adapter_id]["helper_sha256"],
                "package_available": facts["package_present"],
                "package_tree_sha256": facts.get("files_sha256"),
            }
        assert raw["control"]["config"]["instructions"] == raw["treatment"]["config"]["instructions"]
        shared |= {
            "direct_observer_sha256": sha(HERE / "libcst_direct_observer.py"),
            "direct_observer_shared_guidance_sha256": content_digest(DIRECT_HINT),
        }
        differential = raw["differential"]
        differential["shared_definition_digest"] = content_digest(shared)
        inventory = {"capable_local_tools": differential["shared_definition_digest"]}
        differential["control_inventory"] = inventory
        differential["treatment_inventory"] = inventory | differential["candidate_inventory"]
        pair = type(previous_pair).model_validate(raw)
        suite = suite.model_copy(update={
            "suite_id": suite.suite_id.replace("-instrumented-", "-direct-use-"),
            "routes": [
                route.model_copy(update={
                    "route_id": routes[route.route_id], "executor_id": routes[route.executor_id],
                }) for route in suite.routes
            ],
            "baseline_route_id": pair.control.id,
        })
        entries.append((task, recipe, environment, value, truth, pair, shared, suite))
    assert len(entries) == 2 and len(bindings) == 4
    return entries, bindings


def preconditions():
    assert not RUN.exists()
    old, review, audit = read(prior.REVIEW), read(software.REVIEW), read(LAST_AUDIT)
    assert audit["canonical_result_sha256"] == sha(LAST_RESULT)
    assert audit["review_sha256"] == sha(software.REVIEW)
    assert audit["prior_reservations_unchanged"] and audit["proxy_exactly_restored_stopped"]
    assert audit["new_unsettled_operations"] == 0
    assert all(sha(Path(name)) == digest for name, digest in review["pins"].items())
    prior.verify_assets(old)
    original, effective, counters, amendment, pending = snapshot()
    start = old["grant"]["unchanged_counters"]
    accounted = audit["cumulative_accounting"]
    assert (
        (counters[1] - start[0], counters[2] - start[1])
        == (accounted["operations"], accounted["turns"]) == (78, 15)
    )
    assert abs(counters[3] - start[2] - accounted["summed_operation_seconds"]) < 1e-7
    assert float(counters[4]) == float(accounted["cash_usd"]) == 0
    assert amendment == old["grant"]["canonical_amendment_digest"]
    assert content_digest(pending) == old["grant"]["prior_reservations_sha256"]
    assert utc_now() < effective.expires_at and prior.proxy_state(old["proxy"]["Id"]) == old["proxy"]
    with ReceiptStore(DATABASE, read_only=True) as store:
        require_stack_complete(AssessmentRepository(store), old["stack_completion_ref"],
                               source_digest=old["implementation_source"])
    return old, original, effective, list(counters[1:]), {row[0] for row in pending}


def verify_offline():
    review = read(OFFLINE_REVIEW)
    evidence = read(OFFLINE_RESULT)
    assert review["driver_sha256"] == sha(HERE / "check_libcst_direct.py")
    assert review["classifier_sha256"] == sha(HERE / "libcst_direct_observer.py")
    assert evidence["review_sha256"] == sha(OFFLINE_REVIEW)
    assert evidence["checks"] == checks()
    assert evidence["model_turns"] == 0 and float(evidence["cash_usd"]) == 0
    assert review["network"] == "none" and review["credential_mounts"] == 0
    control, treatment = (evidence["workers"][role] for role in ("control", "treatment"))
    assert control["exit_codes"] == {"import": 1, "mention": 0}
    assert treatment["exit_codes"] == {
        "import": 0, "mention": 0, "parse": 0, "heredoc_transform_changed": 0,
        "noop_transform": 0, "read_workspace_source": 0, "parse_error": 1,
    }
    assert all(
        docker("image", "inspect", "--format", "{{.Id}}", row["worker_image"]) == row["worker_image"]
        for row in (control, treatment)
    )


async def freeze():
    old, _, effective, counters, _ = preconditions()
    verify_offline()
    entries, bindings = study_entries()
    tasks = await repaired.bound_tasks(entries)
    for before, after in zip(read(software.REVIEW)["tasks"], tasks, strict=True):
        assert all(before[key] == after[key] for key in (
            "task_id", "recipe_digest", "protected_environment_digest",
        ))
        assert [route.rpartition(".")[2] for route in before["arm_order"]] == [
            route.rpartition(".")[2] for route in after["arm_order"]
        ]
    operations = 21
    seconds = (
        4 * 240 + 6 * 30 + 4 * 305 + 2 * 30 + 120
        + sum(2 * (entry[1].extension.grader.config["timeout_seconds"] + 5) for entry in entries)
    )
    runpy.run_path(str(prior.BUDGET))["require_room"](
        counters, old["grant"]["unchanged_counters"],
        AssessmentLimits(max_operations=operations, max_model_turns=4, max_elapsed_seconds=seconds),
        ENVELOPE,
    )
    pins = [
        Path(__file__), prior.REVIEW, software.REVIEW, LAST_AUDIT, LAST_RESULT,
        HERE / "libcst_direct_observer.py", HERE / "check_libcst_direct.py",
        HERE / "software_rerun.py", OFFLINE_REVIEW, OFFLINE_RESULT,
    ]
    review = {
        "operator_authority": AUTHORITY,
        "opening_counters": counters,
        "grant_expiry": effective.expires_at.isoformat(),
        "model": "gpt-6.1-sol", "reasoning_effort": "medium",
        "destination": "existing managed Codex proxy",
        "tasks": tasks, "observer_bindings": bindings, "cumulative_ceiling": ENVELOPE,
        "maximum_new_operations": operations,
        "maximum_new_model_turns": 4,
        "maximum_reserved_seconds": seconds,
        "automatic_retries": 0,
        "direct_scope": "Pinned isolated Python inline import, parse and transform calls; other paths unknown",
        "inputs": "Same reviewed public repository snapshots and protected grade contracts",
        "worker_changes": False,
        "pins": {str(path.resolve()): sha(path) for path in pins},
    }
    write(REVIEW, review)
    print(sha(REVIEW))


def diagnostics(entry, folder, task_result, review, repo):
    with patch.object(software, "RUN", RUN):
        records = software.diagnostics(entry, folder, task_result, review, repo)
    for index in (1, 2):
        trial = read(folder / f"trial-{index}.json")
        receipt = ExecutionReceipt.model_validate(trial["receipt"])
        [arm] = [row for row in records.values() if row["receipt_ref"] == trial["receipt_ref"]]
        sidecar = read(RUN / "direct-observers" / (content_digest(receipt.metadata["attempt_id"]) + ".json"))
        binding = review["observer_bindings"][receipt.metadata["adapter_id"]]
        with sqlite3.connect((folder / "campaign.sqlite3").as_uri() + "?mode=ro", uri=True) as campaign:
            [(database,)] = campaign.execute(
                "SELECT database_path FROM trial_stores WHERE trial_id=?", (trial["trial_id"],)
            ).fetchall()
        path = Path(database).resolve()
        assert path.parent == (folder / "attempts").resolve()
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as attempt:
            [(payload,)] = attempt.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
                (receipt.metadata["execution_evidence_digest"],),
            ).fetchall()
        journal = bound_journal(receipt, json.loads(payload))
        calls = validate_direct_calls(sidecar, receipt, journal, binding)
        arm |= {
            "positive_direct_calls": calls,
            "observed_direct_import_count": sum(call["import_calls"] for call in calls),
            "observed_direct_parse_count": sum(call["parse_calls"] for call in calls),
            "observed_direct_transform_count": sum(call["transform_calls"] for call in calls),
            "observed_direct_equal_preview_assertions": sum(call["equal_preview_assertions"] for call in calls),
            "observed_direct_different_preview_assertions": sum(call["different_preview_assertions"] for call in calls),
            "direct_observation_overflow": sidecar["overflow"],
            "uncovered_direct_paths": "unknown",
        }
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
    verify_offline()
    assert (
        counters == review["opening_counters"]
        and effective.expires_at.isoformat() == review["grant_expiry"]
    )
    entries, bindings = study_entries()
    assert await repaired.bound_tasks(entries) == review["tasks"]
    assert bindings == review["observer_bindings"]
    router = Router.from_manifest(prior.BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    stamp = "sol-development-proxy-libcst-direct-20261116"
    operation = stamp + ":owned-start-stop"
    result = {"review_sha256": identity, "completed": False, "tasks": []}
    started = owned = False
    startup = 0.0
    try:
        RUN.mkdir(mode=0o700)
        started = True
        write(RUN / "started.json", {"review_sha256": identity, "retries": 0})
        observers, direct = RUN / "observers", RUN / "direct-observers"
        observers.mkdir(mode=0o700)
        direct.mkdir(mode=0o700)
        runpy.run_path(str(prior.BUDGET))["install"](
            repo, router.store._connection, old["grant"]["unchanged_counters"], ENVELOPE,
        )
        subject = prior.store_doc(repo, "subject", _Document(value={"exact_direct_libcst_review": identity}))
        request = prior.request(
            repo, stamp, subject, prior.store_doc(repo, "recipe", entries[0][1]),
            AssessmentEnvironment(
                environment_id=stamp, kind="trusted_local", identity={"review": identity},
            ),
        )
        prior.scope(repo, original, [request], RUN, "proxy")
        repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
                     stage="retained_codex_proxy_control")
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
                authenticated.append(await prior.authenticate_pair(
                    service, original, task, recipe, pair, shared, subject, folder, verify,
                ))
            truth = {entry[0]["id"]: entry[4] for entry in entries}
            with (
                watch_software_workers(observers, bindings),
                watch_direct_workers(direct, bindings),
                observe_grader(truth, repo),
            ):
                for entry, proof, refs in zip(entries, review["tasks"], authenticated, strict=True):
                    folder = RUN / entry[0]["id"]
                    task_result = await prior.run_task(
                        service, original, entry, proof, refs, subject, folder, verify,
                    )
                    task_result["diagnostics"] = diagnostics(entry, folder, task_result, review, repo)
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
                    result["proxy_restored_stopped"] = prior.proxy_state(old["proxy"]["Id"]) == old["proxy"]
                    if result["proxy_restored_stopped"]:
                        repo.finish_operation(operation, elapsed_seconds=startup + time.perf_counter() - at)
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
