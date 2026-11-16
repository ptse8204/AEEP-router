"""Complete Sales Pivot as a fresh development pair under a matched deadline."""

import argparse
import asyncio
import runpy
import sys
import time
from pathlib import Path

import remaining_dispatch as remaining
import resume_dispatch as repaired
import run_dispatch as prior
from check_sales_runtime import RESULT as OFFLINE_RESULT
from check_sales_runtime import REVIEW as OFFLINE_REVIEW
from check_sales_runtime import frozen as offline_bindings
from freeze_study import DATABASE
from prepare_renewal import snapshot
from prepare_runtime import WORK, docker, read, sha, write
from run_sales_pair import run_pair

from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.models import utc_now
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.stack_readiness import require_stack_complete
from aeep_toolkit.worker_readiness import _Document

HERE = Path(__file__).resolve().parent
REVIEW = HERE / "sales-window-review.json"
RUN = WORK / "sales-window-dispatch"
HISTORY = HERE / "comparison-continuation-result.json"
TIMEOUT_RECEIPT = HERE / "sales-treatment-timeout.json"
DEADLINE = 480
ENVELOPE = {
    "maximum_operations": 57,
    "maximum_model_turns": 11,
    "maximum_reserved_seconds": 6800,
    "maximum_cash_usd": "0",
}
AUTHORITY = (
    "Operator explicitly asked the delegated experiment agent to explain the Sales timeout "
    "and finish the pair. Review one fresh matched pair, preserve prior charges, no automatic replay."
)
BOOTSTRAP = (
    "Any optional spreadsheet tools remain optional. If you choose an available "
    "JavaScript spreadsheet package and its import from a workspace script does not resolve, "
    "check the existing local directory "
    "/worker/home/.cache/codex-runtimes/codex-primary-runtime/dependencies/node_modules. "
    "If it exists and /workspace/node_modules is absent, you may link the latter to the "
    "existing directory for normal module resolution. If the package is unavailable, "
    "continue with ordinary local tools. Do not install or change any dependencies. "
)


def sales_entry():
    task, recipe, environment, value, truth, pair, shared, suite = repaired.bind_continuation()[0]
    assert task["id"] == "sales-pivot-analysis"
    raw = pair.model_dump(mode="json")
    routes = []
    for index, role in enumerate(("control", "treatment")):
        spec = raw[role]
        spec["id"] = "sol-pilot-sales-window." + role
        config = spec["config"]
        config["adapter_id"] = "codex-app-server:" + spec["id"]
        config["managed_worker"]["worker_id"] = spec["id"].replace(".", "-")
        config["instructions"] = BOOTSTRAP + config["instructions"]
        config["timeout_seconds"] = float(DEADLINE)
        routes.append(
            suite.routes[index].model_copy(
                update={"route_id": spec["id"], "executor_id": spec["id"]}
            )
        )
    assert raw["control"]["config"]["instructions"] == raw["treatment"]["config"]["instructions"]
    shared = shared | {
        "matched_task_deadline_seconds": DEADLINE,
        "optional_existing_module_resolution_hint_sha256": content_digest({"hint": BOOTSTRAP}),
    }
    difference = raw["differential"]
    difference["shared_definition_digest"] = content_digest(shared)
    inventory = {"capable_local_tools": difference["shared_definition_digest"]}
    difference["control_inventory"] = inventory
    difference["treatment_inventory"] = inventory | difference["candidate_inventory"]
    pair = type(pair).model_validate(raw)
    suite = suite.model_copy(
        update={
            "suite_id": "managed-sol-comparison-20261116-sales-window",
            "routes": routes,
            "baseline_route_id": pair.control.id,
        }
    )
    return task, recipe, environment, value, truth, pair, shared, suite


