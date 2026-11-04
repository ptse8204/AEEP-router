"""Finish only unstarted engine phases under the explicit definition delegation."""
from __future__ import annotations
import argparse,asyncio,hashlib,importlib.util,json,sqlite3,sys,time
from pathlib import Path
import integration as prepared
import run as base
from aeep.models import ResourceVector
from aeep.assessment.models import AssessmentPlan,AssessmentSubject
from run import (AssessmentEnvironment,AssessmentLimits,
 AssessmentScopeAmendment,BenchmarkCase,ActionRequest,ValidationSpec,IncrementalExperiment,
 UtilityPolicy,IntegrationCaseSet,RecipeMaterializationRequest,EngineeringRunReview,
 content_digest,grader_name,verification_source_digest,require_engineering_run,SourcePin,plan_preview)
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];OUT=HERE/'unstarted-engines'
IDENTITY='319d18e4d5fbbebd696f80cebd4cecd39266884f3aed3e7252f6ad049b0e078c'
PARTIAL='plan_f966c3a56138439aa2aedd84cfe511cd'
PARTIAL_REF='a7063c2933cbc35ac03a762cd24c6b323d0036c5a3c325ea46d6f02c90a42b77'
DOCKER=base.DOCKER

def emit(name,value):
 with (OUT/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')

def approve(repository,scopes,extra=()):return base.approve(repository,scopes,extra)

def bind_plan(service,plan,engine):
 repo=service.repository
 review=EngineeringRunReview(plan_digest=content_digest(plan),implementation_source=verification_source_digest(ROOT),
  scope_request_id='stack-engineering-'+plan.plan_id,case_ids=tuple(case.case_id for case in plan.suite.cases),maximum_model_turns=1)
 reference=repo.put('toolkit_engineering_run',content_digest(review),review)
 scope=RecipeMaterializationRequest(plan_id=review.scope_request_id,subject_digest=plan.subject_digest,
  recipe_digest=plan.recipe_digest,mapping_digest=plan.mapping_digest,environment_digest=plan.environment_digest,
  authorization_id='onboarding',definition_digests=[*plan.definition_digests,reference],seed=71)
 repo.put('recipe_materialization_request',scope.plan_id,scope)
 approve(repo,[scope],extra=[('toolkit_engineering_run',review)])
 require_engineering_run(repo,reference,plan=plan,source_digest=review.implementation_source)
 service._verify_dependencies(plan)
 if plan.blocked_reasons or len(plan.suite.routes)!=1 or len(plan.suite.cases)!=1:raise RuntimeError('Unstarted plan is blocked or exceeds its bound')
 emit('plan-'+engine+'.json',plan.model_dump(mode='json'));emit('engineering-'+engine+'.json',review.model_dump(mode='json'))
 return reference

def make_plan(service, pair, recipe, subject, boundary, engine):
    repo = service.repository
    environment = AssessmentEnvironment(environment_id='ase-stack-grader-' + engine,
        kind='container', identity={'source_digest': verification_source_digest(ROOT),
            'purpose': 'One already-exposed engineering task; no qualification or comparison claim'},
        container_image=prepared.GRADER, container_runtime='/usr/local/bin/docker',
        container_socket='/Users/edwintse/.docker/run/docker.sock', memory_mb=512,
        conformance_digests={getattr(pair, role).id: boundary['boundaries'][role]['conformance_digest']
                             for role in ('control', 'treatment')},
        differential_conformance_digest=boundary['differential_conformance_digest'])
    rec_ref = repo.put('recipe', recipe.recipe_id, recipe)
    env_ref = repo.put('environment', content_digest(environment), environment)
    task = prepared.load(HERE / 'task.json')
    public, truth = task['input'], task['truth']
    case = BenchmarkCase(case_id=public['task_id'], split='qualification',
        variation=public['family'], template_family=task['source_repository'].casefold(),
        action=ActionRequest(capability=recipe.capability, input=public),
        validators=[ValidationSpec(kind='callback', config={'name': grader_name(public, truth), 'expected': truth})])
    integration = IntegrationCaseSet(request_id='ase-stack-cases-' + engine, recipe_digest=rec_ref,
        environment_digest=env_ref, benchmark_pack_digest=recipe.dependencies['benchmark_pack'],
        seed=71, cases=[case])
    integration_ref = repo.put('integration_case_set', content_digest(integration), integration)
    repo.review(integration_ref)
    repo.review(rec_ref)
    scheduler = prepared.scheduler() if engine == 'agent-skill-eval' else None
    scheduler_ref = None
    if scheduler is not None:
        scheduler_ref = repo.put('scheduler', content_digest(scheduler), scheduler)
        repo.review(scheduler_ref)
    experiment = IncrementalExperiment(stage='qualification', exposure='required',
        environment=pair.differential,
        utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
    plan = service.propose(subject_id=subject.subject_id, family=recipe.recipe_id,
        candidate_id=pair.treatment.id, baseline_id=pair.control.id, authorization_id='onboarding',
        environment=environment, seed=71, structure='controlled_agent',
        integration_case_set_id=integration_ref, scheduler_digest=scheduler_ref, experiment=experiment)
    return plan

async def main():
 parser=argparse.ArgumentParser();parser.add_argument('--execute-delegated',action='store_true');args=parser.parse_args()
 review=prepared.load(HERE/'operation-review.json');base.require_assets(review)
 amendment=prepared.load(HERE/'unstarted-definition-review.json')
 assert prepared.sha(HERE/'operation-review.json')==IDENTITY
 assert amendment['base_review_sha256']==IDENTITY and amendment['script_sha256']==prepared.sha(Path(__file__))
 assert amendment['authority_quote']==review['routine_unstarted_corrections']
 assert prepared.load(HERE/'operator-approval.json')=={'approved':True,'review_sha256':IDENTITY}
 parent=prepared.load(HERE/'execution-result.json')
 assert parent['error_type']=='ConfigurationError' and parent['error_message']=='assessment record identity is immutable'
 assert not any(parent.get(key) for key in ('cleanup_uncertain','accounting_uncertain','newly_unresolved_operations','interrupted_cli_effects_uncertain'))
 assert not list(HERE.glob('cli-*.json')) and not prepared.SCHEDULER_WORK.exists()
 if not args.execute_delegated:
  print(json.dumps({'passed':True,'execution':False,'scope':'UNSTARTED definitions/engines only','base_review':IDENTITY}));return
 OUT.mkdir(mode=0o700)
 router=base.Router.from_manifest(prepared.WORK/'selected-manifest.json')
 service=base.AssessmentService(router,base.BASE/'.aeep/assessments');repo=service.repository
 anchor=prepared.load(prepared.OLD/'execution-started.json')['grant_before']
 spec=importlib.util.spec_from_file_location('original_review_budget',HERE.parent/'repository-usefulness-pilot-20261029/review-budget.py')
 budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
 old_reserve=budget.install(repo,repo.store._connection,anchor,review)
 before=base.counters(repo);old_reserved={row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'")}
 started=time.perf_counter();nested=0.;wrapper=None;process=None;proxy_started=False
 result={'passed':False,'engines':{},'comparisons':'PAUSED','base_review_sha256':IDENTITY,'grant_before':before}
 try:
  partial=AssessmentPlan.model_validate(repo.get('plan',PARTIAL));assert content_digest(partial)==PARTIAL_REF
  assert not repo.store._connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?',(partial.plan_id,)).fetchone()
  boundary=prepared.load(HERE/'readiness-review.json')
  pair,shared=prepared.pair(review['retained_image_metadata']['Id'],review['source_digest'])
  assert content_digest(pair)==boundary['pair_definition_digest']
  from aeep.assessment.boundary import require_conformance,require_candidate_access
  for role in ('control','treatment'):
   item=boundary['boundaries'][role];observed=require_conformance(repo,item['conformance_digest'],source_digest=review['source_digest'],worker_digest=item['worker_digest'],identity_digest=item['identity_digest'])
   require_candidate_access(repo,observed,pair.differential,available=role=='treatment')
  subject=AssessmentSubject.model_validate(repo.get('subject',partial.subject_digest));recipe=prepared.recipe()
  bootstrap=RecipeMaterializationRequest.model_validate(repo.get('recipe_materialization_request','integration-snapshot-owned-preparation-20261103'))
  setup_before={row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
  wrapper=bootstrap.plan_id+':unstarted-engine-overhead'
  repo.reserve(bootstrap,wrapper,AssessmentLimits(max_operations=1,max_elapsed_seconds=120),stage='owned_proxy_exclusive_overhead')
  emit('started.json',{'base_review_sha256':IDENTITY,'delegation':amendment,'partial_plan_preserved':PARTIAL_REF,'grant_before':before,'anchor':anchor,'workers_replayed':False})
  current=json.loads(base.docker('inspect','--format',review['proxy_inspect_format'],review['proxy_name']));assert current==review['proxy_metadata'] and not current['Running']
  proxy_started=True;base.docker('start',review['proxy_id'])
  active=json.loads(base.docker('inspect','--format',review['proxy_inspect_format'],review['proxy_id']))
  assert active['Running'] and active['Id']==review['proxy_id'] and active['Image']==review['proxy_image'] and active['Networks']['aeep-reviewed-model-private']['IPAddress']=='172.18.0.2'
  source=SourcePin.model_validate(prepared.load(HERE/'source.json'))
  for engine in review['engines']:
   base.require_assets(review)
   plan=partial if engine=='agent-skill-eval' else make_plan(service,pair,recipe,subject,boundary,engine)
   engineering_ref=bind_plan(service,plan,engine)
   preview=service.budget_preview(plan.plan_id);upper=preview['campaign_allowance']['upper_allowance']
   budget.require_room(base.counters(repo),anchor,AssessmentLimits(max_operations=upper['operations'],max_model_turns=upper['model_turns'],max_elapsed_seconds=upper['elapsed_seconds']),review)
   emit('budget-'+engine+'.json',preview)
   assert preview['minimum_trial_model_turns']==1 and preview['campaign_allowance']['fits_remaining']
   assert not repo.store._connection.execute('SELECT 1 FROM assessment_jobs WHERE plan_id=?',(plan.plan_id,)).fetchone()
   argv=[sys.executable,'-B','-m','aeep_toolkit','eval','managed','run','--plan',str(OUT/('plan-'+engine+'.json')),'--source',str(HERE/'source.json'),'--manifest',str(prepared.WORK/'selected-manifest.json'),'--directory',str(service.directory),'--reviewed-digest',plan_preview(plan,source)['review_sha256'],'--engineering-review',engineering_ref,'--output',str(OUT/('result-'+engine))]
   if engine=='agent-skill-eval':argv+=['--scheduler',str(HERE/'scheduler.json')]
   emit('command-'+engine+'.json',{'argv':argv,'automatic_retry':False})
   clock=time.perf_counter()
   try:
    process=await asyncio.create_subprocess_exec(*argv,cwd=ROOT,env={'PATH':'/usr/bin:/bin:/usr/local/bin','PYTHONPATH':str(ROOT/'src'),'PYTHONDONTWRITEBYTECODE':'1'},stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    stdout,stderr=await asyncio.wait_for(process.communicate(),timeout=4200)
   finally:nested+=time.perf_counter()-clock
   emit('cli-'+engine+'.json',{'exit_code':process.returncode,'stdout_sha256':hashlib.sha256(stdout).hexdigest(),'stderr_sha256':hashlib.sha256(stderr).hexdigest()})
   if process.returncode:
    result['model_attempt_unreconciled']=True;raise RuntimeError('CLI stopped; no retry or engine switch')
   from aeep_toolkit.managed import AEEPAssessmentAdapter
   # Reopen canonical completion; normalization starts no worker.
   adapter = AEEPAssessmentAdapter(service, plan.plan_id, source)
   job = adapter.preview()['job']
   if job is None or job['state'] != 'complete' or job['error_code'] is not None:
       raise RuntimeError('Engineering task did not settle completely')
   bundle = adapter.normalize(job['report_id'])
   from aeep.benchmarking import BenchmarkTrial
   evidence_spec = importlib.util.spec_from_file_location('canonical_trial_gate',
       HERE.parent / 'repository-usefulness-pilot-20261029/trial-evidence.py')
   evidence = importlib.util.module_from_spec(evidence_spec)
   evidence_spec.loader.exec_module(evidence)
   expected_rows = prepared.load(HERE / 'task-delivery-controls.json')['checks']
   expected = {(row['case'], row['role']): row['instruction_sha256'] for row in expected_rows}
   campaign_path = service.directory / plan.plan_id / 'campaign.sqlite3'
   with sqlite3.connect(campaign_path.as_uri() + '?mode=ro', uri=True) as connection:
       trial_rows = list(connection.execute('SELECT payload_json FROM trials'))
       if len(trial_rows) != 1:
           raise RuntimeError('Engineering trial positions differ')
       trial = BenchmarkTrial.model_validate_json(trial_rows[0][0])
       trial_evidence = evidence.read_trial(connection, trial, pair, expected,
           service.directory / plan.plan_id / 'attempts')
       evidence.require_complete(trial_evidence)
       emit('trial-evidence-' + engine + '.json', trial_evidence)
   details = adapter.details
   captures = list(details['telemetry_capture'].values())
   if (len(bundle.runs) != 1 or bundle.runs[0].verification not in {'pass', 'fail'}
           or bundle.runs[0].status != 'completed' or bundle.runs[0].retries != 0
           or details['normalization_gaps'] or details['unresolved_operations']
           or len(captures) != 1 or captures[0]['tokens']['status'] != 'verified'
           or captures[0]['candidate']['instructions_loaded'] is not True):
       raise RuntimeError('Task grading, prompt, loading, accounting or token capture is incomplete')
   if engine == 'agent-skill-eval' and details.get('external_scheduler', {}).get('completion') == 'UNKNOWN':
       raise RuntimeError('Canonical upstream scheduler observation is missing')
   result['engines'][engine] = {'report_id': job['report_id'],
       'bundle_ref': content_digest(bundle), 'task_grade': bundle.runs[0].verification, 'details': adapter.details,
       'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED'}

  result['passed']=len(result['engines'])==2
 except BaseException as error:result.update(error_type=type(error).__name__,error_message=str(error)[:300])
 finally:
  try:
   if process is not None and process.returncode is None:
    process.terminate()
    try:await asyncio.wait_for(process.wait(),10)
    except TimeoutError:process.kill();await process.wait()
    result.update(passed=False,interrupted_cli_effects_uncertain=True)
   if proxy_started:
    try:
     base.docker('stop','--time','5',review['proxy_id'])
     result['proxy_restored_stopped']=base.docker('inspect','--format','{{.State.Running}}',review['proxy_id'])=='false'
     if not result['proxy_restored_stopped']:raise RuntimeError('Proxy stop unverified')
    except Exception as error:result.update(passed=False,cleanup_uncertain=True,cleanup_error_type=type(error).__name__)
   if wrapper:
    setup=[(i,json.loads(raw)) for i,raw in repo.store._connection.execute("SELECT id,payload_json FROM assessment_records WHERE kind='setup_cost' AND json_extract(payload_json,'$.subject_digest')=?",(partial.subject_digest,)) if i not in setup_before]
    unbilled=[]
    for i,record in setup:
     state=repo.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(i,)).fetchone()
     if state is None:
      try:
       repo.reserve(bootstrap,i,AssessmentLimits(max_operations=1,max_elapsed_seconds=max(record['elapsed_seconds'],.000001)),stage=record['stage'])
       repo.finish_operation(i,elapsed_seconds=record['elapsed_seconds'],resources=ResourceVector(latency_ms=record['elapsed_seconds']*1000,cpu_ms=record['cpu_ms']))
      except Exception as error:
       unbilled.append(i);result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(error).__name__)
     elif state[0]!='complete':result['accounting_uncertain']=True
    result['unstarted_measured_setup_records']=unbilled
    exclusive=max(0.,time.perf_counter()-started-nested-sum(r['elapsed_seconds'] for _,r in setup))
    if not result.get('cleanup_uncertain'):
     try:repo.finish_operation(wrapper,elapsed_seconds=exclusive)
     except Exception as error:result.update(passed=False,accounting_uncertain=True,accounting_error_type=type(error).__name__)
    result['wrapper_accounting']={'exclusive_seconds':exclusive,'nested_execution_seconds_excluded':nested,'measured_setup_seconds_excluded':sum(r['elapsed_seconds'] for _,r in setup)}
   result['newly_unresolved_operations']=[row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'") if row[0] not in old_reserved]
   if result['newly_unresolved_operations']:result.update(passed=False,accounting_uncertain=True)
   result['grant_after']=base.counters(repo);result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['runtime_unchanged']=prepared.snapshot(prepared.RUNTIME)==review['runtime_tree_sha256']
   emit('result.json',result)
  finally:repo.reserve=old_reserve;await router.close()
 print(json.dumps({k:v for k,v in result.items() if k!='engines'}))
 if not result['passed']:raise SystemExit(1)

if __name__=='__main__':asyncio.run(main())
