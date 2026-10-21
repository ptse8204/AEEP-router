"""Review observed task boundaries through existing contracts; no worker/model starts."""
import hashlib
import json
from pathlib import Path

from pydantic import model_serializer

from aeep.assessment.boundary import BoundaryConformance, DifferentialConformance, require_candidate_access, require_conformance
from aeep.assessment.models import AssessmentScopeAmendment, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection, expected_probes, observations
from aeep.hosts.workers import binding_from_config
from aeep.models import StrictModel
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4]; OUT=Path(__file__).parent
class Document(StrictModel):
    value:dict
    @model_serializer(mode='plain')
    def document(self):return self.value

pair_review=json.loads((OUT/'collector-definitions.json').read_text())
result=json.loads((OUT/'collector-result.json').read_text())
source=verification_source_digest(ROOT)
assert source==pair_review['source_digest']==result['source_digest']
assert result['passed'] and result['proxy_restored_stopped'] and result['source_unchanged']
assert not (OUT/'boundary-review-v3.json').exists()
pair=WorkerPairInspection.model_validate(pair_review['definitions'][pair_review['pair_definition_digest']])
router=Router.from_manifest(Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json'))
repo=AssessmentRepository(router.store)
try:
    before=tuple(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone())
    documents={};records={};workers={};definitions=dict(pair_review['definitions'])
    for role in ('control','treatment'):
        spec=getattr(pair,role);config=spec.managed_host_config();worker=binding_from_config(config.managed_worker);assert worker
        item=result['pair']['workers'][role];actual=repo.get('worker_pair_inspection',item['record_digest']);facts=actual['observations']
        telemetry=result['telemetry_boundary_observations'][worker.digest()]
        assert telemetry['collector_connection_denied'] is True and facts['inspection']['collector_boundary']==telemetry
        assert observations(pair,role,worker,facts)==expected_probes(pair,role)
        probes={repo.get('boundary_probe',d)['name']:d for d in item['probe_digests']}
        assert set(probes)==set(expected_probes(pair,role)) and len(probes)==11
        inventory=getattr(pair.differential,role+'_inventory')
        policy={'source_digest':source,'worker_digest':worker.digest(),'configuration_digest':worker.configuration_digest,
            'identity_digest':facts['inspection']['identity_digest'],'executor':spec.model_dump(mode='json'),
            'active_policy':facts['active_policy'],'inventory_digest':content_digest(inventory),
            'configuration_probe':probes['configuration'],'candidate_access_probe':probes['candidate_access']}
        enforcement={'source_digest':source,'worker_digest':worker.digest(),
            'inspection_record_digest':item['record_digest'],'probe_digests':probes,
            'implementation_sha256':{p:hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in (
                'src/aeep/hosts/workers.py','src/aeep/hosts/codex_pair_inspection.py',
                'src/aeep/hosts/codex_app_server.py','src/aeep/hosts/codex_invocation.py',
                'src/aeep/assessment/boundary.py')},
            'review':'Immutable reviewed worker and native thread policy; observed workspace writes, credential canary denial, absent other worker/answers, network denial, resource limits, exact candidate difference and cleanup. Catalog visibility is not containment.',
            'limits':['11 bounded active-thread probes do not establish task correctness or benefit.','Full model tool inventory and task-level usage are not inferred.','The unchanged binary/configuration has historical connectivity evidence; the new image has no current task outcome before its public diagnostic.']}
        enforcement['collector_boundary']=telemetry
        enforcement['collector_result_sha256']=hashlib.sha256((OUT/'collector-result.json').read_bytes()).hexdigest()
        record=BoundaryConformance(schema_version='assessment.boundary-conformance.v2',
            conformance_id='toolkit-capture-policy-repair-20261021-'+role+'-'+source[:12],source_digest=source,
            worker_digest=worker.digest(),image_digest=worker.image,binary_digest=worker.binary_sha256,
            adapter=config.adapter_id,adapter_version='1',effective_policy_digest=content_digest(policy),
            reviewed_inventory_digest=content_digest(inventory),identity_digest=facts['inspection']['identity_digest'],
            enforcement_definition_digest=content_digest(enforcement),advertised_tools=[],permitted_tools=[],used_tools=[],
            probe_digests=list(probes.values()),configuration_digest=worker.configuration_digest,effective_inventory=inventory)
        records[role]=record;workers[role]=worker
        for kind,value in [('effective_policy_definition',policy),('enforcement_definition',enforcement),
                           ('reviewed_inventory',inventory),('boundary_conformance',record.model_dump(mode='json'))]:
            documents[content_digest(value)]={'kind':kind,'document':value}
        for d in probes.values():
            impl=repo.get('boundary_probe',d)['implementation_digest'];definitions[impl]=repo.get('boundary_probe_definition',impl)
    differential=DifferentialConformance(definition=pair.differential,
        control_conformance_digest=content_digest(records['control']),treatment_conformance_digest=content_digest(records['treatment']))
    documents[content_digest(differential)]={'kind':'differential_conformance','document':differential.model_dump(mode='json')}
    shared=pair.differential.shared_definition_digest
    definitions[shared]=repo.get('shared_environment_definition',shared)
    for role,worker in workers.items():
        documents[content_digest(worker)]={'kind':'worker_binding','id':worker.digest(),'document':worker.model_dump(mode='json')}
    definitions.update({d:item['document'] for d,item in documents.items()})
    previous=AssessmentScopeAmendment.model_validate(pair_review['amendment'])
    amendment=AssessmentScopeAmendment(authorization_id=previous.authorization_id,authorization_digest=previous.authorization_digest,subject_digests=previous.subject_digests,recipe_digests=previous.recipe_digests,environment_digests=previous.environment_digests,reviewed_digests=list(definitions))
    review={'authority':'September25/27 delegated exact routine definition review; continuous Toolkit instruction',
        'source_digest':source,'pair_review_sha256':hashlib.sha256((OUT/'collector-definitions.json').read_bytes()).hexdigest(),
        'pair_result_sha256':hashlib.sha256((OUT/'collector-result.json').read_bytes()).hexdigest(),
        'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'documents':documents,'definitions':definitions,'amendment':amendment.model_dump(mode='json'),
        'model_turns':0,'qualification':False,'admission':False}
    raw=json.dumps(review,indent=2)+'\n';(OUT/'boundary-review-v3.json').write_text(raw)
    for d,item in documents.items():
        value=Document(value=item['document']);assert content_digest(value)==d
        repo.put(item['kind'],item.get('id',item['document'].get('conformance_id',d)),value)
    repo.approve_bundle(amendment,definitions)
    verified={}
    for role,record in records.items():
        checked=require_conformance(repo,content_digest(record),source_digest=source,worker_digest=record.worker_digest,identity_digest=record.identity_digest)
        require_candidate_access(repo,checked,pair.differential,available=role=='treatment')
        verified[role]={'conformance_digest':content_digest(checked),'worker_digest':record.worker_digest,
            'identity_digest':record.identity_digest,'verified_probe_count':len(checked.probe_digests)}
    after=tuple(router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone());assert before==after
    output={'review_sha256':hashlib.sha256(raw.encode()).hexdigest(),'source_digest':source,
        'boundaries':verified,'differential_conformance_digest':content_digest(differential),
        'grant_counters_unchanged':True,'qualification':False,'admission':False,'plan_differential_check_pending':True}
    (OUT/'boundary-result.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output))
finally:router.store.close()
