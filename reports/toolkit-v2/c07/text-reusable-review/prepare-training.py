"""Prepare an inert training-only comparison for exact generated source."""
import asyncio, hashlib, json
from pathlib import Path
from aeep.router import Router
from aeep.models import ExecutorSpec, ExecutorKind, new_id
from aeep.assessment.service import AssessmentService
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.models import AssessmentPlan, AssessmentEnvironment, AssessmentAuthorization, AssessmentScopeAmendment, content_digest
from aeep.assessment.planning import ReusableBuildOutput
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
 assert not (OUT/'training-review.json').exists()
 r=Router.from_manifest(BASE/'aeep.json');s=AssessmentService(r,BASE/'.aeep/assessments');repo=s.repository
 try:
  result=json.loads((OUT/'builder-result.json').read_text());assert result['passed'] and result['proxy_restored']
  source=verification_source_digest(ROOT);assert source==result['source_digest']
  built=ReusableBuildOutput.model_validate(repo.get('reusable_build_output',result['operation_id']))
  assert built.source==(OUT/'generated-source.py.txt').read_text()
  origin=AssessmentPlan.model_validate(repo.get('plan','plan_1eed14b65d3741bca8b92d99edfa63fe'))
  training=[c for c in origin.suite.cases if c.split.value=='training'];assert len(training)==28
  assert [content_digest(c.action.input) for c in training]==built.training_input_digests
  subject=s.inspect_local(OUT/'generated-source.py.txt',kind='command')
  baseline=reference_spec('text').model_copy(update={'id':'toolkit-text-generated-training.reference'})
  candidate=ExecutorSpec(id='toolkit-text-generated-training.generated',capability=baseline.capability,kind=ExecutorKind.COMMAND,description='Exact generated reusable tool; training only',input_schema=baseline.input_schema,output_schema=baseline.output_schema,config={'argv':['python3','-c',built.source],'argv_literal':True,'stdin_json':True,'timeout_seconds':30,'max_output_bytes':1000000,'output':{'type':'json'}})
  candidate.estimate.cash=baseline.estimate.cash.model_copy(deep=True)
  r.register(candidate);r.register(baseline)
  env=AssessmentEnvironment(environment_id='toolkit-generated-text-training-offline',kind='container',identity={'purpose':'Only frozen training inputs; generated source has not been executed'},container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=512)
  proposal=s.propose(subject_id=subject.subject_id,family='text',candidate_id=candidate.id,baseline_id=baseline.id,authorization_id='onboarding',environment=env,seed=2026101001,structure='direct')
  plan=proposal.model_copy(update={'plan_id':new_id('plan'),'suite':proposal.suite.model_copy(update={'cases':training,'suite_id':new_id('training_suite')}),'planning_request_ids':[built.request_id],'applicability':origin.applicability,'feature_combinations':origin.feature_combinations})
  plan=AssessmentPlan.model_validate(plan.model_dump(mode='json'));repo.put('plan',plan.plan_id,plan)
  ds=set(plan.definition_digests)|{plan.subject_digest,content_digest(plan)}
  definitions={d:json.loads(r.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in ds}
  grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
  amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],reviewed_digests=sorted(ds))
  review={'authority':'Preparation only under standing definition delegation; new generated-source execution requires explicit operator approval','source_digest':source,'source_sha256':result['source_sha256'],'build_operation_id':built.operation_id,'training_input_digests':built.training_input_digests,'inert_full_proposal_id':proposal.plan_id,'plan':plan.model_dump(mode='json'),'amendment':amendment.model_dump(mode='json'),'definitions':definitions,'budget_preview':s.budget_preview(plan.plan_id),'review_findings':['Read entire source: json/sys only, stdin/stdout; no filesystem, network, subprocess, eval or dynamic import.','Semantic differences remain: bare requested labels are ignored and both leading/trailing spaces/tabs are stripped; the independent reference has different rules. Do not edit the tool or grader to improve results.','Only original training inputs are dispatched; held-out cases and expected outputs remain outside candidate containers. Training accuracy may be imperfect; later reusable arm keeps tool use optional.'],'qualification':False,'generated_code_executed':False}
  (OUT/'training-review.json').write_text(json.dumps(review,indent=2)+'\n')
  print(json.dumps({'plan_id':plan.plan_id,'blocked_reasons':plan.blocked_reasons,'campaign_allowance':review['budget_preview']['campaign_allowance']}))
 finally:await r.close()
asyncio.run(main())
