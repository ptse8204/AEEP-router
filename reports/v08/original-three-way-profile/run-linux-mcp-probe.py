"""Inert until exact review hash supplied; supplementary inspection, never a model trial."""
import asyncio
import hashlib
import json
import sys
import time
from pathlib import Path

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_pair_inspection import command
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router


class Result(StrictModel):
    facts: dict


ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent


async def main():
    path = OUT / 'linux-mcp-probe-review.json'
    assert len(sys.argv) == 2 and hashlib.sha256(path.read_bytes()).hexdigest() == sys.argv[1]
    review = json.loads(path.read_text())
    assert review['execution_authorized'] is True
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'linux-mcp-probe-result.json').exists()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    repo = service.repository
    result = {'source_digest': review['source_digest'], 'model_turns': 0, 'full_conformance': False, 'workers': {}}
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        for role, value in zip(('outside_mcp',), review['requests'], strict=True):
            request = ConformanceProbeRequest.model_validate(value)
            repo.authorize(request)
            assert content_digest(review['definition']) == request.mapping_digest
            assert repo.get('linux_task_probe_definition', request.mapping_digest) == review['definition']
            verify_dependencies(request.executable_dependencies)
            spec = ExecutorSpec.model_validate(review['definition']['profiles'][role])
            worker = binding_from_config(spec.managed_host_config().managed_worker)
            assert worker and worker.digest() == request.worker_digest
            from aeep.assessment.destinations import require_destination
            from aeep.assessment.models import AssessmentEnvironment
            require_destination(spec, AssessmentEnvironment.model_validate(repo.get('environment', request.environment_digest)), repo.authorize(request))
            operation = 'linux-mcp-task-probe:' + request.plan_id
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=60), stage='worker_inspection')
            started = time.monotonic()
            adapter = None
            facts = {'request_id': request.plan_id, 'operation_id': operation, 'image': worker.image,
                'worker_digest': worker.digest(), 'cleanup_confirmed': False, 'protocol_passed': False,
                'cpu_seconds': None, 'peak_memory_mb': None, 'accounting_complete': False}
            stage = 'adapter_initialization'
            try:
                async with asyncio.timeout(40):
                    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=router.store.host_principal_key())
                    repo.authorize(request)
                    stage = 'command_warmup'
                    await command(adapter, 'import json;print(json.dumps({"ready":True}))', timeout_ms=5000)
                    from aeep.hosts.codex_invocation import advertised_tools, contract_digest
                    stage = 'thread_start'
                    thread = await adapter.transport.request('thread/start', {'ephemeral': True, 'model': 'gpt-6.1-sol', 'cwd': '/workspace', 'permissions': 'aeep', 'approvalPolicy': 'never', 'approvalsReviewer': 'user'})
                    assert thread.get('activePermissionProfile', {}).get('id') == 'aeep'
                    assert thread.get('approvalPolicy') == 'never'
                    thread_id = thread['thread']['id']
                    stage = 'tool_inventory'
                    tools = await advertised_tools(adapter.transport, thread_id)
                    assert contract_digest(tools[('linux_boundary_diagnostic', 'sandbox_probe')]) == review['tool_digest']
                    stage = 'mcp_tool_call'
                    raw = await adapter.transport.request('mcpServer/tool/call', {'threadId': thread_id, 'server': 'linux_boundary_diagnostic', 'tool': 'sandbox_probe', 'arguments': {}}, timeout=10)
                    observed = raw['structuredContent']
                    stage = 'command_sandbox_denial'
                    direct = await command(adapter, review['definition']['programs']['direct'], timeout_ms=5000)
                    observed['model_command'] = direct
                    stage = 'independent_canary_witness'
                    witness = await worker.artifact(adapter._worker_process_id or '', name='private-state.json', limit=1024, timeout=5)
                    observed['independent_canary_unchanged'] = witness['sha256'] == hashlib.sha256(b'aeep-public-canary-v1').hexdigest()
                    facts['observed'] = observed
                    facts['protocol_passed'] = observed.get('exit_code') == 0 and observed.get('child') == {'marker': True, 'read_denied': True, 'write_denied': True} and observed.get('model_command') == {'read_denied': True, 'write_denied': True} and observed.get('independent_canary_unchanged') is True
            except Exception as exc:
                facts['error_type'] = type(exc).__name__
                facts['failing_stage'] = stage
                facts['error_class'] = ('timeout' if isinstance(exc, TimeoutError) else 'protocol_or_configuration' if type(exc).__name__ in {'CodexProtocolError', 'ConfigurationError'} else 'assertion_failed' if isinstance(exc, AssertionError) else 'unclassified')
            finally:
                if adapter is not None:
                    try:
                        await asyncio.wait_for(adapter.transport.close(), 3)
                    except Exception as exc:
                        facts['transport_cleanup_error_type'] = type(exc).__name__
                    try:
                        facts['cleanup_confirmed'] = bool(adapter._worker_process_id) and await asyncio.wait_for(worker.cleanup(adapter._worker_process_id or ''), 8)
                    except Exception as exc:
                        facts['cleanup_error_type'] = type(exc).__name__
                    if adapter._worker_security:
                        try:
                            adapter._worker_security.cleanup()
                        except OSError as exc:
                            facts['security_cleanup_error_type'] = type(exc).__name__
                facts['elapsed_seconds'] = time.monotonic() - started
                repo.finish_operation(operation, elapsed_seconds=facts['elapsed_seconds'], accounting=None, resources=None)
                document = Result(facts=facts)
                facts['canonical_record_digest'] = repo.put('linux_task_boundary_observation', content_digest(document), document)
                result['workers'][role] = facts
            if not facts['protocol_passed'] or not facts['cleanup_confirmed']:
                break
        result['probe_supported'] = len(result['workers']) == 1 and all(f['protocol_passed'] and f['cleanup_confirmed'] for f in result['workers'].values())
    finally:
        result['classification'] = ('mcp_child_and_command_denial_observed' if result.get('probe_supported') else 'mcp_child_support_or_denial_not_established')
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        (OUT / 'linux-mcp-probe-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
