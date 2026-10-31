"""Apply the approved software envelope using existing reservations and executors."""
import asyncio
from datetime import timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest,
    RecipeRuntimeBinding, ReviewedMapping, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ActionConstraints, ActionRequest, ExecutorSpec, Manifest, PolicyConfig, utc_now
from aeep.router import Router

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
PREFIX = 'specialist-732f9cdd'
SCRATCH = ROOT / '.aeep' / PREFIX
DOCKER_CONFIG = SCRATCH / 'docker-config'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def current(repo):
    return list(repo.store._connection.execute(
        "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'"
    ).fetchone())


def command_spec(name, argv, *, build=False):
    return ExecutorSpec(
        id=PREFIX + '.' + name, capability='toolkit.specialist.availability@1', kind='command',
        description='Exact operator-reviewed specialist availability; no models or candidate-value claim',
        input_schema={'type':'object','additionalProperties':False,'properties':{'probe':{'enum':['boundary','ruff','libcst']}}},
        estimate={'cash':{'amount_usd':'0','upper_bound_usd':'0','evidence':{
            'status':'complete','source':'operator_report','trust':'self_asserted'}}},
        side_effect='write' if build else 'read', idempotent=not build,
        config={'argv':argv,'argv_literal':True,'stdin_json':not build,
                'output':{'type':'text' if build else 'json'},'timeout_seconds':250 if build else 40,
                'max_output_bytes':1000000 if build else 8192,'inherit_env':False,
                'env':{'DOCKER_CONFIG':str(DOCKER_CONFIG)}},
    )


def operator_manifest(spec, database):
    return Manifest(database=str(database),executors=[spec],default_policy=PREFIX,
        policies={PREFIX:PolicyConfig(name=PREFIX,
            constraints=ActionConstraints(allowed_executor_ids=[spec.id],max_side_effect=spec.side_effect,
                allow_network=False,max_cost_usd=0),fallback={'enabled':False,'max_attempts':1})})


def prepare(review):
    assert verification_source_digest(ROOT) == review['source_digest']
    for path, expected in review['assets'].items():
        assert not Path(path).is_symlink() and sha(path) == expected, path
    docker = [review['docker_binary'],'--host',review['docker_socket']]
    build = command_spec('build', [*docker,'build','--pull=false','--network=none',
        '--provenance=false','--sbom=false','--tag',review['target_tag'],
        '--file',review['build']['dockerfile'],review['build']['context']], build=True)
    return docker, build


