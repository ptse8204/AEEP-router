"""Operator-requested uninstall only; preserve task evidence and user conflicts."""
import asyncio
import hashlib
import json
import os
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel
from aeep.router import Router
from aeep.tasks import change_state, inspect

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'reports/v08'
SOURCE = '5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PROJECT = ROOT / '.aeep/human-presentation-5fff'


class Definition(StrictModel):
    driver_sha256: str
    task_result_sha256: str
    activation_id: str
    manifest_sha256: str
    maximum_seconds: int = 15
    maximum_operations: int = 1
    maximum_model_turns: int = 0
    maximum_cash_usd: int = 0
    operation: str = 'uninstall owned project configuration; retain canonical receipts and conflicts'


async def main():
    assert os.environ.get('AEEP_RETAINED_HUMAN_CLEANUP_REVIEW') == 'parent-approved-owned-cleanup-5fff'
    assert verification_source_digest(ROOT) == SOURCE
    path = REPORTS / 'retained-human-project-5fff-result.json'
    result = json.loads(path.read_text())
    assert result['source_digest'] == SOURCE and result['project'] == str(PROJECT)
    manifest = Path(result['manifest'])
    assert manifest == PROJECT / 'aeep.json'
    target = REPORTS / 'retained-human-project-5fff-cleanup.json'
    assert not target.exists()
    sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
    definition = Definition(driver_sha256=sha(__file__), task_result_sha256=sha(path),
        activation_id=result['activation_id'], manifest_sha256=sha(manifest))
    router = Router.from_manifest(manifest)
    assert inspect(router, result['activation_id'])['scope_digest'] == result['scope_digest']
    main_router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    repo = AssessmentRepository(main_router.store)
    old = AssessmentPlanningRequest.model_validate(repo.get('planning_request', 'planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    mapping = repo.put('native_human_cleanup', 'retained-human-project-5fff', definition)
    repo.review(mapping)
    request = old.model_copy(update={'plan_id': 'planning_retained_human_cleanup_5fff', 'mapping_digest': mapping,
        'definition_digests': [*old.definition_digests, mapping]})
    digest = repo.put('planning_request', request.plan_id, request)
    repo.review(digest)
    repo.authorize(request)
    operation = 'native-human-cleanup:' + request.plan_id
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=15,
        max_model_turns=0, max_cash_usd=0), stage='owned_human_project_cleanup')
    began = time.perf_counter()
    record = {'source_digest': SOURCE, 'definition': definition.model_dump(), 'request_digest': digest,
        'operation_id': operation, 'model_turns': 0, 'cash_usd': 0, 'task_evidence_retained': True}
    try:
        async with asyncio.timeout(10):
            record['inspection'] = change_state(router, result['activation_id'], 'uninstall')
    except BaseException as exc:
        record['error_type'] = type(exc).__name__
    finally:
        try:
            async with asyncio.timeout(1):
                await router.close()
            record['task_router_closed'] = True
        except BaseException as exc:
            record.update(task_router_closed=False, task_close_error_type=type(exc).__name__)
        try:
            repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - began)
            record['assessment_operation_finished'] = True
        except BaseException as exc:
            record.update(assessment_operation_finished=False, accounting_error_type=type(exc).__name__,
                accounting_status='unknown; original reservation retained, no retry')
        try:
            async with asyncio.timeout(1):
                await main_router.close()
            record['main_router_closed'] = True
        except BaseException as exc:
            record.update(main_router_closed=False, main_close_error_type=type(exc).__name__)
        record['source_unchanged'] = verification_source_digest(ROOT) == SOURCE
        target.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record))


if __name__ == '__main__':
    if sys.argv[1:] != ['--uninstall-reviewed-human-project']:
        raise SystemExit('INERT: run only after participant completion or explicit abandonment')
    asyncio.run(main())
