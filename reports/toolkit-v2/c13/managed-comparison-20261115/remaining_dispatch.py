"""Continue the six untouched slots after the settled Sales treatment timeout."""

import argparse
import asyncio
import runpy
import sys
import time
from pathlib import Path

import resume_dispatch as resumed
import run_dispatch as prior
from freeze_study import DATABASE
from prepare_renewal import snapshot
from prepare_runtime import WORK, docker, read, sha, write

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.models import utc_now
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_stack_complete
from aeep_toolkit.worker_readiness import _Document

SCRIPT = Path(__file__).resolve()
REVIEW = prior.HERE / "remaining-three-review.json"
RUN = WORK / "remaining-three-dispatch"
TIMEOUT = (
    "trial_managed-sol-comparison-20261116-repair-1_development-sales-pivot-analysis"
    "_sol-pilot-repair-1.treatment_fresh-worker_0"
)


def preconditions():
    old, repaired = read(prior.REVIEW), read(resumed.REVIEW)
    previous = read(resumed.PARENT_OUTCOME)
    assert (
        sha(prior.REVIEW) == resumed.OLD_REVIEW
        and sha(resumed.PARENT_OUTCOME) == resumed.OLD_OUTCOME
    )
    prior.verify_assets(old)
    for file, expected in repaired["pins"].items():
        assert sha(Path(file)) == expected
    end = read(resumed.RUN / "result.json")
    assert end["review_sha256"] == sha(resumed.REVIEW)
    assert not end["completed"] and end["proxy_restored_stopped"]
    assert end["tasks"] == [] and end["new_unsettled_operations"] == [TIMEOUT]
    first_arm = read(resumed.RUN / "sales-pivot-analysis" / "trial-1.json")
    assert first_arm["canonical_trial_complete"] and first_arm["independent_grader_observed"]
    assert (
        first_arm["token_capture"]["status"] == "verified" and first_arm["worker_cleanup_confirmed"]
    )
    original, effective, counters, latest, pending = snapshot()
    assert latest == old["grant"]["canonical_amendment_digest"]
    assert utc_now() < effective.expires_at
    assert content_digest(pending) == old["grant"]["prior_reservations_sha256"]
    assert prior.proxy_state(old["proxy"]["Id"]) == old["proxy"] and not old["proxy"]["Running"]
    initial = old["grant"]["unchanged_counters"]
    assert counters[2] == initial[1] + 3
    with ReceiptStore(DATABASE, read_only=True) as store:
        repo = AssessmentRepository(store)
        assert (
            store._connection.execute(
                "SELECT state FROM assessment_operations WHERE id=?",
                (TIMEOUT,),
            ).fetchone()[0]
            == "complete"
        )
        charge = repo.get("operation_measurement", TIMEOUT)
        assert charge["operation_id"] == TIMEOUT and charge["stage"] == "managed_sol_trial"
        assert (
            300 <= charge["elapsed_seconds"] <= 305 and charge["reserved"]["max_model_turns"] == 1
        )
        completion = require_stack_complete(
            repo,
            old["stack_completion_ref"],
            source_digest=old["implementation_source"],
        )
        assert content_digest(completion) == old["stack_completion_ref"]
        entries = resumed.bind_continuation()[1:]
        refs = [resumed.previous_boundaries(repo, entry, previous) for entry in entries]
    return old, repaired, entries, refs, original, effective, list(counters[1:]), pending, charge


