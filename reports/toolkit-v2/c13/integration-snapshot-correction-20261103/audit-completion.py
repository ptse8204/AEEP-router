"""Read-only reconciliation; never execute/review/replay a task or change a grant."""
import asyncio,json,sys
from pathlib import Path
import integration as prepared
import run as base
from aeep.assessment.models import AssessmentPlan,RecipeDefinition,content_digest
from aeep_toolkit.models import EvidenceBundle
from aeep_toolkit.telemetry import bound_journal,token_capture,candidate_loading
HERE=Path(__file__).resolve().parent

async def main():
 review=prepared.load(HERE/'operation-review.json');base.require_assets(review)
 router=base.Router.from_manifest(prepared.WORK/'selected-manifest.json')
 try:
  service=base.AssessmentService(router,base.BASE/'.aeep/assessments');repo=service.repository
  before=base.counters(repo);rows=[];plans=[];recipes=[]
  for engine,folder,plan_file in [
   ('agent-skill-eval',HERE/'unstarted-engines/ase-uri-report',HERE/'unstarted-engines/plan-agent-skill-eval.json'),
   ('managed',HERE/'managed-unstarted/result-managed',HERE/'managed-unstarted/plan-managed.json')]:
   plan=AssessmentPlan.model_validate_json(plan_file.read_bytes());plans.append(plan)
   assert content_digest(AssessmentPlan.model_validate(repo.get('plan',plan.plan_id)))==content_digest(plan)
   job=repo.store._connection.execute('SELECT id,state,report_id,error_code FROM assessment_jobs WHERE plan_id=?',(plan.plan_id,)).fetchall()
   assert len(job)==1 and job[0][1]=='complete' and job[0][3] is None
   bundle=EvidenceBundle.model_validate_json((folder/'toolkit-evidence.json').read_bytes());details=prepared.load(folder/'managed-evidence.json')
   assert len(bundle.runs)==1 and not details['normalization_gaps'] and details['canonical_trials']==1 and details['unresolved_operations']==0
   run=bundle.runs[0];assert run.plan_ref==content_digest(plan) and run.verification=='pass' and run.status=='completed' and run.retries==0
   assert run.task_sha256==content_digest(plan.suite.cases[0])
   receipts=prepared.load(folder/'accounting-records.json');assert len(receipts)==1
   from aeep.models import ExecutionReceipt
   receipt=ExecutionReceipt.model_validate(receipts[run.receipt_refs[0]]);assert content_digest(receipt)==run.receipt_refs[0]
   assert receipt.metadata['worker_cleanup_confirmed'] is True
   capture=details['telemetry_capture'][run.run_id]
   assert capture['tokens']['status']=='verified' and capture['candidate']['instructions_loaded'] is True
   assert not capture['tokens']['provider_usage_independently_verified']
   assert capture['candidate']['invoked'] is None
   if engine=='agent-skill-eval':
    observation=repo.get('scheduler_observation',plan.plan_id)
    assert observation==details['external_scheduler'] and len(observation['trial_refs'])==1
    assert list(observation['grade_summaries'].values())[0]=={'passed':1,'failed':0,'total':1,'pass_rate':1.0,'skipped':0}
   else:assert plan.scheduler_digest is None
   recipe=RecipeDefinition.model_validate(repo.get('recipe',plan.recipe_digest));recipes.append(recipe)
   usage=receipt.accounting.model_usage[0]
   rows.append({'engine':engine,'plan_id':plan.plan_id,'plan_ref':content_digest(plan),'canonical_report_id':job[0][2],
    'trial_id':run.run_id,'receipt_ref':content_digest(receipt),'journal_ref':receipt.metadata['execution_evidence_digest'],
    'case_id':plan.suite.cases[0].case_id,'task_score':1,'score_semantics':'Original protected binary pass; one engineering task, not usefulness qualification',
    'input_tokens':usage.input_tokens,'cached_input_tokens':usage.cached_input_tokens,'cache_write_input_tokens':usage.cache_write_input_tokens,
    'output_tokens':usage.output_tokens,'reasoning_output_tokens':usage.reasoning_output_tokens,
    'cached_semantics':'included_in_input','reasoning_semantics':'included_in_output',
    'agent_wall_seconds':run.agent_wall_seconds,'protected_grading_seconds':run.verification_wall_seconds,
    'token_capture':'verified receipt/journal consistency','token_quantities_source':'provider_report/self_asserted; independent provider usage unverified',
    'instructions_loaded':True,'semantic_candidate_invocation':None,'full_catalog_delivery':capture['candidate']['delivery_complete'],
    'worker_cleanup_confirmed':True,'retries':0,'cash_measurement':receipt.accounting.cash.status,
    'canonical_grading_unchanged':True,'report':str((folder/'report.html').resolve()),
    'serialization_adaptation':'URI family key encoded read-only; original plan/trial unchanged' if engine=='agent-skill-eval' else 'Family keys encoded one-to-one before the first trial; default CLI export passed'})
  assert plans[0].suite.cases[0].action.model_dump(mode='json',exclude={'action_id'})==plans[1].suite.cases[0].action.model_dump(mode='json',exclude={'action_id'})
  assert plans[0].suite.cases[0].validators==plans[1].suite.cases[0].validators
  for key in ('generator','reference','grader','fault_outputs','independent_fixtures','transformed_fixtures'):
   assert getattr(recipes[0].extension,key)==getattr(recipes[1].extension,key)
  assert recipes[0].generator_config==recipes[1].generator_config and recipes[0].dependencies==recipes[1].dependencies
  anchor=prepared.load(prepared.OLD/'execution-started.json')['grant_before']
  assert before[1]-anchor[1]==2 and before[0]-anchor[0]<=144 and before[2]-anchor[2]<=6200 and before[3]==anchor[3]
  pending={row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'")}
  original=set(prepared.load(HERE/'execution-started.json')['old_reserved_operations'])
  assert pending==original
  assert base.docker('inspect','--format','{{.State.Running}}',review['proxy_id'])=='false'
  assert prepared.snapshot(prepared.RUNTIME)==review['runtime_tree_sha256']
  assert base.counters(repo)==before
  result={'passed':True,'evidence_kind':'Read-only reconciliation of two existing real executions of ONE public task',
   'rows':rows,'same_task_inputs_and_protected_verifier_bytes':True,'task_families_not_multiplied':True,
   'original_URI_labels_and_failed_exports_preserved':True,'no_new_trials_or_model_calls':True,'source':review['source_digest'],
   'grant_after':before,'original_anchor':anchor,'cumulative_operations':before[0]-anchor[0],'cumulative_model_turns':before[1]-anchor[1],
   'cumulative_grant_elapsed_seconds':before[2]-anchor[2],'original_ceiling_operations':144,'original_ceiling_model_turns':2,'original_ceiling_seconds':6200,
   'two_old_unresolved_reservations_preserved':sorted(pending),'new_unresolved_operations':[],
   'proxy_stopped':True,'retained_SDK_runtime_unchanged':True,'all_images_and_volumes_retained':True,
   'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED','comparisons':'PAUSED',
   'all_stack_complete':False,'both_SkillsBench_journeys_complete':False,'generic_current_stack_evidence_ingestion':'OPEN',
   'scope':'ASE scheduler and graders actually drove controlled dispatch; AEEP separately selected managed execution and ordinary report passed. URI export adaptation is explicit. Neither diagnostic validates capability benefit or general competence.'}
  with (HERE/'completion-audit.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
  print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
 finally:await router.close()

if __name__=='__main__':asyncio.run(main())
