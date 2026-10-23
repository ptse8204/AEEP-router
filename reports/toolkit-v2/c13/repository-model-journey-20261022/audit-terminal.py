"""Reconcile this terminal bundle and reconstruct payload bindings without execution."""
import asyncio
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import subprocess

from aeep.assessment.containment import container_name
from aeep.assessment.models import RecipeDefinition,content_digest
from aeep.assessment.recipes import faulty_outputs
from aeep.assessment.repository_suites import grade_suite_output,reference_outputs
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import deterministic_digest
from aeep.models import ActionRequest,ActionConstraints,ExecutionReceipt
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


async def main():
    final=json.loads((HERE/'execution-result.json').read_text());model=json.loads((HERE/'model-result.json').read_text());proposal=json.loads((HERE/'collector-definitions.json').read_text())
    recipe=RecipeDefinition.model_validate(proposal['definitions'][proposal['requests'][0]['recipe_digest']]);extension=recipe.extension
    fixtures=[*extension.independent_fixtures,*extension.transformed_fixtures]
    checked=[*[(f.input,f.output) for f in fixtures],*[(c['input'],c['truth']) for c in recipe.generator_config['cases']]]
    references=reference_outputs(recipe,[value for value,truth in checked]);examples=[]
    for f in fixtures:
        if f.grader_output is not None:examples.append((f.input,f.output,f.grader_output,True,'literal-reference'))
    for (value,truth),correct in zip(checked,references,strict=True):
        examples.extend((value,truth,output,index==0,'reference' if index==0 else 'fault') for index,output in enumerate([correct,*faulty_outputs(correct),*extension.fault_outputs]))
    calls=[]
    class Captured(Exception):pass
    for value,truth,output,expected,label in examples:
        async def capture(payload):
            request=ActionRequest(capability=extension.grader.capability,input=payload,constraints=ActionConstraints(allowed_executor_ids=[extension.grader.id]))
            calls.append({'case':value['task_id'],'variant':label,'expected_valid':expected,'artifact_sha256':content_digest(output),'action_digest':deterministic_digest({'capability':request.capability,'input':request.input,'constraints':request.constraints}),'payload_sha256':content_digest(payload)})
            raise Captured()
        try:await grade_suite_output(value,truth,output,capture)
        except Captured:pass
    router=Router.from_manifest(BASE/'aeep.json');repo=AssessmentService(router,BASE/'.aeep/assessments').repository
    try:
        ledger=repo.operation_ledger(model['plan_id'],source_plan_ids=proposal['request_ids'])
        records=[];actual=[]
        for f in sorted((BASE/'.aeep/assessments'/model['plan_id']/'recipe-operations').glob('*.sqlite3')):
            with sqlite3.connect(f.as_uri()+'?mode=ro',uri=True) as con:
                for (raw,) in con.execute('SELECT payload_json FROM receipts'):
                    receipt=ExecutionReceipt.model_validate_json(raw);attempt_id=receipt.metadata['attempt_id'];row=con.execute('SELECT state,action_digest FROM execution_attempts WHERE attempt_id=?',(attempt_id,)).fetchone();assert row and row[0]=='COMPLETED'
                    mirror=repo.get('recipe_receipt',receipt.receipt_id);assert content_digest(mirror)==content_digest(receipt)
                    records.append({'operation_id':f.stem,'receipt_ref':content_digest(receipt),'attempt_id':attempt_id,'attempt_state':row[0],'action_digest':row[1],'started_at':receipt.started_at.isoformat(),'container_name':container_name(attempt_id)})
        records.sort(key=lambda r:r['started_at'])
        print(json.dumps({'actual_call_order':[(r['operation_id'],r['action_digest']) for r in records],'reconstructed_calls':calls[:12]}))
        assert len(records)==9 and [r['action_digest'] for r in records]==[r['action_digest'] for r in calls[:9]]
        docker=['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock']
        names=set(subprocess.check_output([*docker,'ps','-a','--format','{{.Names}}'],text=True,timeout=20).splitlines())
        for record in records:record['container_absent']=record['container_name'] not in names;assert record['container_absent']
        states={o.operation_id:router.store._connection.execute('SELECT state FROM assessment_operations WHERE id=?',(o.operation_id,)).fetchone()[0] for o in ledger.operations}
        assert len(states)==15 and set(states.values())=={'complete'} and all(o.elapsed_seconds is not None and o.elapsed_seconds<=o.reserved.max_elapsed_seconds for o in ledger.operations)
        elapsed=sum(o.elapsed_seconds for o in ledger.operations);assert math.isclose(elapsed,final['charged_seconds_delta'],abs_tol=1e-6)
        proxy=subprocess.check_output([*docker,'inspect','--format','{{.State.Running}}','aeep-reviewed-model-proxy'],text=True,timeout=20).strip();assert proxy=='false'
        (HERE/'terminal-operation-ledger.json').write_text(ledger.model_dump_json(indent=2)+'\n')
        output={'passed':True,'terminal_bundle_completed':False,'canonical_operations':len(states),'operation_states':states,'charged_operation_seconds':elapsed,'global_delta_reconciles_exactly':True,'model_turns':final['model_turns_delta'],'cash_delta':0,'canonical_receipts_attempts_reopened':len(records),'all_owned_grader_containers_absent':True,'proxy_restored_stopped':True,'source_unchanged':verification_source_digest(ROOT)==final['source_digest'],'physical_grader_calls':records,'reconstructed_call_count':len(calls),'observed_prefix_matches_exact_action_digests':True,'last_observed_call':calls[8],'last_call_is_old_marshmallow_import_fault':calls[8]['case']=='marshmallow-code__marshmallow-2800' and calls[8]['variant']=='fault','diagnosis':'The compiled recipe retained the original Marshmallow import-time fault, not the semantic fault certified later in89245763. All nine command receipts succeeded, but raw observer replies were not retained. The sequence ends on that old fault before grader validation completes. The exact malformed reply field remains unknown; no task grade is inferred.','first_party_reconstruction_only':True,'external_code_reexecuted':False,'no_qualification_or_value_claim':True}
        (HERE/'terminal-audit.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps({k:v for k,v in output.items() if k not in ['operation_states','physical_grader_calls']}))
    finally:await router.close()


if __name__=='__main__':asyncio.run(main())
