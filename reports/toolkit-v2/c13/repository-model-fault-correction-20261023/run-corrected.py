"""Reuse the reviewed development runner with one corrected protected fault."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

from aeep.assessment import extensions
from aeep.assessment.models import AssessmentPlan,RecipeDefinition,content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import deterministic_digest
from aeep.models import ActionRequest,ActionConstraints
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'repository-model-journey-20261022'
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name,value):
    with (HERE/name).open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')


def load_runner():
    spec=importlib.util.spec_from_file_location('reviewed_repository_development_runner',PRIOR/'run-model-journey.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    original=driver.construct
    def construct(proposal,boundary):
        pair,old_recipe,mapping,environment,old_plan,definitions=original(proposal,boundary)
        recipe=RecipeDefinition.model_validate_json((HERE/'corrected-recipe.json').read_text())
        assert recipe.input_schema==old_recipe.input_schema and recipe.output_schema==old_recipe.output_schema and recipe.extension.grader==old_recipe.extension.grader
        definitions.pop(content_digest(old_plan));definitions[content_digest(recipe)]=recipe.model_dump(mode='json')
        value=old_plan.model_dump(mode='json');value.update(recipe_digest=content_digest(recipe),definition_digests=list(definitions))
        plan=AssessmentPlan.model_validate(value);definitions[content_digest(plan)]=plan.model_dump(mode='json')
        return pair,recipe,mapping,environment,plan,definitions
    driver.HERE=HERE;driver.construct=construct
    return driver


def bounded_observation(reply):
    result={'reply_type':type(reply).__name__,'reply_digest':content_digest(reply)}
    if not isinstance(reply,dict):return result
    result['field_names']=sorted(str(k)[:200] for k in reply)[:100]
    result['field_types']={key:type(reply[key]).__name__ for key in ['exit_code','statuses','archive_sha256','python','pytest'] if key in reply}
    for key in ['exit_code','archive_sha256','python','pytest']:
        value=reply.get(key)
        if type(value) in [int,bool] or value is None or isinstance(value,str) and len(value)<=200:result[key]=value
    statuses=reply.get('statuses')
    if isinstance(statuses,dict):
        result['status_count']=len(statuses)
        result['statuses']={key:(value if isinstance(value,str) and len(value)<=100 else {'type':type(value).__name__}) for key,value in list(statuses.items())[:10000] if isinstance(key,str) and len(key)<=2048}
        if len(json.dumps(result).encode())>550000:result.pop('statuses');result['statuses_omitted_size_bound']=True
    return result


async def main():
    assert len(sys.argv)==2 and sha(HERE/'operation-review.json')==sys.argv[1]
    review=json.loads((HERE/'operation-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text());assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert verification_source_digest(ROOT)==review['source_digest']
    for name,digest in review['assets'].items():assert sha(Path(name))==digest
    assert not (HERE/'execution-started.json').exists()
    router=Router.from_manifest(BASE/'aeep.json')
    try:
        repo=AssessmentService(router,BASE/'.aeep/assessments').repository;grant=repo.current_grant('onboarding')
        before=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        assert before[0]+review['maximum_operations']<=grant.limits.max_operations and before[1]+review['maximum_model_turns']<=grant.limits.max_model_turns and before[2]+review['maximum_reserved_seconds']<=grant.limits.max_elapsed_seconds
    finally:await router.close()
    save('execution-started.json',{'review_sha256':sys.argv[1],'grant_before':before,'automatic_retry':False})
    original_invoke=extensions.invoke;observations=[];driver=load_runner();result={'review_sha256':sys.argv[1],'grant_before':before,'development_only':True,'formal_qualification':False,'comparative_usefulness':False,'selection_value':False}
    async def invoke(service,scope,spec,value,**kwargs):
        reply,elapsed=await original_invoke(service,scope,spec,value,**kwargs)
        request=ActionRequest(capability=spec.capability,input=value,constraints=ActionConstraints(allowed_executor_ids=[spec.id]))
        item={'plan_id':scope.plan_id,'stage':kwargs.get('stage'),'action_digest':deterministic_digest({'capability':request.capability,'input':request.input,'constraints':request.constraints}),'operation_seconds':elapsed,**bounded_observation(reply)}
        observations.append(item);save(f'observer-{len(observations):03}.json',item)
        return reply,elapsed
    extensions.invoke=invoke
    try:
        await driver.main();observed=json.loads((HERE/'model-result.json').read_text());result['engineering_journey_completed']=observed['completed'] and observed['proxy_restored_stopped'] and observed['source_unchanged']
    except BaseException as exc:result.update(engineering_journey_completed=False,error_type=type(exc).__name__,error_message=str(exc)[:400])
    finally:
        extensions.invoke=original_invoke
        router=Router.from_manifest(BASE/'aeep.json')
        try:after=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        finally:await router.close()
        result.update(grant_after=after,operations_delta=after[0]-before[0],model_turns_delta=after[1]-before[1],charged_seconds_delta=after[2]-before[2],observer_replies_retained=len(observations),source_unchanged=verification_source_digest(ROOT)==review['source_digest'])
        result['review_counters_within_ceiling']=result['operations_delta']<=review['maximum_operations'] and result['model_turns_delta']<=review['maximum_model_turns'] and result['charged_seconds_delta']<=review['maximum_reserved_seconds'] and before[3]==after[3]
        save('execution-result.json',result);print(json.dumps(result))


if __name__=='__main__':asyncio.run(main())
