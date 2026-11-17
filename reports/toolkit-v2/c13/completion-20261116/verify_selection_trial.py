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
import selection_controls as controls

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.benchmarking import BenchmarkCase, BenchmarkRoute, BenchmarkRunner, BenchmarkSuite
from aeep.discovery import DiscoveryRequest, DiscoveryResult, _metadata_digest
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
from aeep_toolkit.selection import SelectionCase, SelectionEvaluation, summarize_selection
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


def bind_policy(repo, root, policy, study_ref):
    if policy == "aeep":
        return {}, None
    common = {"study_ref": study_ref, "driver_ref": file_digest(Path(controls.__file__))}
    records = {}
    if policy == "fixed":
        inputs = (content_digest({"text": "independent development example"}),)
        source = controls.FixturePrior(study_ref=study_ref, prior_input_refs=inputs)
        source_ref = repo.put("selection_fixture_prior", content_digest(source), source)
        prior = controls.FixedPrior(
            source_kind="engineering_fixture", source_report_ref=source_ref, development_task_refs=inputs,
            preferred_executor="baseline", observed_at=utc_now(),
        )
        prior_ref = repo.put(controls.PRIOR, content_digest(prior), prior)
        definition = controls.FixedDefinition(**common, prior_ref=prior_ref, frozen_at=utc_now())
        records[prior_ref] = prior.model_dump(mode="json")
    else:
        snapshot = root / "public-catalog.json"
        entries = [
            {"registry_candidate_id": "fixture:alternate", "name": "Word Alternate", "description": "Count words locally."},
            {"registry_candidate_id": "fixture:words", "name": "Word Counter", "description": "Count words locally."},
        ]
        snapshot.write_text(json.dumps({"candidates": entries}))
        definition = controls.DiscoveryDefinition(
            **common, snapshot_path=str(snapshot), snapshot_sha256=file_digest(snapshot),
            query=DiscoveryRequest(public_query="word", source_ids=["retained-catalog"]),
            candidates={
                entry["registry_candidate_id"]: controls.CatalogCandidate(executor_id=executor, raw_metadata_digest=_metadata_digest(entry))
                for entry, executor in zip(entries, ("alternate", "candidate"), strict=True)
            },
        )
    ref = repo.put(controls.DEFINITION, content_digest(definition), definition)
    records[ref] = definition.model_dump(mode="json")
    return records, ref


