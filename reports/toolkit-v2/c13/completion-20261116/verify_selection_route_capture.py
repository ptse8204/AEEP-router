"""First-party checks of the local Router, using synthetic tasks and private ledgers."""

import asyncio
import hashlib
import json
import socket
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import capture_selection_route as capture

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutionReceipt,
    ExecutorSpec,
    Manifest,
    ResourceVector,
    RouteEstimate,
    StrictModel,
    utc_now,
)
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.selection import SelectionCase


def denied(rejection, function, *args, **kwargs):
    try:
        function(*args, **kwargs)
    except ConfigurationError as error:
        assert rejection in str(error), (rejection, str(error))
    else:
        raise AssertionError(f"expected selection refusal: {rejection}")


def fixture(root, mode):
    case = SelectionCase(
        case_id="demo-case",
        task_sha256=content_digest({"text": "private-fixture-body"}),
        family="synthetic",
        eligible=["candidate-tool"],
        demonstrated_useful=[],
        eligibility_ref="0" * 64,
        value_known=False,
    )
    capabilities = "text.stats"
    action = ActionRequest(
        capability=capabilities,
        input={"text": "private-fixture-body"},
        constraints=ActionConstraints(
            allowed_executor_ids=["baseline", "candidate"],
            max_latency_ms=1 if mode == "blocked" else 5 if mode == "baseline" else 10_000,
        ),
    )
    executors = [
        ExecutorSpec(
            id=name,
            capability=capabilities,
            kind="python",
            config={"callable": "aeep.examples.tools:text_stats"},
            description="Routing fixture",
            input_schema=(
                {"type": "object", "properties": {"text": {"type": "integer"}}}
                if mode == "bad_schema"
                else {"type": "object"}
            ),
            estimate=RouteEstimate(resources=ResourceVector(latency_ms=delay)),
        )
        for name, delay in (("baseline", 50 if mode != "baseline" else 2), ("candidate", 10))
    ]
    path = root / f"{mode}.sqlite3"
    router = Router(Manifest(database=str(path), executors=executors))
    repo = AssessmentRepository(router.store)
    study = {"kind": "fixture", "policies": ["aeep", "discovery", "fixed"]}
    model = Study.model_validate(study)
    study_ref = repo.put("selection_fixture_study", "fixture", model)
    scope = capture.SelectionRouteScope(
        study_ref=study_ref,
        request_id=f"selection-{mode}",
        policy="aeep",
        case_id=case.case_id,
        action_sha256=content_digest(action),
        task_sha256=case.task_sha256,
        source_sha256="a" * 64 if mode == "drift" else capture.implementation_source(),
        driver_sha256=hashlib.sha256(Path(capture.__file__).read_bytes()).hexdigest(),
        manifest_sha256=content_digest(router.manifest),
        baseline_executor_id="baseline",
        candidates_by_executor={"candidate": "candidate-tool"},
        reserved_seconds=5,
    )
    scope_ref = repo.put(capture.SCOPE, content_digest(scope), scope)
    request = RecipeMaterializationRequest(
        plan_id=scope.request_id,
        authorization_id=mode,
        subject_digest=scope_ref,
        recipe_digest=scope_ref,
        mapping_digest=scope_ref,
        environment_digest=scope_ref,
        definition_digests=[scope_ref, study_ref],
        seed=0,
    )
    repo.put("recipe_materialization_request", request.plan_id, request)
    if mode != "unapproved":
        grant = AssessmentAuthorization(
            authorization_id=mode,
            subject_digests=[scope_ref],
            recipe_digests=[scope_ref],
            environment_digests=[scope_ref],
            allowed_destinations=["local"],
            expires_at=utc_now() + timedelta(minutes=2),
            remote_disclosure=False,
            limits=AssessmentLimits(max_operations=5, max_elapsed_seconds=30),
        )
        repo.approve_bundle(grant, {scope_ref: scope.model_dump(mode="json"), study_ref: study})
    return router, repo, scope, scope_ref, action, case


class Study(StrictModel):
    kind: str
    policies: list[str]