def preflight():
    assert not RUN.exists()
    old, history, timeout = read(prior.REVIEW), read(HISTORY), read(TIMEOUT_RECEIPT)
    prior.verify_assets(old)
    assert sha(prior.REVIEW) == repaired.OLD_REVIEW == history["original_dispatch_review_sha256"]
    assert sha(remaining.REVIEW) == history["remaining_tasks_review_sha256"]
    assert sha(repaired.REVIEW) == history["sales_repair_review_sha256"] == timeout["review_sha256"]
    result = remaining.RUN / "result.json"
    assert sha(result) == history["raw_result_sha256"]
    completed = read(result)
    assert completed["completed"] and len(completed["tasks"]) == 3
    assert completed["tasks"] == history["complete_pairs"]
    assert history["model"] == old["model"] == "gpt-6.1-sol"
    assert history["reasoning_effort"] == old["reasoning_effort"] == "medium"
    assert (
        timeout["status"] == "timeout"
        and timeout["grade"] is None
        and 300 <= timeout["agent_wall_seconds"] <= 305
    )
    original, effective, counters, amendment, pending = snapshot()
    grant = old["grant"]
    start = grant["unchanged_counters"]
    accrued = history["accounting"]
    assert accrued["settled_operations"] == 46 and accrued["charged_turns"] == 9
    assert (counters[1] - start[0], counters[2] - start[1]) == (46, 9)
    assert abs(counters[3] - start[2] - accrued["settled_operation_seconds"]) < 1e-7
    assert float(counters[4]) == 0
    assert amendment == grant["canonical_amendment_digest"]
    assert content_digest(pending) == grant["prior_reservations_sha256"]
    assert utc_now() < effective.expires_at
    assert prior.proxy_state(old["proxy"]["Id"]) == old["proxy"] and not old["proxy"]["Running"]
    with ReceiptStore(DATABASE, read_only=True) as store:
        repo = AssessmentRepository(store)
        require_stack_complete(
            repo, old["stack_completion_ref"], source_digest=old["implementation_source"]
        )
        measured = repo.get("operation_measurement", timeout["operation_id"])
        assert content_digest(measured) == timeout["measurement_ref"]
    return old, original, effective, list(counters[1:]), pending


async def freeze():
    old, _, effective, counters, _ = preflight()
    entry = sales_entry()
    [task] = await repaired.bound_tasks([entry])
    historical = read(repaired.REVIEW)["tasks"][0]
    assert {
        "pair_digest",
        "shared_definition_digest",
        "suite_digest",
        "instruction_sha256",
        "arm_order",
    } == {key for key in task if task[key] != historical[key]}
    probe = read(OFFLINE_RESULT)
    assert read(OFFLINE_REVIEW) == offline_bindings() and probe["review_sha256"] == sha(
        OFFLINE_REVIEW
    )
    assert probe["model_turns"] == 0
    for role in ("control", "treatment"):
        record = probe["workers"][role]
        cfg = getattr(entry[5], role).managed_host_config()
        assert (
            cfg.timeout_seconds == DEADLINE
            and cfg.managed_worker["image"] == record["worker_image"]
        )
        assert record["bare_import_module_not_found"] and record["worker_cleanup_confirmed"]
        assert record["candidate_package_available"] is (role == "treatment")
        assert record["scoped_alias_export_verified"] is (role == "treatment")
    grade_limit = int(entry[1].extension.grader.config["timeout_seconds"]) + 5
    operations = 11  # two inspections, three routers, two turns, two grades, one report, one proxy
    seconds = 2 * 240 + 3 * 30 + 2 * (DEADLINE + 5) + 2 * grade_limit + 30 + 120
    runpy.run_path(str(prior.BUDGET))["require_room"](
        counters,
        old["grant"]["unchanged_counters"],
        AssessmentLimits(max_operations=operations, max_model_turns=2, max_elapsed_seconds=seconds),
        ENVELOPE,
    )
    paths = [
        Path(__file__),
        HERE / "check_sales_runtime.py",
        HERE / "run_sales_pair.py",
        prior.REVIEW,
        repaired.REVIEW,
        remaining.REVIEW,
        HISTORY,
        TIMEOUT_RECEIPT,
        OFFLINE_REVIEW,
        OFFLINE_RESULT,
        remaining.RUN / "result.json",
    ]
    review = {
        "operator_authority": AUTHORITY,
        "purpose": "Report a fresh matched pair separately from the prior fixed 300 s observation.",
        "model": old["model"],
        "reasoning_effort": old["reasoning_effort"],
        "destination": "existing managed Codex proxy",
        "deadline_seconds_both_arms": DEADLINE,
        "prior_timeout_preserved": True,
        "task": task,
        "opening_counters": counters,
        "grant_expiry": effective.expires_at.isoformat(),
        "maximum_new_operations": operations,
        "maximum_new_model_turns": 2,
        "maximum_new_reserved_seconds": seconds,
        "cumulative_ceiling": ENVELOPE,
        "pins": {str(path.resolve()): sha(path) for path in paths},
        "automatic_retries": 0,
    }
    write(REVIEW, review)
    print(sha(REVIEW))


