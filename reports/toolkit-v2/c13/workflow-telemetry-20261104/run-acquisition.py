"""Acquire exact Langfuse images only; no container or upstream application runs."""
from __future__ import annotations
import argparse, asyncio, hashlib, json, shutil, sys, time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def validate(review):
    assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'].replace('Z', '+00:00'))
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3 + review['acquisition']['start_headroom_bytes']
    for path, expected in review['component_assets']['acquisition'].items():
        assert sha(path) == expected, path
    sys.path.insert(0, str(Path(review['coordinator_source_snapshot']) / 'src'))
    from aeep.assessment.verification import verification_source_digest
    assert verification_source_digest(Path(review['coordinator_source_snapshot'])) == review['source']
    checks = load(review['source_checks'])
    assert checks['source_before'] == checks['source_after'] == review['source']
    assert len(checks['checks']) == 13 and all(row['exit_code'] == 0 for row in checks['checks'])


async def command(repo, request, review, operation, arguments, seconds):
    from aeep.assessment.models import AssessmentLimits
    from aeep.executors.base import ExecutionContext
    from aeep.executors.command import CommandExecutor
    from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now

    validate(review)
    docker = review['acquisition']['docker']
    argv = [docker, '--config', review['acquisition']['docker_config'], '--host',
            'unix://' + review['acquisition']['docker_socket'], *arguments]
    spec = ExecutorSpec(id='langfuse.image-acquisition', capability='toolkit.upstream-engineering@1',
        kind='command', side_effect='write', description='Exact immutable image acquisition/metadata only',
        config={'argv':argv,'argv_literal':True,'inherit_env':False,
                'env':{'PATH':'/usr/bin:/bin','HOME':review['acquisition']['work']},
                'timeout_seconds':seconds,'max_output_bytes':1048576,'output':{'type':'text'}})
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0,
        max_elapsed_seconds=seconds + 10), stage='langfuse_artifact_acquisition')
    started = utc_now()
    began = time.perf_counter()
    executor, raw, error = CommandExecutor(), None, None

    def authorize():
        validate(review)
        repo.authorize(request)
        return review['source']

    try:
        handle = await executor.start(ExecutionContext(request=ActionRequest(action_id=operation,
            capability=spec.capability), spec=spec, estimate=spec.estimate, attempt=1,
            attempt_id=operation, approved_side_effect=SideEffect.WRITE, invocation_check=authorize))
        while not handle.task.done():
            await asyncio.wait({handle.task}, timeout=1)
            if shutil.disk_usage(ROOT).free < 50 * 1024**3:
                await executor.cancel(handle)
                raise RuntimeError('Actual50GiBReserveCrossed')
        raw = await handle.task
    except BaseException as failure:
        error = type(failure).__name__
    finally:
        await executor.close()
        elapsed = time.perf_counter() - began
        from aeep.models import ResourceVector
        receipt = ExecutionReceipt(decision_id=operation, action_id=operation, capability=spec.capability,
            executor_id=spec.id, executor_kind=spec.kind,
            status=raw.status if raw else 'failed', started_at=started, ended_at=utc_now(), estimated=spec.estimate,
            actual_resources=raw.resources if raw else ResourceVector(latency_ms=elapsed * 1000),
            accounting=raw.accounting if raw else {}, execution_success=raw is not None and raw.status.value == 'success',
            error_type=error or (raw.error_type if raw else None), metadata={
                'review_sha256':review['identity'],'argument_sha256':hashlib.sha256(json.dumps(arguments).encode()).hexdigest(),
                'observed_resource_dimensions':['latency_ms'], 'network_measurement':'UNKNOWN',
                'legacy_vector_defaults_are_not_observations':True})
        repo.store.save_receipt(receipt)
        repo.finish_operation(operation, elapsed_seconds=elapsed,
            accounting=raw.accounting if raw else None, resources=receipt.actual_resources)
        suffix=hashlib.sha256(operation.encode()).hexdigest()[:20]
        write(HERE/'runtime-execution'/('receipt-'+suffix+'.json'),receipt.model_dump(mode='json'))
        if raw is not None:
            write(HERE/'runtime-execution'/('status-'+suffix+'.json'), {
                'operation':operation,'status':raw.status.value,'exit_code':raw.exit_code,
                'stdout':(raw.stdout or '')[:16384],'stderr':(raw.stderr or '')[:16384]})
    return raw, elapsed


