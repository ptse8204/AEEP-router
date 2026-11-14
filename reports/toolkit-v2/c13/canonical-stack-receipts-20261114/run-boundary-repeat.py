"""Run approved, bounded Cisco and agent-skill-eval compatibility checks once."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import importlib.util
import io
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import (
    AssessmentBudgetAmendment,
    AssessmentLimits,
    ConformanceProbeRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import SchedulerDefinition
from aeep.assessment.verification import verification_source_digest
from aeep.execution import persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.cli import main as toolkit_cli
from aeep_toolkit.install_runtime import snapshot
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_security import ScannerRuntimeDefinition, require_scan, scan_preview

specification = importlib.util.spec_from_file_location(
    "prepare_boundary_repeat", Path(__file__).with_name("prepare-boundary-repeat.py")
)
assert specification and specification.loader
helpers = importlib.util.module_from_spec(specification)
specification.loader.exec_module(helpers)
ROOT = helpers.ROOT


def checked_file(binding):
    path = Path(binding["path"])
    if file_digest(path) != binding["sha256"]:
        raise RuntimeError(f"bound input changed: {path.name}")
    return path


def check_conditions(review):
    if (
        not datetime.now(UTC) < datetime.fromisoformat(review["expires_at"])
        or verification_source_digest(ROOT) != review["implementation_source"]
        or shutil.disk_usage(ROOT).free < 50 * 1024**3
        or file_digest(Path(__file__).resolve()) != review["driver"]["sha256"]
        or review["model_turns"] != 0
        or review["maximum_cash_usd"] != 0
    ):
        raise RuntimeError("boundary review has expired or its source, driver, or reserve changed")


def reviewed(repo, content, kind):
    ref = content_digest(content)
    row = repo.store._connection.execute(
        "SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,)
    ).fetchone()
    if row and row[0]:
        raise RuntimeError("exact definition was revoked")
    repo.put(kind, ref, content)
    if row is None:
        repo.review(ref)


def extend(repo, grant, baseline, expires, operations, seconds, *, apply, plan_id=None):
    if helpers.debit_baseline(repo, grant, plan_id=plan_id) != baseline:
        raise RuntimeError("original grant balance or authority changed")
    root = repo.effective_grant(grant)
    limits = root.limits
    counters = baseline["counters"]
    proposal = AssessmentBudgetAmendment(
        authorization_id=grant,
        authorization_digest=baseline["root"],
        previous_amendment_digest=baseline["predecessor"],
        limits=AssessmentLimits(
            max_operations=max(limits.max_operations, counters[1] + operations),
            max_model_turns=limits.max_model_turns,
            max_cash_usd=limits.max_cash_usd,
            max_elapsed_seconds=max(limits.max_elapsed_seconds, counters[3] + seconds),
        ),
        expires_at=max(root.expires_at, datetime.fromisoformat(expires)),
    )
    if apply and (proposal.expires_at != root.expires_at or proposal.limits != limits):
        repo.approve_budget_amendment(proposal)
    return proposal


def scanner(review, *, apply):
    entry = review["scanner"]
    for key in ("original_review", "historical_scan", "manifest", "preview"):
        checked_file(entry[key])
    workflow = checked_file(entry["workflow"])
    runtime = ScannerRuntimeDefinition.model_validate(helpers.load(checked_file(entry["runtime"])))
    scope = WorkflowAccountingDefinition.model_validate(
        helpers.load(checked_file(entry["accounting"]))
    )
    preview, definition, _ = scan_preview(workflow, "document-data")
    assert preview["review_sha256"] == entry["review_sha256"] and definition == runtime
    assert preview == helpers.load(Path(entry["preview"]["path"]))
    plans = (
        ("scan", runtime.request.authorization_id, runtime.timeout_seconds + 40),
        ("wrapper", scope.request.authorization_id, scope.maximum_overhead_seconds),
    )
    assert entry["maximum_additional_operations"] == 2
    assert entry["maximum_reserved_seconds"] == sum(row[2] for row in plans)
    with ReceiptStore(entry["database"], read_only=not apply) as store:
        repo = AssessmentRepository(store)
        amendments = {
            role: extend(
                repo, grant, entry["baselines"][role], review["expires_at"], 1, seconds, apply=apply
            )
            for role, grant, seconds in plans
        }
        if not apply:
            return {"passed": True, "cli_preview": preview["review_sha256"]}
        reviewed(repo, runtime, "toolkit_scanner_runtime")
        reviewed(repo, scope, "toolkit_workflow_accounting")
        check_conditions(review)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            if toolkit_cli(entry["command"]) != 0:
                raise RuntimeError("ordinary scanner command failed")
        result = json.loads(output.getvalue())
        record = require_scan(repo, result["scan_ref"], workflow, "document-data")
        require_scan(repo, result["scan_ref"], workflow, "software-engineering")
        return {
            "passed": True,
            "result": result,
            "receipt_ref": record.receipt_ref,
            "journal_ref": record.execution_evidence_ref,
            "budget_amendments": {
                role: item.model_dump(mode="json") for role, item in amendments.items()
            },
        }


async def native_probe(repo, request, operation, spec, payload, review_ref, seconds, authorize):
    repo.reserve(
        request,
        operation,
        AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=seconds),
        stage="ase_current_native_boundary",
        require_settled_plan=True,
    )
    action = ActionRequest(action_id=operation, capability=spec.capability, input=payload)
    context = ExecutionContext(
        request=action,
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=operation,
        approved_side_effect=SideEffect.WRITE,
        invocation_check=authorize,
    )
    began, clock = utc_now(), time.perf_counter()
    executor = CommandExecutor()
    try:
        with persist_execution_events(
            lambda journal, event: repo.put("execution_event", f"{journal}:{event.sequence}", event)
        ):
            raw = await (await executor.start(context)).task
    finally:
        await executor.close()
    # An exception before definitive process evidence leaves the reservation open.
    elapsed = time.perf_counter() - clock
    observed = raw.output if isinstance(raw.output, dict) else {}
    expected = {
        "outside_read_denied",
        "outside_write_denied",
        "response_write_denied",
        "candidate_write_denied",
        "network_denied",
        "local_git_initialization",
    }
    checks = observed.get("checks", {})
    passed = (
        raw.status.value == "success"
        and raw.exit_code == 0
        and observed.get("passed") is True
        and observed.get("models") == 0
        and observed.get("upstream_imports") == 0
        and isinstance(checks, dict)
        and set(checks) == expected
        and all(result is True for result in checks.values())
    )
    receipt = ExecutionReceipt(
        decision_id=operation,
        action_id=action.action_id,
        capability=spec.capability,
        executor_id=spec.id,
        executor_kind=spec.kind,
        status="success" if passed else "failed",
        started_at=began,
        ended_at=utc_now(),
        estimated=spec.estimate,
        actual_resources=raw.resources,
        accounting=raw.accounting,
        execution_success=passed,
        error_type=(raw.error_type or "NativeBoundaryCheckFailed") if not passed else None,
        metadata={
            **raw.metadata,
            "review_sha256": review_ref,
            "observed_checks": checks,
            "exit_code": raw.exit_code,
            "model_turns": 0,
        },
    )
    repo.store.save_receipt(receipt)
    if raw.exit_code is not None and raw.exit_code >= 0:
        repo.finish_operation(
            operation, elapsed_seconds=elapsed, accounting=raw.accounting, resources=raw.resources
        )
    return {
        "passed": passed,
        "operation_id": operation,
        "receipt_ref": content_digest(receipt),
        "journal_ref": raw.metadata.get("execution_evidence_digest"),
        "checks": checks,
        "exit_code": raw.exit_code,
        "seconds": elapsed,
    }


def agent_skill_eval(review, review_ref, *, apply):
    entry = review["agent_skill_eval"]
    historic = SchedulerDefinition.model_validate(
        helpers.load(checked_file(entry["historical_scheduler"]))
    )
    for key in (
        "historical_profile",
        "historical_native_control",
        "current_profile",
        "probe",
        "outside_canary",
        "git",
    ):
        checked_file(entry[key])
    changes = helpers.changed(historic.executable_dependencies)
    assert set(changes) == {"/usr/bin/sandbox-exec"} and changes == entry["executable_change"]
    assert historic.runtime_tree_digest == entry["runtime_tree_sha256"]
    assert historic.runtime_tree_digest == snapshot(Path(historic.runtime_root))
    assert snapshot(Path(entry["workspace"])) == entry["workspace_tree_sha256"]
    assert not Path(entry["stdin"]["outside_write"]).exists()
    request = ConformanceProbeRequest.model_validate(entry["request"])
    seconds = entry["maximum_reserved_seconds"]
    assert entry["maximum_additional_operations"] == 1 and seconds == 35
    spec = ExecutorSpec(
        id="toolkit.ase-native-compatibility",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        side_effect="write",
        description="Native boundary compatibility for the retained agent-skill-eval scheduler",
        config={
            "argv": entry["command"],
            "argv_literal": True,
            "inherit_env": False,
            "env": entry["environment"],
            "cwd": entry["workspace"],
            "stdin_json": True,
            "max_stdin_bytes": 16384,
            "max_output_bytes": 8192,
            "timeout_seconds": 25,
            "output": {"type": "json"},
        },
    )
    with ReceiptStore(entry["database"], read_only=not apply) as store:
        repo = AssessmentRepository(store)
        assert content_digest(repo.get("conformance_request", request.plan_id)) == content_digest(
            request
        )
        if store._connection.execute(
            "SELECT id FROM assessment_operations WHERE id=?", (entry["operation_id"],)
        ).fetchone():
            raise RuntimeError("native check already reserved")
        budget = extend(
            repo,
            request.authorization_id,
            entry["baseline"],
            review["expires_at"],
            1,
            seconds,
            apply=apply,
            plan_id=request.plan_id,
        )
        if not apply:
            return {"passed": True, "changed_dependency_count": len(changes)}
        reviewed(repo, spec, "toolkit_ase_native_compatibility")
        request = request.model_copy(
            update={
                "definition_digests": [*request.definition_digests, content_digest(spec)],
            }
        )

        def authorize():
            repo.authorize(request)
            check_conditions(review)
            for key in ("current_profile", "probe", "outside_canary", "git"):
                checked_file(entry[key])
            verify_dependencies(
                {
                    **historic.executable_dependencies,
                    "/usr/bin/sandbox-exec": changes["/usr/bin/sandbox-exec"]["current"],
                }
            )

        authorize()
        result = asyncio.run(
            native_probe(
                repo,
                request,
                entry["operation_id"],
                spec,
                entry["stdin"],
                review_ref,
                seconds,
                authorize,
            )
        )
        result["budget_amendment"] = budget.model_dump(mode="json")
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    review_file = args.review.resolve()
    review = helpers.load(review_file)
    ref = file_digest(review_file)
    check_conditions(review)
    # Both components must pass preflight. An execution failure remains component-scoped.
    checks = {
        "scanner": scanner(review, apply=False),
        "agent_skill_eval": agent_skill_eval(review, ref, apply=False),
    }
    if not args.execute_approved:
        print(json.dumps({"review_sha256": ref, "preflight": checks, "execution": False}, indent=2))
        return
    approval = helpers.load(review_file.with_name("operator-approval.json"))
    assert (
        args.execute_approved == ref == approval["review_sha256"] and approval["approved"] is True
    )
    helpers.save(review_file.with_name("started.json"), {"review_sha256": ref})
    with (review_file.with_name("result.json")).open("x") as output:
        results = {}
        for name, invoke in (
            ("scanner", lambda: scanner(review, apply=True)),
            ("agent_skill_eval", lambda: agent_skill_eval(review, ref, apply=True)),
        ):
            try:
                results[name] = invoke()
            except (Exception, SystemExit) as error:
                results[name] = {"passed": False, "error_type": type(error).__name__}
            output.write(json.dumps({name: results[name]}, allow_nan=False) + "\n")
            output.flush()
    print(json.dumps(results, indent=2, allow_nan=False))
    if not all(item["passed"] for item in results.values()):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
