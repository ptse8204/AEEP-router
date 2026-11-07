"""Build the two protected grader images under an exact finite local grant."""

import argparse
import asyncio
import importlib.util
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutorSpec,
    ResourceVector,
    SideEffect,
    StrictModel,
    utc_now,
)
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]

spec = importlib.util.spec_from_file_location('protected_image_inputs', HERE.parents[1]/'skillsbench-contained-graders-20261105/prepare-images.py')
assert spec and spec.loader
inputs_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inputs_module)


class Scope(StrictModel):
    purpose: str
    review_sha256: str


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


async def build(review, identity):
    work = Path(review['work'])
    out = HERE/'build-execution'
    out.mkdir(mode=0o700)
    write(HERE/'build-started.json', {'review_sha256': identity})
    docker = [review['docker'],'--config',review['docker_config'],'--host','unix://'+review['docker_socket']]
    env = {'HOME':str(work),'PATH':'/usr/bin:/bin','LC_ALL':'C','DOCKER_BUILDKIT':'1'}

    def inspect(name):
        result = subprocess.run([*docker,'image','inspect','--format','{{json .}}',name],
                                env=env,capture_output=True,timeout=15)
        return json.loads(result.stdout) if result.returncode == 0 else None

    facts = {'models':0,'cash_usd':'0','comparison':'PAUSED','images':{}}
    parent = inspect(review['parent']['reference'])
    assert parent and parent['Id'] == review['parent']['id']
    assert parent['RootFS']['Layers'] == review['parent']['layers']
    assert parent['Os']=='linux' and parent['Architecture']=='arm64'
    scope = Scope(purpose='Protected offline COPY-only SkillsBench packaging', review_sha256=identity)
    binding = content_digest(scope)
    limits = AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=150)
    grant = AssessmentAuthorization(
        authorization_id=review['grant_id'],subject_digests=[binding],recipe_digests=[binding],
        environment_digests=[binding],limits=limits,remote_disclosure=False,allowed_destinations=['local'],
        expires_at=datetime.fromisoformat(review['expires_at']),
    )
    request = RecipeMaterializationRequest(
        plan_id=review['grant_id'],subject_digest=binding,recipe_digest=binding,environment_digest=binding,
        mapping_digest=binding,authorization_id=grant.authorization_id,definition_digests=[binding],seed=0,
    )
    contexts = inputs_module.read(Path(review['private_inventory']))['contexts']
    with ReceiptStore(review['ledger']) as store:
        repository = AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        assert repository.put('toolkit_skillsbench_build_scope',binding,scope)==binding
        repository.approve_bundle(grant,{binding:scope.model_dump(mode='json')})
        for context in contexts:
            role, tag = context['role'], context['image_tag']
            path = Path(context['context'])
            assert not inspect(tag), tag
            assert all(inputs_module.digest(Path(p))==value for p,value in review['pins'].items())
            assert inputs_module.inventory(path)==context['files']
            assert 'RUN ' not in (path/'Dockerfile').read_text()
            operation = request.plan_id+':'+role
            repository.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=150),stage='protected_grader_packaging')
            iid = work/(role+'-image-id')
            assert not iid.exists()
            executor = ExecutorSpec(id='skillsbench.build.'+role,capability='toolkit.upstream-engineering@1',
                kind='command',side_effect='write',description='Offline protected grader COPY build',
                config={'argv':[*docker,'build','--pull=false','--network=none','--platform=linux/arm64','--builder=default',
                                '--provenance=false','--sbom=false','--iidfile',str(iid),'--tag',tag,str(path)],
                        'argv_literal':True,'inherit_env':False,'env':env,'cwd':str(work),
                        'timeout_seconds':125,'max_output_bytes':65536,'output':{'type':'text'}})
            runner = CommandExecutor()
            started, clock = utc_now(), time.perf_counter()
            raw = None
            failure = None
            image = None

            def check():
                repository.authorize(request)
                assert shutil.disk_usage(ROOT).free >= 52*1024**3
                assert all(inputs_module.digest(Path(p))==value for p,value in review['pins'].items())
                return identity

            try:
                raw = await runner.execute(ExecutionContext(
                    request=ActionRequest(action_id=operation,capability=executor.capability),
                    spec=executor,estimate=executor.estimate,attempt=1,attempt_id=operation,
                    approved_side_effect=SideEffect.WRITE,invocation_check=check))
                assert raw.exit_code==0 and iid.is_file()
                output_id = iid.read_text().strip()
                assert re.fullmatch(r'sha256:[0-9a-f]{64}',output_id)
                built = inspect(tag)
                assert built and built['Id']==output_id and built['Architecture']=='arm64'
                layers = built['RootFS']['Layers']
                assert layers[:-1]==review['parent']['layers']
                assert built['Config']['User']=='65534:65534' and not built['Config'].get('Volumes')
                image = dict(image_id=output_id,tag=tag,layers=layers,binding_sha256=context['binding_sha256'])
            except Exception as error:
                failure = type(error).__name__
                if raw is not None:
                    write(out/(role+'-exit.json'),{'exit_code':raw.exit_code, 'stderr_sha256':__import__('hashlib').sha256((raw.stderr or '').encode()).hexdigest()})
                # Build progress is private and may contain host paths. Keep only a bounded error class.
                if raw and raw.stderr:
                    failure = next((item for item in ('pull access denied','no such image','not found','permission denied')
                                    if item in raw.stderr.lower()),failure)
            finally:
                await runner.close()
                elapsed = time.perf_counter()-clock
                receipt = ExecutionReceipt(decision_id=operation,action_id=operation,capability=executor.capability,
                    executor_id=executor.id,executor_kind='command',status='success' if image else 'failed',
                    started_at=started,ended_at=utc_now(),estimated=executor.estimate,
                    actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=image is not None,
                    error_type=failure,metadata={'review_sha256':identity,'observed_resource_dimensions':['latency_ms'],
                                                'image':image,'raw_stream_retained':False})
                store.save_receipt(receipt)
                repository.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
                write(out/(role+'-receipt.json'),receipt.model_dump(mode='json'))
                facts['images'][role] = image or {'failure':failure}
        ledger = repository.operation_ledger(request.plan_id)
        write(out/'ledger.json',ledger.model_dump(mode='json'))
        facts['passed'] = len(facts['images'])==1 and all('image_id' in entry for entry in facts['images'].values())
        facts['accounting_settled'] = all(entry.elapsed_seconds is not None for entry in ledger.operations)
        facts['verifiers_executed'] = 0
    write(out/'summary.json',facts)
    print(json.dumps(facts))
    return facts['passed'] and facts['accounting_settled']


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated',required=True)
    args = parser.parse_args()
    review_path = HERE/'build-review.json'
    review = inputs_module.read(review_path)
    identity = inputs_module.digest(review_path)
    authority = inputs_module.read(HERE/'build-authority.json')
    assert args.execute_delegated==identity==authority['review_sha256'] and authority['first_attempt'] is True
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'])
    assert shutil.disk_usage(ROOT).free >= 52*1024**3
    assert not (HERE/'build-started.json').exists()
    assert all(inputs_module.digest(Path(p))==value for p,value in review['pins'].items())
    raise SystemExit(not asyncio.run(build(review,identity)))