def execute(review):
    from aeep.assessment.models import AssessmentAuthorization, RecipeMaterializationRequest
    from aeep.assessment.models import AssessmentLimits
    from aeep.assessment.repository import AssessmentRepository
    from aeep.models import StrictModel
    from aeep.store import ReceiptStore

    class Scope(StrictModel):
        role: str
        source_digest: str
        artifact_plan_sha256: str

    validate(review)
    prepared = load(HERE/'acquisition-preparation.json')
    request = RecipeMaterializationRequest.model_validate(prepared['request'])
    out=HERE/'runtime-execution';out.mkdir(mode=0o700)
    with (HERE/'runtime-started.json').open('x') as stream:
        json.dump({'review_sha256':review['identity']},stream)
    result={'passed':False,'models':0,'comparisons':'PAUSED','all_stack_complete':False,
            'guest_programs_executed':0,'services_started':0,'cleanup_uncertain':False,
            'accounting_uncertain':False,'images':[]}
    with ReceiptStore(prepared['ledger']) as store:
        repo=AssessmentRepository(store)
        for reference, raw in prepared['definitions'].items():
            value=Scope.model_validate(raw)
            assert repo.put('toolkit_langfuse_acquisition_scope',reference,value)==reference
            repo.review(reference)
        grant=AssessmentAuthorization.model_validate(prepared['grant'])
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        repo.grant(grant)
        overhead_request=request.model_copy(update={'plan_id':request.plan_id+':driver-overhead'})
        overhead=request.plan_id+':driver-overhead'
        repo.reserve(overhead_request,overhead,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='artifact_driver_overhead')
        began=time.perf_counter();nested=0.
        try:
            for image in review['acquisition']['images']:
                item={'image':image['reference'],'acquired':False,'attempts':0}
                for attempt in range(1,3):
                    operation=request.plan_id+':'+image['key']+':pull:'+str(attempt)
                    raw,elapsed=asyncio.run(command(repo,request,review,operation,
                        ['image','pull','--platform','linux/arm64','--quiet',image['reference']],180))
                    nested+=elapsed
                    if raw is None:
                        result['cleanup_uncertain']=True
                        raise RuntimeError('Acquisition command lacks terminal evidence')
                    item['attempts']=attempt
                    if raw.status.value=='success':
                        item['acquired']=True
                        break
                if item['acquired']:
                    raw,elapsed=asyncio.run(command(repo,request,review,request.plan_id+':'+image['key']+':inspect',
                        ['image','inspect',image['reference'],'--format','{{json .RepoDigests}}'],20))
                    nested+=elapsed
                    if raw is None:
                        result['cleanup_uncertain']=True
                        raise RuntimeError('Inspection command lacks terminal evidence')
                    try:
                        assert raw.status.value=='success'
                        names=json.loads(raw.output)
                        assert isinstance(names,list) and all(isinstance(name,str) for name in names)
                        assert any(name.endswith('@'+image['manifest_digest']) for name in names)
                        item['immutable_reference_verified']=True
                    except (AssertionError,ValueError,TypeError) as error:
                        item['immutable_reference_verified']=False
                        item['inspection_error_type']=type(error).__name__
                result['images'].append(item)
            result['passed']=all(row['acquired'] and row.get('immutable_reference_verified') for row in result['images'])
        except BaseException as error:
            result['error_type']=type(error).__name__
        finally:
            from aeep.models import ResourceVector
            elapsed=max(0.,time.perf_counter()-began-nested)
            repo.finish_operation(overhead,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            result['accounting_uncertain']=store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant.authorization_id,)).fetchone() is not None
            result['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone())
            write(out/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(out/'overhead-ledger.json',repo.operation_ledger(overhead_request.plan_id).model_dump(mode='json'))
            result['free_bytes_after']=shutil.disk_usage(ROOT).free
            write(out/'summary.json',result)
    return result


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
    review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json');validate(review)
    if args.execute_approved is None:
        print(json.dumps({'review_sha256':identity,'execution':False}));raise SystemExit(0)
    approval=load(HERE/'operator-approval.json')
    assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    review['identity']=identity
    result=execute(review);print(json.dumps(result))
    if not result['passed']:raise SystemExit(1)
