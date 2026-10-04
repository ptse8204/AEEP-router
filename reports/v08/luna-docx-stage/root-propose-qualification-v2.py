"""One inert ordinary proposal; no approval, reservation or task execution."""
import asyncio,hashlib,json
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentEnvironment,IncrementalExperiment,AssessmentScopeAmendment,AssessmentAuthorization,content_digest
from aeep.assessment.boundary import require_managed_boundaries,require_differential
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='eaad5bc7b30f3671284b1d7291a4483ff0d87399c2ea13a298be4006bc717ee1'
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 with (OUT/'root-proposal-v2-started.json').open('x') as f:json.dump({'source_digest':SOURCE},f)
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
 try:
  review=json.loads((OUT/'root-final-materialization-review.json').read_text());result=json.loads((OUT/'root-final-materialization-result.json').read_text());assert result['materialization_passed']
  pr=json.loads((OUT/'pair-review.json').read_text());pair=q.get('worker_pair_definition',pr['pair_definition_digest'])
  specs=[ExecutorSpec.model_validate(pair[role]) for role in ('control','treatment')]
  for spec in specs:r.register(spec)
  env=AssessmentEnvironment.model_validate(q.get('environment',review['request']['environment_digest']))
  prior=AssessmentPlan.model_validate(q.get('plan','f9e91a1c34bb4c93ca5a8cbfeed9b5c1408837ef4840e84c3d03c59c40891f6e'))
  costs=json.loads((OUT/'root-preparation-costs.json').read_text())
  experiment=IncrementalExperiment(stage='qualification',exposure='required',environment=pair['differential'],utility=prior.comparison.experiment.utility,reusable_build_operation_ids=[x['operation_id'] for x in costs['operations']])
  plan=s.propose(subject_id=review['request']['subject_digest'],family=review['request']['recipe_digest'],candidate_id=specs[1].id,baseline_id=specs[0].id,authorization_id='onboarding',environment=env,seed=2026100203,structure='controlled_agent',case_set_id=result['case_set_digest'],experiment=experiment)
  identities={spec.id:q.get('boundary_conformance',env.conformance_digests[spec.id])['identity_digest'] for spec in specs}
  require_managed_boundaries(q,env,specs,identities);require_differential(q,env,plan)
  r.managed_hosts.configure(specs,principal_salt=r.store.host_principal_key,manifest_directory=r.manifest_path.parent)
  preview=s.budget_preview(plan.plan_id)
  digests=set(plan.definition_digests)|{content_digest(plan),plan.subject_digest}
  definitions={d:json.loads(r.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in digests}
  grant=AssessmentAuthorization.model_validate(q.get('authorization','onboarding'))
  amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],reviewed_digests=sorted(digests))
  summary={'authority':'September25/27 delegated finite exact assessment review','source_digest':SOURCE,'runner_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'plan_id':plan.plan_id,'plan_digest':content_digest(plan),'environment_digest':plan.environment_digest,'case_set_digest':plan.recipe_case_set_digest,'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'budget_preview':preview,'blocked_reasons':plan.blocked_reasons,'boundaries_and_differential_verified':True,'not_enqueued':True,'qualification':False,'admission':False,'utility':experiment.utility.model_dump(mode='json'),'prior_proposal_attempt':'No plan created; extra campaign_path rejected before propose; retained as wrapper preparation failure'}
  (OUT/'root-qualification-review.json').write_text(json.dumps(summary,indent=2)+'\n')
  print(json.dumps({k:v for k,v in summary.items() if k not in ('definitions','amendment','budget_preview')}));print(json.dumps(preview['campaign_allowance']['upper_allowance']));print(json.dumps(preview['campaign_allowance']['gaps']))
 finally:await r.close()
asyncio.run(main())
