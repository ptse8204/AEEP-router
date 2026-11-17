"""Exercise selection, execution and protected grading in a local first-party fixture."""

import argparse
import asyncio
import json
import socket
import time
from contextlib import closing
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bind_selection_trial as link
import capture_selection_route as capture

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCase, BenchmarkRoute, BenchmarkRunner, BenchmarkSuite
from aeep.errors import ConfigurationError
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    CashEstimate,
    ExecutionReceipt,
    ExecutorSpec,
    Manifest,
    MeasurementEvidence,
    ResourceVector,
    RouteEstimate,
    StrictModel,
    ValidationResult,
    ValidationSpec,
    utc_now,
)
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep.validators import ValidationContext
from aeep_toolkit.install_runtime import file_digest
from aeep_toolkit.selection import SelectionCase
from aeep_toolkit.workflow_evidence import _settled


class FixtureStudy(StrictModel):
    fixture: str


def reject(text, fn, *args):
    try:
        fn(*args)
    except ConfigurationError as exc:
        assert text in str(exc), (text, str(exc))
    else:
        raise AssertionError("fixture accepted altered selection evidence")


async def fixture(root, selected, *, corrupted=False):
    root.mkdir()
    attempt_root = root / "attempts"
    attempt_root.mkdir()
    database = root / "campaign.sqlite3"
    text = "first-party private fixture"
    capability = "text.stats@1"
    action = ActionRequest(
        capability=capability, input={"text": text},
        constraints=ActionConstraints(
            allowed_executor_ids=["baseline", "candidate"],
            max_latency_ms=5 if selected == "baseline" else 100,
        ),
    )
    case = SelectionCase(
        case_id="demo", family="text", task_sha256=content_digest(action.input),
        eligible=["extra-tool"], demonstrated_useful=[], value_known=False, eligibility_ref="0" * 64,
    )
    def callable_for(name):
        return "invalid_stats" if corrupted and name == selected else "text_stats"

    specs = [
        ExecutorSpec(
            id=name, capability=capability, kind="python",
            config={"callable": f"aeep.examples.tools:{callable_for(name)}", "isolation": "in_process"},
            description="Local first-party fixture",
            estimate=RouteEstimate(
                resources=ResourceVector(latency_ms=delay),
                cash=CashEstimate(upper_bound_usd=0, evidence=MeasurementEvidence(
                    status="complete", source="confirmed_no_incremental_charge", trust="verified",
                    source_reference="First-party in-process text statistics with network denied.",
                )),
            ),
        )
        for name, delay in (("baseline", 2 if selected == "baseline" else 50), ("candidate", 10))
    ]
    manifest = Manifest(database=str(root / "selection.sqlite3"), executors=specs)
    router = Router(manifest)
    repo = AssessmentRepository(router.store)
    study = FixtureStudy(fixture="no-model-selection-fixture")
    study_ref = repo.put("selection_fixture_study", "fixture", study)
    scope = capture.SelectionRouteScope(
        study_ref=study_ref, request_id="fixture-scope", policy="aeep", case_id=case.case_id,
        action_sha256=content_digest(action), task_sha256=case.task_sha256,
        source_sha256=capture.implementation_source(), driver_sha256=file_digest(Path(capture.__file__)),
        manifest_sha256=content_digest(router.manifest), baseline_executor_id="baseline",
        candidates_by_executor={"candidate": "extra-tool"}, reserved_seconds=5,
    )
    scope_ref = repo.put(capture.SCOPE, content_digest(scope), scope)
    grade_spec = ValidationSpec(kind="callback", config={"name": "count-words"})
    benchmark_case = BenchmarkCase(case_id=case.case_id, split="qualification", action=action, validators=[grade_spec])
    suite = BenchmarkSuite(
        suite_id="selection-fixture", routes=[BenchmarkRoute(route_id=scope.policy, executor_id=selected)],
        cases=[benchmark_case], repetitions=1, conditions=["process-cold"], max_total_cash_usd=0,
    )
    approval = link.ApprovedTrial(
        scope_ref=scope_ref, case_ref=content_digest(benchmark_case), condition=suite.conditions[0], database=str(database),
    )
    approval_ref = repo.put(link.APPROVAL, content_digest(approval), approval)
    grant = AssessmentAuthorization(
        authorization_id="fixture", subject_digests=[scope_ref], recipe_digests=[scope_ref],
        environment_digests=[scope_ref], allowed_destinations=["local"],
        expires_at=utc_now() + timedelta(minutes=2),
        limits=AssessmentLimits(max_operations=3, max_elapsed_seconds=15),
    )
    request = RecipeMaterializationRequest(
        plan_id=scope.request_id, authorization_id=grant.authorization_id,
        subject_digest=scope_ref, recipe_digest=scope_ref, mapping_digest=scope_ref,
        environment_digest=scope_ref, definition_digests=[scope_ref, study_ref, approval_ref], seed=0,
    )
    repo.put("recipe_materialization_request", request.plan_id, request)
    repo.approve_bundle(grant, {
        scope_ref: scope.model_dump(mode="json"), study_ref: study.model_dump(mode="json"),
        approval_ref: approval.model_dump(mode="json"),
    })
    runner = None
    observed = {}
    fixture_rejections = 0
    try:
        reject("unknown assessment", link.bind_before_dispatch, router, scope_ref, case, suite, database, approval_ref)
        fixture_rejections += 1
        choice = capture.capture_route(router, scope_ref, action)
        assert choice.selected_executor_id == selected
        wrong = suite.model_copy(update={
            "routes": [BenchmarkRoute(route_id="aeep", executor_id="baseline" if selected == "candidate" else "candidate")],
        })
        reject("differs from the selection", link.bind_before_dispatch, router, scope_ref, case, wrong, database, approval_ref)
        fixture_rejections += 1
        wrong_grader = benchmark_case.model_copy(update={"validators": [
            grade_spec.model_copy(update={"config": {"name": "different"}})
        ]})
        changed_scope = suite.model_copy(update={"cases": [wrong_grader]})
        reject("differs from the reviewed", link.bind_before_dispatch, router, scope_ref, case, changed_scope, database, approval_ref)
        fixture_rejections += 1
        binding, binding_ref = link.bind_before_dispatch(router, scope_ref, case, suite, database, approval_ref)

        async def before_trial(trial_router, route, trial):
            nonlocal fixture_rejections
            inactive = trial_router.registry.get("baseline" if selected == "candidate" else "candidate")
            trial_router.registry.replace(inactive.model_copy(update={"description": "unreviewed inventory"}))
            reject("runner slot or execution environment", link.authorize_trial, repo, scope_ref, case, suite, trial_router, route, trial)
            fixture_rejections += 1
            trial_router.registry.replace(inactive)
            assert link.authorize_trial(repo, scope_ref, case, suite, trial_router, route, trial) == request
            observed["trial"] = trial.trial_id
            observed["start"] = time.perf_counter()
            repo.reserve(request, trial.trial_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=5), stage="trial")

        def grade(context: ValidationContext):
            start = time.perf_counter()
            assert content_digest(context.input) == case.task_sha256
            rows = runner.connection.execute(
                "SELECT payload_json FROM trial_receipts WHERE trial_id=?", (observed["trial"],)
            ).fetchall()
            assert len(rows) == 1
            receipt = ExecutionReceipt.model_validate_json(rows[0][0])
            operation = binding.grade_operation()
            repo.reserve(
                request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=5), stage=link.GRADE_STAGE,
            )
            valid = context.output.get("words") == len(text.split())
            result = ValidationResult(kind="callback", trust="verified", valid=valid, quality_score=int(valid))
            observed["grader"] = time.perf_counter() - start
            repo.finish_operation(operation, elapsed_seconds=observed["grader"])
            repo.put(link.GRADE, operation, link.ProtectedGrade(
                binding_ref=binding_ref, trial_id=observed["trial"], receipt_ref=content_digest(receipt),
                grader_definition_ref=content_digest(grade_spec),
                measurement_ref=content_digest(_settled(repo, operation)), result=result,
            ))
            return result

        def finish(trial):
            repo.finish_operation(trial.trial_id, elapsed_seconds=max(0, time.perf_counter() - observed["start"] - observed.get("grader", 0)))

        count = 0

        def router_factory():
            nonlocal count
            count += 1
            path = attempt_root / f"{count}.sqlite3"
            return Router(manifest, store=ReceiptStore(path), validator_callbacks={"count-words": grade})

        runner = BenchmarkRunner(
            router_factory, database, before_trial=before_trial, after_trial=finish, separate_grading=True,
        )
        reject("benchmark was already opened", link.bind_before_dispatch, router, scope_ref, case, suite, database, approval_ref)
        fixture_rejections += 1
        run = await runner.run(suite)
        trial = run.trials[0]
        assert len(run.trials) == 1 and trial.valid is (not corrupted), trial
        with closing(link.open_store(router.store.path)) as reader:
            read_repo = AssessmentRepository(reader)
            resolved, proof = link.resolve_outcome(read_repo, scope_ref, case, suite)
            assert resolved.task_verified == trial.valid and proof["quality_score"] == int(trial.valid)
            assert resolved.selected == ("extra-tool" if selected == "candidate" else None)
            bad_task = case.model_copy(update={"task_sha256": "c" * 64})
            reject("another frozen", link.resolve_outcome, read_repo, scope_ref, bad_task, suite)
            fixture_rejections += 1
            grader_changed = suite.model_copy(update={"cases": [
                benchmark_case.model_copy(update={"validators": [
                    grade_spec.model_copy(update={"config": {"name": "different"}})
                ]})
            ]})
            reject("benchmark binding differs", link.resolve_outcome, read_repo, scope_ref, case, grader_changed)
            fixture_rejections += 1
            pinned_environment = runner.connection.execute("SELECT content_sha256 FROM environments").fetchone()[0]
            runner.connection.execute("UPDATE environments SET content_sha256=?", ("c" * 64,))
            runner.connection.commit()
            reject("inventory, policies or suite changed", link.resolve_outcome, read_repo, scope_ref, case, suite)
            fixture_rejections += 1
            runner.connection.execute("UPDATE environments SET content_sha256=?", (pinned_environment,))
            runner.connection.commit()
            with router.store._immediate_transaction() as db:
                db.execute("UPDATE assessment_operations SET state='reserved' WHERE id=?", (binding.grade_operation(),))
            reject("accounting is incomplete", link.resolve_outcome, read_repo, scope_ref, case, suite)
            fixture_rejections += 1
            with router.store._immediate_transaction() as db:
                db.execute("UPDATE assessment_operations SET state='complete' WHERE id=?", (binding.grade_operation(),))
            assert link.resolve_outcome(read_repo, scope_ref, case, suite)[1] == proof
        assert text not in repo.store.get_decision(choice.decision_id).model_dump_json()
        assert len(repo.operation_ledger(request.plan_id).operations) == 3
        return {
            "choice": resolved.selected, "grade": proof["quality_score"], "task_verified": resolved.task_verified,
            "settled_operations": 3, "refusal_checks": fixture_rejections,
        }
    finally:
        if runner is not None:
            runner.connection.close()
        await router.close()


async def check(root):
    with patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")):
        return {
            "schema_version": "aeep.c13.selected-trial-fixture.v1",
            "source": capture.implementation_source(),
            "capture_driver_sha256": file_digest(Path(capture.__file__)),
            "link_driver_sha256": file_digest(Path(link.__file__)),
            "fixture_sha256": file_digest(Path(__file__)),
            "candidate": await fixture(root / "candidate", "candidate"),
            "baseline": await fixture(root / "baseline", "baseline"),
            "wrong_output": await fixture(root / "wrong-output", "candidate", corrupted=True),
            "evidence_scope": "First-party deterministic fixture with real Router, runner, and grader. No candidate usefulness evidence.",
            "model_turns": 0,
        }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with TemporaryDirectory(prefix="aeep-c13-selection-trial.") as directory:
        report = asyncio.run(check(Path(directory).resolve()))
    with args.output.open("x") as stream:
        stream.write(json.dumps(report, indent=2, sort_keys=True) + "\n")
