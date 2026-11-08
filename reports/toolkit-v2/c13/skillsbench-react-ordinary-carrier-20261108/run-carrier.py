"""Build and exercise the pinned React grader through ContainerExecutor."""

import argparse
import asyncio
import importlib.util
import json
import shutil
import subprocess
import time
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import decode_patch
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CALIBRATION = HERE.parent/'skillsbench-react-nonroot-calibration-20261108'
WORK = ROOT/'.aeep'/HERE.name
REVIEW = HERE/'runtime-review.json'
IMAGE = 'aeep-skillsbench-react:protected-amd64-20261108'
GRANT = 'skillsbench-react-ordinary-grader-20261108'
RESERVE = 50 * 1024**3


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stage = load('staged_react_build', HERE/'stage-carrier.py')
guest = load('reviewed_react_grader', HERE/'grade.py')


class Scope(StrictModel):
    review_sha256: str
    source_sha256: str


def docker(review, *args, timeout=20):
    return subprocess.run([*review['docker'], *args], env=review['env'], cwd=WORK,
                          capture_output=True, timeout=timeout, text=True)


def image(review, name):
    fmt = '{{.Id}} {{.Os}}/{{.Architecture}} {{json .RootFS.Layers}} {{json (index .Config "User")}} {{json (index .Config "Volumes")}}'
    result = docker(review, 'image', 'inspect', '--format', fmt, name)
    if result.returncode:
        return None
    identity, platform, layers, user, volumes = result.stdout.strip().split(' ', 4)
    return {'id': identity, 'platform': platform, 'layers': json.loads(layers),
            'user': json.loads(user), 'volumes': json.loads(volumes)}


def freeze():
    reference = stage.read(CALIBRATION/'operation-review.json')
    measured = stage.read(CALIBRATION/'result.json')
    assert measured['passed'] and measured['cleanup_verified']
    assert measured['observed']['peak_used_bytes_above_start']['/tmp'] <= 128*1024**2
    prepare = stage.read(HERE/'carrier-preparation.json')
    prior = stage.read(HERE.parent/'skillsbench-document-managed-20261106/excel-build-continuation/build-review.json')
    docker_prefix = [prior['docker'], '--config', prior['docker_config'], '--host', 'unix://'+prior['docker_socket']]
    review = {
        'scope':'One retained AMD64 COPY-only build and four protected ordinary-executor checks.',
        'source_sha256':verification_source_digest(ROOT),
        'pins':{str(path):stage.sha(path) for path in (
            Path(__file__),HERE/'stage-carrier.py',HERE/'grade.py',HERE/'verify-source.py',HERE/'carrier-preparation.json',
            HERE/'acquisition-continuation-result.json',CALIBRATION/'result.json',CALIBRATION/'operation-review.json',
            WORK/'controls.json',WORK/'context-inventory.json',Path(prior['docker']),
            Path(prior['docker_config'])/'config.json',
        )},
        'docker':docker_prefix,
        'env':{'HOME':str(WORK),'PATH':'/usr/bin:/bin','LC_ALL':'C','DOCKER_BUILDKIT':'1'},
        'image':IMAGE,'parent_id':reference['image'],'parent_tag':prepare['parent_tag'],
        'context_sha256':prepare['context_sha256'],'scratch_mib':160,'memory_mib':4096,'cpu':4,'pids':384,
        'maximum_operations':6,'maximum_reserved_seconds':435,
        'model_turns':0,'cash_usd':'0','network_inside_containers':False,
        'automatic_retries':False,'comparisons':'PAUSED',
        'retention':'Keep both image tags. Remove only fresh, owned grader containers.',
        'expires_at':(utc_now()+timedelta(hours=8)).isoformat(),
        'ledger':reference['ledger'],
    }
    parent=image(review,review['parent_id'])
    assert parent and parent['id']==review['parent_id'] and parent['platform']=='linux/amd64' and not parent['volumes']
    review['parent']=parent
    usage=docker(review,'system','df','--format','{{.Type}} {{.Size}}')
    assert usage.returncode==0
    review['docker_usage']=usage.stdout.splitlines()
    review['argv']={
        'tag':[*docker_prefix,'image','tag',review['parent_id'],review['parent_tag']],
        'build':[*docker_prefix,'build','--pull=false','--network=none','--platform=linux/amd64','--builder=default',
                 '--provenance=false','--sbom=false','--iidfile',str(WORK/'image-id'),'--tag',IMAGE,str(stage.CONTEXT)],
    }
    stage.write(REVIEW,review)


