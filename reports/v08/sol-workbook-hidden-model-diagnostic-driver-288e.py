"""One-shot, reviewed worker model-list diagnostic; no auth or model turns."""

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.models import AssessmentLimits, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.workers import binding_from_config
from aeep.router import Router


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports/v08"
BASE = ROOT / ".aeep/live-review-v3"
SOURCE = "288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782"
REVIEW = REPORTS / "sol-workbook-hidden-model-diagnostic-review-288e.json"
START = REPORTS / "sol-workbook-hidden-model-diagnostic-start-288e.json"
RESULT = REPORTS / "sol-workbook-hidden-model-diagnostic-result-288e.json"


async def main() -> None:
    start = json.loads(START.read_text())
    review = json.loads(REVIEW.read_text())
    assert verification_source_digest(ROOT) == SOURCE == start["source_digest"] == review["source_digest"]
    assert hashlib.sha256(REVIEW.read_bytes()).hexdigest() == start["review_sha256"]
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest() == start["driver_sha256"]
    assert review["request_id"] == start["request_id"]
    assert not RESULT.exists()
    router = Router.from_manifest(BASE / "aeep.json")
    try:
        service = AssessmentService(router, BASE / ".aeep/assessments")
        repo = service.repository
        request = ConformanceProbeRequest.model_validate(repo.get("conformance_request", review["request_id"]))
        assert request.operation == "worker_inspection" and content_digest(request) == review["request_digest"]
        repo.authorize(request)
        definition = BoundaryProbeDefinition.model_validate(repo.get("boundary_probe_definition", request.mapping_digest))
        assert content_digest(definition) == request.mapping_digest
        config = definition.executor.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        assert worker is not None and worker.digest() == request.worker_digest
        operation = "hidden-model-discovery:" + request.plan_id
        repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
                     stage="worker_model_discovery")
        began = time.perf_counter()
        adapter = None
        observations = {"model_turns": 0, "include_hidden": True, "models": [],
                        "complete": False, "cleanup_confirmed": False}
        stage = "adapter_start"
        try:
            async with asyncio.timeout(90):
                repo.authorize(request)
                adapter = CodexAppServerAdapter.from_executor(
                    definition.executor, principal_salt=router.store.host_principal_key())
                cursor = None
                seen_models = set()
                seen_cursors = set()
                for _ in range(100):
                    stage = "model/list"
                    repo.authorize(request)
                    params = {"includeHidden": True}
                    if cursor is not None:
                        params["cursor"] = cursor
                    payload = await adapter.transport.request("model/list", params, timeout=20)
                    page = payload.get("data")
                    if not isinstance(page, list):
                        raise ValueError("model/list omitted data")
                    for item in page:
                        if not isinstance(item, dict):
                            continue
                        model_id = item.get("model") or item.get("id")
                        if not isinstance(model_id, str) or not model_id or model_id in seen_models:
                            continue
                        efforts = item.get("supportedReasoningEfforts")
                        names = sorted({entry["reasoningEffort"] for entry in efforts
                                        if isinstance(entry, dict) and isinstance(entry.get("reasoningEffort"), str)}) \
                            if isinstance(efforts, list) else []
                        observations["models"].append({"id": model_id, "reasoning_efforts": names})
                        seen_models.add(model_id)
                    next_cursor = payload.get("nextCursor")
                    if not isinstance(next_cursor, str) or not next_cursor:
                        observations["complete"] = True
                        break
                    if next_cursor in seen_cursors:
                        raise ValueError("model/list cursor repeated")
                    seen_cursors.add(next_cursor)
                    cursor = next_cursor
                else:
                    raise ValueError("model/list exceeded page bound")
        except BaseException as exc:
            observations["failed_stage"] = stage
            observations["error_type"] = type(exc).__name__
        finally:
            if adapter is not None:
                try:
                    await asyncio.wait_for(adapter.transport.close(), 5)
                except BaseException as exc:
                    observations["cleanup_error_type"] = type(exc).__name__
                try:
                    observations["cleanup_confirmed"] = bool(adapter._worker_process_id) and \
                        await asyncio.wait_for(worker.cleanup(adapter._worker_process_id or ""), 20)
                except BaseException as exc:
                    observations["cleanup_error_type"] = type(exc).__name__
                if adapter._worker_security:
                    adapter._worker_security.cleanup()
            repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - began)
            sol = [item for item in observations["models"] if item["id"] == "gpt-6-sol"]
            observations["reviewed_model_present"] = len(sol) == 1
            observations["reviewed_medium_present"] = len(sol) == 1 and "medium" in sol[0]["reasoning_efforts"]
            grant = router.store._connection.execute(
                "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?",
                (request.authorization_id,),).fetchone()
            value = {"recorded_at": datetime.now(timezone.utc).isoformat(), "source_digest": SOURCE,
                     "request_id": request.plan_id, "operation_id": operation,
                     "observations": observations, "auth_state": "unknown; no account request made",
                     "grant_after": dict(zip(("operations", "model_turns", "elapsed_seconds", "cash_usd"), grant)),
                     "source_unchanged": verification_source_digest(ROOT) == SOURCE,
                     "replay_allowed": False, "release_ready": False}
            with RESULT.open("x") as stream:
                json.dump(value, stream, indent=2)
                stream.write("\n")
            print(json.dumps({"complete": observations["complete"],
                              "reviewed_model_present": observations["reviewed_model_present"],
                              "cleanup_confirmed": observations["cleanup_confirmed"],
                              "operations": grant[0]}))
    finally:
        await router.close()


asyncio.run(main())
