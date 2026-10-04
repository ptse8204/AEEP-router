"""Apply the exact operator-reviewed DOCX boundary records, then use the existing verifier."""
import hashlib
import json
import sys
from pathlib import Path
from typing import Any
from pydantic import model_serializer
from aeep.assessment.boundary import BoundaryConformance, DifferentialConformance, require_conformance
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentScopeAmendment, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import ExecutorSpec, StrictModel
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent
class Document(StrictModel):
    value:dict[str,Any]
    @model_serializer(mode='plain')
    def document(self):return self.value

path=OUT/'qualification-boundary-review.json'
if len(sys.argv)!=2 or hashlib.sha256(path.read_bytes()).hexdigest()!=sys.argv[1]:
    raise RuntimeError('exact boundary review hash required')
review=json.loads(path.read_text())
if verification_source_digest(ROOT)!=review['source_digest']:
    raise RuntimeError('source changed')
pair=json.loads((OUT/'pair-review.json').read_text())
if hashlib.sha256((OUT/'root-connectivity-result.json').read_bytes()).hexdigest()!=review['connectivity_result_sha256']:
    raise RuntimeError('connectivity evidence changed')
for req in pair['requests']:verify_dependencies(req['executable_dependencies'])
with (OUT/'boundary-apply-started.json').open('x') as f:
    json.dump({'review_sha256':sys.argv[1]},f)
router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
repo=AssessmentRepository(router.store)
try:
    before=router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
    definitions={}
    needed=set()
    records={}
    for role,item in review['conformance_records'].items():
        record=BoundaryConformance.model_validate(item['document'])
        if content_digest(record)!=item['digest']:raise RuntimeError('record digest differs')
        records[role]=record
        needed.update([item['digest'],record.enforcement_definition_digest,record.effective_policy_digest,record.reviewed_inventory_digest])
    differential=DifferentialConformance.model_validate(review['differential_conformance']['document'])
    if content_digest(differential)!=review['differential_conformance']['digest']:
        raise RuntimeError('differential digest differs')
    needed.add(content_digest(differential))
    for digest in sorted(needed):
        item=review['review_documents'][digest];doc=Document(value=item['document'])
        if content_digest(doc)!=digest:raise RuntimeError('definition changed')
        identity=item['document'].get('conformance_id',digest)
        repo.put(item['kind'],identity,doc);definitions[digest]=item['document']
    pair_definition=pair['definitions'][pair['pair_definition_digest']]
    for role,record in records.items():
        spec=ExecutorSpec.model_validate(pair_definition[role])
        worker=binding_from_config(spec.managed_host_config().managed_worker)
        if worker is None or worker.digest()!=record.worker_digest:raise RuntimeError('worker changed')
        digest=repo.put('worker_binding',worker.digest(),worker);definitions[digest]=worker.model_dump(mode='json')
        for digest in record.probe_digests:
            probe=repo.get('boundary_probe',digest)
            pd=probe['implementation_digest'];definitions[pd]=repo.get('boundary_probe_definition',pd)
        observed=review['connectivity_observations'][role]
        probe=repo.get('boundary_probe',observed['probe_digest'])
        if probe['observed']!={'connected':True} or probe['worker_digest']!=worker.digest():
            raise RuntimeError('connectivity mismatch')
    shared=review['shared_definition_digest']
    definitions[shared]=repo.get('worker_shared_definition',shared)
    source=pair['requests'][0]
    for kind,key in [('subject','subject_digest'),('recipe','recipe_digest'),('environment','environment_digest')]:
        definitions[source[key]]=repo.get(kind,source[key])
    for digest in definitions:
        row=router.store._connection.execute('SELECT revoked FROM assessment_reviews WHERE digest=?',(digest,)).fetchone()
        if row is not None and row[0]:raise RuntimeError('revoked definition cannot be revived')
    previous=AssessmentScopeAmendment.model_validate(pair['amendment'])
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=previous.authorization_digest,
        subject_digests=[source['subject_digest']],recipe_digests=[source['recipe_digest']],
        environment_digests=[source['environment_digest']],reviewed_digests=list(definitions))
    repo.approve_bundle(amendment,definitions)
    verified={}
    for role,record in records.items():
        actual=require_conformance(repo,content_digest(record),source_digest=review['source_digest'],
            worker_digest=record.worker_digest,identity_digest=record.identity_digest)
        verified[role]={'digest':content_digest(actual),'probe_count':len(actual.probe_digests),'verified':True}
    if (differential.control_conformance_digest!=verified['control']['digest']
        or differential.treatment_conformance_digest!=verified['treatment']['digest']
        or differential.definition.model_dump(mode='json')!=pair_definition['differential']):
        raise RuntimeError('differential linkage mismatch')
    after=router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone()
    result={'review_sha256':sys.argv[1],'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'source_digest':review['source_digest'],'scope_amendment':amendment.model_dump(mode='json'),
        'verified_boundaries':verified,'differential_digest':content_digest(differential),
        'differential_linkage_matches':True,'full_plan_differential_verification_pending':True,
        'grant_counters_unchanged':before==after,'model_turns':0,'no_task_or_grader_execution':True,
        'qualification':False,'admission':False}
    with (OUT/'boundary-apply-result.json').open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
finally:router.store.close()
