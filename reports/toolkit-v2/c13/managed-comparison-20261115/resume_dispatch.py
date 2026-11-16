"""Finish the same development study after correcting its Sales artifact handoff."""

import argparse
import asyncio
import runpy
import sys
import time
from pathlib import Path

import run_dispatch as prior
from dispatch_tasks import bind_tasks, verify_prompt
from freeze_study import DATABASE
from prepare_renewal import snapshot
from prepare_runtime import DESIGN_SHA256, WORK, docker, read, sha, write

from aeep.assessment.boundary import BoundaryConformance, require_managed_boundaries
from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.models import utc_now
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_stack_complete
from aeep_toolkit.worker_readiness import _Document

OLD_REVIEW = "bd939ed730bebfe8c12005bc05b57cf085328809ee7f326dc5f34deb9eb907f0"
OLD_OUTCOME = "d9b1e39c27b0a2787d5e3406fadc67d152f15968601a3c7058ef716fd2d4dd00"
SCRIPT = Path(__file__).resolve()
PARENT_OUTCOME = prior.HERE / "dispatch-outcome.json"
REVIEW = prior.HERE / "sales-handoff-continuation-review.json"
RUN = WORK / "sales-handoff-continuation"
AUTHORITY = (
    "Operator directed completing this approved experiment, including fixing its mistakes "
    "without asking for repeated approval, and delegated the experiment to a subagent."
)
ENVELOPE = {
    "maximum_operations": 48,
    "maximum_reserved_seconds": 6800,
    "maximum_model_turns": 9,
    "maximum_cash_usd": "0",
}


def bind_continuation():
    from sales_handoff import corrected_sales_instructions

    entries = []
    for index, entry in enumerate(bind_tasks(), 1):
        task, recipe, protected, value, truth, pair, shared, suite = entry
        if index == 1:
            raw = pair.model_dump(mode="json")
            routes = []
            for role in ("control", "treatment"):
                spec = raw[role]
                config = spec["config"]
                # Distinct inspection and trial keys preserve the previous settled attempt.
                spec["id"] = f"sol-pilot-repair-1.{role}"
                config["adapter_id"] = "codex-app-server:" + spec["id"]
                config["managed_worker"]["worker_id"] = spec["id"].replace(".", "-")
                config["instructions"] = corrected_sales_instructions(config["instructions"])
                routes.append(
                    suite.routes[len(routes)].model_copy(
                        update={"route_id": spec["id"], "executor_id": spec["id"]},
                    )
                )
            assert (
                raw["control"]["config"]["instructions"]
                == raw["treatment"]["config"]["instructions"]
            )
            shared = shared | {
                "shared_workbook_handoff": content_digest(
                    {"instructions": raw["control"]["config"]["instructions"]}
                )
            }
            diff = raw["differential"]
            diff["shared_definition_digest"] = content_digest(shared)
            inventory = {"capable_local_tools": content_digest(shared)}
            diff["control_inventory"] = inventory
            diff["treatment_inventory"] = inventory | diff["candidate_inventory"]
            pair = type(pair).model_validate(raw)
            suite = suite.model_copy(
                update={"routes": routes, "baseline_route_id": pair.control.id}
            )
        suite = suite.model_copy(
            update={"suite_id": f"managed-sol-comparison-20261116-repair-{index}"}
        )
        entries.append((task, recipe, protected, value, truth, pair, shared, suite))
    return entries


async def bound_tasks(entries):
    tasks = []
    for task, recipe, environment, _, _, pair, shared, suite in entries:
        tasks.append(
            {
                "task_id": task["id"],
                "recipe_digest": content_digest(recipe),
                "protected_environment_digest": content_digest(environment),
                "pair_digest": content_digest(pair),
                "shared_definition_digest": content_digest(shared),
                "suite_digest": content_digest(suite),
                "instruction_sha256": await verify_prompt(pair, suite),
                "arm_order": [route.route_id for route in suite.routes],
            }
        )
    return tasks


def previous_boundaries(repo, entry, outcome):
    task, _, environment, _, _, pair, _, _ = entry
    path = prior.RUN / task["id"] / "authenticated-readiness.json"
    assert sha(path) == outcome["authenticated_readiness"][task["id"]]["readiness_sha256"]
    boundary = read(path)["boundaries"]
    references, identities, specs = {}, {}, []
    for role, row in boundary.items():
        spec = getattr(pair, role)
        ref = row["conformance_digest"]
        record = BoundaryConformance.model_validate(repo.get("boundary_conformance", ref))
        assert content_digest(record) == ref and row["observed_probe_count"] == 11
        references[spec.id] = ref
        identities[spec.id] = row["identity_digest"]
        specs.append(spec)
    require_managed_boundaries(
        repo,
        environment.model_copy(update={"conformance_digests": references}),
        specs,
        identities,
    )
    return references


