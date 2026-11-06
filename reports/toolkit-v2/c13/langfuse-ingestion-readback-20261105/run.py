"""Observe the previous trace after an approved restart, with no POST path."""

import argparse
import base64
import importlib.util
import json
import shutil
import sqlite3
import sys
import time
from pathlib import Path

HERE=Path(__file__).resolve().parent
PREVIOUS=HERE.parent/'langfuse-retained-budget-20261105'
DISABLED=HERE.parent/'langfuse-disablement-20261105'
PROBE=HERE.parent/'langfuse-redis-path-20261105'
sys.path.insert(1,str(PREVIOUS))
spec=importlib.util.spec_from_file_location('retained_service_controls',PREVIOUS/'run.py')
runtime=importlib.util.module_from_spec(spec)
spec.loader.exec_module(runtime)
from relay import observations  # noqa: E402

base=runtime.base
PROJECT=runtime.PROJECT
PLAN=HERE.name


def latest(review):
    with sqlite3.connect(Path(review['ledger']).as_uri()+'?mode=ro',uri=True) as db:
        grant=review['grant_authorization_id']
        counters=list(db.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(grant,)).fetchone())
        assert runtime.export_count(db,grant)==1
        assert not db.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(grant,)).fetchone()
        records=db.execute("SELECT digest,payload_json FROM assessment_records WHERE kind='toolkit_receipt_export_transport'").fetchall()
        assert len(records)==1
        receipt=base.ExecutionReceipt.model_validate_json(records[0][1])
        assert base.content_digest(receipt)==records[0][0] and receipt.status.value=='failed'
        return counters, records[0][0], receipt


def check(review):
    base.validate(review)
    counters, ref, receipt=latest(review)
    assert counters==review['counters_before'] and ref==review['prior_transport_receipt_ref']
    assert receipt.metadata['trace_id']==review['trace_id']
    assert receipt.metadata['source_receipt_sha256']==review['source_receipt_sha256']
    ids=[review['containers'][name] for name in base.SERVICES]
    for name,row in zip(base.SERVICES,runtime.safe_read(review,'inspect','--format',runtime.STATE_TEMPLATE,*ids).splitlines(),strict=True):
        ident,state,code,labels=tuple(runtime.decode(row))
        assert ident==review['containers'][name] and state=='exited'
        assert labels[base.LABEL]==PROJECT and labels['com.docker.compose.service']==name
        if name not in runtime.LIVE:
            assert code==0
    assert runtime.check_permissions(review,ids)
    assert shutil.disk_usage(base.ROOT).free>=50*1024**3
    return counters


def freeze():
    old=base.load(PREVIOUS/'operation-review.json')
    stopped=base.load(PREVIOUS/'service-execution/stop-verdict.json')
    disabled=base.load(DISABLED/'service-execution/summary.json')
    probe=base.load(PROBE/'result.json')
    recovered=base.load(PROBE/'cleanup-recovery.json')
    assert stopped['all_retained_stopped'] and disabled['passed'] and recovered['passed']
    assert all(x['result']=='authenticated_ping' for x in probe['cases'].values())
    preview=base.load(PREVIOUS/'service-execution/export-preview.json')
    counters, ref, _receipt=latest(old)
    assert counters==disabled['grant_after']
    assert old['maximum_operations']-counters[0]>=28
    paths=(HERE/'run.py',HERE/'redis.cjs',PREVIOUS/'operation-review.json',PREVIOUS/'service-execution/summary.json',
           PREVIOUS/'service-execution/stop-verdict.json',PREVIOUS/'service-execution/export-preview.json',
           DISABLED/'service-execution/summary.json',PROBE/'result.json',PROBE/'cleanup-recovery.json')
    review=old|{
        'purpose':'First read-only reconciliation of the one previously dispatched trace. No export or second POST.',
        'continuation_plan_id':PLAN,'counters_before':counters,'maximum_additional_operations':28,
        'maximum_driver_commands':30,'previous_failed_export_must_remain_terminal':True,
        'prior_transport_receipt_ref':ref,'trace_id':preview['trace_id'],'span_id':preview['span_id'],
        'source_receipt_sha256':preview['source_receipt_sha256'],
        'new_post_requests':0,'maximum_observation_gets':8,'same_grant_without_amendment':True,
        'lifecycle':{'restart_exact_retained_services':list(runtime.LIVE),
                     'initializer_jobs_not_restarted':True,'new_images_networks_volumes_containers':0,
                     'redis_probe':'Run authenticated read-only PING in the owned web and worker; retain only outcome codes.',
                     'readback':'Use fixed local Node transport to GET only the prior trace observations. No raw response retained.',
                     'cleanup':'Stop the same reviewed service processes. Keep every resource and past receipt.'},
        'service_assets':old['service_assets']|{str(path):base.sha(path) for path in paths},
    }
    check(review)
    path=HERE/'operation-review.json'
    with path.open('x') as out:
        json.dump(review,out,indent=2);out.write('\n')
    print(base.sha(path))


