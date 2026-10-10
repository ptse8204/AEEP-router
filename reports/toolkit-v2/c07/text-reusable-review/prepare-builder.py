"""Freeze one training-only construction call using the existing reviewed service."""
import asyncio, hashlib, json
from pathlib import Path
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentPlan, AssessmentScopeAmendment, ReviewedMapping, content_digest
from aeep.assessment.planning import prepare_reusable
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.qualification import behavior_fingerprint
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
CANONICAL=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
 assert not (OUT/'builder-review.json').exists()
 pair=json.loads((OUT/'pair-review.json').read_text()); boundary=json.loads((OUT/'boundary-result.json').read_text())
 source=verification_source_digest(ROOT); assert source==pair['source_digest']==boundary['source_digest']
 router=Router.from_manifest(CANONICAL/'aeep.json');service=AssessmentService(router,CANONICAL/'.aeep/assessments');repo=service.repository
 try:
  plan=AssessmentPlan.model_validate(repo.get('plan','plan_1eed14b65d3741bca8b92d99edfa63fe'))
  mapping=ReviewedMapping.model_validate(repo.get('mapping',plan.mapping_digest));router.register(mapping.baseline)
  planner=ExecutorSpec.model_validate(pair['definitions'][pair['pair_definition_digest']]['control']);router.register(planner)
  env=AssessmentEnvironment(environment_id='toolkit-text-training-builder-'+source[:12],kind='codex_sandbox',identity={'source_digest':source,'purpose':'One candidate-absent construction call; only current qualification training inputs, never holdouts'},conformance_digests={planner.id:boundary['boundaries']['control']['conformance_digest']})
  request=prepare_reusable(service,training_plan_id=plan.plan_id,planner_id=planner.id,environment=env)
  assert behavior_fingerprint(request.planner)==behavior_fingerprint(planner)
  ds=set(request.definition_digests)|{content_digest(request),request.subject_digest}
  definitions={d:json.loads(router.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in ds}
  grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
  amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=sorted(ds))
  review={'authority':'September 25/27 routine exact definition and finite assessment delegation; existing reviewed model and workers only','source_digest':source,'request':request.model_dump(mode='json'),'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'training_plan':plan.plan_id,'training_plan_digest':content_digest(plan),'baseline':mapping.baseline.model_dump(mode='json'),'maximum_model_turns':1,'maximum_call_seconds':request.planner.managed_host_config().timeout_seconds+5,'maximum_cash_usd':0,'generated_source_remains_inert':True,'untrusted_source_execution_authorized':False,'grant_before':list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())}
  (OUT/'builder-review.json').write_text(json.dumps(review,indent=2)+'\n')
  print(json.dumps({'request_id':request.plan_id,'review_sha256':hashlib.sha256((OUT/'builder-review.json').read_bytes()).hexdigest(),'model_calls_started':0}))
 finally:await router.close()
asyncio.run(main())