def preconditions():
    assert sha(prior.REVIEW) == OLD_REVIEW and sha(PARENT_OUTCOME) == OLD_OUTCOME
    old = read(prior.REVIEW)
    outcome = read(PARENT_OUTCOME)
    prior.verify_assets(old)
    assert not RUN.exists()
    assert read(prior.APPROVAL) == {"approved": True, "review_sha256": OLD_REVIEW}
    assert outcome["model_turns_dispatched"] == 1 and outcome["completed_pairs"] == 0
    assert outcome["observed_trial"]["failure_code"] == "worker_artifact_failed"
    assert outcome["observed_trial"]["worker_cleanup_confirmed"]
    assert outcome["accounting"]["new_unsettled_operations"] == 0
    assert (
        sha(Path(outcome["raw_evidence"]["local_result"]))
        == outcome["raw_evidence"]["local_result_sha256"]
    )
    original, effective, counters, latest, pending = snapshot()
    assert latest == old["grant"]["canonical_amendment_digest"]
    assert utc_now() < effective.expires_at
    assert content_digest(pending) == old["grant"]["prior_reservations_sha256"]
    initial = old["grant"]["unchanged_counters"]
    assert list(counters[1:3]) == [initial[0] + 12, initial[1] + 1]
    assert (
        abs(counters[3] - (initial[2] + outcome["accounting"]["settled_operation_seconds"])) < 1e-7
    )
    assert float(counters[4]) == 0
    state = prior.proxy_state(old["proxy"]["Id"])
    assert state == old["proxy"] and not state["Running"]
    return old, outcome, original, effective, list(counters[1:]), pending


async def freeze(smoke):
    old, outcome, _, effective, counters, _ = preconditions()
    entries = bind_continuation()
    tasks = await bound_tasks(entries)
    for index, (before, after) in enumerate(zip(old["tasks"], tasks, strict=True)):
        different = {key for key in before if before[key] != after[key]}
        assert different == (
            {
                "suite_digest",
                "pair_digest",
                "shared_definition_digest",
                "instruction_sha256",
                "arm_order",
            }
            if index == 0
            else {"suite_digest"}
        )
    with ReceiptStore(DATABASE, read_only=True) as store:
        repo = AssessmentRepository(store)
        require_stack_complete(
            repo, old["stack_completion_ref"], source_digest=old["implementation_source"]
        )
        for entry in entries[1:]:
            assert len(previous_boundaries(repo, entry, outcome)) == 2
    # Two changed probes, three routers, two turns and two grades per case, four reports, one proxy.
    operations = 2 + 4 * (3 + 2 + 2 + 1) + 1
    seconds = (
        2 * 240
        + 8 * 305
        + 12 * 30
        + 4 * 30
        + 120
        + sum(2 * (entry[1].extension.grader.config["timeout_seconds"] + 5) for entry in entries)
    )
    budget = runpy.run_path(str(prior.BUDGET))
    budget["require_room"](
        counters,
        old["grant"]["unchanged_counters"],
        AssessmentLimits(max_model_turns=8, max_operations=operations, max_elapsed_seconds=seconds),
        ENVELOPE,
    )
    smoke_result = read(smoke)
    smoke_review = WORK / "sales-handoff-offline-review.json"
    assert smoke_result["review_sha256"] == sha(smoke_review)
    assert smoke_result["synthetic_output"] is True
    assert set(smoke_result["workers"]) == {"control", "treatment"}
    for role, record in smoke_result["workers"].items():
        worker = getattr(entries[0][5], role).managed_host_config().managed_worker
        assert record["worker_image"] == worker["image"]
        assert record["input_archive_readable"] and record["owned_worker_removed"]
        assert 1 <= record["output_bytes"] <= 300_000 and record["model_turns"] == 0
        assert set(record["rejected_transfer_controls"]) == {
            "missing",
            "overwrite",
            "oversize",
            "symlink",
            "directory",
        }
    assets = [
        smoke_review,
        prior.HERE / "check_sales_handoff.py",
        SCRIPT,
        prior.HERE / "sales_handoff.py",
        prior.REVIEW,
        PARENT_OUTCOME,
        smoke.resolve(strict=True),
    ]
    review = {
        "parent_review_sha256": OLD_REVIEW,
        "parent_outcome_sha256": OLD_OUTCOME,
        "design_sha256": DESIGN_SHA256,
        "delegated_authority": AUTHORITY,
        "model": old["model"],
        "reasoning_effort": old["reasoning_effort"],
        "destination": "existing managed Codex proxy",
        "implementation_source": old["implementation_source"],
        "stack_completion_ref": old["stack_completion_ref"],
        "grant_expiry": effective.expires_at.isoformat(),
        "opening_counters": counters,
        "cumulative_ceiling": ENVELOPE,
        "prior_failed_turns": 1,
        "remaining_trial_slots": 8,
        "replacement_turns": 1,
        "automatic_retries": 0,
        "calculated_new_operation_bound": operations,
        "calculated_new_reserved_seconds": seconds,
        "fresh_sales_worker_checks": 2,
        "reused_unchanged_worker_checks": 6,
        "tasks": tasks,
        "pins": {str(path): sha(path) for path in assets},
    }
    write(REVIEW, review)
    print(sha(REVIEW))


