"""Audit the failed task delivery without replaying any model or repository code."""
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.containment import container_name
from aeep.assessment.models import content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def main():
    result=json.loads((HERE/'execution-result.json').read_text());model=json.loads((HERE/'model-result.json').read_text());review=json.loads((HERE/'operation-review.json').read_text());proposal=json.loads((HERE/'collector-definitions.json').read_text());pair=proposal['definitions'][proposal['pair_definition_digest']]
    recipe=json.loads((HERE/'corrected-recipe.json').read_text());case_checks=[]
    for case in recipe['generator_config']['cases']:
        instruction=pair['control']['config']['instructions'];assert instruction==pair['treatment']['config']['instructions'] and '{input' not in instruction and '{action' not in instruction
        case_checks.append({'case':case['input']['task_id'],'task_text_delivered':case['input']['task'] in instruction,'base_hash_delivered':case['truth']['input_sha256'] in instruction,'input_path_delivered':'/workspace/repository.tar.gz' in instruction,'output_path_delivered':'/workspace/patch.json.gz' in instruction,'instruction_sha256':hashlib.sha256(instruction.encode()).hexdigest()})
    assert not any(c[k] for c in case_checks for k in ['task_text_delivered','base_hash_delivered','input_path_delivered','output_path_delivered'])
    router=Router.from_manifest(BASE/'aeep.json')
    try:
        repo=AssessmentService(router,BASE/'.aeep/assessments').repository;ledger=repo.operation_ledger(model['plan_id']);assert len(ledger.operations)==29
        states={o.operation_id:router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(o.operation_id,)).fetchone()[0] for o in ledger.operations};assert set(states.values())=={'complete'}
        total=sum(o.elapsed_seconds for o in ledger.operations);assert math.isclose(total,result['charged_seconds_delta'],abs_tol=1e-6)
        names=set(subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--format','{{.Names}}'],text=True,timeout=20).splitlines())
        base=BASE/'.aeep/assessments'/model['plan_id'];records=[]
        for f in (base/'recipe-operations').glob('*.sqlite3'):
            with sqlite3.connect(f.as_uri()+'?mode=ro',uri=True) as c:
                for (raw,) in c.execute('SELECT payload_json FROM receipts'):
                    r=ExecutionReceipt.model_validate_json(raw);attempt=r.metadata['attempt_id'];state=c.execute('SELECT state FROM execution_attempts WHERE attempt_id=?',(attempt,)).fetchone()[0];assert state=='COMPLETED' and container_name(attempt) not in names
                    assert content_digest(repo.get('recipe_receipt',r.receipt_id))==content_digest(r);records.append({'receipt_ref':content_digest(r),'state':state,'container_absent':True})
        for record in model['records'].values():
            r=ExecutionReceipt.model_validate(record['receipt']);assert r.metadata['task_instruction_sha256']==case_checks[0]['instruction_sha256'] and r.task_valid is None
        assert len(records)==15 and len(model['records'])==5
        for role in ['control','treatment']:
            active=subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--filter','ancestor='+review['images'][role],'--format','{{.Names}}'],text=True,timeout=20).strip();assert not active
        assert subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','inspect','--format','{{.State.Running}}',review['proxy_name']],text=True,timeout=20).strip()=='false'
        output={'passed':True,'engineering_journey_completed':False,'canonical_operations':len(states),'charged_operation_seconds':total,'model_turns_charged':5,'model_receipts_and_completed_turns':5,'independently_graded_tasks':0,'cash_delta':0,'grader_receipts_attempts_reopened':records,'model_receipts_reopened':len(model['records']),'all_reviewed_worker_images_absent_from_running_and_stopped_containers':True,'all_owned_graders_absent':True,'proxy_restored_stopped':True,'source_digest_at_execution':review['source_digest'],'current_source_matches_execution':verification_source_digest(ROOT)==review['source_digest'],'task_delivery_checks':case_checks,'known_token_capture_chains':'Five partial chains with all five named categories;provider_report/self_asserted provenance;no verified-success token-capture status.','positive_optional_instruction_loads':sum(r['candidate_loading']['instructions_loaded'] is True for r in model['records'].values()),'unknown_historical_fields':['Cleanup confirmation and artifact hash/size were filtered from receipts.','The exact failure cause was sanitized to execution_failed;no raw model output was retained.'],'stop':'Supported cancellation was requested after three repeated indeterminate invocations were observed;five turns had begun/completed before the stop took effect. No sixth turn. The current after_trial only stops environment_failure,so indeterminate results wrongly permitted further reservations.','selection_or_value_or_qualification':False}
        (HERE/'completion-audit.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({k:v for k,v in output.items() if k not in ['grader_receipts_attempts_reopened','task_delivery_checks']}))
    finally:router.store.close()


if __name__=='__main__':main()
