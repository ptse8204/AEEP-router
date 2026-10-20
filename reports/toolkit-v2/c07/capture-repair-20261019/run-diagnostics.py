"""At most four reviewed capture diagnostics through the existing AssessmentService."""
import asyncio
import hashlib
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, AssessmentPlan, AssessmentScopeAmendment, RecipeDefinition, ReviewedMapping, content_digest
from aeep.assessment.identity import runtime_dependencies, verify_dependencies
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.models import ExecutionReceipt, new_id
from aeep.qualification import behavior_fingerprint
from aeep.router import Router
from aeep_toolkit.telemetry import bound_journal, candidate_loading, token_capture

OUT=Path(__file__).parent
ROOT=OUT.parents[3]
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    path=OUT/'collector-operation-review.json'
    assert len(sys.argv)==2 and sha(path)==sys.argv[1]
    review=json.loads(path.read_text())
    approval=json.loads((OUT/'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert sha(Path(__file__))==review['diagnostics_runner_sha256']
    assert sha(OUT/'diagnostic-tasks.json')==review['diagnostic_tasks_sha256']
    assert verification_source_digest(ROOT)==review['source_digest']
    assert json.loads((OUT/'validation/source-stability.json').read_text())['all_passed']
    collector=json.loads((OUT/'collector-result.json').read_text())
    boundary=json.loads((OUT/'boundary-result.json').read_text())
    assert collector['passed'] and collector['source_unchanged'] and collector['proxy_restored_stopped']
    assert boundary['source_digest']==review['source_digest'] and boundary['grant_counters_unchanged']
    assert shutil.disk_usage(ROOT).free>51*1024**3
    assert not (OUT/'diagnostics-started.json').exists()
    from importlib.util import module_from_spec, spec_from_file_location
    spec=spec_from_file_location('reviewed_collector_driver',OUT/'run-collector.py')
    driver=module_from_spec(spec);spec.loader.exec_module(driver)
    assert sha(OUT/'run-collector.py')==review['runner_sha256']
    proxy=json.loads(driver.docker('inspect','--format',review['proxy_inspect_format'],review['proxy_name']))
    assert proxy['Id']==review['proxy_id'] and proxy['Image']==review['proxy_image'] and not proxy['Running']
    assert proxy['Memory']==proxy['MemorySwap']==review['proxy_memory_bytes']
    assert review['network_id'] in [v['NetworkID'] for v in proxy['Networks'].values()]
    router=Router.from_manifest(BASE/'aeep.json')
    service=AssessmentService(router,BASE/'.aeep/assessments')
    repo=service.repository
    result={'source_digest':review['source_digest'],'review_sha256':sys.argv[1],
        'new_model_turn_ceiling':4,'holdouts':0,'admission':False,'efficacy_claim':False,'records':{},'plans':[]}
    started_proxy=False
    reserved=False
    began=time.monotonic()
    before=tuple(router.store._connection.execute("SELECT operations,model_turns FROM assessment_grants WHERE id='onboarding'").fetchone())
    original_reserve=repo.reserve

    def reserve(plan,operation,limits,**kwargs):
        current=router.store._connection.execute("SELECT operations,model_turns FROM assessment_grants WHERE id='onboarding'").fetchone()
        assert current[0]+limits.max_operations<=before[0]+64
        assert current[1]+limits.max_model_turns<=before[1]+4
        return original_reserve(plan,operation,limits,**kwargs)

    repo.reserve=reserve
    try:
        proposal=json.loads((OUT/'collector-definitions.json').read_text())
        pair=proposal['definitions'][proposal['pair_definition_digest']]
        from aeep.models import ExecutorSpec
        control,treatment=(ExecutorSpec.model_validate(pair[role]) for role in ('control','treatment'))
        assert treatment.config['invocation']['exposure']=='optional'
        for item in (control,treatment):
            assert item.config['timeout_seconds']<=102
            router.register(item)
        router.managed_hosts.configure([control,treatment],principal_salt=router.store.host_principal_key,
            manifest_directory=router.manifest_path.parent)
        prior=AssessmentPlan.model_validate(repo.get('plan','plan_017bce61874c437296c66276e91876d6'))
        dependencies={name:digest for name,digest in prior.executable_dependencies.items()
                      if not Path(name).is_relative_to(ROOT/'src/aeep')}
        dependencies.update(runtime_dependencies())
        verify_dependencies(dependencies)
        recipe=RecipeDefinition.model_validate(repo.get('recipe',prior.recipe_digest))
        mapping=ReviewedMapping(candidate=treatment,baseline=control)
        mapping_ref=repo.put('mapping',content_digest(mapping),mapping)
        env=AssessmentEnvironment(environment_id='capture-diagnostic-'+review['source_digest'][:12],kind='container',
            identity={'source_digest':review['source_digest'],'purpose':'Public capture diagnostics only; no holdouts or efficacy'},
            container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',
            container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=512,
            conformance_digests={s.id:boundary['boundaries'][role]['conformance_digest']
                for s,role in ((control,'control'),(treatment,'treatment'))},
            differential_conformance_digest=boundary['differential_conformance_digest'])
        env_ref=repo.put('environment',content_digest(env),env)
        tasks=json.loads((OUT/'diagnostic-tasks.json').read_text())['cases']
        definitions={ref:repo.get(kind,ref) for kind,ref in (
            ('subject',prior.subject_digest),('recipe',prior.recipe_digest),('mapping',mapping_ref),('environment',env_ref))}
        plans=[]
        for task in tasks:
            case=prior.suite.cases[0].model_dump(mode='json')
            case.update(case_id='capture-'+task['label'],split='training',variation=task['input']['variation'])
            case['action'].update(action_id=new_id('act'),input=task['input'])
            case['validators'][-1]['config']['expected']=task['expected']
            case=BenchmarkCase.model_validate(case)
            suite=prior.suite.model_dump(mode='json')
            suite.update(suite_id=new_id('capture-suite'),cases=[case.model_dump(mode='json')],repetitions=1,
                routes=[{'route_id':s.id,'executor_id':s.id} for s in (control,treatment)],
                conditions=['fresh-worker'],warmup_cases=[],max_total_cash_usd='0',baseline_route_id=control.id)
            plan=AssessmentPlan(subject_digest=prior.subject_digest,recipe_digest=prior.recipe_digest,
                mapping_digest=mapping_ref,environment_digest=env_ref,authorization_id='onboarding',
                candidate_id=treatment.id,baseline_id=control.id,definition_digests=list(definitions),
                route_fingerprints={s.id:behavior_fingerprint(s) for s in (control,treatment)},
                executable_dependencies=dependencies,suite=BenchmarkSuite.model_validate(suite),
                applicability={'purpose':['capture_diagnostic_only'],'mode':[task['label']]})
            repo.put('plan',plan.plan_id,plan)
            definitions[content_digest(plan)]=plan.model_dump(mode='json')
            plans.append((task['label'],plan))
        grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),
            subject_digests=[prior.subject_digest],recipe_digests=[prior.recipe_digest],environment_digests=[env_ref],
            reviewed_digests=list(definitions))
        (OUT/'diagnostic-definition-review.json').write_text(json.dumps({'authority':'September25/27 routine exact definition delegation within this explicitly approved four-turn capture envelope.',
            'definitions':definitions,'amendment':amendment.model_dump(mode='json'),'maximum_model_turns':4,
            'source_digest':review['source_digest'],'comparison_semantics':'Legacy diagnostic plans only; no incremental qualification, holdouts or utility claim.'},indent=2)+'\n')
        repo.approve_bundle(amendment,definitions)
        for _,plan in plans:
            service._verify_dependencies(plan)
            preview=service.budget_preview(plan.plan_id)
            assert preview['minimum_trial_model_turns']==2 and preview['campaign_allowance']['fits_remaining']
        with (OUT/'diagnostics-started.json').open('x') as stream:json.dump(result,stream)
        operation=plans[0][1].plan_id+':capture-diagnostic-proxy'
        repo.reserve(plans[0][1],operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=1200,max_model_turns=0),stage='capture_diagnostic_proxy')
        reserved=True
        started_proxy=True
        driver.docker('start',review['proxy_name'])
        for label,plan in plans:
            assessment=service.enqueue(plan.plan_id)
            async with asyncio.timeout(600):report=await service.run(assessment)
            assert report.distinct_holdout_cases==0 and not report.qualification_passed
            result['plans'].append({'label':label,'plan_id':plan.plan_id,'assessment_id':assessment,'report_id':report.report_id})
            campaign_path=service.directory/plan.plan_id/'campaign.sqlite3'
            with sqlite3.connect(campaign_path.as_uri()+'?mode=ro',uri=True) as campaign:
                rows=list(campaign.execute('SELECT trial_id,payload_json FROM trial_receipts'))
                stores=dict(campaign.execute('SELECT trial_id,database_path FROM trial_stores'))
            assert len(rows)==2
            loaded=False
            for tid,raw in rows:
                receipt=ExecutionReceipt.model_validate_json(raw)
                original_path=Path(stores[tid]).resolve(strict=True)
                assert original_path.parent==service.directory/plan.plan_id/'attempts'
                with sqlite3.connect(original_path.as_uri()+'?mode=ro',uri=True) as original:
                    retained=ExecutionReceipt.model_validate_json(original.execute('SELECT payload_json FROM receipts WHERE receipt_id=?',(receipt.receipt_id,)).fetchone()[0])
                    assert content_digest(retained)==content_digest(receipt)
                    payload=json.loads(original.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",(receipt.metadata['execution_evidence_digest'],)).fetchone()[0])
                journal=bound_journal(receipt,payload)
                tokens=token_capture(receipt,journal)
                loading=candidate_loading(receipt,journal,skill_sha256=pair['candidate_skill_digest'] if receipt.executor_id==treatment.id else None)
                assert tokens['status']=='verified'
                result['records'][tid]={'tokens':tokens,'candidate':loading,'receipt':receipt.model_dump(mode='json'),'journal':payload}
                if receipt.executor_id==treatment.id:loaded=loading['instructions_loaded'] is True
            if label=='explicit_request' and not loaded:
                result['optional_pair_skipped']='Explicit read-request diagnostic did not produce bound positive loading evidence.'
                break
        result['passed']=len(result['records'])==4
    except BaseException as exc:
        result.update(passed=False,error_type=type(exc).__name__)
    finally:
        if started_proxy:
            try:
                driver.docker('stop','--time','5',review['proxy_name'])
                result['proxy_restored_stopped']=driver.docker('inspect','--format','{{.State.Running}}',review['proxy_name'])=='false'
            except Exception as exc:result.update(proxy_restored_stopped=False,cleanup_error_type=type(exc).__name__)
        if reserved:repo.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
        repo.reserve=original_reserve
        result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
        result['grant_after']=list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        (OUT/'diagnostic-result.json').write_text(json.dumps(result,indent=2)+'\n')
        await router.close()
        print(json.dumps({k:v for k,v in result.items() if k!='records'}))


if __name__=='__main__':
    asyncio.run(main())
