"""One-shot synthetic discovery-to-profile lifecycle check; see companion review."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import traceback
from collections import Counter
from datetime import timedelta
from pathlib import Path

from aeep.benchmarking import BenchmarkSplit
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.recipes import recipe_features, reference_csv
from aeep.capability_lifecycle import CapabilityLifecycle
from aeep.configuration_profile import capture
from aeep.discovery_service import DiscoveryConfig, DiscoveryRequest, DiscoveryService, DiscoverySourceConfig
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import NoRouteError
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import ActionRequest, ExecutorKind, Manifest, TaskScope, utc_now
from aeep.profiles import bind_service, from_scope, inspect, preflight, teardown
from aeep.router import Router


ASSESSMENT_COROUTINE_DEADLINE_SECONDS = 2700
CLEANUP_GRACE_SECONDS = 45
MAX_TEMP_BYTES = 2 * 1024**3
MAX_TEMP_ENTRIES = 20_000
MAX_ASSESSMENT_OPERATIONS = 1000
MAX_ASSESSMENT_SECONDS = 12_000
COMMAND_TIMEOUT_SECONDS = 5
BASELINE_DELAY_SECONDS = 1.0
MAX_TASK_ATTEMPTS = 4
CAPTURE_CANARY = "AEEP_XHIGH_BRIDGE_CANARY"
PINNED_LAUNCHER = Path(
    "/Users/edwintse/.codex/packages/standalone/releases/0.154.0-aarch64-apple-darwin/bin/codex"
)
PINNED_LAUNCHER_SHA256 = "4f85982624b3898c8991cb80c0981b2aa71070e3537046c9a95950318a95afcc"

CSV_PROGRAM = '''import csv,io,json,sys
try:
    value=json.load(sys.stdin)
    reader=csv.reader(io.StringIO(value["text"], newline=""), delimiter=value["delimiter"], strict=True)
    headers=next(reader)
    if not headers or len(headers) != len(set(headers)) or any(not key for key in headers):
        result={"error":"invalid_input"}
    else:
        rows=list(reader)
        result=(
            {"error":"invalid_input"}
            if any(len(row) != len(headers) for row in rows)
            else {"records":[dict(zip(headers,row,strict=True)) for row in rows]}
        )
except (csv.Error,StopIteration,ValueError,KeyError,TypeError):
    result={"error":"invalid_input"}
print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
'''


class TemporaryTreeLimitExceeded(RuntimeError):
    def __init__(self, limit_code: str, observed: int) -> None:
        super().__init__(limit_code)
        self.limit_code = limit_code
        self.observed = observed


class ProcessCleanupTimeout(RuntimeError):
    pass


def _set_stage(stage: dict[str, str], name: str) -> None:
    stage["name"] = name


def _task_profile_is_current(router: Router, profile_id: str, activation_id: str,
                             scope_digest: str) -> bool:
    state = inspect(router, profile_id, activation_id=activation_id)
    activation = state.get("activation", {})
    return bool(
        state.get("ready")
        and state.get("activated")
        and activation.get("scope_digest") == scope_digest
        and activation.get("reviewed")
        and activation.get("scope_reviewed")
        and not activation.get("scope_expired")
        and activation.get("attempts_remaining", 0) > 0
    )


def _task_invocation_counts(router: Router, scope_digest: str, executor_id: str) -> tuple[int, int]:
    with router.store._lock:
        successful_receipts = router.store._connection.execute(
            "SELECT COUNT(*) FROM receipts WHERE executor_id=? "
            "AND json_extract(payload_json,'$.metadata.task_scope_digest')=? "
            "AND json_extract(payload_json,'$.transport_success')=1",
            (executor_id, scope_digest),
        ).fetchone()[0]
        invocations = router.store._connection.execute(
            "SELECT COUNT(*) FROM execution_attempts "
            "WHERE json_extract(payload_json,'$.executor_id')=? "
            "AND json_extract(payload_json,'$.task_scope_digest')=? "
            "AND json_extract(payload_json,'$.invocation_start_digest') IS NOT NULL",
            (executor_id, scope_digest),
        ).fetchone()[0]
    return successful_receipts, invocations


def _tree_measure(root: Path) -> tuple[int, int]:
    total = entries = 0
    pending = [root]
    while pending:
        directory = pending.pop()
        try:
            children = os.scandir(directory)
        except FileNotFoundError:
            continue
        with children:
            for child in children:
                try:
                    entries += 1
                    if entries > MAX_TEMP_ENTRIES:
                        raise TemporaryTreeLimitExceeded("temporary_entries_ceiling", entries)
                    if child.is_dir(follow_symlinks=False):
                        pending.append(Path(child.path))
                    elif child.is_file(follow_symlinks=False):
                        total += child.stat(follow_symlinks=False).st_size
                        if total > MAX_TEMP_BYTES:
                            raise TemporaryTreeLimitExceeded("temporary_bytes_ceiling", total)
                except FileNotFoundError:
                    continue
    return total, entries


async def _watch_tree(root: Path, stop: asyncio.Event, meter: dict[str, int]) -> None:
    while not stop.is_set():
        try:
            current, entries = await asyncio.to_thread(_tree_measure, root)
        except TemporaryTreeLimitExceeded as exc:
            if exc.limit_code == "temporary_bytes_ceiling":
                meter["sampled_high_water_bytes"] = max(meter["sampled_high_water_bytes"], exc.observed)
            else:
                meter["sampled_high_water_entries"] = max(meter["sampled_high_water_entries"], exc.observed)
            raise
        meter["sampled_high_water_bytes"] = max(meter["sampled_high_water_bytes"], current)
        meter["sampled_high_water_entries"] = max(meter["sampled_high_water_entries"], entries)
        try:
            await asyncio.wait_for(stop.wait(), timeout=1.0)
        except TimeoutError:
            pass


def _command_spec(identity: str, program: str, boundary: NativeSandboxConfig, *, enabled: bool):
    return reference_spec("csv").model_copy(update={
        "id": identity,
        "kind": ExecutorKind.COMMAND,
        "enabled": enabled,
        "config": {
            "argv": [sys.executable, "-I", "-c", program],
            "argv_literal": True,
            "stdin_json": True,
            "output": {"type": "json"},
            "timeout_seconds": COMMAND_TIMEOUT_SECONDS,
            "max_output_bytes": 65_536,
            "native_sandbox": boundary.model_dump(mode="json"),
        },
    })


async def _exercise(root: Path, binary: Path, binary_digest: str,
                    stage: dict[str, str]) -> dict[str, object]:
    boundary = NativeSandboxConfig(
        binary=str(binary),
        binary_sha256=binary_digest,
        project_root=str(root),
        read_roots=[str(Path(sys.prefix).resolve())],
    )
    candidate_id = "fixture.native-csv-candidate"
    baseline_id = "fixture.native-csv-delayed-baseline"
    candidate = _command_spec(candidate_id, CSV_PROGRAM, boundary, enabled=False)
    baseline = _command_spec(
        baseline_id,
        f"import time\ntime.sleep({BASELINE_DELAY_SECONDS})\n" + CSV_PROGRAM,
        boundary,
        enabled=True,
    )
    manifest_path = root / "aeep.json"
    manifest_path.write_text(Manifest(
        database=str(root / ".aeep" / "state.sqlite3"), executors=[candidate, baseline],
    ).model_dump_json())
    router = Router.from_manifest(manifest_path)
    activation_id: str | None = None
    try:
        _set_stage(stage, "local_discovery")
        lifecycle = CapabilityLifecycle.from_router(router)
        assessment = lifecycle.assessment
        repository = lifecycle.repository
        selected = root / "selected-plugin.txt"
        selected.write_text("Synthetic local fixture artifact; no plugin code is executed.\n")
        fixture = root / "discovery-candidates.json"
        fixture.write_text(json.dumps({"candidates": [{
            "registry_candidate_id": "fixture.native-csv-helper",
            "name": "Synthetic native CSV helper",
            "description": "Local lifecycle fixture, not a real plugin or benefit claim.",
            "version": "fixture-only",
            "package_locator": {"kind": "local", "value": selected.name},
            "provenance": {"entry": {"type": "plugin", "license": "MIT"}},
        }]}))
        discovery = DiscoveryService.from_config(router.store, DiscoveryConfig(sources=[
            DiscoverySourceConfig(
                source_id="local-synthetic-fixture", kind="fixture",
                path=fixture.name, artifact_types=["plugin"],
            ),
        ]), base_directory=root)
        found = await discovery.search(DiscoveryRequest(
            public_query="Synthetic native CSV helper",
            source_ids=["local-synthetic-fixture"], limit=1, artifact_types=["plugin"],
        ))
        if found.candidate_ids != ["fixture.native-csv-helper"]:
            raise AssertionError("local discovery did not return the fixed synthetic candidate")

        _set_stage(stage, "operator_selected_intake")
        intake = lifecycle.inspect_candidate(found.candidate_ids[0], selected)
        repository.review(content_digest(intake))
        environment = AssessmentEnvironment(
            environment_id="synthetic-native-command-lifecycle",
            kind="codex_sandbox",
            identity={"approved_root": str(root), "purpose": "synthetic lifecycle only"},
        )
        plan = assessment.propose(
            subject_id=intake.subject_id, family="csv", candidate_id=candidate_id,
            baseline_id=baseline_id, authorization_id="synthetic-bridge-only",
            environment=environment,
        )
        if plan.subject_digest != intake.subject_digest:
            raise AssertionError("assessment subject differs from reviewed local intake")
        counts = Counter(case.split for case in plan.suite.cases)
        if counts != {
            BenchmarkSplit.QUALIFICATION: 8,
            BenchmarkSplit.TRAINING: 28,
            BenchmarkSplit.HOLDOUT: 105,
        }:
            raise AssertionError("the standard 8/28/105 campaign shape changed")
        if any(route.route_id not in {candidate_id, baseline_id} for route in plan.suite.routes):
            raise AssertionError("assessment route set differs from the two reviewed COMMAND arms")
        task_case = next(
            case for case in plan.suite.cases
            if case.split == BenchmarkSplit.TRAINING and case.variation == "plain"
        )
        recipe = RecipeDefinition.model_validate(repository.get("recipe", plan.recipe_digest))
        original_input = dict(task_case.action.input)
        original_text = original_input["text"]
        if not original_text.isascii() or original_text.count("Ada") != 1:
            raise AssertionError("selected training case lacks one ordinary ASCII cell for the canary")
        rows = list(csv.reader(
            io.StringIO(original_text, newline=""),
            delimiter=original_input["delimiter"], strict=True,
        ))
        matches = [(row_index, column_index) for row_index, row in enumerate(rows)
                   for column_index, cell in enumerate(row) if cell == "Ada"]
        if len(matches) != 1 or not CAPTURE_CANARY.isascii():
            raise AssertionError("training case cell is not uniquely replaceable by an ASCII canary")
        row_index, column_index = matches[0]
        rows[row_index][column_index] = CAPTURE_CANARY
        output_buffer = io.StringIO(newline="")
        csv.writer(output_buffer, delimiter=original_input["delimiter"]).writerows(rows)
        modified_input = {**original_input, "text": output_buffer.getvalue()}
        if modified_input["text"] != original_text.replace("Ada", CAPTURE_CANARY, 1):
            raise AssertionError("canary edit changed more than the selected ordinary ASCII cell")
        planned_features = recipe_features(recipe, original_input)
        canary_features = recipe_features(recipe, modified_input)
        if (not planned_features or canary_features != planned_features
                or planned_features not in (plan.feature_combinations or [])):
            raise AssertionError("canary request changed the training-derived joint recipe features")
        request = task_case.action.model_copy(update={"input": modified_input})
        expected_output = reference_csv(**modified_input)
        if expected_output.get("error"):
            raise AssertionError("mutated supported training request is not valid CSV")
        before = lifecycle.lookup(found.candidate_ids[0], request, intake_id=intake.intake_id)
        if before.disposition != "assess" or before.reason_codes != ["applicable_admission_missing"]:
            raise AssertionError("missing evidence did not preserve the current environment")
        _set_stage(stage, "plan_review_and_bound")
        for digest in plan.definition_digests:
            repository.review(digest)
        preview = assessment.budget_preview(plan.plan_id)["campaign_allowance"]
        upper = preview["upper_allowance"]
        if (preview["gaps"] or upper["operations"] > MAX_ASSESSMENT_OPERATIONS
                or upper["elapsed_seconds"] > MAX_ASSESSMENT_SECONDS
                or upper["model_turns"] != 0 or upper["cash_usd"] != "0"):
            raise RuntimeError("frozen campaign reservation bound exceeds the synthetic local ceiling")
        repository.grant(AssessmentAuthorization(
            authorization_id=plan.authorization_id,
            subject_digests=[plan.subject_digest],
            recipe_digests=[plan.recipe_digest],
            environment_digests=[plan.environment_digest],
            limits=AssessmentLimits(
                max_operations=MAX_ASSESSMENT_OPERATIONS,
                max_elapsed_seconds=MAX_ASSESSMENT_SECONDS,
            ),
            automatic_admission=True,
            expires_at=utc_now() + timedelta(hours=4),
        ))
        _set_stage(stage, "assessment_run")
        report = await assessment.run(assessment.enqueue(plan.plan_id))
        summary: dict[str, object] = {
            "status": "assessment_not_admitted",
            "plan_id": plan.plan_id,
            "report_id": report.report_id,
            "qualification_passed": report.qualification_passed,
            "report_outcome": report.outcome,
            "admission_created": False,
            "assessment_reservation_upper_operations": upper["operations"],
            "assessment_reservation_upper_seconds": upper["elapsed_seconds"],
        }
        if not report.qualification_passed or report.outcome != "useful_within_scope":
            return summary

        admission = assessment.admit(report.report_id)
        _set_stage(stage, "positive_admission_lookup")
        summary.update(status="lifecycle_complete", admission_id=admission.admission_id,
                       admission_created=True,
                       assessment_reservation_upper_operations=upper["operations"],
                       assessment_reservation_upper_seconds=upper["elapsed_seconds"])
        if (admission.executor_id != candidate_id
                or admission.subject_digest != intake.subject_digest
                or admission.candidate_fingerprint != plan.route_fingerprints[candidate_id]):
            raise AssertionError("admission is not bound to the discovered intake and exact command candidate")

        admitted = lifecycle.lookup(found.candidate_ids[0], request, intake_id=intake.intake_id)
        if (admitted.disposition != "admit" or admitted.executor_id != candidate_id
                or admitted.admission_id != admission.admission_id
                or admitted.evidence_cohort.get("candidate_fingerprint") != admission.candidate_fingerprint):
            raise AssertionError("positive lookup differs from the current command admission")

        scope = TaskScope(
            scope_id="synthetic-native-profile",
            project_root=str(root),
            executor_fingerprints={candidate_id: executor_fingerprint(candidate)},
            max_attempts=MAX_TASK_ATTEMPTS,
            max_attempt_seconds=COMMAND_TIMEOUT_SECONDS,
            expires_at=utc_now() + timedelta(minutes=10),
        )
        scope_digest = repository.put("task_scope", scope.scope_id, scope)
        repository.review(scope_digest)
        profile = from_scope(
            router, scope.scope_id, profile_id="synthetic-native-profile", host="task-service",
        )
        profile_digest = repository.put("capability_profile", profile.profile_id, profile)
        _set_stage(stage, "task_profile_preflight")
        if preflight(router, profile.profile_id)["ready"]:
            raise AssertionError("unreviewed task profile unexpectedly passed preflight")
        repository.review(profile_digest)
        if not preflight(router, profile.profile_id)["ready"]:
            raise AssertionError("reviewed task profile did not pass preflight")
        activation, task_service = bind_service(router, profile.profile_id)
        activation_id = activation.activation_id
        _set_stage(stage, "profile_dispatch")
        response = await task_service.call("aeep_csv", request.input)
        outcome = response.get("structuredContent", {})
        if (response.get("isError") or not outcome.get("ok")
                or outcome.get("output") != expected_output
                or outcome.get("task_scope_digest") != scope_digest):
            raise AssertionError("task-profile dispatch did not use the admitted CSV command")
        receipt_ids = [item["receipt_id"] for item in outcome["receipts"]]
        receipts = [router.store.get_receipt(identity) for identity in receipt_ids]
        if (not receipts or receipts[-1] is None
                or receipts[-1].executor_id != admitted.executor_id
                or receipts[-1].metadata.get("assessment_admission_id") != admitted.admission_id
                or receipts[-1].executor_fingerprint != "sha256:" + admission.candidate_fingerprint):
            raise AssertionError("dispatch receipt is not bound to the lookup admission")
        _set_stage(stage, "receipt_capture")
        observation = capture(router, profile.profile_id, activation.activation_id, receipt_ids)
        if (not observation.receipts or observation.receipts[-1].invocation_started is not True
                or observation.actual_host_context_tokens is not None
                or observation.actual_visible_inventory != "unavailable"):
            raise AssertionError("capture lost invocation evidence or filled unknown context")
        stored = json.dumps(
            repository.get("configuration_observation", observation.observation_id), sort_keys=True,
        )
        if modified_input["text"] in stored or json.dumps(expected_output, sort_keys=True) in stored:
            raise AssertionError("capture persisted synthetic task input/output content")

        if not _task_profile_is_current(router, profile.profile_id, activation.activation_id, scope_digest):
            raise AssertionError("reviewed task profile, scope expiry or attempt capacity is not current before revocation")
        evidence_before_revocation = _task_invocation_counts(router, scope_digest, candidate_id)
        if min(evidence_before_revocation) < 1:
            raise AssertionError("revocation counters do not observe the successful scoped invocation")
        stale = router.route(request)
        if stale.selected_executor_id != candidate_id:
            raise AssertionError("pre-revocation decision did not select the admitted command")
        _set_stage(stage, "revocation_and_rejection")
        repository.revoke_admission(candidate_id)
        revoked = lifecycle.lookup(found.candidate_ids[0], request, intake_id=intake.intake_id)
        if (revoked.disposition != "restrict" or revoked.reason_codes != ["admission_revoked"]
                or revoked.admission_id != admission.admission_id):
            raise AssertionError("lookup did not reflect admission revocation")
        try:
            await router.execute(stale)
        except NoRouteError:
            pass
        else:
            raise AssertionError("stale pre-revocation decision dispatched after admission revocation")
        if not _task_profile_is_current(router, profile.profile_id, activation.activation_id, scope_digest):
            raise AssertionError("revocation check was confounded by stale review, expired scope or exhausted attempts")
        if _task_invocation_counts(router, scope_digest, candidate_id) != evidence_before_revocation:
            raise AssertionError("stale revoked decision created a successful receipt or invocation")
        fresh_response = await task_service.call("aeep_csv", request.input)
        if (not fresh_response.get("isError")
                or fresh_response.get("structuredContent", {}).get("error_type") != "NoRouteError"):
            raise AssertionError("new task-profile dispatch survived admission revocation")
        if _task_invocation_counts(router, scope_digest, candidate_id) != evidence_before_revocation:
            raise AssertionError("fresh revoked task request created a successful receipt or invocation")
        summary.update(
            lookup_executor_id=admitted.executor_id,
            receipt_id=receipts[-1].receipt_id,
            captured_observation_id=observation.observation_id,
            stale_decision_id=stale.decision_id,
            revoked_lookup_reason=revoked.reason_codes[0],
        )
        return summary
    finally:
        if sys.exc_info()[0] is None:
            _set_stage(stage, "teardown")
        try:
            if activation_id is not None:
                removed = teardown(router, activation_id)
                if removed.get("overlay") != "absent":
                    raise AssertionError("task activation teardown left an overlay")
        finally:
            await router.close()


async def _supervised(root: Path, binary: Path, binary_digest: str, meter: dict[str, int],
                      stage: dict[str, str]) -> dict[str, object]:
    stop = asyncio.Event()
    run_task = asyncio.create_task(_exercise(root, binary, binary_digest, stage))
    monitor_task = asyncio.create_task(_watch_tree(root, stop, meter))
    try:
        async with asyncio.timeout(ASSESSMENT_COROUTINE_DEADLINE_SECONDS):
            done, _ = await asyncio.wait(
                {run_task, monitor_task}, return_when=asyncio.FIRST_COMPLETED,
            )
            if monitor_task in done:
                await monitor_task
            result = await run_task
            return result
    except BaseException:
        stop.set()
        if not run_task.done():
            run_task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(run_task), timeout=CLEANUP_GRACE_SECONDS)
            except asyncio.CancelledError:
                pass
            except TimeoutError as exc:
                raise ProcessCleanupTimeout("assessment cancellation cleanup wait expired") from exc
        raise
    finally:
        stop.set()
        if not monitor_task.done():
            monitor_task.cancel()
        await asyncio.gather(monitor_task, return_exceptions=True)


def main() -> int:
    launcher = os.environ.get("AEEP_NATIVE_CODEX")
    if not launcher:
        raise SystemExit("set AEEP_NATIVE_CODEX to the separately reviewed pinned native launcher")
    binary = Path(launcher).expanduser().resolve(strict=True)
    if binary != PINNED_LAUNCHER:
        raise SystemExit("AEEP_NATIVE_CODEX does not resolve to the reviewed pinned launcher")
    with binary.open("rb") as stream:
        binary_digest = "sha256:" + hashlib.file_digest(stream, "sha256").hexdigest()
    if binary_digest != "sha256:" + PINNED_LAUNCHER_SHA256:
        raise SystemExit("the reviewed native launcher SHA-256 changed; prepare a fresh definition")
    root = Path(tempfile.mkdtemp(prefix="aeep-discovery-profile-bridge-")).resolve(strict=True)
    started = time.monotonic()
    meter = {"sampled_high_water_bytes": 0, "sampled_high_water_entries": 0}
    stage = {"name": "runner_setup"}
    print(json.dumps({
        "status": "started",
        "temporary_directory": str(root),
        "launcher": str(binary),
        "launcher_sha256": binary_digest,
        "evidence_label": "synthetic lifecycle only; not live benefit or backend-transfer evidence",
    }, sort_keys=True), flush=True)
    try:
        result = asyncio.run(_supervised(root, binary, binary_digest, meter, stage))
    except Exception as exc:
        failure_code = (
            exc.limit_code if isinstance(exc, TemporaryTreeLimitExceeded)
            else "wall_timeout" if isinstance(exc, TimeoutError)
            else "cooperative_cleanup_wait_expired"
            if isinstance(exc, ProcessCleanupTimeout)
            else "assessment_integration_failure"
        )
        source_frame = next((frame for frame in reversed(traceback.extract_tb(exc.__traceback__))
                             if Path(frame.filename).resolve() == Path(__file__).resolve()), None)
        print(json.dumps({
            "status": "failed",
            "failure_code": failure_code,
            "stage": stage["name"],
            "error_type": type(exc).__name__,
            "source_location": None if source_frame is None else {
                "file": Path(source_frame.filename).name,
                "line": source_frame.lineno,
                "function": source_frame.name,
            },
            "launcher": str(binary),
            "launcher_sha256": binary_digest,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "temporary_directory": str(root),
            "temporary_bytes_sampled_high_water": meter["sampled_high_water_bytes"],
            "temporary_entries_sampled_high_water": meter["sampled_high_water_entries"],
            "temporary_retained_for_review": True,
        }, sort_keys=True))
        return 2
    print(json.dumps({
        **result,
        "launcher": str(binary),
        "launcher_sha256": binary_digest,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "temporary_directory": str(root),
        "temporary_bytes_sampled_high_water": meter["sampled_high_water_bytes"],
        "temporary_bytes_final": _tree_measure(root)[0],
        "temporary_entries_sampled_high_water": meter["sampled_high_water_entries"],
        "temporary_retained_for_review": True,
        "evidence_label": "synthetic lifecycle only; not live benefit or backend-transfer evidence",
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
