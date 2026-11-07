"""Run one reviewed negative case with the unchanged protected React verifier."""

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
from aeep.execution import ExecutionEvidence, persist_execution_events
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


def validate_negative(exit_code, guest, expected_failure):
    statuses = guest['test_statuses']
    assert exit_code == guest['verifier_exit_code'] == 1
    assert guest['passed'] is False and guest['upstream_binary_reward'] == 0
    assert guest['phase'] == 'complete' and guest['solver_replayed'] is False
    assert not guest['missing_collected'] and guest['unexpected_collected_count'] == 0
    assert len(statuses) == 11 and set(statuses.values()) <= {'PASSED', 'FAILED'}
    assert statuses.get(expected_failure) == 'FAILED'


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
    grant=AssessmentAuthorization(authorization_id=review['grant_id'],
        subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],
        limits=AssessmentLimits(max_operations=1,max_elapsed_seconds=360),
        expires_at=datetime.fromisoformat(review['expires_at']),allowed_destinations=['local'],remote_disclosure=False)
    request=RecipeMaterializationRequest(plan_id=grant.authorization_id,subject_digest=ref,recipe_digest=ref,
        mapping_digest=ref,environment_digest=ref,authorization_id=grant.authorization_id,
        definition_digests=[ref],seed=0)
    ident=request.plan_id+':check'
    spec=ExecutorSpec(id='skillsbench.react.reference',capability='toolkit.upstream-engineering@1',
        kind='command',description='One protected verifier and reference controls',side_effect='write',
        config={'argv':review['argv'],'argv_literal':True,'inherit_env':False,'env':review['environment'],
                'timeout_seconds':320,'max_output_bytes':65536,'output':{'type':'json'}})
    write(HERE/'started.json',{'review_sha256':identity})
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        repo.put('toolkit_skillsbench_reference_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})
        repo.reserve(request,ident,grant.limits,stage='skillsbench_react_reference')
        raw,error=None,None
        result={'passed':False,'models':0,'review_sha256':identity,'runtime_image_id':review['image']}
        clock,started=time.perf_counter(),utc_now()
        executor=CommandExecutor()
        try:
            with persist_execution_events(lambda key,event:repo.put('execution_event',key+':'+str(event.sequence),event)):
                handle=await executor.start(ExecutionContext(
                    request=ActionRequest(action_id=ident,capability=spec.capability),spec=spec,
                    estimate=spec.estimate,attempt=1,attempt_id=ident,approved_side_effect=spec.side_effect,
                    invocation_check=lambda:(repo.authorize(request),identity)[1]))
                raw=await handle.task
            evidence=ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
            result['execution_evidence_ref']=repo.put('execution_evidence',evidence.digest(),evidence)
            assert evidence.complete
            guest = raw.output
            if not isinstance(guest, dict):
                guest = json.loads(raw.stdout)
            assert guest.get('models')==0 and guest.get('network')=='loopback only'
            result['observed']=guest
            validate_negative(raw.exit_code, guest, review['expected_failure'])
            result['cleanup_verified']=not containers()
            assert result['cleanup_verified']
            result['passed']=True
        except BaseException as exc:
            error=type(exc).__name__
            result.update(error_type=error,cleanup_verified=not containers())
            if raw is not None:
                guest=None
                if raw.stdout and len(raw.stdout.encode())<4096:
                    try:
                        parsed=json.loads(raw.stdout)
                    except json.JSONDecodeError:
                        parsed=None
                    if isinstance(parsed,dict) and parsed.get('passed') is False:
                        guest={key:parsed[key] for key in ('error_type','locations') if key in parsed}
                write(HERE/'diagnostic.json',{'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest(),
                    'exit_code':raw.exit_code,'guest':guest})
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