async def main():
    digest = sha(HERE / 'specialist-runtime-review.json')
    assert sys.argv[1] == digest
    review = json.loads((HERE / 'specialist-runtime-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == digest
    docker, build_spec = prepare(review)
    if len(sys.argv) == 3:
        assert sys.argv[2] == '--prepare-only'
        assert 'run' not in build_spec.config['argv']
        assert review['accounting']['maximum_model_turns'] == 0
        assert all('--mount' not in arg and '--volume' not in arg for arg in build_spec.config['argv'])
        save('driver-preparation.json', {'passed':True,'driver_sha256':sha(__file__),
            'source_digest':review['source_digest'],'build_argv':build_spec.config['argv'],
            'external_code_executed':False,'new_grant_operations':0,
            'boundary_choice':'Stock ContainerExecutor mounts runtime source and is excluded by this review. Reuse CommandExecutor with exact mount-free Docker argv instead; no executor implementation change.'})
        print('Preparation passed; no external execution or charge.')
        return
    assert len(sys.argv) == 2
    assert not SCRATCH.exists() and not (HERE / 'specialist-execution-started.json').exists()
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    SCRATCH.mkdir(mode=0o700)
    DOCKER_CONFIG.mkdir(mode=0o700)
    (DOCKER_CONFIG / 'config.json').write_text('{}\n')
    os.chmod(DOCKER_CONFIG / 'config.json',0o600)
    env = {key:os.environ[key] for key in ('PATH','TMPDIR') if key in os.environ}
    env['DOCKER_CONFIG'] = str(DOCKER_CONFIG)

    def metadata(*args, optional=False):
        done = subprocess.run([*docker,*args],env=env,stdin=subprocess.DEVNULL,
            capture_output=True,text=True,timeout=15)
        if not optional:
            assert done.returncode == 0, 'Docker metadata check failed'
        return done

    def inspect(reference):
        return json.loads(metadata('image','inspect',reference).stdout)[0]

    def absent(kind, name):
        done=metadata(kind,'inspect',name,optional=True)
        expected='no such image' if kind=='image' else 'no such container'
        assert done.returncode==1 and (expected in done.stderr.lower() or 'no such object' in done.stderr.lower()), 'Absence/cleanup is not established'
        return {'absent':True,'exit_code':done.returncode}

    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    initial = current(repo)
    assert initial == review['accounting']['counters_anchor'], 'Ledger changed before this review; reconcile first'
    effective=repo.effective_grant('onboarding')
    if effective.expires_at <= utc_now()+timedelta(minutes=30):
        previous=repo.store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json,'$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1").fetchone()
        amendment=AssessmentBudgetAmendment(authorization_id='onboarding',
            authorization_digest=content_digest(repo.get('authorization','onboarding')),
            previous_amendment_digest=previous[0] if previous else None,
            limits=effective.limits,expires_at=utc_now()+timedelta(hours=24))
        save('expiry-only-amendment.json',{'authority':'September27 standing finite amendment delegation; expiry only after approval delay',
            'amendment':amendment.model_dump(mode='json'),'counters_preserved':initial})
        repo.approve_budget_amendment(amendment)
        assert current(repo)==initial
    original_reserve = repo.reserve
    reserved_operations = reserved_seconds = 0

    def reserve(scope, operation, limits, *, stage):
        nonlocal reserved_operations, reserved_seconds
        now = current(repo)
        assert limits.max_model_turns == 0 and limits.max_cash_usd == 0
        assert reserved_operations + limits.max_operations <= 6
        assert reserved_seconds + limits.max_elapsed_seconds <= 600
        assert now[0] >= initial[0] and now[1] == initial[1] and now[3] == initial[3]
        assert now[0] + limits.max_operations <= initial[0] + 6
        assert now[2] + limits.max_elapsed_seconds <= initial[2] + 600
        original_reserve(scope,operation,limits,stage=stage)
        reserved_operations += limits.max_operations
        reserved_seconds += limits.max_elapsed_seconds

    repo.reserve = reserve
    subject = AssessmentSubject(subject_id=PREFIX,kind='command',location=str(HERE),
        dependency_digests=review['assets'],description='Reviewed software availability only, never a qualification result')
    recipe = RecipeDefinition(recipe_id=PREFIX,capability=build_spec.capability,
        description='Operator software availability; this recipe is not materialized or used as task evidence',
        input_schema=build_spec.input_schema,output_schema={'type':'object'},
        generator='operator_availability:none',grader='synthetic_literal_assertions:1',
        extractor='none',variations=['availability'],dependencies=review['assets'])
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())

    def scope(image, specs, suffix):
        environment = AssessmentEnvironment(environment_id=PREFIX+'.'+suffix,kind='container',
            identity={'review':digest,'purpose':'availability_only'},container_image=image,
            container_runtime=review['docker_binary'],container_socket=review['docker_socket'].removeprefix('unix://'),
            memory_mb=512,cpu_count=1,process_limit=64)
        mapping = ReviewedMapping(candidate=specs[0],baseline=specs[0],dependencies=specs[1:])
        docs = [('subject',subject.subject_id,subject),('recipe',recipe.recipe_id,recipe),
                ('recipe_runtime',content_digest(runtime),runtime),('environment',environment.environment_id,environment),
                ('mapping',content_digest(mapping),mapping)]
        definitions = {repo.put(kind,identity,value):value.model_dump(mode='json') for kind,identity,value in docs}
        request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
            plan_id=PREFIX+'.'+suffix,subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),
            mapping_digest=content_digest(mapping),environment_digest=content_digest(environment),
            authorization_id='onboarding',definition_digests=list(definitions),seed=0,
            runtime_dependencies=runtime.dependencies)
        definitions[repo.put('recipe_materialization_request',request.plan_id,request)] = request.model_dump(mode='json')
        root_authorization = repo.get('authorization','onboarding')
        amendment = AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(root_authorization),
            subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],
            environment_digests=[request.environment_digest],reviewed_digests=list(definitions))
        save('scope-'+suffix+'.json',{'authority':'Actual approval732f9cdd plus standing finite definition delegation',
            'request':request.model_dump(mode='json'),'definitions':definitions,'amendment':amendment.model_dump(mode='json')})
        repo.approve_bundle(amendment,definitions)
        repo.authorize(request)
        return request

    result = {'review_sha256':digest,'source_digest':review['source_digest'],'passed':False,
              'build_started':False,'checks':[],'grant_before':initial,'model_turns':0,
              'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED',
              'stack_integration':'COMPONENT_AVAILABILITY_ONLY'}
    owned_names=[]
    operation=None
    began=None

    async def execute(request, spec, name, value, seconds):
        nonlocal operation,began
        prepare(review)
        operation=PREFIX+'.'+name
        repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=seconds),stage='specialist_'+name)
        began=time.perf_counter()
        database=SCRATCH/(name+'.sqlite3')
        trial=Router(operator_manifest(spec,database))
        outcome=None
        try:
            trial._trial_check=lambda: (repo.authorize(request),prepare(review))
            outcome=await trial.execute(ActionRequest(capability=spec.capability,input=value,
                policy=PREFIX,constraints=ActionConstraints(allowed_executor_ids=[spec.id],
                    max_side_effect=spec.side_effect,allow_network=False,max_cost_usd=0)),approved_side_effect=spec.side_effect)
            for receipt in outcome.receipts:
                stored=trial.store.get_receipt(receipt.receipt_id)
                assert stored is not None and content_digest(stored)==content_digest(receipt)
                repo.put('specialist_availability_receipt',stored.receipt_id,stored)
            record={'operation_id':operation,'ok':outcome.ok,'output':outcome.output,
                'receipts':[r.model_dump(mode='json') for r in outcome.receipts],
                'store':str(database),'purpose':'software_availability_not_task_value'}
            save(name+'-result.json',record)
            assert outcome.ok, 'Reviewed software call failed; no automatic retry'
            return record
        finally:
            await trial.close()
            from aeep.accounting import aggregate_accounting
            finished_operation=operation
            operation=None
            repo.finish_operation(finished_operation,elapsed_seconds=time.perf_counter()-began,
                accounting=aggregate_accounting(outcome.receipts) if outcome else None)

    try:
        save('specialist-execution-started.json',{'review_sha256':digest,'driver_sha256':sha(__file__),
            'grant_before':initial,'automatic_retry':False})
        build_scope=scope(review['parent_image'],[build_spec],'build')
        operation=PREFIX+'.setup';repo.reserve(build_scope,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=30),stage='specialist_setup')
        began=time.perf_counter()
        parent=inspect(review['parent_reference'])
        assert parent['Id']==review['parent_image'] and parent['Config'].get('OnBuild') in (None,[])
        assert parent['Config']['User']=='65534:65534' and parent['Architecture']=='arm64'
        absent('image',review['target_tag'])
        (HERE/'docker-usage-before.txt').write_text(metadata('system','df').stdout)
        repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-began);operation=None
        result['build_started']=True
        await execute(build_scope,build_spec,'build',{},300)
        image=inspect(review['target_tag']);assert image['Id']!=parent['Id']
        assert image['Config']==parent['Config']
        assert image['RootFS']['Layers'][:len(parent['RootFS']['Layers'])]==parent['RootFS']['Layers']
        assert 0<image['Size']-parent['Size']<=1024**3
        assert inspect(review['parent_reference'])['Id']==review['parent_image']
        result['image_id']=image['Id'];result['image_growth_bytes']=image['Size']-parent['Size']
        save('specialist-image-binding.json',{'image_id':image['Id'],'parent_id':parent['Id'],
            'tag':review['target_tag'],'config_inherited':True,'layers_inherited':True,
            'image_growth_bytes':result['image_growth_bytes'],'kept_for_remaining_work':True})
        code=(HERE/'specialist-probe.py.txt').read_text()
        specs=[]
        for probe in ['boundary','ruff','libcst']:
            name='aeep-'+PREFIX+'-'+probe
            absent('container',name)
            argv=[*docker,'run','--pull=never','--rm','--name',name,'--read-only','--user','65534:65534',
                '--cap-drop=ALL','--security-opt=no-new-privileges','--cpus','1','--memory','512m','--memory-swap','512m',
                '--pids-limit','64','--network','none','--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=32m',
                '--tmpfs','/workspace:rw,noexec,nosuid,nodev,size=32m','--workdir','/tmp','-i',
                '--entrypoint','python3',image['Id'],'-I','-c',code]
            assert '--mount' not in argv and '--volume' not in argv
            specs.append(command_spec(probe,argv))
        probe_scope=scope(image['Id'],specs,'probes')
        for probe,spec in zip(['boundary','ruff','libcst'],specs,strict=True):
            name='aeep-'+PREFIX+'-'+probe;owned_names.append(name)
            record=await execute(probe_scope,spec,probe,{'probe':probe},45)
            assert record['output']['passed'] is True and record['output']['probe']==probe
            absent('container',name)
            result['checks'].append({'probe':probe,'passed':True,'owned_container_absent':True})
        operation=PREFIX+'.analysis';repo.reserve(probe_scope,operation,AssessmentLimits(max_operations=1,max_elapsed_seconds=120),stage='specialist_analysis')
        began=time.perf_counter()
        assert len(result['checks'])==3
        assert verification_source_digest(ROOT)==review['source_digest']
        assert shutil.disk_usage(ROOT).free>50*1024**3
        result['passed']=True
    except BaseException as error:
        result['error_type']=type(error).__name__
        raise
    finally:
        if operation is not None:
            repo.finish_operation(operation,elapsed_seconds=time.perf_counter()-began)
        result['reserved_operations']=reserved_operations
        result['reserved_seconds_sum']=reserved_seconds
        result['grant_after']=current(repo)
        result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
        result['owned_container_states']={name:absent('container',name) for name in owned_names}
        save('specialist-execution-result.json',result)
        save('specialist-build-ledger.json',repo.operation_ledger(PREFIX+'.build').model_dump(mode='json'))
        if 'image_id' in result:
            save('specialist-probe-ledger.json',repo.operation_ledger(PREFIX+'.probes').model_dump(mode='json'))
        await router.close()
        print(json.dumps({key:value for key,value in result.items() if key not in {'owned_container_states'}}))


if __name__=='__main__':
    asyncio.run(main())
