"""Accounted offline conformance for first-party fixture programs; no model calls."""
import asyncio, hashlib, json, shutil, time
from pathlib import Path
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, RecipeDefinition, content_digest
from aeep.assessment.extensions import prepare, invoke, grader_results
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
 assert not (OUT/'contained-started.json').exists()
 assert shutil.disk_usage(ROOT).free>51*1024**3
 router=Router.from_manifest(BASE/'aeep.json');service=AssessmentService(router,BASE/'.aeep/assessments');repo=service.repository
 result={'evidence_kind':'first_party_recipe_conformance','model_calls':0,'candidate_execution':False,'live_qualification':False,'future_live_seeds_exclude':[7,8]}
 try:
  recipe=RecipeDefinition.model_validate_json((OUT/'recipe.json').read_text());assert recipe.extension
  rd=repo.put('recipe',content_digest(recipe),recipe)
  environment=AssessmentEnvironment(environment_id='toolkit-edit-recipe-offline',kind='container',identity={'purpose':'First-party generator/reference/grader only; no returned code executes'},container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=512)
  scope=prepare(service,subject_id='70d40b19d9dc6e75b61bd9aa3aaabaeec59325bac658f5e28ec3ef3d2733bf05',recipe_id=rd,authorization_id='onboarding',environment=environment,seed=7)
  ds=set(scope.definition_digests)|{scope.subject_digest,content_digest(scope)}
  definitions={d:json.loads(router.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in ds}
  grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
  amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[scope.subject_digest],recipe_digests=[scope.recipe_digest],environment_digests=[scope.environment_digest],reviewed_digests=sorted(ds))
  review={'authority':'September 25/27 exact routine fixture definition and finite assessment delegation; first-party fixtures only','source_digest':verification_source_digest(ROOT),'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'recipe_digest':rd,'scope':scope.model_dump(mode='json'),'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'maximum_operations':3,'maximum_model_turns':0,'maximum_reserved_seconds':60,'cash_usd':0,'returned_python_never_executed':True,'free_bytes':shutil.disk_usage(ROOT).free,'offline_seed':7}
  (OUT/'contained-review.json').write_text(json.dumps(review,indent=2)+'\n')
  repo.approve_bundle(amendment,definitions);repo.authorize(scope)
  (OUT/'contained-started.json').write_text(json.dumps({'request_id':scope.plan_id,'review_sha256':hashlib.sha256((OUT/'contained-review.json').read_bytes()).hexdigest()})+'\n')
  generated,_=await invoke(service,scope,recipe.extension.generator,{'seed':7,'stages':[{'split':'qualification','count':8},{'split':'training','count':28},{'split':'holdout','count':105}]},stage='offline_recipe_check',operation_id=scope.plan_id+':generator')
  cases=generated['cases'];assert len(cases)==141
  reference,_=await invoke(service,scope,recipe.extension.reference,{'inputs':[c['input'] for c in cases]},stage='offline_recipe_check',operation_id=scope.plan_id+':reference')
  assert reference['outputs']==[c['output'] for c in cases]
  examples=[{'input':c['input'],'output':o,'expected':c['output']} for c,o in zip(cases,reference['outputs'],strict=True)]
  examples += [{'input':c['input'],'output':{},'expected':c['output']} for c in cases]
  graded,_=await invoke(service,scope,recipe.extension.grader,{'examples':examples},stage='offline_recipe_check',operation_id=scope.plan_id+':grader')
  decisions=grader_results(graded,recipe.extension,282);assert [v.valid for v in decisions]==[True]*141+[False]*141
  result.update(passed=True,generated_cases=141,reference_agreements=141,accepted_correct_artifacts=141,rejected_empty_artifacts=141,request_id=scope.plan_id,recipe_digest=rd)
 except BaseException as exc:
  result.update(passed=False,error_type=type(exc).__name__)
  raise
 finally:
  result['grant_after']=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
  await router.close();(OUT/'contained-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
asyncio.run(main())