async def execute(identity):
    assert not sys.flags.optimize
    assert sha(REVIEW) == identity
    review = read(REVIEW)
    assert review["delegated_authority"] == AUTHORITY and review["cumulative_ceiling"] == ENVELOPE

    def check_pins():
        for name, digest in review["pins"].items():
            assert sha(Path(name)) == digest

    check_pins()
    old, previous, original, effective, counters, pending = preconditions()
    assert counters == review["opening_counters"]
    assert effective.expires_at.isoformat() == review["grant_expiry"]
    entries = bind_continuation()
    assert await bound_tasks(entries) == review["tasks"]
    router = Router.from_manifest(prior.BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    before = {row[0] for row in pending}
    stamp = "sol-development-proxy-handoff-20261116"
    operation_id = stamp + ":owned-start-stop"
    started = False
    proxy_owned = False
    start_elapsed = 0.0
    result = {"review_sha256": identity, "completed": False, "prior_failed_turns": 1, "tasks": []}
    try:
        require_stack_complete(
            repo, review["stack_completion_ref"], source_digest=review["implementation_source"]
        )
        reused = [previous_boundaries(repo, entry, previous) for entry in entries[1:]]
        RUN.mkdir(mode=0o700)
        started = True
        write(RUN / "started.json", {"review_sha256": identity, "restart_allowed": False})
        runpy.run_path(str(prior.BUDGET))["install"](
            repo,
            router.store._connection,
            old["grant"]["unchanged_counters"],
            ENVELOPE,
        )
        subject = prior.store_doc(
            repo,
            "subject",
            _Document(
                value={
                    "purpose": "same four paired development tasks with corrected shared Sales artifact handoff",
                    "prior_review_sha256": OLD_REVIEW,
                    "review_sha256": identity,
                }
            ),
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
            operation_id,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
            stage="retained_codex_proxy_control",
        )
        start_clock = time.perf_counter()
        proxy_owned = True
        try:
            docker("start", old["proxy"]["Id"])
        finally:
            start_elapsed = time.perf_counter() - start_clock

        def verify():
            check_pins()
            prior.verify_assets(old)
            assert utc_now() < effective.expires_at
            assert before <= prior.reservations(repo)
            state = prior.proxy_state(old["proxy"]["Id"])
            assert state["Running"]
            for field in ("Id", "Image", "Memory", "MemorySwap"):
                assert state[field] == old["proxy"][field]
            assert {name: row["NetworkID"] for name, row in state["Networks"].items()} == {
                name: row["NetworkID"] for name, row in old["proxy"]["Networks"].items()
            }
            assert state["Networks"]["aeep-reviewed-model-private"]["IPAddress"] == "172.18.0.2"

        async with asyncio.timeout(old["proxy_session_wall_timeout_seconds"]):
            for entry in entries:
                (RUN / entry[0]["id"]).mkdir(mode=0o700)
            task, recipe, _, _, _, pair, shared, _ = entries[0]
            refreshed = await prior.authenticate_pair(
                service,
                original,
                task,
                recipe,
                pair,
                shared,
                subject,
                RUN / task["id"],
                verify,
            )
            for entry, proof, refs in zip(
                entries, review["tasks"], [refreshed, *reused], strict=True
            ):
                verify()
                result["tasks"].append(
                    await prior.run_task(
                        service,
                        original,
                        entry,
                        proof,
                        refs,
                        subject,
                        RUN / entry[0]["id"],
                        verify,
                    )
                )
            result["completed"] = len(result["tasks"]) == 4
    except BaseException as error:
        result.update(completed=False, error_type=type(error).__name__)
        raise
    finally:
        if started:
            if proxy_owned:
                began = time.perf_counter()
                try:
                    if prior.proxy_state(old["proxy"]["Id"])["Running"]:
                        docker("stop", "--time", "5", old["proxy"]["Id"])
                    result["proxy_restored_stopped"] = not prior.proxy_state(old["proxy"]["Id"])[
                        "Running"
                    ]
                    if result["proxy_restored_stopped"]:
                        repo.finish_operation(
                            operation_id,
                            elapsed_seconds=start_elapsed + time.perf_counter() - began,
                        )
                except BaseException as error:
                    result.update(completed=False, cleanup_error=type(error).__name__)
            result["new_unsettled_operations"] = sorted(prior.reservations(repo) - before)
            if result["new_unsettled_operations"]:
                result["completed"] = False
            write(RUN / "result.json", result)
            prior.render_result(result, RUN)
        await router.close()
    if not result["completed"]:
        raise RuntimeError("stopped without a verified four-pair result")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--freeze", type=Path, metavar="SMOKE_RECEIPT")
    command.add_argument("--execute", metavar="REVIEW_SHA256")
    arguments = parser.parse_args()
    asyncio.run(freeze(arguments.freeze) if arguments.freeze else execute(arguments.execute))