def observe(journey, review):
    target=journey.owned['web']
    send=runtime.carrier.docker_transport(journey.docker(),target,journey.env)
    path=observations(review['trace_id'])
    env=base.load(journey.work/'compose-tmpfs.json')['services']['web']['environment']
    auth='Basic '+base64.b64encode((env['LANGFUSE_INIT_PROJECT_PUBLIC_KEY']+':'+env['LANGFUSE_INIT_PROJECT_SECRET_KEY']).encode()).decode()
    rows=[]
    for index in range(review['maximum_observation_gets']):
        operation=f'{PLAN}:readback:{index}'
        journey.repo.reserve(journey.request,operation,base.AssessmentLimits(max_operations=1,max_elapsed_seconds=9),stage='langfuse_readonly_reconciliation')
        started=base.utc_now();clock=time.perf_counter()
        result={'status':None,'matched':False,'error_type':None}
        try:
            status, reply=send('GET',path,auth,b'')
            result['status']=status
            if status==200:
                result['matched']=base.ingestion_match(json.loads(reply),review)
        except Exception as error:
            result['error_type']=type(error).__name__
        finally:
            elapsed=time.perf_counter()-clock
            journey.child_seconds+=elapsed
            receipt=base.ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',
                executor_id='langfuse.local-readonly-observer',executor_kind='python',
                status='success' if result['matched'] else 'failed',
                started_at=started,ended_at=base.utc_now(),estimated={},
                actual_resources=base.ResourceVector(latency_ms=elapsed*1000),
                execution_success=result['matched'],error_type=result['error_type'],
                metadata={'review_sha256':journey.identity,'trace_id':review['trace_id'],
                          'http_status':result['status'],'response_body_not_retained':True})
            journey.repo.store.save_receipt(receipt)
            journey.repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
            rows.append(result|{'receipt_id':receipt.receipt_id})
        if result['matched']:
            break
        if index+1 < review['maximum_observation_gets']:
            time.sleep(2)
    return rows


def execute(review, identity):
    check(review)
    out=HERE/'service-execution'
    out.mkdir(mode=0o700)
    base.write(HERE/'started.json',{'review_sha256':identity,'post_authorized':False})
    base.HERE=HERE
    request=base.RecipeMaterializationRequest.model_validate(base.load(runtime.PRIOR/'prepared.json')['request']).model_copy(
        update={'plan_id':PLAN})
    with base.ReceiptStore(review['ledger']) as store:
        repo=base.AssessmentRepository(store)
        journey=runtime.Journey(review,repo,request,identity)
        cleanup=PLAN+':cleanup';overhead=PLAN+':overhead'
        repo.reserve(request,cleanup,base.AssessmentLimits(max_operations=1,max_elapsed_seconds=100),stage='owned_reconciliation_cleanup')
        repo.reserve(request,overhead,base.AssessmentLimits(max_operations=1,max_elapsed_seconds=180),stage='readback_driver_overhead')
        clock=time.perf_counter()
        result={'passed':False,'models':0,'comparisons':'PAUSED','export_replayed':False,'ingestion_verified':False}
        phase='retained startup'
        try:
            journey.inspect([PROJECT+'-'+name for name in base.SERVICES])
            journey.start(*runtime.DATASTORES)
            journey.wait_datastores()
            journey.start('web','worker')
            journey.inspect_security()
            phase='active Redis path'
            probe=(HERE/'redis.cjs').read_text()
            for role in ('web','worker'):
                value=json.loads(journey.command('redis-'+role,journey.docker('exec',journey.owned[role],'node','-e',probe),8))
                assert set(value)=={'expected_address','result'}
                base.write(out/('redis-'+role+'.json'),value)
            phase='read back prior trace'
            rows=observe(journey,review)
            result['ingestion_verified']=any(row['matched'] for row in rows)
            result['bounded_readback']=rows
            result['trace_id']=review['trace_id']
            result['span_id']=review['span_id']
            result['source_receipt_sha256']=review['source_receipt_sha256']
            result['passed']=True
        except Exception as error:
            result.update(stopped_phase=phase,error_type=type(error).__name__)
        finally:
            try:
                journey.stop_owned()
                repo.finish_operation(cleanup,elapsed_seconds=journey.cleanup_seconds)
                result['cleanup_verified']=True
            except Exception as error:
                result.update(cleanup_verified=False,cleanup_error_type=type(error).__name__)
            repo.finish_operation(overhead,elapsed_seconds=max(0.,time.perf_counter()-clock-journey.child_seconds))
            result['grant_after']=journey.counters()
            result['post_reservation_count']=runtime.export_count(store._connection,request.authorization_id)
            result['accounting_settled']=not bool(store._connection.execute(
                "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone())
            result['passed']=result['passed'] and result['accounting_settled'] and result['cleanup_verified'] and result['post_reservation_count']==1
            for label,plan in (('commands',PLAN+':driver-commands'),('readback',PLAN)):
                base.write(out/(label+'-ledger.json'),repo.operation_ledger(plan).model_dump(mode='json'))
            base.write(out/'summary.json',result)
    print(json.dumps(result))
    return int(not result['passed'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute-approved')
    args=parser.parse_args()
    path=HERE/'operation-review.json'
    if args.prepare:
        freeze()
    else:
        review=base.load(path);identity=base.sha(path)
        assert not (HERE/'started.json').exists()
        if args.execute_approved is None:
            print(json.dumps({'passed':bool(check(review)),'review_sha256':identity,'execution':False}))
        else:
            approval=base.load(HERE/'operator-approval.json')
            assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
            raise SystemExit(execute(review,identity))
