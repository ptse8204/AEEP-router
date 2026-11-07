"""Exercise both retained packaged graders through the ordinary contained executor."""

import argparse
import asyncio
import base64
import hashlib
import json
import re
import shutil
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeDefinition,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ResourceVector,
    SideEffect,
    StrictModel,
    utc_now,
)
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


class Scope(StrictModel):
    review_sha256: str
    purpose: str


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


async def verify(review, identity):
    work = Path(review['work'])
    docker = [review['docker'],'--config',review['docker_config'],'--host','unix://'+review['docker_socket']]
    env = {'HOME':str(work),'PATH':'/usr/bin:/bin','LC_ALL':'C'}
    out = HERE/'grader-execution'
    out.mkdir(mode=0o700)
    write(HERE/'grader-started.json', {'review_sha256':identity})
    scope = Scope(review_sha256=identity,purpose='Local protected SkillsBench packaged grader calibration')
    reference = content_digest(scope)
    grant = AssessmentAuthorization(
        authorization_id=review['grant_id'],subject_digests=[reference],recipe_digests=[reference],
        environment_digests=[reference],limits=AssessmentLimits(max_operations=6,max_model_turns=0,max_elapsed_seconds=390),
        remote_disclosure=False,allowed_destinations=['local'],expires_at=datetime.fromisoformat(review['expires_at']),
    )
    request = RecipeMaterializationRequest(plan_id=grant.authorization_id,subject_digest=reference,
        recipe_digest=reference,environment_digest=reference,mapping_digest=reference,
        authorization_id=grant.authorization_id,definition_digests=[reference],seed=0)
    results = {}
    with ReceiptStore(review['ledger']) as store:
        repo = AssessmentRepository(store)
        assert not store._connection.execute('SELECT 1 FROM assessment_grants WHERE id=?',(grant.authorization_id,)).fetchone()
        assert repo.put('toolkit_skillsbench_packaged_grader_scope',reference,scope)==reference
        repo.approve_bundle(grant,{reference:scope.model_dump(mode='json')})
        for role, selected in review['cases'].items():
            if results and not all(row['cleanup_verified'] for row in results.values()):
                break
            recipe = RecipeDefinition.model_validate(read(selected['recipe_file']))
            assert content_digest(recipe)==selected['recipe_digest'] and recipe.extension is not None
            pack = BenchmarkPack.model_validate(read(selected['pack_path']))
            value = task_input(pack,Path(selected['asset_root']),selected['task_id'])
            assert content_digest(value)==selected['input_digest']
            archive = value['task_archive_sha256']
            expected = {'task_archive_sha256':archive}
            field = selected['output_field']
            payload = recipe.extension.reference.config['argv']
            assert payload[5:8] == [archive, selected['task_id'], field]
            answer = ''.join(payload[8:])
            assert hashlib.sha256(base64.b64decode(answer,validate=True)).hexdigest()==selected['reference_sha256']
            control = recipe.extension.fault_outputs[0]
            variants = [('reference', {field:answer}, True, None),
                        ('missing', {}, False, 'output_contract'),
                        ('fault', control, False, 'upstream_rejected')]
            environment = AssessmentEnvironment(
                environment_id='skillsbench-'+role+'-protected',
                kind='container',identity={'task_id':selected['task_id']},
                container_image=selected['image_id'],container_runtime=review['docker'],
                container_socket=review['docker_socket'],memory_mb=1024 if role=='excel' else 512,
                process_limit=96,
            )
            write(out/(role+'-environment.json'),environment.model_dump(mode='json'))
            spec = recipe.extension.grader
            timeout = spec.config['timeout_seconds']
            facts = results[role] = {'observations':{},'passed':False,'cleanup_verified':True}
            for name, output, expected_valid, expected_code in variants:
                operation = request.plan_id+':'+role+':'+name
                executor = ContainerExecutor(environment)
                context = ExecutionContext(request=ActionRequest(action_id=operation,capability=spec.capability,
                    input={'examples':[{'input':value,'output':output,'expected':expected}]}),
                    spec=spec,estimate=spec.estimate,attempt=1,attempt_id=operation,
                    approved_side_effect=SideEffect.READ)
                argv, container = executor.command(context)
                assert container==container_name(operation) and str(environment.container_image) in argv
                assert '--pull=never' in argv and '--read-only' in argv and argv[argv.index('--network')+1]=='none'
                assert argv[argv.index('--user')+1]=='65534:65534'
                repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,
                    max_elapsed_seconds=timeout+5),stage='packaged_skillsbench_grader')
                clock, started = time.perf_counter(), utc_now()
                grade = failure = None
                valid = False
                stopped = False
                try:
                    assert shutil.disk_usage(ROOT).free >= 52*1024**3
                    assert all(sha(path)==digest for path,digest in review['pins'].items())
                    repo.authorize(request)
                    raw = await executor.execute(context)
                    assert raw.status.value=='success', raw.error_type
                    grade = grader_results(raw.output,recipe.extension,1)[0]
                    valid = grade.valid is expected_valid and (grade.detail or None)==expected_code
                except Exception as exc:
                    failure = type(exc).__name__
                    if isinstance(exc, AssertionError) and exc.args and isinstance(exc.args[0],str):
                        category = exc.args[0]
                        if re.fullmatch(r'[A-Za-z][A-Za-z_]{0,79}',category):
                            failure = category
                finally:
                    await executor.close()
                    listed = await asyncio.to_thread(subprocess.run,
                        [*docker,'ps','-aq','--filter','name=^/'+container+'$'],
                        env=env,capture_output=True,timeout=15)
                    stopped = listed.returncode==0 and not listed.stdout.strip()
                    elapsed = time.perf_counter()-clock
                    observation = {'valid':grade.valid if grade else None,'score':grade.quality_score if grade else None,
                        'failure_code':grade.detail if grade else None,'expected_valid':expected_valid,
                        'matches_expected':valid,'owned_container_removed':stopped,'elapsed_seconds':elapsed}
                    receipt = ExecutionReceipt(decision_id=operation,action_id=operation,capability=spec.capability,
                        executor_id=spec.id,executor_kind='command',status='success' if valid and stopped else 'failed',
                        started_at=started,ended_at=utc_now(),estimated=spec.estimate,
                        actual_resources=ResourceVector(latency_ms=elapsed*1000),execution_success=valid and stopped,
                        error_type=failure,metadata={'review_sha256':identity,'role':role,'variant':name,
                            'task_id':selected['task_id'],'recipe_digest':selected['recipe_digest'],
                            'image_id':selected['image_id'],'observation':observation,
                            'observed_resource_dimensions':['latency_ms']})
                    store.save_receipt(receipt)
                    repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
                    facts['observations'][name]=observation|{'receipt_id':receipt.receipt_id,'error_type':failure}
                    write(out/(role+'-'+name+'-receipt.json'),receipt.model_dump(mode='json'))
                if not stopped:
                    facts['cleanup_verified'] = False
                    break
                if not valid:
                    break
            facts['passed'] = len(facts['observations'])==len(variants) and all(
                row['matches_expected'] and row['owned_container_removed'] for row in facts['observations'].values())
        ledger = repo.operation_ledger(request.plan_id)
        write(out/'ledger.json',ledger.model_dump(mode='json'))
        result = {'passed':len(results)==2 and all(row['passed'] for row in results.values()),'results':results,
                  'operations':len(ledger.operations),'accounting_settled':all(
                       row.elapsed_seconds is not None for row in ledger.operations),
                  'models':0,'cash_usd':'0','ordinary_cli_workload_execution':'OPEN','comparisons':'PAUSED'}
        write(out/'summary.json',result)
        print(json.dumps(result))
        return result['passed'] and result['accounting_settled']


if __name__=='__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-delegated',required=True)
    args = parser.parse_args()
    review_path = HERE/'grader-review.json'
    review = read(review_path)
    identity = sha(review_path)
    authority = read(HERE/'grader-authority.json')
    assert args.execute_delegated==identity==authority['review_sha256'] and authority['first_attempt'] is True
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'])
    assert shutil.disk_usage(ROOT).free >= 52*1024**3
    assert verification_source_digest(ROOT)==review['source_digest']
    assert all(sha(path)==digest for path,digest in review['pins'].items())
    assert not (HERE/'grader-started.json').exists()
    docker = [review['docker'],'--config',review['docker_config'],'--host','unix://'+review['docker_socket']]
    env = {'HOME':review['work'],'PATH':'/usr/bin:/bin','LC_ALL':'C'}
    for row in review['cases'].values():
        facts = subprocess.check_output([*docker,'image','inspect','--format',
            '{{.Id}} {{.Architecture}} {{.Os}} {{json (index .Config "Volumes")}}',row['image_id']],
            text=True,env=env,timeout=15).split()
        assert facts == [row['image_id'],'arm64','linux','null']
    raise SystemExit(not asyncio.run(verify(review,identity)))