async def freeze(settlement):
    old, repaired, entries, refs, _, effective, counters, _, charge = preconditions()
    assert not RUN.exists()
    settled = read(settlement)
    assert settled["operation_id"] == TIMEOUT and settled["grant_after"] == counters
    assert settled["new_unsettled_operations"] == 0
    tasks = await resumed.bound_tasks(entries)
    assert tasks == repaired["tasks"][1:]
    assert all(len(pair) == 2 for pair in refs)
    operations = 3 * (3 + 2 + 2 + 1) + 1
    seconds = (
        6 * 305
        + 9 * 30
        + 3 * 30
        + 120
        + sum(2 * (entry[1].extension.grader.config["timeout_seconds"] + 5) for entry in entries)
    )
    runpy.run_path(str(prior.BUDGET))["require_room"](
        counters,
        old["grant"]["unchanged_counters"],
        AssessmentLimits(max_model_turns=6, max_operations=operations, max_elapsed_seconds=seconds),
        resumed.ENVELOPE,
    )
    pins = [
        SCRIPT,
        resumed.REVIEW,
        settlement.resolve(strict=True),
        resumed.RUN / "result.json",
        resumed.RUN / "sales-pivot-analysis" / "trial-1.json",
    ]
    review = {
        "delegated_authority": resumed.AUTHORITY,
        "prior_review_sha256": sha(resumed.REVIEW),
        "settled_timeout_charge_ref": content_digest(charge),
        "cumulative_ceiling": resumed.ENVELOPE,
        "opening_counters": counters,
        "grant_expiry": effective.expires_at.isoformat(),
        "checks_reused": 6,
        "new_turns": 6,
        "new_operation_bound": operations,
        "new_reserved_seconds_bound": seconds,
        "retries": 0,
        "tasks": tasks,
        "pins": {str(path): sha(path) for path in pins},
    }
    write(REVIEW, review)
    print(sha(REVIEW))


async def execute(identity):
    assert not sys.flags.optimize
    assert sha(REVIEW) == identity
    review = read(REVIEW)
    assert review["delegated_authority"] == resumed.AUTHORITY
    assert review["cumulative_ceiling"] == resumed.ENVELOPE

    def check_pins():
        for name, expected in review["pins"].items():
            assert sha(Path(name)) == expected

    check_pins()
    old, _, entries, refs, original, effective, counters, pending, charge = preconditions()
    assert content_digest(charge) == review["settled_timeout_charge_ref"]
    assert counters == review["opening_counters"]
    assert effective.expires_at.isoformat() == review["grant_expiry"]
    assert await resumed.bound_tasks(entries) == review["tasks"]
    router = Router.from_manifest(prior.BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    before = {row[0] for row in pending}
    stamp = "sol-development-proxy-remaining-20261116"
    operation = stamp + ":owned-start-stop"
    started = False
    proxy_owned = False
    startup = 0.0
    result = {
        "review_sha256": identity,
        "completed": False,
        "sales_timeout_preserved": True,
        "tasks": [],
    }
    try:
        RUN.mkdir(mode=0o700)
        started = True
        write(RUN / "started.json", {"review_sha256": identity, "restart_allowed": False})
        runpy.run_path(str(prior.BUDGET))["install"](
            repo,
            router.store._connection,
            old["grant"]["unchanged_counters"],
            resumed.ENVELOPE,
        )
        subject = prior.store_doc(
            repo,
            "subject",
            _Document(
                value={
                    "purpose": "run only the final three untouched task pairs",
                    "exact_continuation": identity,
                    "model": old["model"],
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
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
            stage="retained_codex_proxy_control",
        )
        started_at = time.perf_counter()
        proxy_owned = True
        try:
            docker("start", old["proxy"]["Id"])
        finally:
            startup = time.perf_counter() - started_at

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
            for entry, proof, pair_refs in zip(entries, review["tasks"], refs, strict=True):
                verify()
                folder = RUN / entry[0]["id"]
                folder.mkdir(mode=0o700)
                result["tasks"].append(
                    await prior.run_task(
                        service,
                        original,
                        entry,
                        proof,
                        pair_refs,
                        subject,
                        folder,
                        verify,
                    )
                )
            result["completed"] = len(result["tasks"]) == 3
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
                            operation, elapsed_seconds=startup + time.perf_counter() - began
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
        raise RuntimeError("one or more remaining pairs failed evidence verification")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    command = parser.add_mutually_exclusive_group(required=True)
    command.add_argument("--freeze", type=Path, metavar="SETTLEMENT_EVIDENCE")
    command.add_argument("--execute", metavar="REVIEW_SHA256")
    arguments = parser.parse_args()
    asyncio.run(freeze(arguments.freeze) if arguments.freeze else execute(arguments.execute))
