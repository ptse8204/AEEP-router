"""Exactly three fresh grader probes under the approved parent envelope."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import time

from aeep.assessment.containment import container_name
from aeep.assessment.extensions import invoke
from aeep.assessment.models import AssessmentLimits,AssessmentScopeAmendment,RecipeDefinition,RecipeMaterializationRequest,content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutionReceipt
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
BASE=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def save(name,value):
    with (HERE/name).open('x') as f:json.dump(value,f,indent=2);f.write('\n')


async def main():
    review=json.loads((HERE/'operation-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text());assert len(sys.argv)==2 and hashlib.sha256((HERE/'operation-review.json').read_bytes()).hexdigest()==sys.argv[1]==approval['review_sha256'] and approval['approved']
    assert verification_source_digest(ROOT)==review['source_digest'] and not (HERE/'grader-probes-started.json').exists()
    for path,digest in review['assets'].items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    definition=json.loads((HERE/'grader-probe-definitions.json').read_text());request=RecipeMaterializationRequest.model_validate(definition['request']);recipe=RecipeDefinition.model_validate(definition['documents'][request.recipe_digest]['document'])
    probes=json.loads((HERE/'grader-probes.json').read_text());assert len(probes)==3
    canary=Path(definition['canary']);assert not canary.exists()
    router=Router.from_manifest(BASE/'aeep.json');repo=AssessmentService(router,BASE/'.aeep/assessments').repository;service=AssessmentService(router,BASE/'.aeep/assessments')
    spec=importlib.util.spec_from_file_location('grader_review_budget',HERE/'review-budget.py');budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget);original=budget.install(repo,router.store._connection,json.loads((HERE/'execution-started.json').read_text())['grant_before'],review);service.repository=repo
    save('grader-probes-started.json',{'request_id':request.plan_id,'automatic_retry':False});result={'passed':False,'records':[],'model_turns':0};analysis_reserved=False;created_canary=False;started=time.perf_counter();child=[]
    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(definition['amendment']),{k:v['document'] for k,v in definition['documents'].items()})
        repo.reserve(request,request.plan_id+':setup',AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='grader_boundary_setup')
        try:
            with canary.open('x') as f:
                created_canary=True;f.write(definition['canary_text'])
        finally:repo.finish_operation(request.plan_id+':setup',elapsed_seconds=time.perf_counter()-started)
        repo.reserve(request,request.plan_id+':analysis',AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='grader_boundary_analysis');analysis_reserved=True;started=time.perf_counter()
        for index,item in enumerate(probes):
            assert hashlib.sha256(json.dumps(item['payload'],separators=(',',':')).encode()).hexdigest()==item['payload_sha256']
            operation=request.plan_id+':probe-'+str(index);reply,_=await invoke(service,request,recipe.extension.grader,item['payload'],stage='grader_boundary_probe',operation_id=operation,elapsed_times=child)
            save('grader-probe-'+str(index)+'.json',reply)
            assert isinstance(reply,dict) and reply.get('exit_code')==0 and reply.get('archive_sha256')==item['archive_sha256'] and reply.get('statuses',{}).get(item['expected_node'])=='PASSED'
            database=service.directory/request.plan_id/'recipe-operations'/(operation+'.sqlite3')
            with sqlite3.connect(database.as_uri()+'?mode=ro',uri=True) as c:
                raw=c.execute('SELECT payload_json FROM receipts').fetchone()[0];receipt=ExecutionReceipt.model_validate_json(raw);attempt=receipt.metadata['attempt_id'];assert c.execute('SELECT state FROM execution_attempts WHERE attempt_id=?',(attempt,)).fetchone()[0]=='COMPLETED'
            assert content_digest(repo.get('recipe_receipt',receipt.receipt_id))==content_digest(receipt)
            absent=not subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--filter','name=^/'+container_name(attempt)+'$','--format','{{.ID}}'],text=True,timeout=20).strip();assert absent
            result['records'].append({'name':item['name'],'receipt_ref':content_digest(receipt),'completed_attempt':attempt,'owned_container_absent':True})
        result['passed']=True
    except BaseException as exc:result.update(error_type=type(exc).__name__,error_message=str(exc)[:300])
    finally:
        if analysis_reserved:repo.finish_operation(request.plan_id+':analysis',elapsed_seconds=max(0,time.perf_counter()-started-sum(child)))
        if created_canary and canary.exists() and canary.read_text()==definition['canary_text']:canary.unlink()
        result['canary_removed']=not canary.exists();result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest'];result['operation_ledger']=repo.operation_ledger(request.plan_id).model_dump(mode='json');repo.reserve=original;save('grader-probes-result.json',result);await router.close()
    print(json.dumps({k:v for k,v in result.items() if k!='operation_ledger'}))


if __name__=='__main__':asyncio.run(main())
