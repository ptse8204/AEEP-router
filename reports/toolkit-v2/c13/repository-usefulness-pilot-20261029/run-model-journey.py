"""At most42 development turns with per-trial evidence checks."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sqlite3
import sys
import time

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentPlan, AssessmentEnvironment, AssessmentScopeAmendment, ReviewedMapping, RecipeDefinition, content_digest
from aeep.assessment.extensions import grader_name,callbacks
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase,BenchmarkSuite,BenchmarkTrial
from aeep.models import ActionRequest,ExecutionReceipt,ValidationSpec
from aeep.qualification import behavior_fingerprint
from aeep.router import Router
from aeep_toolkit.telemetry import bound_journal,candidate_loading,token_capture

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def independent_grade(trial,receipt):
    assert receipt.receipt_id in trial.receipt_ids and trial.route_id==receipt.executor_id
    return isinstance(trial.valid,bool) and any(v.kind.value=='callback' and v.trust.value=='verified' and isinstance(v.valid,bool) for v in trial.case_validation)


def construct(proposal,boundary):
    from aeep.hosts.codex_pair_inspection import WorkerPairInspection
    pair=WorkerPairInspection.model_validate(proposal['definitions'][proposal['pair_definition_digest']])
    recipe_digest=proposal['requests'][0]['recipe_digest'];recipe=RecipeDefinition.model_validate(proposal['definitions'][recipe_digest])
    definitions=dict(proposal['definitions']);mapping=ReviewedMapping(candidate=pair.treatment,baseline=pair.control);mapping_ref=content_digest(mapping);definitions[mapping_ref]=mapping.model_dump(mode='json')
    environment=AssessmentEnvironment(environment_id='repository-usefulness-pilot-'+proposal['source_digest'][:12],kind='container',identity={'source_digest':proposal['source_digest'],'purpose':'21 development pairs only; no formal qualification or admission'},
        container_image='sha256:35dc1bcb7e8162c2a0cef6cbd30bc4bf276c082b11b6e5fc259b6800e8c5ca04',container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=512,
        conformance_digests={getattr(pair,role).id:boundary['boundaries'][role]['conformance_digest'] for role in ('control','treatment')},differential_conformance_digest=boundary['differential_conformance_digest'])
    env_ref=content_digest(environment);definitions[env_ref]=environment.model_dump(mode='json')
    cases=[]
    for value in recipe.generator_config['cases']:
        assert value['split']=='development' and value['used_for_development']
        public,truth=value['input'],value['truth']
        cases.append(BenchmarkCase(case_id='development-'+public['task_id'],split='training',variation=public['family'],template_family=value['source_repository'].casefold(),
            action=ActionRequest(capability=recipe.capability,input=public),validators=[ValidationSpec(kind='callback',config={'name':grader_name(public,truth),'expected':truth})]))
    suite=BenchmarkSuite(suite_id='repository-usefulness-pilot-'+proposal['source_digest'][:12],domain='repository-usefulness-pilot-only',seed=71,repetitions=1,
        routes=[{'route_id':s.id,'executor_id':s.id} for s in (pair.control,pair.treatment)],conditions=['fresh-worker'],warmup_cases=[],max_total_cash_usd='0',baseline_route_id=pair.control.id,paired_order=True,cases=cases)
    plan=AssessmentPlan(subject_digest=proposal['requests'][0]['subject_digest'],recipe_digest=recipe_digest,mapping_digest=mapping_ref,environment_digest=env_ref,authorization_id='onboarding',candidate_id=pair.treatment.id,baseline_id=pair.control.id,
        definition_digests=list(definitions),route_fingerprints={s.id:behavior_fingerprint(s) for s in (pair.control,pair.treatment)},executable_dependencies=runtime_dependencies(),suite=suite,
        applicability={'purpose':['repository_development_journey_only'],'formal_qualification':[False],'candidate_use':['optional'],'future_holdout_eligible':[False]})
    definitions[content_digest(plan)]=plan.model_dump(mode='json')
    return pair,recipe,mapping,environment,plan,definitions


async def main():
    review=json.loads((HERE/'operation-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text())
    assert len(sys.argv)==2 and sha(HERE/'operation-review.json')==sys.argv[1]==approval['review_sha256'] and approval['approved']
    for name,expected in review['assets'].items():assert sha(Path(name))==expected
    assert verification_source_digest(ROOT)==review['source_digest'] and shutil.disk_usage(ROOT).free>51*1024**3
    boundary=json.loads((HERE/'boundary-result.json').read_text());collector=json.loads((HERE/'collector-result.json').read_text());assert boundary['source_digest']==review['source_digest'] and collector['passed'] and collector['proxy_restored_stopped'] and collector['source_unchanged']
    assert all(item['verified_probe_count']==11 for item in boundary['boundaries'].values())
    assert not (HERE/'model-started.json').exists()
    proposal=json.loads((HERE/'collector-definitions.json').read_text());pair,recipe,mapping,environment,plan,definitions=construct(proposal,boundary)
    spec=importlib.util.spec_from_file_location('reviewed_collector_driver',HERE/'run-collector.py');driver=importlib.util.module_from_spec(spec);spec.loader.exec_module(driver)
    proxy=json.loads(driver.docker('inspect','--format',review['proxy_inspect_format'],review['proxy_name']));assert proxy['Id']==review['proxy_id'] and proxy['Image']==review['proxy_image'] and not proxy['Running']
    assert proxy['Memory']==proxy['MemorySwap']==review['proxy_memory_bytes'] and review['network_id'] in [v['NetworkID'] for v in proxy['Networks'].values()]
    router=Router.from_manifest(BASE/'aeep.json');service=AssessmentService(router,BASE/'.aeep/assessments');repo=service.repository
    spec=importlib.util.spec_from_file_location('hard_review_budget',HERE/'review-budget.py');budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
    initial=json.loads((HERE/'execution-started.json').read_text())['grant_before'];original_reserve=budget.install(repo,router.store._connection,initial,review)
    result={'review_sha256':sys.argv[1],'source_digest':review['source_digest'],'plan_id':plan.plan_id,'development_only':True,'formal_qualification':False,'admission':False,'efficacy_claim':False,'records':{},'model_turn_ceiling':42}
    started_proxy=False;reserved=False;began=time.monotonic()
    from aeep.assessment import extensions
    observation_spec=importlib.util.spec_from_file_location('bounded_public_observer',HERE.parent/'repository-model-fault-correction-20261023/run-corrected.py');observation_module=importlib.util.module_from_spec(observation_spec);observation_spec.loader.exec_module(observation_module)
    original_invoke=extensions.invoke;observation_count=0
    async def capture_invoke(service,scope,spec,value,**kwargs):
        nonlocal observation_count
        reply,elapsed=await original_invoke(service,scope,spec,value,**kwargs)
        observation_count+=1
        with (HERE/f'observer-{observation_count:03}.json').open('x') as stream:json.dump({'stage':kwargs.get('stage'),'operation_seconds':elapsed,**observation_module.bounded_observation(reply)},stream,indent=2);stream.write('\n')
        return reply,elapsed
    extensions.invoke=capture_invoke
    try:
        for executor in (pair.control,pair.treatment):router.register(executor)
        router.managed_hosts.configure([pair.control,pair.treatment],principal_salt=router.store.host_principal_key,manifest_directory=router.manifest_path.parent)
        for kind,value in [('mapping',mapping),('environment',environment),('plan',plan)]:repo.put(kind,getattr(value,'plan_id',content_digest(value)),value)
        from aeep.assessment.models import AssessmentAuthorization,AssessmentLimits
        authorization=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(authorization),subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],reviewed_digests=list(definitions))
        (HERE/'development-definition-review.json').write_text(json.dumps({'authority':'Standing finite definition delegation within this exact human-approved development envelope.','definitions':definitions,'amendment':amendment.model_dump(mode='json'),'model_turn_ceiling':42,'no_formal_study_or_holdout_change':True},indent=2)+'\n')
        repo.approve_bundle(amendment,definitions)
        registered=callbacks(service,plan,recipe);assert len(registered)==21
        for case in plan.suite.cases:assert case.validators[0].config['name'] in registered
        service._verify_dependencies(plan);preview=service.budget_preview(plan.plan_id)
        (HERE/'development-budget-preview.json').write_text(json.dumps(preview,indent=2)+'\n')
        assert preview['minimum_trial_model_turns']==42 and preview['campaign_allowance']['fits_remaining']
        (HERE/'model-started.json').write_text(json.dumps({'plan_id':plan.plan_id,'maximum_model_turns':42,'automatic_retry':False})+'\n')
        operation=plan.plan_id+':repository-development-proxy'
        repo.reserve(plan,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=18000,max_model_turns=0),stage='repository_development_proxy_lifecycle');reserved=True
        started_proxy=True;driver.docker('start',review['proxy_name'])
        assessment=service.enqueue(plan.plan_id);result['assessment_id']=assessment
        from aeep.benchmarking import BenchmarkRunner
        evidence_spec=importlib.util.spec_from_file_location('pilot_trial_evidence',HERE/'trial-evidence.py')
        evidence=importlib.util.module_from_spec(evidence_spec);evidence_spec.loader.exec_module(evidence)
        expected_rows=json.loads((HERE/'task-delivery-check.json').read_text())['checks']
        expected_prompts={(item['case'],item['role']):item['instruction_sha256'] for item in expected_rows}
        original_trial=BenchmarkRunner._execute_trial
        async def checked_trial(runner,*args,**kwargs):
            trial=await original_trial(runner,*args,**kwargs)
            record=evidence.read_trial(runner.connection,trial,pair,expected_prompts,service.directory/plan.plan_id/'attempts')
            with (HERE/('trial-evidence-'+trial.trial_id+'.json')).open('x') as stream:
                json.dump(record,stream,indent=2);stream.write('\n')
            evidence.require_complete(record)
            return trial
        BenchmarkRunner._execute_trial=checked_trial
        try:
            async with asyncio.timeout(17500):report=await service.run(assessment)
        finally:BenchmarkRunner._execute_trial=original_trial
        assert report.distinct_holdout_cases==0 and not report.qualification_passed
        result['report_id']=report.report_id;result['canonical_report']=report.model_dump(mode='json')
    except BaseException as exc:
        result.update(completed=False,error_type=type(exc).__name__,error_message=str(exc)[:400])
    finally:
        try:
            campaign_path=service.directory/plan.plan_id/'campaign.sqlite3'
            if campaign_path.exists():
                with sqlite3.connect(campaign_path.as_uri()+'?mode=ro',uri=True) as connection:
                    rows=list(connection.execute('SELECT trial_id,payload_json FROM trial_receipts'));stores=dict(connection.execute('SELECT trial_id,database_path FROM trial_stores'));trials={trial_id:BenchmarkTrial.model_validate_json(raw) for trial_id,raw in connection.execute('SELECT trial_id,payload_json FROM trials')}
                for trial_id,raw in rows:
                    receipt=ExecutionReceipt.model_validate_json(raw);path=Path(stores[trial_id]).resolve(strict=True);assert path.parent==service.directory/plan.plan_id/'attempts'
                    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as original:
                        canonical=ExecutionReceipt.model_validate_json(original.execute('SELECT payload_json FROM receipts WHERE receipt_id=?',(receipt.receipt_id,)).fetchone()[0]);assert content_digest(canonical)==content_digest(receipt)
                        row=original.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",(receipt.metadata.get('execution_evidence_digest'),)).fetchone()
                        journal=None if row is None else json.loads(row[0])
                    record={'receipt_ref':content_digest(receipt),'receipt':receipt.model_dump(mode='json'),'token_capture':None,'candidate_loading':None,'worker_cleanup_confirmed':receipt.metadata.get('worker_cleanup_confirmed') is True,'independent_grader_observed':independent_grade(trials[trial_id],receipt),'canonical_trial_ref':content_digest(trials[trial_id]),'task_grade':trials[trial_id].valid if independent_grade(trials[trial_id],receipt) else None}
                    if journal is not None:
                        bound=bound_journal(receipt,journal);record['token_capture']=token_capture(receipt,bound);record['candidate_loading']=candidate_loading(receipt,bound,skill_sha256=pair.candidate_skill_digest if receipt.executor_id==pair.treatment.id else None)
                    result['records'][trial_id]=record
            result['all_worker_cleanup_confirmed']=len(result['records'])==42 and all(v['worker_cleanup_confirmed'] for v in result['records'].values())
            result['independent_grade_coverage']=sum(v['independent_grader_observed'] for v in result['records'].values())
            result['verified_capture_coverage']=sum(v['token_capture'] is not None and v['token_capture'].get('status')=='verified' for v in result['records'].values())
            expected=json.loads((HERE/'task-delivery-check.json').read_text());expected_hashes={(item['case'],item['role']):item['instruction_sha256'] for item in expected['checks']}
            result['task_prompt_binding_coverage']=sum(record['receipt']['metadata'].get('task_instruction_sha256')==expected_hashes[(trials[trial_id].case_id.removeprefix('development-'),'skill' if record['receipt']['executor_id']==pair.treatment.id else 'turn')] for trial_id,record in result['records'].items())
            result['completed']=result.get('completed',len(result['records'])==42 and result['all_worker_cleanup_confirmed'] and result['independent_grade_coverage']==42 and result['verified_capture_coverage']==42 and result['task_prompt_binding_coverage']==42)
        finally:
            if started_proxy:
                try:driver.docker('stop','--time','5',review['proxy_name']);result['proxy_restored_stopped']=driver.docker('inspect','--format','{{.State.Running}}',review['proxy_name'])=='false'
                except Exception as exc:result.update(proxy_restored_stopped=False,cleanup_error_type=type(exc).__name__)
            if reserved:repo.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
            result['operation_ledger']=repo.operation_ledger(plan.plan_id).model_dump(mode='json');result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
            extensions.invoke=original_invoke
            result['observer_replies_retained']=observation_count
            result['grant_after']=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone());repo.reserve=original_reserve
            (HERE/'model-result.json').write_text(json.dumps(result,indent=2)+'\n');await router.close()
    print(json.dumps({k:v for k,v in result.items() if k not in ('records','canonical_report','operation_ledger')}))


if __name__=='__main__':asyncio.run(main())