async def fixture(root, selected, *, corrupted=False, policy="aeep"):
    root.mkdir()
    attempt_root = root / "attempts"
    attempt_root.mkdir()
    database = root / "campaign.sqlite3"
    text = "first-party private fixture"
    capability = "text.stats@1"
    force_baseline = policy == "aeep" and selected == "baseline"
    action = ActionRequest(
        action_id="act_selection_fixture", capability=capability, input={"text": text},
        constraints=ActionConstraints(
            allowed_executor_ids=["baseline", "candidate", "alternate"],
            max_latency_ms=5 if force_baseline else 100,
        ),
    )
    case = SelectionCase(
        case_id="demo", family="text", task_sha256=content_digest(action.input),
        eligible=["extra-tool", "alternate-tool"], demonstrated_useful=[], value_known=False, eligibility_ref="0" * 64,
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
        for name, delay in (("baseline", 2 if force_baseline else 50), ("candidate", 10), ("alternate", 35))
    ]
    manifest = Manifest(database=str(root / "selection.sqlite3"), executors=specs)
    router = Router(manifest)
    repo = AssessmentRepository(router.store)
    study = FixtureStudy(fixture="no-model-selection-fixture")
    study_ref = repo.put("selection_fixture_study", "fixture", study)
    scope = capture.SelectionRouteScope(
        study_ref=study_ref, request_id="fixture-scope", policy=policy, case_id=case.case_id,
        action_sha256=content_digest(action), task_sha256=case.task_sha256,
        source_sha256=capture.implementation_source(), driver_sha256=file_digest(Path(capture.__file__)),
        manifest_sha256=content_digest(router.manifest), baseline_executor_id="baseline",
        candidates_by_executor={"candidate": "extra-tool", "alternate": "alternate-tool"}, reserved_seconds=5,
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
    policy_documents, policy_ref = bind_policy(repo, root, policy, study_ref)
    grant = AssessmentAuthorization(
        authorization_id="fixture", subject_digests=[scope_ref], recipe_digests=[scope_ref],
        environment_digests=[scope_ref], allowed_destinations=["local"],
        expires_at=utc_now() + timedelta(minutes=2),
        limits=AssessmentLimits(max_operations=3, max_elapsed_seconds=15),
    )
    request = RecipeMaterializationRequest(
        plan_id=scope.request_id, authorization_id=grant.authorization_id,
        subject_digest=scope_ref, recipe_digest=scope_ref, mapping_digest=scope_ref,
        environment_digest=scope_ref, definition_digests=[scope_ref, study_ref, approval_ref, *policy_documents], seed=0,
    )
    repo.put("recipe_materialization_request", request.plan_id, request)
    repo.approve_bundle(grant, {
        scope_ref: scope.model_dump(mode="json"), study_ref: study.model_dump(mode="json"),
        approval_ref: approval.model_dump(mode="json"), **policy_documents,
    })
    runner = None
    observed = {}
    fixture_rejections = 0
    try:
        reject("unknown assessment", link.bind_before_dispatch, router, scope_ref, case, suite, database, approval_ref)
        fixture_rejections += 1
        if policy_ref is None:
            choice = capture.capture_route(router, scope_ref, action)
        else:
            reject("requires its own reviewed selector", capture.capture_route, router, scope_ref, action)
            fixture_rejections += 1
            choice = await controls.capture_control(router, scope_ref, action, policy_ref)
            origin = capture.SelectionRouteCapture.model_validate(repo.get(capture.CAPTURE, scope.operation_id()))
            evidence = controls.ControlObservation.model_validate(repo.get(controls.OBSERVATION, origin.control_ref))
            assert evidence.shared_router_seconds + evidence.preference_seconds <= origin.router_seconds
            checked = controls.load_definition(repo, request, scope, policy_ref)
            guard = repo.store.get_decision(evidence.guard_id)
            assert guard.selected_executor_id == "candidate" and selected != guard.selected_executor_id
            assert controls.ranked_choice(scope, guard, ()) == "baseline"
            denied = guard.model_copy(update={
                "candidates": [row.model_copy(update={"feasible": False}) for row in guard.candidates],
            })
            assert controls.ranked_choice(scope, denied, evidence.ordered_executors) is None
            fixture_rejections += 1
            if policy == "fixed":
                prior = controls.FixedPrior.model_validate(repo.get(controls.PRIOR, checked.prior_ref))
                exposed = scope.model_copy(update={"task_sha256": prior.development_task_refs[0]})
                reject("outside approved prior", controls.prior_preference, repo, request, exposed, checked, utc_now())
                fixture_rejections += 1
            else:
                result = DiscoveryResult.model_validate(repo.get("discovery_result", evidence.source_id))
                changed = result.model_copy(update={
                    "candidates": [result.candidates[0].model_copy(update={"raw_metadata_digest": "sha256:" + "0" * 64}),
                                   *result.candidates[1:]],
                })
                reject("reviewed catalog identity changed", controls.discovery_order, checked, scope, changed)
                fixture_rejections += 1

        assert choice.selected_executor_id == selected
        wrong = suite.model_copy(update={
            "routes": [BenchmarkRoute(route_id=policy, executor_id="baseline" if selected == "candidate" else "candidate")],
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
            assert resolved.selected == scope.candidates_by_executor.get(selected)
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
            "study_ref": study_ref, "action_ref": content_digest(action),
            "shared_environment_ref": binding.execution_environment_ref,
            "grant_limits": grant.limits.model_dump(mode="json"),
            "authority_ref": content_digest(grant.model_dump(
                mode="json", include={"limits", "allowed_destinations", "remote_disclosure", "automatic_admission"},
            )),
        }, resolved, case, {scope.candidates_by_executor[spec.id]: content_digest(spec) for spec in specs if spec.id != "baseline"}, policy_ref or scope_ref
    finally:
        if runner is not None:
            runner.connection.close()
        await router.close()


async def check(root):
    with patch.object(socket.socket, "connect", side_effect=AssertionError("network denied")):
        linked = {
            "aeep": await fixture(root / "aeep", "candidate"),
            "discovery-only": await fixture(root / "discovery", "alternate", policy="discovery-only"),
            "fixed": await fixture(root / "fixed", "baseline", policy="fixed"),
        }
        arms = {policy: value[0] for policy, value in linked.items()}
        _, _, frozen_case, inventory, _ = linked["aeep"]
        assert all(value[2:4] == (frozen_case, inventory) for value in linked.values())
        for key in ("study_ref", "action_ref", "shared_environment_ref", "authority_ref"):
            assert all(arm[key] == arms["aeep"][key] for arm in arms.values())
        common = {
            "inventory_sha256": content_digest(inventory),
            "shared_environment_sha256": arms["aeep"]["shared_environment_ref"],
            "authority_sha256": arms["aeep"]["authority_ref"],
            "model_settings_sha256": content_digest({"external_model": False}),
        }
        evaluation = SelectionEvaluation(
            evidence_kind="synthetic", plan_ref=arms["aeep"]["study_ref"], inventory=inventory,
            shared_environment_sha256=common["shared_environment_sha256"], authority_sha256=common["authority_sha256"],
            model_settings_sha256=common["model_settings_sha256"], cases=(frozen_case,),
            policies={name: {**common, "definition_ref": value[4]} for name, value in linked.items()},
            decisions=tuple(value[1] for value in linked.values()),
        )
        scoring = summarize_selection(evaluation)
        assert scoring["outcome"] == "NOT_ASSESSED" and not scoring["admission_changed"]
        assert all(pair["graded_pairs"] == pair["decision_time_pairs"] == 1 for pair in scoring["comparisons"])
        return {
            "schema_version": "aeep.c13.selection-controls-preflight.v1",
            "source": capture.implementation_source(),
            "capture_driver_sha256": file_digest(Path(capture.__file__)),
            "link_driver_sha256": file_digest(Path(link.__file__)),
            "fixture_sha256": file_digest(Path(__file__)),
            "arms": arms,
            "control_driver_sha256": file_digest(Path(controls.__file__)),
            "baseline": (await fixture(root / "baseline", "baseline"))[0],
            "wrong_output": (await fixture(root / "wrong-output", "candidate", corrupted=True))[0],
            "selection_report": {
                "outcome": scoring["outcome"], "admission_changed": scoring["admission_changed"],
                "pairs_with_verified_grades_and_decision_times": len(scoring["comparisons"]),
            },
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
