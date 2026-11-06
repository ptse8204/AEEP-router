"""Check the exact Redis image and Node transport on an isolated Docker bridge."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import ipaddress
import json
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRIOR=HERE.parent/'langfuse-retained-budget-20261105'
DISABLED=HERE.parent/'langfuse-disablement-20261105'
AUTH=HERE.parent/'pipeline-standing-authority-20261104.json'
NAME='aeep-lf-redis-probe-20261105'
SUBNET='172.31.247.0/27'
POOL='172.31.247.0/28'
STATIC='172.31.247.30'


class Scope(StrictModel):
    review_sha256: str


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(name,value):
    with (HERE/name).open('x') as out:
        json.dump(value,out,indent=2);out.write('\n')


def docker(review,*args):
    return [review['docker'],'--config',review['docker_config'],
            '--host','unix://'+review['docker_socket'],*args]


def inspect(review,*args):
    return subprocess.check_output(docker(review,*args),text=True,timeout=10).strip()


def clean_preflight(review):
    ids=inspect(review,'network','ls','-q').splitlines()
    networks=inspect(review,'network','inspect','--format','{{json .IPAM.Config}}',*ids).splitlines()
    candidate=ipaddress.ip_network(SUBNET)
    for line in networks:
        for config in json.loads(line) or []:
            if 'Subnet' in config:
                assert not candidate.overlaps(ipaddress.ip_network(config['Subnet']))
    assert not inspect(review,'ps','-aq','--filter','label=com.aeep.engineering.owner='+NAME)
    for image in (review['node_image'],review['redis_image']):
        assert inspect(review,'image','inspect','--format','{{.Id}}',image)==image


def freeze():
    previous=read(PRIOR/'operation-review.json')
    terminal=read(PRIOR/'service-execution/summary.json')
    assert terminal['stopped_phase']=='one local receipt export' and not terminal['cleanup_uncertain']
    refs=(HERE/'run.py',HERE/'probe.cjs',AUTH,PRIOR/'service-execution/summary.json',
          PRIOR/'service-execution/stop-verdict.json',DISABLED/'service-execution/summary.json',
          Path(previous['docker']),Path(previous['docker_config'])/'config.json')
    review={
        'purpose':'First distinct Redis static/DNS/hosts-entry transport check, without starting any existing service.',
        'pins':{str(path):sha(path) for path in refs},'source_sha256':verification_source_digest(ROOT),
        **{key:previous[key] for key in ('docker','docker_config','docker_socket','ledger')},
        'node_image':previous['image_ids']['langfuse-langfuse'],'redis_image':previous['image_ids']['library-redis'],
        'network':{'name':NAME,'internal':True,'subnet':SUBNET,'dynamic_range':POOL,'static_redis':STATIC},
        'new_temporary_containers':3,'new_temporary_networks':1,
        'maximum_operations':6,'maximum_seconds':180,'models':0,'cash_usd':'0',
        'disclosure':False,'no_existing_restart':True,'automatic_retries':False,
        'only_remove_new_verified_owned_resources':True,
    }
    clean_preflight(review)
    write('operation-review.json',review)
    print(sha(HERE/'operation-review.json'))


async def run(review,identity):
    assert not (HERE/'started.json').exists()
    assert verification_source_digest(ROOT)==review['source_sha256']
    assert all(sha(path)==digest for path,digest in review['pins'].items())
    assert shutil.disk_usage(ROOT).free>50*1024**3
    clean_preflight(review)
    write('started.json',{'review_sha256':identity,'models':0,'existing_services_started':False})
    scope=Scope(review_sha256=identity);ref=content_digest(scope)
    grant=AssessmentAuthorization(authorization_id=HERE.name,subject_digests=[ref],recipe_digests=[ref],
        environment_digests=[ref],limits=AssessmentLimits(max_operations=6,max_elapsed_seconds=180),
        allowed_destinations=['local'],remote_disclosure=False,expires_at=utc_now()+timedelta(minutes=20))
    request=RecipeMaterializationRequest(plan_id=HERE.name,subject_digest=ref,recipe_digest=ref,
        environment_digest=ref,mapping_digest=ref,authorization_id=grant.authorization_id,definition_digests=[ref],seed=0)
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        repo.put('langfuse_redis_path_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})
        label='com.aeep.engineering.owner='+NAME
        cleanup=NAME+':cleanup'
        repo.reserve(request,cleanup,AssessmentLimits(max_operations=1,max_elapsed_seconds=35),stage='owned_probe_cleanup')
        outcome={'passed':False,'models':0,'comparisons':'PAUSED','isolated_synthetic_probe':True}
        created=False

        async def op(name,args,output='text'):
            operation=NAME+':'+name
            repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=25),stage=name)
            executor=CommandExecutor()
            started=utc_now();clock=time.perf_counter();raw=None
            spec=ExecutorSpec(id='langfuse.redis-probe.'+name,capability='toolkit.upstream-engineering@1',
                description='Exact private Redis path fixture',kind='command',side_effect='write',config={
                    'argv':docker(review,*args),'argv_literal':True,'inherit_env':False,
                    'env':{'PATH':'/usr/bin:/bin','LC_ALL':'C'},'timeout_seconds':18,
                    'max_output_bytes':16384,'output':{'type':output}})
            try:
                raw=await executor.execute(ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,approved_side_effect=SideEffect.WRITE))
                assert raw.status.value=='success'
                return raw.output
            finally:
                await executor.close()
                elapsed=time.perf_counter()-clock
                resources=ResourceVector(latency_ms=elapsed*1000)
                receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability=spec.capability,
                    executor_id=spec.id,executor_kind='command',status=raw.status if raw else 'failed',
                    started_at=started,ended_at=utc_now(),estimated={},actual_resources=resources,
                    execution_success=raw is not None and raw.status.value=='success',
                    error_type=raw.error_type if raw else None,metadata={'review_sha256':identity})
                store.save_receipt(receipt)
                repo.finish_operation(operation,elapsed_seconds=elapsed,resources=resources)
                write(name+'-receipt.json',receipt.model_dump(mode='json'))

        def container(name):
            return ['run','--pull=never','--rm','--name',NAME+'-'+name,'--label',label,'--network',NAME,
                    '--user','65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges','--read-only',
                    '--memory=192m','--memory-swap=192m','--pids-limit=32',
                    '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=16m']

        try:
            network=await op('create-network',['network','create','--internal','--label',label,'--subnet',SUBNET,'--ip-range',POOL,NAME])
            created=True
            assert inspect(review,'network','inspect','--format','{{.Internal}}',network.strip())=='true'
            for role,extra in (('static',['--ip',STATIC]),('dynamic',[])):
                await op('start-'+role,[*container(role),'-d',*extra,'--network-alias','aeep-redis-'+role,
                    '--tmpfs','/data:rw,noexec,nosuid,nodev,size=4m','--entrypoint','redis-server',review['redis_image'],
                    '--bind','0.0.0.0','--protected-mode','yes','--requirepass','aeep-public-fixture','--save','',
                    '--appendonly','no'])
            template='{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'
            assigned=inspect(review,'inspect','--format',template,NAME+'-static',NAME+'-dynamic').splitlines()
            assert assigned[0]==STATIC and ipaddress.ip_address(assigned[1]) in ipaddress.ip_network(POOL)
            await asyncio.sleep(1)
            rows=await op('probe-paths',[*container('client'),'--add-host','redis:'+STATIC,
                '--entrypoint','node',review['node_image'],'-e',(HERE/'probe.cjs').read_text(),*assigned],output='json')
            assert set(rows)=={'static_ip','static_dns','static_hosts_entry','dynamic_ip','dynamic_dns'}
            outcome.update(passed=True,cases=rows,static_redis_ip=assigned[0],dynamic_redis_ip=assigned[1])
        except BaseException as error:
            outcome['error_type']=type(error).__name__
        finally:
            clock=time.perf_counter()
            try:
                owned=inspect(review,'ps','-aq','--filter','label='+label).splitlines()
                for item in owned:
                    current=inspect(review,'inspect','--format','{{.Name}}',item)
                    assert current in {'/'+NAME+'-'+name for name in ('static','dynamic','client')}
                    inspect(review,'stop','--time','2',item)
                assert not inspect(review,'ps','-aq','--filter','label='+label)
                if created:
                    assert inspect(review,'network','inspect','--format','{{index .Labels "com.aeep.engineering.owner"}}',NAME)==NAME
                    inspect(review,'network','rm',NAME)
                outcome['owned_cleanup_verified']=True
                elapsed=time.perf_counter()-clock
                repo.finish_operation(cleanup,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            except BaseException as error:
                outcome.update(passed=False,owned_cleanup_verified=False,cleanup_error_type=type(error).__name__)
            ledger=repo.operation_ledger(request.plan_id)
            write('operation-ledger.json',ledger.model_dump(mode='json'))
            outcome['accounting_settled']=all(item.elapsed_seconds is not None for item in ledger.operations)
            outcome['passed']=outcome['passed'] and outcome['accounting_settled']
            write('result.json',outcome)
    print(json.dumps(outcome))
    return int(not outcome['passed'])


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute')
    args=parser.parse_args()
    if args.prepare:
        freeze()
    else:
        path=HERE/'operation-review.json'
        assert args.execute==sha(path)
        raise SystemExit(asyncio.run(run(read(path),args.execute)))
