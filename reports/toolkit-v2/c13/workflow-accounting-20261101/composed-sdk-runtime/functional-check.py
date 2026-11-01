"""Real, no-model SDK check; execute only under the bound operator review."""
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import timedelta
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.agent_framework_workflow import PipelineDefinition, compile_pipeline
from aeep_toolkit.install_runtime import digest


class EngineeringScope(StrictModel):
    role: str
    review_sha256: str
    implementation_source: str
    purpose: str = "Owned public numeric pipeline; real SDK engineering, no capability comparison"


async def main():
    request = json.load(sys.stdin)
    assert set(request) == {"review_sha256", "installed_source", "canary_path"}
    assert version("agent-framework-core") == "1.21.0"
    installed_root = Path(__import__("aeep.assessment.verification", fromlist=["x"]).__file__).resolve().parents[3]
    assert verification_source_digest(installed_root) == request["installed_source"]
    try:
        Path(request["canary_path"]).read_bytes()
        raise AssertionError("outside home file was readable")
    except PermissionError:
        pass

    # This isolated engineering database cannot authorize an existing assessment.
    store = ReceiptStore(Path.cwd() / "canonical.sqlite3")
    repo = AssessmentRepository(store)
    scopes = [EngineeringScope(role=role, review_sha256=request["review_sha256"],
                               implementation_source=request["installed_source"])
              for role in ("subject", "recipe", "environment", "mapping")]
    refs = [repo.put("toolkit_engineering_scope", item.role, item) for item in scopes]
    for ref in refs:
        repo.review(ref)
    grant = AssessmentAuthorization(
        authorization_id="agent-framework-engineering-" + request["review_sha256"],
        subject_digests=[refs[0]], recipe_digests=[refs[1]], environment_digests=[refs[2]],
        limits=AssessmentLimits(max_operations=8, max_model_turns=0,
                                max_elapsed_seconds=120, max_cash_usd=Decimal(0)),
        allowed_destinations=["local"], expires_at=utc_now() + timedelta(minutes=10),
    )
    repo.grant(grant)
    scope = RecipeMaterializationRequest(
        subject_digest=refs[0], recipe_digest=refs[1], environment_digest=refs[2],
        mapping_digest=refs[3], authorization_id=grant.authorization_id,
        definition_digests=refs, seed=0,
    )
    repo.put("recipe_materialization_request", scope.plan_id, scope)
    executor = CommandExecutor()
    script = 'import json,sys;d=json.load(sys.stdin);print(json.dumps({"value":d["value"]+1}));sys.exit(d["exit"])'
    spec = ExecutorSpec(
        id="owned.public-increment", capability="toolkit.public-calibration@1", kind="command",
        description="Reviewed numeric increment, no model, shell or generated code",
        config={"argv": [sys.executable, "-I", "-B", "-c", script],
                "argv_literal": True, "inherit_env": False, "stdin_json": True,
                "timeout_seconds": 5, "max_output_bytes": 1024, "output": {"type": "json"}},
    )
    fingerprint = executor_fingerprint(spec)
    step = {"executor_id": spec.id, "fingerprint": fingerprint}
    allowed = {}
    observed = []
    values = {}  # Transient outputs, keyed by actual canonical receipt digest.
    interrupt_keys = set()
    revoked = False

    def authorize():
        assert not revoked, "dispatcher revoked"
        assert verification_source_digest(installed_root) == request["installed_source"]
        assert executor_fingerprint(spec) == fingerprint
        repo.authorize(scope)

    async def dispatch(executor_id, key, task_ref, predecessors, expected_fingerprint):
        authorize()
        assert executor_id == spec.id and expected_fingerprint == fingerprint
        assert key in allowed
        task, expected_predecessors, initial, exit_code = allowed[key]
        assert (task_ref, predecessors) == (task, expected_predecessors)
        assert key not in {item["key"] for item in observed}, "attempt replay denied"
        value = values[predecessors[-1]] if predecessors else initial
        assert type(value) is int
        action = ActionRequest(action_id=key, capability=spec.capability,
                               input={"value": value, "exit": exit_code})
        repo.reserve(scope, key, AssessmentLimits(max_operations=1, max_model_turns=0,
                     max_elapsed_seconds=15), stage="sdk_approved_step")
        started, clock, raw = utc_now(), time.monotonic(), None
        try:
            context = ExecutionContext(
                request=action, spec=spec, estimate=spec.estimate, attempt=1, attempt_id=key,
                approved_side_effect=SideEffect.NONE, invocation_check=authorize,
            )
            raw = await (await executor.start(context)).task
            receipt = ExecutionReceipt(
                decision_id="framework-" + key, action_id=key, capability=spec.capability,
                executor_id=spec.id, executor_kind=spec.kind, executor_fingerprint=fingerprint,
                status=raw.status, started_at=started, ended_at=utc_now(), estimated=spec.estimate,
                actual_resources=raw.resources, accounting=raw.accounting,
                execution_success=raw.status.value == "success", error_type=raw.error_type,
                metadata={"review_sha256": request["review_sha256"],
                          "evidence_kind": "engineering_fixture", **raw.metadata},
            )
            store.save_receipt(receipt)
            ref = repo.put("toolkit_integration_receipt", key, receipt)
            assert ref == content_digest(receipt)
            assert receipt.execution_success is (exit_code == 0)
            if exit_code == 0:
                assert raw.output == {"value": value + 1}
            else:
                assert raw.exit_code == exit_code and raw.error_type == "CommandExitError"
            observed.append({"key": key, "ref": ref, "receipt_id": receipt.receipt_id,
                             "succeeded": receipt.execution_success})
            values[ref] = value + 1
            if key in interrupt_keys:
                # The command's actual receipt survives interruption of the SDK callback.
                raise asyncio.CancelledError("reviewed interruption after durable receipt")
            return receipt
        finally:
            repo.finish_operation(key, elapsed_seconds=time.monotonic() - clock,
                                  accounting=raw.accounting if raw else None,
                                  resources=raw.resources if raw else None)

    def prepare(run_id, count, initial=2, exits=None):
        definition = PipelineDefinition(steps=tuple(step for _ in range(count)))
        task = content_digest({"public_calibration": run_id})
        # Receipt predecessors are learned only from canonical dispatch, never SDK guesses.
        keys = []

        async def bounded_dispatch(executor_id, key, task_ref, predecessors, expected):
            index = len(keys)
            assert index < count
            expected_refs = tuple(item["ref"] for item in observed[start:])
            assert predecessors == expected_refs
            expected_key = digest({"definition": digest(definition), "run_id": run_id,
                                   "task": task, "step": index, "predecessors": expected_refs})
            assert key == expected_key
            keys.append(key)
            allowed[key] = (task, expected_refs, initial, exits[index] if exits else 0)
            if run_id == "interrupt" and index == 0:
                interrupt_keys.add(key)
            return await dispatch(executor_id, key, task_ref, predecessors, expected)

        start = len(observed)
        return compile_pipeline(definition, run_id=run_id, dispatch=bounded_dispatch), task

    checks = []
    try:
        pipeline, task = prepare("success", 2)
        result = await pipeline.run(task_ref=task)
        assert result["completed"] and result["state"]["next_step"] == 2
        assert values[result["state"]["receipt_refs"][-1]] == 4
        checks.append({"check": "real_sdk_successor_consumption", "passed": True, "calls": 2})

        pipeline, task = prepare("failure", 2, exits=[7, 0])
        result = await pipeline.run(task_ref=task)
        assert not result["completed"] and result["state"]["next_step"] == 1
        assert len(observed) == 3
        checks.append({"check": "command_failure_stops_successors", "passed": True, "calls": 1})

        pipeline, task = prepare("interrupt", 2)
        try:
            await pipeline.run(task_ref=task)
            raise AssertionError("interruption silently completed")
        except asyncio.CancelledError:
            pass
        assert len(observed) == 4 and observed[-1]["succeeded"]
        retained = observed[-1]["ref"]
        try:
            await pipeline.run(task_ref=task)
            raise AssertionError("interrupted pipeline replayed")
        except ValueError as error:
            assert "already started" in str(error)
        assert len(observed) == 4
        checks.append({"check": "interruption_retains_receipt_refuses_replay", "passed": True, "calls": 1})

        # Explicit new run: consume the verified public output; do not resume or replay the old SDK.
        assert repo.get("toolkit_integration_receipt", retained)
        pipeline, task = prepare("reviewed-recovery", 1, initial=values[retained])
        result = await pipeline.run(task_ref=task)
        assert result["completed"] and values[result["state"]["receipt_refs"][-1]] == 4
        checks.append({"check": "separate_reviewed_continuation", "passed": True, "calls": 1,
                       "retained_predecessor_receipt": retained,
                       "sdk_checkpoint_restoration": "UNSUPPORTED"})

        revoked = True
        pipeline, task = prepare("denied", 1)
        try:
            await pipeline.run(task_ref=task)
            raise AssertionError("revoked dispatch accepted")
        except AssertionError as error:
            assert "dispatcher revoked" in str(error)
        assert len(observed) == 5
        checks.append({"check": "revoked_dispatch_denied", "passed": True, "calls": 0})

        ledger = repo.operation_ledger(scope.plan_id)
        assert len(ledger.operations) == 5
        assert all(op.elapsed_seconds is not None for op in ledger.operations)
        repo.put("operation_ledger", scope.plan_id, ledger)
        for item in observed:
            stored = ExecutionReceipt.model_validate(repo.get("toolkit_integration_receipt", item["ref"]))
            assert content_digest(stored) == item["ref"]
        print(json.dumps({"sdk": "agent-framework-core", "version": version("agent-framework-core"),
                          "checks": checks, "operations": 5, "models": 0, "receipts": observed,
                          "candidate_usefulness": "NOT_ASSESSED", "selection_usefulness": "NOT_ASSESSED",
                          "ordinary_workflow_composition": "NOT_VERIFIED",
                          "cross_process_sdk_recovery": "UNSUPPORTED"}))
    finally:
        await executor.close()
        store.close()


if __name__ == "__main__":
    asyncio.run(main())