def preflight(review, identity):
    assert stage.sha(REVIEW)==identity and datetime.fromisoformat(review['expires_at'])>utc_now()
    assert verification_source_digest(ROOT)==review['source_sha256']
    assert shutil.disk_usage(ROOT).free >= RESERVE+3*1024**3
    assert not (HERE/'runtime-started.json').exists() and not (WORK/'image-id').exists()
    assert all(stage.sha(Path(path))==expected for path,expected in review['pins'].items())
    assert content_digest(stage.inventory())==review['context_sha256']
    assert not image(review,review['parent_tag']) and not image(review,IMAGE)
    assert image(review,review['parent_id'])==review['parent']
    builder=docker(review,'buildx','inspect','default')
    assert builder.returncode==0 and 'Driver:        docker' in builder.stdout and 'linux/amd64' in builder.stdout
    files=stage.read(WORK/'context/protected/pins.json')
    controls=stage.read(WORK/'controls.json')
    task=controls['input']['task_archive_sha256']
    assert files['task_archive_sha256']==task and 'patches' not in files
    assert len(controls['variants'])==4
    for variant in controls['variants']:
        try:
            guest.checked_changes(variant['artifact'],task,files['app_files'],decode_patch)
        except ValueError:
            assert variant['failure_code']=='output_contract'
        else:
            assert variant['failure_code']!='output_contract'
    return controls


