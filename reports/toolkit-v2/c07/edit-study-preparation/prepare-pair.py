"""Prepare actual text qualification worker observations; no worker or model starts."""
import hashlib
import json
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, ConformanceProbeRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection, prepare_pair
from aeep.hosts.workers import binding_from_config
from aeep.models import StrictModel, ExecutorSpec
from aeep.assessment.recipes import shipped_recipe
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).resolve().parent
CANONICAL=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')

class Definition(StrictModel):
    values:dict

assert not (OUT/'pair-review.json').exists()
prior=json.loads((OUT.parent/'text-prompt-schema-review/pair-review.json').read_text())
pair=WorkerPairInspection.model_validate(prior['definitions'][prior['pair_definition_digest']])
from aeep.assessment.models import RecipeDefinition
recipe=RecipeDefinition.model_validate_json((OUT/'recipe.json').read_text())
source=verification_source_digest(ROOT)
router=Router.from_manifest(CANONICAL/'aeep.json');service=AssessmentService(router,CANONICAL/'.aeep/assessments');repo=service.repository
try:
    prior=repo.get('plan','plan_d634949396264514b929eda14e505743')
    mapping=repo.get('mapping',prior['mapping_digest'])
    pair=WorkerPairInspection.model_validate(pair.model_dump(mode='json') | {
        'control':mapping['baseline'], 'treatment':mapping['candidate']})
    for role in ('control','treatment'):
        spec=getattr(pair,role);spec.id='toolkit-edit-qualification.'+role
        spec.capability=recipe.capability;spec.input_schema=recipe.input_schema;spec.output_schema=recipe.output_schema
        spec.config['instructions']=recipe.description+' Return only the requested JSON. Input: {input}'
    subject=service.inspect_local(Path('/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-ponytail-410-source-f1eq_9us/candidate'),kind='skill')
    assert subject.dependency_digests == {'SKILL.md':pair.candidate_skill_digest}
    definitions={}
    def put(kind,value,identity=None):
        d=content_digest(value);repo.put(kind,identity or d,value);definitions[d]=value.model_dump(mode='json');return d
    sd=content_digest(subject);rd=put('recipe',recipe)
    definitions[sd]=repo.get('subject',sd);definitions[rd]=repo.get('recipe',rd)
    runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies());runtime_digest=put('probe_runtime',runtime)
    sources=[];environments=[]
    for role in ('control','treatment'):
        spec=getattr(pair,role);binding=binding_from_config(spec.managed_host_config().managed_worker);assert binding
        env=AssessmentEnvironment(environment_id='toolkit-edit-qualification-'+role,kind='codex_sandbox',identity={'purpose':'Current-source task-profile inspection; exact three-family editing contract and required qualification exposure','source_digest':source,'image':binding.image})
        ed=put('environment',env);environments.append(ed)
        mapping=BoundaryProbeDefinition(name='worker_inspection',executor=spec,expected={});md=put('boundary_probe_definition',mapping)
        request=ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',operation='worker_inspection',subject_digest=sd,recipe_digest=rd,mapping_digest=md,environment_digest=ed,authorization_id='onboarding',definition_digests=[sd,rd,ed,md,runtime_digest],worker_digest=binding.digest(),executable_dependencies=runtime.dependencies)
        put('conformance_request',request,request.plan_id);sources.append(request.plan_id)
    prepared=prepare_pair(service,*sources,pair)
    definitions[prepared['pair_definition_digest']]=pair.model_dump(mode='json')
    requests=[ConformanceProbeRequest.model_validate(v) for v in prepared['requests']]
    for request in requests:
        definitions[content_digest(request)]=request.model_dump(mode='json')
        for d in request.definition_digests:
            if d not in definitions:definitions[d]=repo.get('boundary_probe_definition',d)
    grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[sd],recipe_digests=[rd],environment_digests=environments,reviewed_digests=list(definitions))
    review={'authority':'Standing September25/27 routine exact definition and scope delegation; current continuous toolkit instruction','source_digest':source,'pair_definition_digest':prepared['pair_definition_digest'],'request_ids':[r.plan_id for r in requests],'requests':[r.model_dump(mode='json') for r in requests],'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'maximum_operations':2,'maximum_model_turns':0,'maximum_reserved_seconds':480,'cash_usd':0,'authentication_state_access':False,'full_conformance':False,'scope_applied':False}
    (OUT/'pair-review.json').write_text(json.dumps(review,indent=2)+'\n')
    print(json.dumps({'source_digest':source,'request_ids':review['request_ids'],'workers_started':False}))
finally:router.store.close()
