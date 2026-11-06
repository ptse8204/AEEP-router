"""Run one approved check on the unchanged retained AFlow image."""

import argparse
import asyncio
import hashlib
import json
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
import os

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent


class Scope(StrictModel):
    review_sha256: str


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


async def run(review, identity):
    for file,digest in review['assets'].items():
        assert sha(file)==digest
    assert datetime.fromisoformat(review['expires_at'])>utc_now()
    assert shutil.disk_usage(HERE).free>=50*1024**3
    assert not (HERE/'started.json').exists()
    version = subprocess.check_output([*review['docker'], 'version', '--format',
        '{{.Server.Version}} {{.Server.GitCommit}}'], text=True, env=review['environment'], timeout=10)
    assert version.strip().split() == [review['engine_version'], review['engine_revision_short']]
    assert subprocess.check_output([*review['docker'],'image','inspect','--format','{{.Id}}',review['image']],
                                   text=True,env=review['environment'],timeout=10).strip()==review['image']
    def containers():
        return subprocess.check_output([*review['docker'],'ps','-aq','--filter','name=^/'+review['container_name']+'$'],
                                       text=True,env=review['environment'],timeout=10).strip()
    assert not containers()
    scope=Scope(review_sha256=identity)
    ref=content_digest(scope)
    grant=AssessmentAuthorization(authorization_id='evoagentx-planner-handoff-20261106',
        subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],
        limits=AssessmentLimits(max_operations=1,max_elapsed_seconds=70),
        expires_at=datetime.fromisoformat(review['expires_at']),allowed_destinations=['local'],remote_disclosure=False)
    request=RecipeMaterializationRequest(plan_id=grant.authorization_id,subject_digest=ref,recipe_digest=ref,
        mapping_digest=ref,environment_digest=ref,authorization_id=grant.authorization_id,
        definition_digests=[ref],seed=0)
    ident=request.plan_id+':check'
    spec=ExecutorSpec(id='evoagentx.runtime.planner-handoff',capability='toolkit.upstream-engineering@1',
        kind='command',description='One offline actual planner handoff check',side_effect='write',
        config={'argv':review['argv'],'argv_literal':True,'inherit_env':False,'env':review['environment'],
                'timeout_seconds':60,'max_output_bytes':65536,'output':{'type':'json'}})
    write(HERE/'started.json',{'review_sha256':identity})
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        repo.put('toolkit_evoagentx_planner_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})
        repo.reserve(request,ident,grant.limits,stage='evoagentx_planner_handoff')
        raw,error=None,None
        result={'passed':False,'models':0,'review_sha256':identity,'runtime_image_id':review['image']}
        clock,started=time.perf_counter(),utc_now()
        executor=CommandExecutor()
        try:
            handle=await executor.start(ExecutionContext(
                request=ActionRequest(action_id=ident,capability=spec.capability),spec=spec,
                estimate=spec.estimate,attempt=1,attempt_id=ident,approved_side_effect=spec.side_effect,
                invocation_check=lambda:(repo.authorize(request),identity)[1]))
            raw=await handle.task
            assert raw.exit_code==0 and raw.status.value=='success'
            assert isinstance(raw.output,dict) and raw.output.get('models')==0
            observed=raw.output
            assert observed['status']=='request_ready' and observed['relay_calls']==1
            messages=observed['messages']
            case=read(HERE/'case.json')
            assert [row['role'] for row in messages]==['system','user']
            assert all(set(row)=={'role','content'} for row in messages)
            assert case['goal'] in messages[1]['content'] and case['suggestion'] in messages[1]['content']
            data=json.dumps(messages,separators=(',',':'),sort_keys=True,allow_nan=False).encode()
            assert len(data)<=32768 and hashlib.sha256(data).hexdigest()==observed['request_sha256']
            assert observed['boundary']['local_unix_pair_verified'] and observed['boundary']['inherited_sockets']==0
            assert not containers()
            dest=Path(review['private_request'])
            with os.fdopen(os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600),'wb') as out:
                out.write(data)
            result.update(request_sha256=observed['request_sha256'],request_bytes=len(data),
                          relay_calls=1,boundary=observed['boundary'],cleanup_verified=True,
                          proposal_generated=False)
            result['passed']=True
        except BaseException as exc:
            error=type(exc).__name__
            result.update(error_type=error,cleanup_verified=not containers())
            if raw is not None:
                write(HERE/'diagnostic.json',{'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest(),
                    'exit_code':raw.exit_code})
        finally:
            await executor.close()
            elapsed=time.perf_counter()-clock
            receipt=ExecutionReceipt(decision_id=ident,action_id=ident,capability=spec.capability,
                executor_id=spec.id,executor_kind=spec.kind,status='success' if result['passed'] else 'failed',
                started_at=started,ended_at=utc_now(),estimated=spec.estimate,
                actual_resources=ResourceVector(latency_ms=elapsed*1000),
                execution_success=result['passed'],error_type=error,
                metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms']})
            store.save_receipt(receipt)
            repo.finish_operation(ident,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            write(HERE/'receipt.json',receipt.model_dump(mode='json'))
            write(HERE/'ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(HERE/'result.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--execute-delegated',required=True)
    args=parser.parse_args()
    path=HERE/'operation-review.json'
    identity=sha(path)
    assert args.execute_delegated==identity
    authority=read(HERE/'delegated-authority.json')
    assert authority['first_attempt'] and authority['review_sha256']==identity
    result=asyncio.run(run(read(path),identity))
    print(json.dumps(result))
    raise SystemExit(not result['passed'])