async def execute(identity):
    assert not sys.flags.optimize and sha(REVIEW) == identity
    review = read(REVIEW)
    assert review["operator_authority"] == AUTHORITY and review["cumulative_ceiling"] == ENVELOPE
    assert review["deadline_seconds_both_arms"] == DEADLINE

    def check_pins():
        assert sha(REVIEW) == identity
        for name, digest in review["pins"].items():
            assert sha(Path(name)) == digest

    check_pins()
    old, original, effective, counters, pending = preflight()
    assert (
        counters == review["opening_counters"]
        and effective.expires_at.isoformat() == review["grant_expiry"]
    )
    entry = sales_entry()
    assert await repaired.bound_tasks([entry]) == [review["task"]]
    router = Router.from_manifest(prior.BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    before = {row[0] for row in pending}
    stamp = "sol-development-proxy-sales-window-20261116"
    operation = stamp + ":owned-start-stop"
    result = {
        "review_sha256": identity,
        "completed": False,
        "tasks": [],
        "prior_timeout_preserved": True,
    }
    owned = False
    begun = False
    startup = 0.0
    try:
        RUN.mkdir(mode=0o700)
        begun = True
        write(RUN / "started.json", {"review_sha256": identity, "restart_allowed": False})
        runpy.run_path(str(prior.BUDGET))["install"](
            repo, router.store._connection, old["grant"]["unchanged_counters"], ENVELOPE
        )
        subject = prior.store_doc(
            repo, "subject", _Document(value={"exact_sales_window_review": identity})
        )
        request = prior.request(
            repo,
            stamp,
            subject,
            prior.store_doc(repo, "recipe", entry[1]),
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
        started = time.perf_counter()
        owned = True
        try:
            docker("start", old["proxy"]["Id"])
        finally:
            startup = time.perf_counter() - started

        def verify():
            check_pins()
            prior.verify_assets(old)
            assert utc_now() < effective.expires_at and before <= prior.reservations(repo)
            state = prior.proxy_state(old["proxy"]["Id"])
            assert state["Running"]
            for field in ("Id", "Image", "Memory", "MemorySwap"):
                assert state[field] == old["proxy"][field]
            assert {name: row["NetworkID"] for name, row in state["Networks"].items()} == {
                name: row["NetworkID"] for name, row in old["proxy"]["Networks"].items()
            }
            assert state["Networks"]["aeep-reviewed-model-private"]["IPAddress"] == "172.18.0.2"

        folder = RUN / entry[0]["id"]
        folder.mkdir(mode=0o700)
        task, recipe, _, _, _, pair, shared, _ = entry
        async with asyncio.timeout(review["maximum_new_reserved_seconds"]):
            refs = await prior.authenticate_pair(
                service, original, task, recipe, pair, shared, subject, folder, verify
            )
            result["tasks"].append(
                await run_pair(
                    service,
                    original,
                    entry,
                    review["task"],
                    refs,
                    subject,
                    folder,
                    verify,
                    DEADLINE,
                )
            )
        result["completed"] = True
    except BaseException as error:
        result.update(completed=False, error_type=type(error).__name__)
        raise
    finally:
        if begun:
            if owned:
                started = time.perf_counter()
                try:
                    if prior.proxy_state(old["proxy"]["Id"])["Running"]:
                        docker("stop", "--time", "5", old["proxy"]["Id"])
                    result["proxy_restored_stopped"] = (
                        prior.proxy_state(old["proxy"]["Id"]) == old["proxy"]
                    )
                    if result["proxy_restored_stopped"]:
                        repo.finish_operation(
                            operation, elapsed_seconds=startup + time.perf_counter() - started
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
