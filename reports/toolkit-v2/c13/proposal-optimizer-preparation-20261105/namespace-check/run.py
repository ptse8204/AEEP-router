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
    assert subprocess.check_output([*review['docker'],'image','inspect','--format','{{.Id}}',review['image']],
                                   text=True,env=review['environment'],timeout=10).strip()==review['image']
    def containers():
        return subprocess.check_output([*review['docker'],'ps','-aq','--filter','name=^/'+review['container_name']+'$'],
                                       text=True,env=review['environment'],timeout=10).strip()
    assert not containers()
    scope=Scope(review_sha256=identity)
    ref=content_digest(scope)
    grant=AssessmentAuthorization(authorization_id='aflow-runtime-namespace-20261105',
        subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],
        limits=AssessmentLimits(max_operations=1,max_elapsed_seconds=70),
        expires_at=datetime.fromisoformat(review['expires_at']),allowed_destinations=['local'],remote_disclosure=False)
    request=RecipeMaterializationRequest(plan_id=grant.authorization_id,subject_digest=ref,recipe_digest=ref,
        mapping_digest=ref,environment_digest=ref,authorization_id=grant.authorization_id,
        definition_digests=[ref],seed=0)
    ident=request.plan_id+':check'
    spec=ExecutorSpec(id='aflow.runtime.namespace-check',capability='toolkit.upstream-engineering@1',
        kind='command',description='One offline graph parser and namespace check',side_effect='write',
        config={'argv':review['argv'],'argv_literal':True,'inherit_env':False,'env':review['environment'],
                'timeout_seconds':60,'max_output_bytes':65536,'output':{'type':'json'}})
    write(HERE/'started.json',{'review_sha256':identity})
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        repo.put('toolkit_aflow_runtime_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})
        repo.reserve(request,ident,grant.limits,stage='aflow_runtime_namespace_check')
        raw,error=None,None
        result={'passed':False,'models':0,'review_sha256':identity,'runtime_image_id':review['image']}
        clock,started=time.perf_counter(),utc_now()
        executor=CommandExecutor()
        try:
            raw=await executor.execute(ExecutionContext(
                request=ActionRequest(action_id=ident,capability=spec.capability),spec=spec,
                estimate=spec.estimate,attempt=1,attempt_id=ident,approved_side_effect=spec.side_effect,
                invocation_check=lambda:(repo.authorize(request),identity)[1]))
            assert raw.exit_code==0 and raw.status.value=='success'
            assert raw.output=={
                'optimizer_imported':True,'actual_graph_parser_passed':True,'models':0,
                'network_interfaces':['lo'],'python':'3.12.16','generated_code_executed':False,
                'optimizer_calibration':'UNSTARTED',
            }
            assert not containers()
            result.update(passed=True,observed=raw.output,cleanup_verified=True)
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
                executor_id=spec.id,executor_kind=spec.kind,status=raw.status if raw else 'failed',
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
    parser.add_argument('--execute-approved',required=True)
    args=parser.parse_args()
    path=HERE/'operation-review.json'
    identity=sha(path)
    assert args.execute_approved==identity
    assert read(HERE/'operator-approval.json')=={'approved':True,'review_sha256':identity}
    result=asyncio.run(run(read(path),identity))
    print(json.dumps(result))
    raise SystemExit(not result['passed'])