async def execute(review, identity, controls):
    checks=stage.read(WORK/'verification/checks.json')
    assert checks['source_before']==checks['source_after']==review['source_sha256']
    assert len(checks['checks'])==13 and all(row['exit_code']==0 for row in checks['checks'])
    scope=Scope(review_sha256=identity,source_sha256=review['source_sha256'])
    digest=content_digest(scope)
    limits=AssessmentLimits(max_operations=6,max_elapsed_seconds=435)
    grant=AssessmentAuthorization(authorization_id=GRANT,subject_digests=[digest],recipe_digests=[digest],
        environment_digests=[digest],limits=limits,allowed_destinations=['local'],remote_disclosure=False,
        expires_at=datetime.fromisoformat(review['expires_at']))
    request=RecipeMaterializationRequest(plan_id=GRANT,subject_digest=digest,recipe_digest=digest,
        mapping_digest=digest,environment_digest=digest,authorization_id=GRANT,definition_digests=[digest],seed=0)
    stage.write(HERE/'runtime-started.json',{'review_sha256':identity})
    result={'review_sha256':identity,'passed':False,'models':0,'observations':{},'comparisons':'PAUSED'}
    with ReceiptStore(review['ledger']) as store:
        repo=AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(GRANT,)).fetchone()
        assert repo.put('toolkit_react_grader_scope',digest,scope)==digest
        repo.approve_bundle(grant,{digest:scope.model_dump(mode='json')})

        def invocation():
            repo.authorize(request)
            assert shutil.disk_usage(ROOT).free>=RESERVE
            assert verification_source_digest(ROOT)==review['source_sha256']
            return identity

        async def operation(name, executor, spec, reservation, data, check):
            operation_id=GRANT+':'+name
            repo.reserve(request,operation_id,AssessmentLimits(max_operations=1,max_elapsed_seconds=reservation),stage=name)
            clock,started=time.perf_counter(),utc_now()
            facts=None
            failure=None
            try:
                invocation()
                context=ExecutionContext(request=ActionRequest(action_id=operation_id,capability=spec.capability,input=data),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation_id,
                    approved_side_effect=spec.side_effect,invocation_check=invocation)
                raw=await executor.execute(context)
                facts=check(raw,context)
                return facts
            except Exception as error:
                failure=type(error).__name__
                if isinstance(error, AssertionError) and error.args and isinstance(error.args[0],str):
                    label=error.args[0]
                    if label.replace('_','').isalnum() and len(label)<=60:
                        failure=label
                raise
            finally:
                await executor.close()
                elapsed=time.perf_counter()-clock
                receipt=ExecutionReceipt(decision_id=operation_id,action_id=operation_id,capability=spec.capability,
                    executor_id=spec.id,executor_kind=spec.kind,status='success' if facts is not None else 'failed',
                    started_at=started,ended_at=utc_now(),estimated=spec.estimate,
                    actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=facts is not None,
                    error_type=failure,metadata={'review_sha256':identity,'observation':facts,
                                                'observed_resource_dimensions':['latency_ms']})
                store.save_receipt(receipt)
                repo.finish_operation(operation_id,elapsed_seconds=elapsed,resources=receipt.actual_resources)
                stage.write(HERE/(name+'-receipt.json'),receipt.model_dump(mode='json'))

        try:
            for name,timeout,reservation in (('tag',5,10),('build',150,165)):
                destination=review['parent_tag'] if name=='tag' else IMAGE
                assert image(review,destination) is None
                spec=ExecutorSpec(id='skillsbench.react.'+name,capability='toolkit.upstream-engineering@1',
                    kind='command',description='Offline reviewed React carrier preparation',side_effect=SideEffect.WRITE,
                    config={'argv':review['argv'][name],'argv_literal':True,'inherit_env':False,'env':review['env'],
                            'cwd':str(WORK),'timeout_seconds':timeout,'max_output_bytes':65536,'output':{'type':'text'}})

                def confirm(raw,_context):
                    assert raw.exit_code==0, raw.error_type or 'docker_command_failed'
                    if name=='tag':
                        parent=image(review,review['parent_tag'])
                        assert parent==review['parent']
                        return parent
                    built=image(review,IMAGE)
                    assert built and built['id']==(WORK/'image-id').read_text().strip()
                    assert built['platform']=='linux/amd64' and built['user']=='65534:65534' and not built['volumes']
                    assert built['layers'][:-4]==review['parent']['layers']
                    return built

                result[name]=await operation(name,CommandExecutor(),spec,reservation,{},confirm)

            environment=AssessmentEnvironment(environment_id='react-protected-20261108',kind='container',
                identity={'review_sha256':identity},container_image=result['build']['id'],
                container_runtime=review['docker'][0],container_socket=review['docker'][-1].removeprefix('unix://'),
                network=False,cpu_count=review['cpu'],memory_mb=review['memory_mib'],process_limit=review['pids'],
                container_tmpfs_mb=review['scratch_mib'])
            stage.write(HERE/'environment.json',environment.model_dump(mode='json'))
            spec=ExecutorSpec(id='skillsbench.react.grader',capability='assessment.skillsbench.react@1',
                kind='command',description='Original React verifier on a bounded source artifact',
                side_effect=SideEffect.READ,config={'argv':['/usr/bin/python3','-I','-B',
                    '/opt/aeep-react-reference/grade.py',str(ROOT/'src')],'argv_literal':True,'stdin_json':True,
                    'timeout_seconds':60,'max_output_bytes':32768,'output':{'type':'json'}})
            stage.write(HERE/'grader-spec.json',spec.model_dump(mode='json'))
            for row in controls['variants']:
                name=row['name']
                executor=ContainerExecutor(environment)
                from aeep.assessment.containment import container_name
                container=container_name(GRANT+':'+name)
                listed=docker(review,'ps','-aq','--filter','name=^/'+container+'$')
                assert listed.returncode==0 and not listed.stdout.strip()

                def confirm_grade(raw,context):
                    assert raw.status.value=='success', raw.error_type or 'contained_program_failed'
                    assert raw.output=={'valid':[row['valid']],'failure_codes':[row['failure_code']]}
                    argv,container=executor.command(context)
                    assert argv[argv.index('--user')+1]=='65534:65534'
                    assert argv[argv.index('--tmpfs')+1]=='/tmp:rw,noexec,nosuid,nodev,size=160m'
                    assert argv[argv.index('--network')+1]=='none' and '--read-only' in argv
                    listed=docker(review,'ps','-aq','--filter','name=^/'+container+'$')
                    assert listed.returncode==0 and not listed.stdout.strip()
                    return {'valid':row['valid'],'failure_code':row['failure_code'],
                            'binary_score':int(row['valid']),'owned_container_removed':True}

                data={'examples':[{'input':controls['input'],'output':row['artifact'],
                    'expected':{'task_archive_sha256':controls['input']['task_archive_sha256']}}]}
                result['observations'][name]=await operation(name,executor,spec,65,data,confirm_grade)
            result['passed']=True
        except Exception as error:
            result['error_type']=type(error).__name__
        finally:
            ledger=repo.operation_ledger(GRANT)
            result['accounting_settled']=all(row.elapsed_seconds is not None for row in ledger.operations)
            result['operations']=len(ledger.operations)
            stage.write(HERE/'runtime-ledger.json',ledger.model_dump(mode='json'))
            stage.write(HERE/'runtime-result.json',result)
    print(json.dumps(result))
    return result['passed'] and result['accounting_settled']


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    flags=parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze',action='store_true')
    flags.add_argument('--preflight')
    flags.add_argument('--execute-approved')
    args=parser.parse_args()
    if args.freeze:
        freeze()
    identity=stage.sha(REVIEW) if args.freeze else args.preflight or args.execute_approved
    review=stage.read(REVIEW)
    controls=preflight(review,identity)
    if args.execute_approved:
        assert stage.read(HERE/'runtime-approval.json')=={'approved':True,'review_sha256':identity}
        raise SystemExit(not asyncio.run(execute(review,identity,controls)))
    print(json.dumps({'passed':True,'review_sha256':identity,'models':0,'build_or_grader_run':False}))
