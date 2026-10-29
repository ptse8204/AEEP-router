"""Prepare a small real-repository development journey; start no worker or model."""
import hashlib
import json
from pathlib import Path

from pydantic import model_serializer
from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, ConformanceProbeRequest, RecipeRuntimeBinding, RecipeDefinition, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_metrics import WORKER_PATH
from aeep.hosts.codex_pair_inspection import WorkerPairInspection, prepare_pair
from aeep.hosts.workers import binding_from_config
from aeep.models import StrictModel
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
PRIOR=HERE.parent.parent/'c07/capture-explicit-profile-20261021'


class Document(StrictModel):
    value:dict
    @model_serializer(mode='plain')
    def document(self):return self.value


def main():
    assert not (HERE/'collector-definitions.json').exists()
    source=verification_source_digest(ROOT)
    old=json.loads((PRIOR/'collector-definitions.json').read_text());pair=old['definitions'][old['pair_definition_digest']]
    recipe=RecipeDefinition.model_validate(json.loads((HERE/'recipe.json').read_text()))
    cases=recipe.generator_config['cases'];assert len(cases)==6 and all(c['split']=='development' and c['used_for_development'] for c in cases)
    public_roots=sorted({str(Path(c['truth']['source']['path']).parent) for c in cases})
    assert len(public_roots)==1 and public_roots[0].endswith('/public')
    artifact={'input_field':'source_b64','output_field':'patch_gzip_b64','input_name':'repository.tar.gz','output_name':'patch.json.gz','max_bytes':650000}
    instructions=('Complete the repository maintenance task using the tools available in your isolated workspace. Read the current task,unpack the supplied repository.tar.gz into that workspace,and inspect the relevant Python source. Use optional capabilities only when useful. Do not install software or access external services. Only change listed existing editable Python files; preserve omitted files. Write the output artifact as gzip-compressed UTF-8 JSON with exactly base_sha256(the supplied canonical hash) and files(a mapping of changed existing paths to full replacement text). An empty files mapping is valid when no change is needed. The output path is supplied by the host. Do not put base64 bytes in the final answer. Independent protected tests run outside your workspace; report completion after writing the artifact.')
    instructions += '\nCurrent task JSON and bound artifact paths:\n{input}'
    shared={'kind':'shared_environment_definition','previous_shared_definition':pair['differential']['shared_definition_digest'],
        'purpose':'6 unstarted tasks from the original21-slot development experiment;other started cases remain engineering-censored. No formal qualification,holdout,value verdict,admission or selection claim.',
        'source_digest':source,'artifact':artifact,'assessment_adapter':{'input_transform':'repository_archive:1','read_only_roots':public_roots},
        'collector_file':{WORKER_PATH:hashlib.sha256((ROOT/'src/aeep/hosts/codex_metrics.py').read_bytes()).hexdigest()},
        'recipe_digest':content_digest(recipe),'instructions_sha256':hashlib.sha256(instructions.encode()).hexdigest()}
    shared_digest=content_digest(shared);pair['differential']['shared_definition_digest']=shared_digest
    for role in ('control','treatment'):
        spec=pair[role];spec['id']='toolkit-repository-usefulness-gzip-20261029.'+role;spec['capability']=recipe.capability;spec['input_schema']=recipe.input_schema;spec['output_schema']=recipe.output_schema
        cfg=spec['config'];cfg['instructions']=instructions;cfg['timeout_seconds']=300;cfg['artifact']=artifact;cfg['assessment_adapter']=shared['assessment_adapter']
        if role=='treatment':cfg['invocation']['exposure']='optional'
        pair['differential'][role+'_inventory']['common_profile']=shared_digest
    pair=WorkerPairInspection.model_validate(pair)
    router=Router.from_manifest(BASE/'aeep.json');service=AssessmentService(router,BASE/'.aeep/assessments');repo=service.repository
    try:
        before=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        prior=repo.get('plan','plan_017bce61874c437296c66276e91876d6')
        repo.put('recipe',recipe.recipe_id,recipe)
        definitions={shared_digest:shared,content_digest(recipe):recipe.model_dump(mode='json')};repo.put('shared_environment_definition',shared_digest,Document(value=shared))
        runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies());runtime_ref=repo.put('probe_runtime',content_digest(runtime),runtime);definitions[runtime_ref]=runtime.model_dump(mode='json')
        sources=[];environments=[]
        for role in ('control','treatment'):
            spec=getattr(pair,role);worker=binding_from_config(spec.managed_host_config().managed_worker)
            environment=AssessmentEnvironment(environment_id='toolkit-repository-usefulness-gzip-20261029-'+role,kind='codex_sandbox',identity={'source_digest':source,'purpose':'repository development artifact profile inspection','image':worker.image})
            env_ref=repo.put('environment',content_digest(environment),environment);environments.append(env_ref)
            mapping=BoundaryProbeDefinition(name='worker_inspection',executor=spec,expected={});mapping_ref=repo.put('boundary_probe_definition',content_digest(mapping),mapping)
            request=ConformanceProbeRequest(schema_version='assessment.conformance-request.v2',operation='worker_inspection',subject_digest=prior['subject_digest'],recipe_digest=content_digest(recipe),mapping_digest=mapping_ref,environment_digest=env_ref,authorization_id='onboarding',definition_digests=[prior['subject_digest'],content_digest(recipe),env_ref,mapping_ref,runtime_ref],worker_digest=worker.digest(),executable_dependencies=runtime.dependencies)
            repo.put('conformance_request',request.plan_id,request);sources.append(request.plan_id)
        prepared=prepare_pair(service,*sources,pair)
        for request in prepared['requests']:
            for digest in {*request['definition_digests'],request['subject_digest'],content_digest(request)}:
                if digest not in definitions:definitions[digest]=json.loads(router.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(digest,)).fetchone()[0])
        grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[prior['subject_digest']],recipe_digests=[content_digest(recipe)],environment_digests=environments,reviewed_digests=list(definitions))
        after=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone());assert before==after
        result={'authority':'Standing finite definition preparation only; no actual execution authority.','source_digest':source,'source_commit':'591ef4d','pair_definition_digest':prepared['pair_definition_digest'],'requests':prepared['requests'],'request_ids':[r['plan_id'] for r in prepared['requests']],'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'maximum_inspection_operations':2,'maximum_inspection_seconds':480,'model_turns':0,'workers_started':False,'scope_applied':False,'grant_before':before,'grant_after':after,'intended_followup':'A separate exact review must cover fresh current-source pair/collector isolation and a gated maximum42-turn optional-candidate development comparison. This is not a frozen full study or qualification.'}
        (HERE/'collector-definitions.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'pair_definition_digest':prepared['pair_definition_digest'],'source_digest':source,'requests':result['request_ids'],'grant_unchanged':True,'model_calls':0,'workers_started':False}))
    finally:router.store.close()


if __name__=='__main__':main()
