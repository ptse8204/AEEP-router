"""Build and check the exact offline EvoAgentX runtime once, using canonical receipts."""

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
from aeep.assessment.verification import verification_source_digest
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


class Scope(StrictModel):
    purpose: str
    review_sha256: str


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def inventory(path):
    result = {}
    for file in path.rglob('*'):
        if file.is_symlink():
            result[str(file.relative_to(path))] = {'symlink':str(file.readlink())}
        elif file.is_file():
            result[str(file.relative_to(path))] = {'sha256':sha(file),'mode':file.stat().st_mode & 0o777}
    return result


async def run(review, identity):
    context = Path(review['context'])
    assert shutil.disk_usage(ROOT).free >= 53 * 1024**3
    assert verification_source_digest(ROOT) == review['implementation_source']
    assert datetime.fromisoformat(review['expires_at']) > utc_now()
    for name, expected in review['assets'].items():
        assert sha(name) == expected, name
    assert content_digest(inventory(context)) == review['context_inventory_sha256']
    docker = review['docker']
    env = review['environment']
    assert not subprocess.run([*docker,'image','inspect',review['tag']],env=env,timeout=10,capture_output=True).returncode == 0
    def inspect(ref):
        fmt = '{{json .Id}} {{json .Architecture}} {{json .Os}} {{json .RootFS.Layers}}'
        text = subprocess.check_output([*docker,'image','inspect','--format',fmt,ref],env=env,timeout=15,text=True)
        fields = []
        decoder = json.JSONDecoder()
        while text.strip():
            value, end = decoder.raw_decode(text.strip())
            fields.append(value)
            text = text.strip()[end:]
        return fields
    assert inspect(review['base_reference']) == review['base_identity']

    version = subprocess.check_output([*docker, 'version', '--format', '{{.Server.Version}} {{.Server.GitCommit}}'],
                                      env=env, timeout=10, text=True)
    assert version.strip() == review['docker_server']
    write(HERE/'evoagentx-runtime-started.json',{'review_sha256':identity})
    scope = Scope(purpose='Offline retained EvoAgentX runtime build and actual graph parsing',review_sha256=identity)
    ref = content_digest(scope)
    grant = AssessmentAuthorization(authorization_id='evoagentx-runtime-20261106',
        subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],
        limits=AssessmentLimits(max_operations=2,max_elapsed_seconds=340),
        expires_at=datetime.fromisoformat(review['expires_at']),allowed_destinations=['local'],remote_disclosure=False)
    request = RecipeMaterializationRequest(plan_id=grant.authorization_id,subject_digest=ref,
        recipe_digest=ref,mapping_digest=ref,environment_digest=ref,authorization_id=grant.authorization_id,
        definition_digests=[ref],seed=0)
    result = {'passed':False,'model_turns':0,'images_preserved':True,'review_sha256':identity}
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        repo.put('toolkit_evoagentx_runtime_scope',ref,scope)
        repo.approve_bundle(grant,{ref:scope.model_dump(mode='json')})

        async def operation(name, argv, timeout):
            ident = request.plan_id+':'+name
            repo.reserve(request,ident,AssessmentLimits(max_operations=1,max_elapsed_seconds=timeout+10),stage=name)
            spec = ExecutorSpec(id='evoagentx.runtime.'+name,capability='toolkit.upstream-engineering@1',
                kind='command',description='Reviewed offline EvoAgentX engineering check',side_effect='write',
                config={'argv':argv,'argv_literal':True,'inherit_env':False,'env':env,
                        'cwd':str(context.parent),'timeout_seconds':timeout,'max_output_bytes':65536,'output':{'type':'text'}})
            begin, now = time.perf_counter(), utc_now()
            runner, raw, evidence_ref, failure = CommandExecutor(), None, None, None
            try:
                with persist_execution_events(lambda key,event:repo.put('execution_event',key+':'+str(event.sequence),event)):
                    handle = await runner.start(ExecutionContext(
                        request=ActionRequest(action_id=ident,capability=spec.capability),spec=spec,
                        estimate=spec.estimate,attempt=1,attempt_id=ident,approved_side_effect=spec.side_effect,
                        invocation_check=lambda: (repo.authorize(request),identity)[1]))
                    while not handle.task.done():
                        await asyncio.wait({handle.task},timeout=1)
                        if shutil.disk_usage(ROOT).free < 50*1024**3:
                            await runner.cancel(handle)
                            raise RuntimeError('Storage reserve crossed')
                    raw = await handle.task
                evidence = ExecutionEvidence.model_validate(raw.metadata['execution_evidence'])
                assert evidence.complete and raw.exit_code == 0
                evidence_ref = repo.put('execution_evidence',evidence.digest(),evidence)
            except BaseException as error:
                failure = type(error).__name__
                if raw is not None:
                    (HERE/('evoagentx-runtime-'+name+'.log')).write_text((raw.stderr or '')[-8192:])
                raise
            finally:
                await runner.close()
                elapsed = time.perf_counter()-begin
                receipt = ExecutionReceipt(decision_id=ident,action_id=ident,capability=spec.capability,
                    executor_id=spec.id,executor_kind=spec.kind,status=raw.status if raw else 'failed',
                    started_at=now,ended_at=utc_now(),estimated=spec.estimate,
                    actual_resources=ResourceVector(latency_ms=elapsed*1000),
                    execution_success=failure is None,error_type=failure,
                    metadata={'review_sha256':identity,'execution_evidence_ref':evidence_ref,
                              'observed_resource_dimensions':['latency_ms']})
                store.save_receipt(receipt)
                repo.finish_operation(ident,elapsed_seconds=elapsed,resources=receipt.actual_resources)
                write(HERE/('evoagentx-runtime-'+name+'-receipt.json'),receipt.model_dump(mode='json'))
            return raw

        try:
            await operation('build',review['build_command'],240)
            ident, arch, os_name, layers = inspect(review['tag'])
            assert arch == 'arm64' and os_name == 'linux' and layers[:len(review['base_identity'][3])] == review['base_identity'][3]
            assert inspect(review['base_reference']) == review['base_identity']
            assert content_digest(inventory(context)) == review['context_inventory_sha256']
            result['runtime_image_id'] = ident
            result['runtime_image_tag'] = review['tag']
            checked = await operation('check', [*review['check_prefix'],ident,*review['check_args']],60)
            parsed = json.loads(checked.stdout)
            assert parsed['actual_graph_builder_passed'] is True and parsed['actual_proposal_generation'] is False
            assert parsed['models'] == 0 and parsed['generated_code_executed'] is False
            assert not subprocess.check_output([*docker,'ps','-aq','--filter','name=^/'+review['container_name']+'$'],
                                               env=env,timeout=10,text=True).strip()
            result.update(passed=True,observed=parsed)
        except BaseException as error:
            result['error_type'] = type(error).__name__
            raise
        finally:
            ledger = repo.operation_ledger(request.plan_id).model_dump(mode='json')
            result['accounting_settled'] = all(row['elapsed_seconds'] is not None for row in ledger['operations'])
            write(HERE/'evoagentx-runtime-ledger.json',ledger)
            write(HERE/'evoagentx-runtime-result.json',result)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated',required=True)
    args = parser.parse_args()
    path = HERE/'evoagentx-runtime-build-review.json'
    identity = sha(path)
    authority = read(HERE/'evoagentx-runtime-build-authority.json')
    assert args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']
    print(json.dumps(asyncio.run(run(read(path),identity))))