results = {}
with (
    TemporaryDirectory(prefix="aeep-selection-capture-fixture-") as directory,
    patch.object(socket.socket, "connect", side_effect=AssertionError("network calls forbidden")),
):
    for mode in (
        "candidate",
        "baseline",
        "blocked",
        "bad_schema",
        "drift",
        "unapproved",
        "interrupted",
    ):
        router, repo, scope, scope_ref, action, case = fixture(Path(directory), mode)
        kwargs = {"study_ref": scope.study_ref, "case": case}
        try:
            if mode == "blocked":
                denied("blocked", capture.capture_route, router, scope_ref, action)
                denied("blocked", capture.resolve_route, repo, scope_ref, **kwargs)
            elif mode == "bad_schema":
                denied("inventory", capture.capture_route, router, scope_ref, action)
            elif mode == "drift":
                denied("scope changed", capture.capture_route, router, scope_ref, action)
            elif mode == "unapproved":
                denied(
                    "unknown assessment authorization",
                    capture.capture_route,
                    router,
                    scope_ref,
                    action,
                )
            elif mode == "interrupted":
                with patch.object(router, "route", side_effect=KeyboardInterrupt):
                    try:
                        capture.capture_route(router, scope_ref, action)
                    except KeyboardInterrupt:
                        pass
                    else:
                        raise AssertionError("interruption did not propagate")
                denied("unknown assessment", capture.resolve_route, repo, scope_ref, **kwargs)
                denied("unresolved accounting", capture.capture_route, router, scope_ref, action)
            else:
                decision = capture.capture_route(router, scope_ref, action)
                assert decision.selected_executor_id == mode
                stored = router.store.get_decision(decision.decision_id)
                assert stored is not None and stored.action.input == {"__aeep_redacted__": True}
                assert "private-fixture-body" not in stored.model_dump_json()
                assert not router.store.list_receipts(decision_id=decision.decision_id)
                chosen, linked = capture.resolve_route(repo, scope_ref, **kwargs)
                assert chosen.decision_ref == content_digest(decision) and linked is None
                assert chosen.selected == ("candidate-tool" if mode == "candidate" else None)
                denied("already reserved", capture.capture_route, router, scope_ref, action)
                changed_action = action.model_copy(update={"input": {"text": "other-task"}})
                denied("scope changed", capture.capture_route, router, scope_ref, changed_action)
                changed = {**kwargs, "study_ref": "d" * 64}
                denied("another frozen", capture.resolve_route, repo, scope_ref, **changed)
                changed = {**kwargs, "case": case.model_copy(update={"task_sha256": "d" * 64})}
                denied("another frozen", capture.resolve_route, repo, scope_ref, **changed)
                good = ExecutionReceipt(
                    decision_id=decision.decision_id,
                    action_id=action.action_id,
                    capability=action.capability,
                    executor_id=mode,
                    executor_kind="python",
                    status="success",
                    execution_success=True,
                    estimated=RouteEstimate(),
                )
                repo.store.save_receipt(good)
                with ReceiptStore(router.store.path, read_only=True) as reader:
                    proof, digest = capture.resolve_route(
                        AssessmentRepository(reader),
                        scope_ref,
                        receipt_id=good.receipt_id,
                        **kwargs,
                    )
                assert digest == content_digest(good)
                assert proof.task_verified is None and proof.verification_ref is None
                for change in (
                    {"executor_id": "other"},
                    {"action_id": "act_other"},
                    {"started_at": decision.created_at},
                    {"decision_id": "dec_other"},
                ):
                    wrong = good.model_copy(
                        update={"receipt_id": f"rcpt_drift_{next(iter(change))}", **change}
                    )
                    repo.store.save_receipt(wrong)
                    denied(
                        "outside",
                        capture.resolve_route,
                        repo,
                        scope_ref,
                        receipt_id=wrong.receipt_id,
                        **kwargs,
                    )
                repo.store.save_decision(stored.model_copy(update={"explanation": "later edit"}))
                denied("missing or changed", capture.resolve_route, repo, scope_ref, **kwargs)
            ledger = repo.operation_ledger(scope.request_id)
            measured = sum(row.elapsed_seconds is not None for row in ledger.operations)
            assert len(ledger.operations) == int(
                mode in {"candidate", "baseline", "blocked", "interrupted"}
            )
            assert measured == int(mode in {"candidate", "baseline", "blocked"})
            results[mode] = {"operations": len(ledger.operations), "settled": measured}
        finally:
            asyncio.run(router.close())

record = {
    "schema_version": "aeep.c13.selection-route-capture-preflight.v1",
    "source": capture.implementation_source(),
    "driver_sha256": hashlib.sha256(Path(capture.__file__).read_bytes()).hexdigest(),
    "check_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    "controls": results,
    "synthetic_receipt_link_controls": 10,
    "recorded_verifier_grades": 0,
    "task_executions": 0,
    "model_calls": 0,
    "authority_changes_to_existing_grants": 0,
}
print(json.dumps(record, indent=2, sort_keys=True))
