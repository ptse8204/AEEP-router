"""Prepare exact current-source collector definitions; no worker, listener or model starts."""
import hashlib
import json
from pathlib import Path

from pydantic import model_serializer

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, ConformanceProbeRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection, prepare_pair
from aeep.hosts.codex_metrics import WORKER_PATH
from aeep.hosts.workers import binding_from_config
from aeep.router import Router
from aeep.models import StrictModel

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


class Document(StrictModel):
    value: dict

    @model_serializer(mode='plain')
    def document(self):
        return self.value


def main():
    assert not (OUT / 'collector-definitions.json').exists()
    source = verification_source_digest(ROOT)
    images = json.loads((OUT / 'build-result.json').read_text())['images']
    old = json.loads((OUT.parent / 'edit-value-native-20261019/pair-review.json').read_text())
    pair = old['definitions'][old['pair_definition_digest']]
    collector = hashlib.sha256((ROOT / 'src/aeep/hosts/codex_metrics.py').read_bytes()).hexdigest()
    shared = {'kind':'shared_environment_definition', 'previous_shared_definition': pair['differential']['shared_definition_digest'],
              'collector_file': {WORKER_PATH: collector}, 'catalog_metrics': True,
              'source_digest': source, 'purpose':'COPY-only collector repair conformance; no efficacy or release qualification'}
    shared_digest = content_digest(shared)
    pair['differential']['shared_definition_digest'] = shared_digest
    for role in ('control', 'treatment'):
        pair[role]['id'] = 'toolkit-capture-local-parent-20261021.' + role
        cfg = pair[role]['config']
        cfg['managed_worker']['image'] = images[role]['id']
        cfg['adapter_options']['catalog_metrics'] = True
        files = cfg['managed_worker'].get('reviewed_files') or {}
        cfg['managed_worker']['reviewed_files'] = {**files, WORKER_PATH: collector}
        pair['differential'][role + '_inventory']['common_profile'] = shared_digest
        pair['differential'][role + '_inventory']['collector'] = collector
    pair = WorkerPairInspection.model_validate(pair)
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    try:
        prior = repo.get('plan', 'plan_017bce61874c437296c66276e91876d6')
        definitions = {shared_digest: shared}
        repo.put('shared_environment_definition',shared_digest,Document(value=shared))
        runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
        runtime_ref = repo.put('probe_runtime', content_digest(runtime), runtime)
        definitions[runtime_ref] = runtime.model_dump(mode='json')
        sources, environments = [], []
        for role in ('control', 'treatment'):
            spec = getattr(pair, role)
            worker = binding_from_config(spec.managed_host_config().managed_worker)
            env = AssessmentEnvironment(environment_id='toolkit-capture-local-parent-20261021-' + role,
                kind='codex_sandbox', identity={'source_digest':source, 'purpose':'exact local collector boundary check', 'image':worker.image})
            env_ref = repo.put('environment', content_digest(env), env)
            environments.append(env_ref)
            mapping = BoundaryProbeDefinition(name='worker_inspection', executor=spec, expected={})
            mapping_ref = repo.put('boundary_probe_definition', content_digest(mapping), mapping)
            request = ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',
                operation='worker_inspection', subject_digest=prior['subject_digest'], recipe_digest=prior['recipe_digest'],
                mapping_digest=mapping_ref, environment_digest=env_ref, authorization_id='onboarding',
                definition_digests=[prior['subject_digest'], prior['recipe_digest'], env_ref, mapping_ref, runtime_ref],
                worker_digest=worker.digest(), executable_dependencies=runtime.dependencies)
            repo.put('conformance_request', request.plan_id, request)
            sources.append(request.plan_id)
        prepared = prepare_pair(service, *sources, pair)
        for request in prepared['requests']:
            for ref in {*request['definition_digests'], request['subject_digest'], content_digest(request)}:
                if ref not in definitions:
                    definitions[ref] = json.loads(router.store._connection.execute(
                        'SELECT payload_json FROM assessment_records WHERE digest=?', (ref,)).fetchone()[0])
        grant = AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=content_digest(grant),
            subject_digests=[prior['subject_digest']], recipe_digests=[prior['recipe_digest']],
            environment_digests=environments, reviewed_digests=list(definitions))
        result = {'authority':'September25/27 routine inert definition preparation. Execution requires the exact image-repair parent approval; resulting image IDs and definitions are bound before launch.',
            'source_digest':source, 'source_commit':'44bdad98c1a6b2d845c4e084afe07bbf96a0073e', 'pair_definition_digest':prepared['pair_definition_digest'],
            'request_ids':[v['plan_id'] for v in prepared['requests']], 'requests':prepared['requests'],
            'definitions':definitions, 'amendment':amendment.model_dump(mode='json'),
            'maximum_model_turns':0, 'maximum_inspection_operations':2, 'maximum_inspection_seconds':480,
            'maximum_proxy_lifecycle_operations':1, 'maximum_proxy_lifecycle_seconds':600,
            'cash_usd':0, 'workers_started':False, 'scope_applied':False}
        (OUT / 'collector-definitions.json').write_text(json.dumps(result, indent=2)+'\n')
        print(json.dumps({k:result[k] for k in ('source_digest','request_ids','workers_started')}))
    finally:
        router.store.close()


if __name__ == '__main__':
    main()
