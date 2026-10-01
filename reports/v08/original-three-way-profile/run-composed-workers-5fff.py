"""Exact reviewed declaration-only worker inspection; no task handler or model turn."""
import asyncio, hashlib, importlib.util, json, sys
from pathlib import Path
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.models import Manifest, StrictModel
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).parent
SOURCE = '5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'

class DynamicDefinition(StrictModel):
    namespace: str
    tools: list[dict]
    identity: dict
    max_calls: int
    timeout_seconds: float

async def forbidden_call(name, arguments):
    raise ConfigurationError('declaration inspection has no task invocation authority')

async def main(review_sha):
    review_path = OUT/'composed-workers-5fff-exact-review.json'
    assert file_digest(review_path) == review_sha
    review = json.loads(review_path.read_text())
    assert review['execution_authorized'] and verification_source_digest(ROOT) == SOURCE
    verify_dependencies(review['dependencies'])
    assert review['dependencies'][str(Path(__file__).resolve())] == file_digest(Path(__file__))
    validated = json.loads((ROOT/'reports/v08/delivery-boundary-validation-5fffda8a3210.json').read_text())
    assert validated['complete'] and validated['release_ready'] and validated['source_digest'] == SOURCE
    assert len(validated['checks']) == 22 and all(x['exit_code'] == 0 and x['source_unchanged'] for x in validated['checks'])
    bundle_path = OUT/'composed-workers-5fff-assembly.json'
    assert file_digest(bundle_path) == review['bundle_sha256']
    bundle = json.loads(bundle_path.read_text())
    result_path = OUT/'composed-workers-5fff-result.json'
    assert not result_path.exists()
    collector_path = OUT/'collect-composed-workers-5fff.py'
    assert review['dependencies'][str(collector_path.resolve())] == file_digest(collector_path)
    native_manifest_path = Path(review['native_manifest']).resolve()
    assert review['dependencies'][str(native_manifest_path)] == file_digest(native_manifest_path)
    module_spec = importlib.util.spec_from_file_location('reviewed_composed_worker_collector', collector_path)
    collector = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(collector)
    component = collector.WorkerComponentDefinition.model_validate(bundle['component'])
    assert content_digest(component) == bundle['component_digest'] and bundle['source_digest'] == SOURCE
    router = Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
    service = AssessmentService(router, ROOT/'.aeep/live-review-v3')
    repo = service.repository
    def register(kind, identifier, value):
        digest = content_digest(value)
        with repo.store._lock:
            row = repo.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)).fetchone()
        if row is not None and row[0]:
            raise ConfigurationError('existing exact definition review revoked')
        repo.review(repo.put(kind, identifier, value))
    try:
        bindings = []
        for role in ('control', 'treatment'):
            selected = getattr(component, role)
            worker = collector.binding_from_config(selected.managed_host_config().managed_worker)
            digest = component.composed.callback_bindings[worker.digest()]
            document = DynamicDefinition.model_validate(bundle['callbacks'][digest])
            assert content_digest(document) == digest
            register('codex_dynamic_tools', digest, document)
            def current(document=document, digest=digest, worker=worker, selected=selected):
                verify_dependencies(review['dependencies'])
                if verification_source_digest(ROOT) != SOURCE:
                    raise ConfigurationError('declaration source changed')
                with repo.store._lock:
                    row = repo.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)).fetchone()
                if row is None or row[0] or repo.get('codex_dynamic_tools', digest) != document.model_dump(mode='json'):
                    raise ConfigurationError('declaration review absent or changed')
                identity = document.identity
                if identity['worker_digest'] != worker.digest() or identity['implementation_digest'] != CodexDynamicTools.implementation_digest():
                    raise ConfigurationError('actual declaration worker/implementation changed')
                if identity['artifact'] != selected.managed_host_config().artifact.model_dump(mode='json'):
                    raise ConfigurationError('declaration artifact changed')
                if review['dependencies'][str(native_manifest_path)] != file_digest(native_manifest_path):
                    raise ConfigurationError('protected native manifest changed')
                native_manifest = Manifest.model_validate_json(native_manifest_path.read_text())
                specs = {spec.id: spec for spec in native_manifest.executors if spec.id in identity['executor_fingerprints']}
                if {name: executor_fingerprint(spec) for name, spec in specs.items()} != identity['executor_fingerprints']:
                    raise ConfigurationError('protected native executor changed')
                backends = {}
                for name, spec in specs.items():
                    native = NativeSandboxConfig.model_validate(spec.config['native_sandbox'])
                    native.validate_single_process(); native.argv([])
                    backends[name] = native_backend_digest(native)
                if contract_digest(backends) != identity['native_backend_digest']:
                    raise ConfigurationError('protected native backend changed')
                return digest
            binding = CodexDynamicTools(**document.model_dump(), call=forbidden_call, check=current)
            current(); bindings.append(binding)
        register('composed_pair_definition', content_digest(component.composed), component.composed)
        register('composed_worker_component', content_digest(component), component)
        for digest, value in bundle['probe_definitions'].items():
            probe = BoundaryProbeDefinition.model_validate(value)
            assert content_digest(probe) == digest
            register('boundary_probe_definition', digest, probe)
        requests = [ConformanceProbeRequest.model_validate(value) for value in bundle['requests']]
        for request in requests:
            register('conformance_request', request.plan_id, request)
        collector.authorize_component(service, *[r.plan_id for r in requests], tuple(bindings))
        result = await collector.execute_composed_workers(service, *[r.plan_id for r in requests], bindings=tuple(bindings))
        result['declaration_only'] = True
        result['task_calls'] = 0
        result['model_exposure'] = 'unobserved'
        result_path.write_text(json.dumps(result, indent=2)+'\n')
    except BaseException as exc:
        result_path.write_text(json.dumps({'error_type': type(exc).__name__,
            'error_sha256': hashlib.sha256(str(exc).encode()).hexdigest(),
            'request_ids': [r['plan_id'] for r in bundle['requests']],
            'classification': 'Declaration inspection failed; canonical partial records/operations retained.',
            'full_conformance': False, 'replay_allowed': False}, indent=2)+'\n')
        raise
    finally:
        await router.close()

if __name__ == '__main__':
    if len(sys.argv) != 3 or sys.argv[1] != '--execute-reviewed':
        raise SystemExit('INERT: exact review required')
    asyncio.run(main(sys.argv[2]))
