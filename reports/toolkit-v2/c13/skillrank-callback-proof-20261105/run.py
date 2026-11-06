"""Build the retained SkillRank core and exercise its real bounded callback path."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import time
from datetime import timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT/'.aeep'/HERE.name
ORIGINAL = ROOT/'.aeep/skillrank-build-preparation-20261103/context/source'
VENDOR = ROOT/'.aeep/skillrank-license-correction-20261103/runtime/vendor'
BRIDGE = ROOT/'integrations/toolkit/skillrank/bridge.rs'
PRIOR = HERE.parent/'skillrank-license-correction-20261103'
AUTH = HERE.parent/'pipeline-standing-authority-20261104.json'
SALES = HERE.parent/'skillsbench-managed-worker-preparation-20261105/engineering-dispatch-review.json'
DOCKER = ['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock']
CASE = 'json-format-fixture'
ARMS = ('control','treatment')


class Scope(StrictModel):
    review_sha256: str


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()


def tree(path):
    files = {}
    for file in sorted(path.rglob('*')):
        assert not file.is_symlink()
        if file.is_file():
            files[file.relative_to(path).as_posix()]=sha(file)
    return files


def write(path, value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


def inspect(*args):
    return subprocess.check_output([*DOCKER,*args],text=True,timeout=20).strip()


def freeze():
    prior=read(PRIOR/'operation-review.json')
    result=read(PRIOR/'runtime-execution/summary.json')
    assert result['passed'] and content_digest(tree(VENDOR))==result['vendor_tree_sha256']
    assert inspect('image','inspect','--format','{{.Id}}',result['compiler_image']['Id'])==result['compiler_image']['Id']
    grader=read(SALES)['cases'][0]['grader_image_id']
    assert inspect('image','inspect','--format','{{.Id}}',grader)==grader
    assert shutil.disk_usage(ROOT).free > 52*1024**3
    # Check the source portion of the earlier frozen context.
    context=ORIGINAL.parent
    assert content_digest(tree(context)) == prior['build_context_sha256']
    overlay=WORK/'source'
    if WORK.exists():
        assert list(WORK.iterdir())==[overlay] and tree(overlay)==tree(ORIGINAL)
    else:
        WORK.mkdir(mode=0o700)
        shutil.copytree(ORIGINAL,overlay)
    extension=overlay/'crates/skillrank/src/bin/aeep-skillrank-bridge.rs'
    parent=extension.parent.parent
    original_mode=parent.stat().st_mode & 0o777
    parent.chmod(original_mode|0o200)
    try:
        extension.parent.mkdir()
        shutil.copyfile(BRIDGE,extension)
        extension.chmod(0o444)
        extension.parent.chmod(0o555)
    finally:
        parent.chmod(original_mode)
    expected=tree(ORIGINAL)|{extension.relative_to(overlay).as_posix():sha(BRIDGE)}
    assert tree(overlay)==expected
    review={'scope':'One offline build of a new bridge binary and a zero-model callback check with two synthetic isolated task runs.',
        'source_sha256':verification_source_digest(ROOT),'upstream_revision':prior['source_revision'],
        'upstream_cargo_lock_sha256':sha(ORIGINAL/'Cargo.lock'),'source_tree_sha256':content_digest(expected),
        'vendor_tree_sha256':result['vendor_tree_sha256'],'compiler_image':result['compiler_image']['Id'],
        'fixture_image':grader,'runner_sha256':sha(HERE/'run.py'),'bridge_sha256':sha(BRIDGE),
        'docker_sha256':sha(Path(DOCKER[0]).resolve()),'ledger':prior['original_ledger'],
        'standing_authority_sha256':sha(AUTH),'maximum_operations':8,'maximum_reserved_seconds':850,
        'models':0,'cash_usd':'0','network':'none','automatic_retries':False,
        'comparison_usefulness':'NOT_ASSESSED','existing_resources_preserved':True}
    write(HERE/'operation-review.json',review)
    print(sha(HERE/'operation-review.json'))


def config(argv, timeout, output, *, stdin=False):
    return {'argv':argv,'argv_literal':True,'inherit_env':False,'env':{'PATH':'/usr/bin:/bin','LC_ALL':'C'},
            'timeout_seconds':timeout,'max_output_bytes':65536,'output':output,'stdin_json':stdin}


async def execute(review, identity):
    assert not (HERE/'started.json').exists()
    assert review['source_sha256']==verification_source_digest(ROOT)
    assert review['runner_sha256']==sha(HERE/'run.py') and review['bridge_sha256']==sha(BRIDGE)
    assert review['standing_authority_sha256']==sha(AUTH)
    assert review['docker_sha256']==sha(Path(DOCKER[0]).resolve())
    assert content_digest(tree(WORK/'source'))==review['source_tree_sha256']
    assert content_digest(tree(VENDOR))==review['vendor_tree_sha256']
    assert shutil.disk_usage(ROOT).free > 52*1024**3
    for folder in ('target','home','tmp','responses'):
        (WORK/folder).mkdir(mode=0o700)
    # The build user is the owning host UID. The runtime gets only a readable
    # directory of nonsecret, immutable grade certificates.
    (WORK/'responses').chmod(0o755)
    write(HERE/'started.json',{'review_sha256':identity,'models':0})
    scope=Scope(review_sha256=identity);ref=content_digest(scope)
    grant=AssessmentAuthorization(authorization_id=HERE.name,subject_digests=[ref],recipe_digests=[ref],
        environment_digests=[ref],limits=AssessmentLimits(max_operations=review['maximum_operations'],
            max_elapsed_seconds=review['maximum_reserved_seconds']),
        expires_at=utc_now()+timedelta(minutes=40),allowed_destinations=['local'],remote_disclosure=False)
    request=RecipeMaterializationRequest(plan_id=HERE.name,subject_digest=ref,recipe_digest=ref,mapping_digest=ref,
        environment_digest=ref,authorization_id=grant.authorization_id,definition_digests=[ref],seed=0)
    result={'passed':False,'models':0,'comparisons':'PAUSED','bounded_live_evaluation':'OPEN'}
    phase='compile'
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        repo.put('skillrank_callback_proof_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})

        async def operation(name,spec,payload,runner,*,nested=lambda:0.):
            ident=request.plan_id+':'+name
            seconds=float(spec.config['timeout_seconds'])+10
            repo.reserve(request,ident,AssessmentLimits(max_operations=1,max_elapsed_seconds=seconds),stage=name)
            started=utc_now();clock=time.perf_counter();raw=None
            try:
                raw=await runner.execute(ExecutionContext(
                    request=ActionRequest(action_id=ident,capability=spec.capability,input=payload),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=ident,approved_side_effect=SideEffect.WRITE))
                return raw
            finally:
                elapsed=max(0.,time.perf_counter()-clock-nested())
                resources=ResourceVector(latency_ms=elapsed*1000)
                receipt=ExecutionReceipt(decision_id=ident,action_id=ident,capability=spec.capability,
                    executor_id=spec.id,executor_kind='command',status=raw.status if raw else 'failed',
                    started_at=started,ended_at=utc_now(),estimated={},actual_resources=resources,
                    execution_success=raw is not None and raw.status.value=='success',
                    error_type=raw.error_type if raw else None,
                    metadata={'review_sha256':identity,'nested_intervals_excluded_seconds':nested(),
                        'stderr_sha256':hashlib.sha256((raw.stderr or '').encode()).hexdigest() if raw else None})
                store.save_receipt(receipt)
                repo.finish_operation(ident,elapsed_seconds=elapsed,resources=resources)
                write(HERE/(name+'-receipt.json'),receipt.model_dump(mode='json'))

        def spec(name, argv, timeout, output, stdin=False):
            return ExecutorSpec(id='skillrank.'+name,capability='toolkit.upstream-engineering@1',
                kind='command',side_effect='write',description='Finite selected SkillRank callback engineering check',
                config=config(argv,timeout,output,stdin=stdin))

        def container(role,uid):
            return [*DOCKER,'run','--pull=never','--rm','--name','aeep-sr-callback-'+role,
                    '--label','com.aeep.engineering.owner='+HERE.name,'--network=none','--read-only',
                    '--user',uid,'--cap-drop=ALL','--security-opt=no-new-privileges','--cpus=2',
                    '--memory=2g','--memory-swap=2g','--pids-limit=256',
                    '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=64m']

        def bind(source,target,writable=False):
            return ['--mount','type=bind,src='+str(source)+',dst='+target+('' if writable else ',readonly')]

        try:
            assert not inspect('ps','-aq','--filter','label=com.aeep.engineering.owner='+HERE.name)
            docker=container('build',f'{os.getuid()}:{os.getgid()}')
            argv=[*docker,*bind(WORK/'source','/source'),*bind(VENDOR,'/vendor'),*bind(WORK/'target','/target',True),
                  '--workdir','/source','--env','HOME=/tmp','--env','CARGO_HOME=/tmp/cargo',
                  '--env','RUSTUP_AUTO_INSTALL=0',review['compiler_image'],'cargo','build','--release','--locked',
                  '--offline','--jobs','2','--package','skillrank','--bin','aeep-skillrank-bridge',
                  '--target-dir','/target','--config','source.crates-io.replace-with="vendored-sources"',
                  '--config','source.vendored-sources.directory="/vendor"']
            builder=CommandExecutor()
            try:
                built=await operation('build',spec('build',argv,400,{'type':'text'}),{},builder)
            finally:
                await builder.close()
            if built.status.value!='success':
                # Only compiler diagnostics for the public source and bounded build.
                (HERE/'build-diagnostic.txt').write_text((built.stderr or '')[-8000:])
                raise RuntimeError('Reviewed offline bridge build failed')
            binary=WORK/'target/release/aeep-skillrank-bridge'
            result['bridge_binary_sha256']=sha(binary)
            assert sha(WORK/'source/Cargo.lock')==review['upstream_cargo_lock_sha256']
            phase='real upstream callback'
            argv=[*container('runner','65534:65534'),'-i',*bind(binary,'/opt/aeep-skillrank-bridge'),
                  *bind(WORK/'responses','/responses'),'--entrypoint','/opt/aeep-skillrank-bridge',review['compiler_image']]
            token=content_digest({'review':identity,'binary':result['bridge_binary_sha256']})
            payload={'case_id':CASE,'skill_slug':'aeep-fixture',
                     'skill_sha256':hashlib.sha256(b'engineering identity only').hexdigest(),
                     'run_token':token,'timeout_seconds':40}
            queue=asyncio.Queue(maxsize=2);buffer=bytearray()
            settled={};nested=0.

            def observe(chunk):
                buffer.extend(chunk)
                if len(buffer)>16384:
                    raise ValueError('Unexpected SkillRank frame length')
                while b'\n' in buffer:
                    line,_,rest=buffer.partition(b'\n');buffer[:]=rest
                    message=json.loads(line)
                    if message['kind']!='done':
                        queue.put_nowait(message)

            async def dispatch():
                nonlocal nested
                env=AssessmentEnvironment(environment_id='skillrank-offline-fixture',kind='container',
                    identity={'review':identity},container_image=review['fixture_image'],
                    container_runtime=DOCKER[0],container_socket=DOCKER[2].removeprefix('unix://'),
                    memory_mb=512,process_limit=64)
                for arm in ARMS:
                    message=await queue.get()
                    assert message=={'kind':'trial','run_token':token,'case_id':CASE,'arm':arm}
                    clock=time.perf_counter()
                    worker=ContainerExecutor(env)
                    # Two controlled plumbing fixtures, not candidate runs.
                    program=("import json,sys; d=json.load(sys.stdin); "
                             "print(json.dumps({'formatted':json.dumps(json.loads(d['raw']), sort_keys="
                             +str(arm=='control')+",separators=(',',':'))}))")
                    fixture=ExecutorSpec(id='skillrank.fixture',capability='toolkit.upstream-engineering@1',
                        kind='command',side_effect='read',description='Local synthetic JSON formatting fixture',
                        config={'argv':['python3','-I','-B','-c',program],'argv_literal':True,'stdin_json':True,
                                'timeout_seconds':12,'output':{'type':'json'}})
                    try:
                        raw=await operation('fixture-'+arm,fixture,{'raw':'{"z":2,"a":1}'},worker)
                        assert raw.status.value=='success'
                        assert isinstance(raw.output,dict) and set(raw.output)=={'formatted'}
                        # Grading stays in the coordinator. Only its binary certificate leaves.
                        valid=raw.output['formatted']=='{"a":1,"z":2}'
                        assert valid==(arm=='control')
                        receipt=read(HERE/('fixture-'+arm+'-receipt.json'))
                        grade={'case_id':CASE,'arm':arm,'verified':valid,'receipt_sha256':content_digest(receipt)}
                        write(HERE/('fixture-'+arm+'-grade.json'),grade)
                        row={'run_token':token,'case_id':CASE,'arm':arm,'trial_ref':content_digest(grade),'canonical_valid':valid}
                        temp=WORK/'responses'/(arm+'.tmp')
                        write(temp,row);temp.chmod(0o444)
                        os.link(temp,WORK/'responses'/(arm+'.json'),follow_symlinks=False)
                        temp.unlink()
                        settled[arm]={'arm':arm,'trial_ref':row['trial_ref'],'canonical_valid':valid}
                    finally:
                        await worker.close()
                        nested+=time.perf_counter()-clock

            scheduler=CommandExecutor(stdout_observer=observe)
            child=asyncio.create_task(operation('skillrank-callback',
                spec('callback',argv,100,{'type':'jsonl','match':{'kind':'done'}},True),payload,scheduler,
                nested=lambda:nested))
            parent=asyncio.create_task(dispatch())
            try:
                done,_=await asyncio.wait({child,parent},return_when=asyncio.FIRST_COMPLETED)
                if parent in done:
                    await parent
                raw=await child
                assert parent.done()
                await parent
                assert raw.status.value=='success' and not buffer and queue.empty()
                assert raw.output=={'kind':'done','run_token':token,'harness':'skillrank-runner',
                    'harness_version':'0.1.0','trials':[settled[arm] for arm in ARMS],
                    'upstream_numeric_fields_excluded':True}
                result.update(passed=True,real_upstream_harness=raw.output['harness'],
                              harness_version=raw.output['harness_version'],trials=raw.output['trials'],
                              upstream_numeric_fields_excluded=True)
            finally:
                for task in (parent,child):
                    if not task.done():
                        task.cancel()
                await asyncio.gather(parent,child,return_exceptions=True)
                await scheduler.close()
        except BaseException as error:
            result.update(error_type=type(error).__name__,stopped_phase=phase)
        finally:
            owned=inspect('ps','-aq','--filter','label=com.aeep.engineering.owner='+HERE.name)
            result['owned_containers_removed']=not bool(owned)
            result['passed']=result['passed'] and not owned
            ledger=repo.operation_ledger(request.plan_id)
            write(HERE/'operation-ledger.json',ledger.model_dump(mode='json'))
            result['settled_operations']=sum(item.elapsed_seconds is not None for item in ledger.operations)
            result['accounting_settled']=all(item.elapsed_seconds is not None for item in ledger.operations)
            result['passed']=result['passed'] and result['accounting_settled']
            write(HERE/'result.json',result)
    print(json.dumps(result))
    return int(not result['passed'])


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
        raise SystemExit(asyncio.run(execute(read(path),args.execute)))
