"""One synthetic native READ task retained for an operator comprehension exercise."""
import asyncio
import contextlib
import io
import hashlib
import json
import os
import runpy
import sys
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.models import AssessmentLimits, AssessmentPlanningRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService
from aeep.models import Manifest, SideEffect, StrictModel, TaskScope, ValidationKind, ValidationSpec, utc_now
from aeep.router import Router
from aeep.task_cli import show_result
from aeep.tasks import activate, inspect

ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / 'reports/v08'
ASSETS = ROOT / 'integrations/assessment-runtime'
SOURCE = '5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
PROJECT = ROOT / '.aeep/human-presentation-5fff'
BINARY = Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON = Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3.12').resolve()


def file_hash(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


class Definition(StrictModel):
    source_digest: str
    driver_sha256: str
    fixture_sha256: str
    program_sha256: str
    grader_sha256: str
    binary_sha256: str
    python_sha256: str
    maximum_seconds: int = 60
    maximum_operations: int = 1
    maximum_model_turns: int = 0
    maximum_cash_usd: int = 0
    maximum_task_attempts: int = 1
    maximum_task_seconds: int = 30
    scope_lifetime_seconds: int = 3600
    fixture_index: int = 0
    classification: str = 'synthetic zero-model task/result/control comprehension project; no human responses or qualification claim'


async def main():
    assert os.environ.get('AEEP_RETAINED_HUMAN_PROJECT_REVIEW') == 'parent-approved-exact-5fff'
    assert verification_source_digest(ROOT) == SOURCE
    validation = json.loads((REPORTS / 'delivery-boundary-validation-5fffda8a3210.json').read_text())
    assert validation['complete'] and validation['source_unchanged'] and validation['source_digest'] == SOURCE
    assert len(validation['checks']) == 22 and all(check['exit_code'] == 0 for check in validation['checks'])
    assert file_hash(BINARY) == '50ac633af64851511f9bbc71032cdae7f1ba20b3234c189687d61ba846c354c5'
    assert file_hash(PYTHON) == '5ccd02f7849086e9314db5778ba9085c10a7dd3879c949626f2cf838294c7325'
    assert not PROJECT.exists()
    assert not (REPORTS / 'retained-human-project-5fff-result.json').exists()
    assert not (REPORTS / 'retained-human-project-5fff-ordinary-result.txt').exists()
    definition = Definition(source_digest=SOURCE, driver_sha256=file_hash(__file__),
        fixture_sha256=file_hash(ASSETS / 'workbook-grader-fixtures.json'),
        program_sha256=file_hash(ASSETS / 'workbook_program.py'), grader_sha256=file_hash(ASSETS / 'workbook_grader.py'),
        binary_sha256=file_hash(BINARY), python_sha256=file_hash(PYTHON))
    main_router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    repo = AssessmentRepository(main_router.store)
    old = AssessmentPlanningRequest.model_validate(repo.get('planning_request', 'planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
    mapping = repo.put('native_human_presentation', 'retained-human-project-5fff', definition)
    repo.review(mapping)
    request = old.model_copy(update={'plan_id': 'planning_retained_human_project_5fff', 'mapping_digest': mapping,
        'definition_digests': [*old.definition_digests, mapping]})
    request_digest = repo.put('planning_request', request.plan_id, request)
    repo.review(request_digest)
    repo.authorize(request)
    operation = 'native-human:' + request.plan_id
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=60,
        max_model_turns=0, max_cash_usd=0), stage='native_human_presentation')
    began = time.perf_counter()
    task = None
    record = {'source_digest': SOURCE, 'operation_id': operation, 'request_digest': request_digest,
        'definition_digest': mapping, 'definition': definition.model_dump(), 'model_turns': 0, 'cash_usd': 0,
        'human_comprehension': 'not measured', 'project': str(PROJECT), 'cleanup': 'retained intentionally for operator controls'}
    try:
        async with asyncio.timeout(50):
            PROJECT.mkdir()
            scratch = PROJECT / 'scratch'
            scratch.mkdir()
            fixture = json.loads((ASSETS / 'workbook-grader-fixtures.json').read_text())[0]
            boundary = NativeSandboxConfig(binary=str(BINARY), binary_sha256='sha256:' + definition.binary_sha256,
                project_root=str(PROJECT), read_roots=[str(PYTHON.parent.parent), str(ROOT / 'AGENTS.md')],
                write_roots=[str(scratch)], single_process=True, python_binary=str(PYTHON), python_sha256='sha256:' + definition.python_sha256)
            recipe = workbook_recipe()
            spec = recipe.extension.reference.model_copy(deep=True)
            spec.id = 'native.workbook.human-presentation-5fff'
            spec.input_schema, spec.output_schema = recipe.input_schema, recipe.output_schema
            program = "import json,sys;ns={'__name__':'reference'};exec(" + repr((ASSETS / 'workbook_program.py').read_text()) + ",ns);inp=json.load(sys.stdin);print(json.dumps(ns['reference'](inp)))"
            spec.config = {**spec.config, 'argv': [str(PYTHON), '-I', '-c', program],
                'native_sandbox': boundary.model_dump(mode='json'), 'env': {'TMPDIR': str(scratch)},
                'timeout_seconds': 30, 'max_output_bytes': 200000}
            spec.validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
                config={'name': 'aeep.workbook.native.v1', 'implementation_digest': implementation_digest()})]
            manifest = PROJECT / 'aeep.json'
            manifest.write_text(Manifest(database=str(PROJECT / '.aeep/state.db'), executors=[spec]).model_dump_json())
            task = Router.from_manifest(manifest)
            task_repo = AssessmentRepository(task.store)
            task_repo.review(task_repo.put('recipe', recipe.recipe_id, recipe))
            scope = TaskScope(scope_id='human-presentation-5fff', project_root=str(PROJECT),
                executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.READ,
                max_attempts=1, max_attempt_seconds=30, expires_at=utc_now() + timedelta(hours=1))
            scope_digest = task_repo.put('task_scope', scope.scope_id, scope)
            task_repo.review(scope_digest)
            activation = activate(task, scope.scope_id)
            record.update(scope_digest=scope_digest, scope=scope.model_dump(mode='json'), activation_id=activation.activation_id,
                manifest=str(manifest), executor_fingerprint=executor_fingerprint(spec))
            service = AEEPToolService(task, profile='task', task_activation=activation.activation_id)
            tools = service.list_tools()
            assert len(tools) == 1
            output = (await service.call(tools[0]['name'], fixture['input']))['structuredContent']
            independent = runpy.run_path(str(ASSETS / 'workbook_grader.py'))['grade'](
                {'input': fixture['input'], 'output': output.get('output'), 'expected': fixture['expected']})
            from aeep.models import TaskExecutionOutcome
            value = TaskExecutionOutcome.model_validate(output)
            record.update(ok=value.ok, receipt_ids=[receipt.receipt_id for receipt in value.receipts],
                independent_grader_valid=independent, summary=value.summary, inspection=inspect(task, activation.activation_id))
            text = io.StringIO()
            with contextlib.redirect_stdout(text):
                show_result(SimpleNamespace(obj=task), value.receipts[0].receipt_id, text=True, activation=activation.activation_id)
            assert isinstance(fixture['input']['task'], str)
            (REPORTS / 'retained-human-project-5fff-ordinary-result.txt').write_text(
                'Original synthetic task instruction:\n' + fixture['input']['task'] + '\n\n' + text.getvalue())
            assert value.ok and independent and all(receipt.task_valid is True for receipt in value.receipts)
    except BaseException as exc:
        record.update(ok=False, error_type=type(exc).__name__, effects_or_attempts='inspect retained canonical task records; no retry')
    finally:
        if task is not None:
            try:
                async with asyncio.timeout(3):
                    await task.close()
                record['task_router_closed'] = True
            except BaseException as exc:
                record.update(task_router_closed=False, task_close_error_type=type(exc).__name__,
                    effects_or_attempts='inspect retained canonical task records; no retry')
        elapsed = time.perf_counter() - began
        try:
            repo.finish_operation(operation, elapsed_seconds=elapsed)
            record['assessment_operation_finished'] = True
        except BaseException as exc:
            record.update(assessment_operation_finished=False, accounting_error_type=type(exc).__name__,
                accounting_status='unknown; original reservation and canonical evidence retained, no reset/retry')
        record.update(elapsed_seconds=elapsed, source_unchanged=verification_source_digest(ROOT) == SOURCE)
        try:
            async with asyncio.timeout(2):
                await main_router.close()
            record['main_router_closed'] = True
        except BaseException as exc:
            record.update(main_router_closed=False, main_close_error_type=type(exc).__name__)
        (REPORTS / 'retained-human-project-5fff-result.json').write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps({key: record.get(key) for key in ['ok', 'receipt_ids', 'independent_grader_valid', 'elapsed_seconds', 'source_unchanged', 'error_type']}))


if __name__ == '__main__':
    if sys.argv[1:] != ['--execute-reviewed-human-fixture']:
        raise SystemExit('INERT: exact review, source22PASS and explicit execute flag required')
    asyncio.run(main())
