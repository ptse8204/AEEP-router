"""One fresh protected operation; preserve safe transport diagnostics before privacy scrubbing."""
import asyncio
import hashlib
import json
import re
import time
import traceback
from pathlib import Path

from aeep.assessment import containment
from aeep.assessment.extensions import materialize
from aeep.assessment.models import AssessmentScopeAmendment, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.executors import command
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
KNOWN = {'ConfigurationError', 'ExecutorError', 'JSONDecodeError', 'TimeoutError', 'CommandExitError',
    'CONTAINER_PROTOCOL_ERROR', 'STREAM_OBSERVER_FAILED', 'BACKGROUND_PROCESS_REJECTED',
    'execution_failed', 'ValueError', 'ValidationError', 'OSError', 'UnicodeDecodeError', 'MemoryError',
    'ModuleNotFoundError', 'ImportError', 'PermissionError', 'FileNotFoundError', 'BrokenPipeError',
    'TypeError', 'KeyError', 'AttributeError', 'IndexError', 'RuntimeError', 'ProcessLookupError'}
events = []


def safe_error(kind, message):
    text = str(message or '')
    category = next((label for pattern, label in [
        ('expecting value', 'json_expected_value'), ('extra data', 'json_extra_data'),
        ('unterminated string', 'json_unterminated_string'), ('delimiter', 'json_delimiter'),
        ('parse', 'output_parser'), ('input exceeds', 'input_limit'),
        ('container protocol', 'container_protocol'), ('memory', 'memory'),
        ('timeout', 'timeout'), ('changed', 'dependency_change')]
        if pattern in text.lower()), 'unclassified')
    numbers = re.search(r'line (\d+) column (\d+) \(char (\d+)\)', text)
    return {'known_error_type': kind if kind in KNOWN else 'unclassified', 'classification': category,
        'json_position': list(map(int, numbers.groups())) if numbers else None}


def append(event):
    if len(events) < 32:
        events.append(event)


def raw_facts(raw):
    result = {'status': raw.status.value, 'exit_code': raw.exit_code,
        **safe_error(raw.error_type, raw.error_message)}
    for key in ('stdout_bytes', 'stderr_bytes', 'stdout_truncated', 'stderr_truncated'):
        value = raw.metadata.get(key)
        if isinstance(value, (int, bool)):
            result[key] = value
    if isinstance(raw.output, dict) and 'status' in raw.output and 'error_type' in raw.output:
        result['child'] = safe_error(raw.output.get('error_type'), raw.output.get('error_message'))
        result['child']['status'] = raw.output.get('status') if raw.output.get('status') in {'success', 'failed', 'timeout', 'rejected'} else 'unclassified'
        metadata = raw.output.get('metadata')
        if isinstance(metadata, dict):
            for key in ('stdout_bytes', 'stderr_bytes', 'stdout_truncated', 'stderr_truncated'):
                value = metadata.get(key)
                if isinstance(value, (int, bool)):
                    result['child'][key] = value
    return result


async def main():
    path = OUT / 'pilot-materialization-workflow-46803-review.json'
    assert hashlib.sha256(path.read_bytes()).hexdigest() == 'a89c1aa08eb9517c80253c456381620c7f00ea522fd78a0333239e8ce5a50122'
    review = json.loads(path.read_text())
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'materialization-workflow-46803-result.json').exists()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    result = {'source_digest': review['source_digest'], 'request_id': review['request']['plan_id'],
        'model_turns': 0, 'prior_cause_remains_unknown': True, 'no_admission': True, 'replay_allowed': False}
    original_parse = command.parse_output
    original_command = command.CommandExecutor.execute
    original_container = containment.ContainerExecutor.execute

    def parse(text, config=None):
        event = {'stage': 'parent_output_parser', 'declared_type': (config or {}).get('type', 'text'),
            'encoded_bytes': len(text.encode())}
        try:
            output = original_parse(text, config)
            event['parsed'] = True
            return output
        except Exception as exc:
            event.update(parsed=False, **safe_error(type(exc).__name__, str(exc)))
            raise
        finally:
            append(event)

    async def execute_command(self, context):
        raw = await original_command(self, context)
        append({'stage': 'parent_command_transport', 'declared_output_limit': context.spec.config.get('max_output_bytes'),
            'declared_output_type': context.spec.config.get('output', {}).get('type'), **raw_facts(raw)})
        return raw

    async def execute_container(self, context):
        raw = await original_container(self, context)
        append({'stage': 'contained_result', **raw_facts(raw)})
        return raw

    began = time.monotonic()
    try:
        service.repository.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        command.parse_output = parse
        command.CommandExecutor.execute = execute_command
        containment.ContainerExecutor.execute = execute_container
        async with asyncio.timeout(35):
            cases = await materialize(service, result['request_id'])
        counts = {name: sum(c.split.value == name for c in cases.cases) for name in ('qualification', 'training', 'holdout')}
        screening = [c.case_id for c in cases.cases if c.split.value == 'qualification']
        assert counts == {'qualification': 8, 'training': 28, 'holdout': 105} and len(set(screening)) == 8 and len({c.case_id for c in cases.cases}) == 141
        result.update(materialization_passed=True, case_set_digest=content_digest(cases), case_count=len(cases.cases), split_counts=counts, distinct_screening_count=len(set(screening)), distinct_case_count=len({c.case_id for c in cases.cases}))
    except Exception as exc:
        result.update(materialization_passed=False, **safe_error(type(exc).__name__, str(exc)),
            stack=[{'module_file': Path(f.filename).name, 'line': f.lineno, 'function': f.name}
                for f in traceback.extract_tb(exc.__traceback__)[-8:]])
    finally:
        command.parse_output = original_parse
        command.CommandExecutor.execute = original_command
        containment.ContainerExecutor.execute = original_container
        result['diagnostics'] = events
        result['elapsed_seconds'] = time.monotonic() - began
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        (OUT / 'materialization-workflow-46803-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
