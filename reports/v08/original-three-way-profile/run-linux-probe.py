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
    path = OUT / 'linux-probe-review.json'
    assert len(sys.argv) == 2 and hashlib.sha256(path.read_bytes()).hexdigest() == sys.argv[1]
    review = json.loads(path.read_text())
    assert review['execution_authorized'] is True
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'linux-probe-result.json').exists()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT / '.aeep/live-review-v3/.aeep/assessments')
    repo = service.repository
    result = {'source_digest': review['source_digest'], 'model_turns': 0, 'full_conformance': False, 'workers': {}}
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        for role, value in zip(('availability', 'denial'), review['requests'], strict=True):
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
            operation = 'linux-task-probe:' + request.plan_id
            repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=45), stage='worker_inspection')
            started = time.monotonic()
            adapter = None
            facts = {'request_id': request.plan_id, 'operation_id': operation, 'image': worker.image,
                'worker_digest': worker.digest(), 'cleanup_confirmed': False, 'protocol_passed': False,
                'cpu_seconds': None, 'peak_memory_mb': None, 'accounting_complete': False}
            try:
                async with asyncio.timeout(25):
                    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=router.store.host_principal_key())
                    repo.authorize(request)
                    await command(adapter, 'import json;print(json.dumps({"ready":True}))', timeout_ms=5000)
                    if role == 'denial':
                        import base64
                        await worker.artifact(adapter._worker_process_id or '', name='private-state.json', limit=1024, data=base64.b64encode(b'aeep-public-canary-v1').decode(), timeout=5)
                    observed = await command(adapter, review['definition']['programs'][role], timeout_ms=15000)
                    if role == 'denial':
                        witness = await worker.artifact(adapter._worker_process_id or '', name='private-state.json', limit=1024, timeout=5)
                        observed['canary_unchanged'] = witness['sha256'] == hashlib.sha256(b'aeep-public-canary-v1').hexdigest()
                    facts['observed'] = observed
                    facts['protocol_passed'] = all(observed.get(k) == v for k, v in review['definition']['expected'][role].items())
            except Exception as exc:
                facts['error_type'] = type(exc).__name__
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
        result['probe_supported'] = len(result['workers']) == 2 and all(f['protocol_passed'] and f['cleanup_confirmed'] for f in result['workers'].values())
    finally:
        result['classification'] = ('supported_denial_observed' if result.get('probe_supported') else 'unsupported_or_denial_failed')
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        (OUT / 'linux-probe-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))
        await router.close()


asyncio.run(main())
