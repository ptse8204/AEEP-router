"""Bind one Prefix Cache engineering task to the existing managed CLI."""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import runpy
import shutil
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.extensions import grader_name, require_environment
from aeep.assessment.models import (
    AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits,
    IntegrationCaseSet, RecipeDefinition, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import ActionRequest, Manifest, ValidationSpec, utc_now
from aeep.registry import validate_json
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep.templates import render
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.models import EvidenceBundle, ExtensionManifest
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
C13 = STAGE.parents[1]
REACT = C13 / 'skillsbench-react-managed-preparation-20261107'
PREVIOUS = REACT / 'sol-permitted-path-live-20261109'
legacy = runpy.run_path(str(REACT / 'run-managed-react.py'))
engine, owner, read, sha, save = (legacy[key] for key in ('engine', 'owner', 'read', 'sha', 'save'))
ROOT = legacy['ROOT']
DEFS = ROOT / '.aeep' / STAGE.parent.name / STAGE.name / 'cli-definitions'
WORK = DEFS.parent / 'cli-execution'
GRADER = STAGE / 'carrier-verification'
REVIEW = HERE / 'operation-review.json'
TASK = 'llm-prefix-cache-replay'
ROLE = 'prefix-cache'
CONFIGURATION = 'software-engineering'
TAG = 'prefix-cache-sol-20261113'
MODEL = 'gpt-6.1-sol'
CONFIG = ('--configuration', CONFIGURATION)
PROOF = GRADER / 'execution-audit.json'
TRIAL_AUDIT = Path(engine.__file__).with_name('audit-trial.py')


def inputs():
    disclosure = read(STAGE / 'proposed-disclosure.json')
    transport = read(STAGE.parent / 'task-pack-transport.json')
    proposed = TaskRightsReview.model_validate(disclosure['proposed_rights'])
    assert content_digest(proposed) == disclosure['rights_record_ref']
    assert proposed.local_execution_allowed and proposed.provider_disclosure_allowed
    pack = BenchmarkPack.model_validate(read(STAGE.parent / 'task-pack.json'))
    task = pack.task(TASK)
    assert proposed.source_revision == pack.source.revision and proposed.task_id == TASK
    assert proposed.assets == {asset.path: asset.sha256 for asset in task.assets}
    assert task.rights_review_ref is None
    pack = pack.model_copy(update={'tasks': (task.model_copy(update={'rights_review_ref': content_digest(proposed)}),)})
    asset_root = Path(transport['pack_root'])
    value = task_input(pack, asset_root, TASK)
    raw = base64.b64decode(value['task_archive_b64'], validate=True)
    assert value['task_archive_sha256'] == disclosure['public_archive_sha256'] == transport['public_archive_sha256']
    assert len(raw) == transport['public_archive_bytes']
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        public = {name: hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
        assert len(archive.infolist()) == len(public) == 3
    assert public == disclosure['public_files'] == transport['public_files']
    return proposed, pack, value, asset_root, public


def protected_grader():
    proof, result = read(PROOF), read(GRADER / 'result.json')
    assert proof['result_sha256'] == sha(GRADER / 'result.json')
    assert proof['ledger_sha256'] == sha(GRADER / 'ledger.json')
    assert proof['environment_sha256'] == sha(GRADER / 'environment.json')
    assert all(sha(GRADER / name) == digest for name, digest in proof['receipt_sha256'].items())
    assert result['passed'] and result['accounting_settled'] and result['operations'] == 9
    environment = AssessmentEnvironment.model_validate(read(GRADER / 'environment.json'))
    assert environment.container_image == result['observations']['build']['id'] == proof['retained_image']['id']
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', environment.container_image) == environment.container_image
    return environment


def definitions():
    rights, pack, value, asset_root, public = inputs()
    evidence, draft = read(GRADER / 'operation-review.json'), read(STAGE / 'result.json')
    original = RecipeDefinition.model_validate(read(draft['recipe']))
    assert content_digest(original) == evidence['recipe_digest'] == draft['recipe_digest']
    raw = original.model_dump(mode='json')
    raw['recipe_id'] = 'skillsbench-prefix-cache-protected-managed-v1'
    raw['dependencies']['benchmark_pack'] = value['benchmark_pack_sha256']
    raw['input_schema']['properties']['benchmark_pack_sha256']['const'] = value['benchmark_pack_sha256']
    recipe = RecipeDefinition.model_validate(raw)
    assert recipe.extension == original.extension and recipe.output_schema == original.output_schema
    validate_json(value, recipe.input_schema, label='disclosure-bound Prefix Cache input')
    env = protected_grader()
    require_environment(recipe, env)

    worker = read(STAGE / 'worker-draft.json')
    draft_pair = WorkerPairInspection.model_validate(read(worker['pair']))
    assert content_digest(draft_pair) == worker['pair_sha256']
    shared = read(worker['shared'])
    assert content_digest(shared) == draft_pair.differential.shared_definition_digest == worker['shared_sha256']
    shared.update(recipe=content_digest(recipe), task_id=TASK, public_archive_sha256=value['task_archive_sha256'],
                  source_sha256=verification_source_digest(ROOT))
    pair_data = draft_pair.model_dump(mode='json')
    common = pair_data['differential']['control_inventory'] | {'common_profile': content_digest(shared)}
    pair_data['differential'].update(shared_definition_digest=content_digest(shared), control_inventory=common,
        treatment_inventory=common | pair_data['differential']['candidate_inventory'])
    for arm in ('control', 'treatment'):
        pair_data[arm]['input_schema'] = recipe.input_schema
    pair = WorkerPairInspection.model_validate(pair_data)
    for arm in ('control', 'treatment'):
        config = getattr(pair, arm).managed_host_config()
        assert getattr(draft_pair, arm).managed_host_config() == config
        assert tuple(config.model_constraints.allowed_model_ids) == (MODEL,) and tuple(config.reasoning_efforts) == ('medium',)
        assert not config.store_prompt and not config.store_output
        image = engine.binding_from_config(config.managed_worker).image
        assert image == worker['worker_images'][arm]
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image
    truth = {'task_archive_sha256': value['task_archive_sha256']}
    case = BenchmarkCase(case_id=TASK, split='qualification', variation=TASK, template_family='skillsbench:'+TASK,
        action=ActionRequest(action_id=TASK, capability=recipe.capability, input=value),
        validators=[ValidationSpec(kind='callback', config={'name': grader_name(value, truth), 'expected': truth})])
    cases = IntegrationCaseSet(request_id=TAG+'-cases', recipe_digest=content_digest(recipe),
        environment_digest=content_digest(env), benchmark_pack_digest=value['benchmark_pack_sha256'], seed=0, cases=[case])
    return rights, pack, recipe, pair, shared, env, cases, asset_root, public


def build_workflow(recipe, pack, asset_root):
    previous = read(PREVIOUS / 'operation-review.json')
    execution = Path(previous['work'])
    workflow = read(execution / 'react-prepared/workflow.json')
    for key in ('registry', 'policy'):
        assert engine.binding(Path(workflow[key]['path'])) == workflow[key]
    registry, policy = (read(workflow[k]['path']) for k in ('registry', 'policy'))
    rights = 'Proposed disclosure of three exact public Prefix Cache files for one Codex engineering run.'
    for component in registry['extensions']:
        if component['extension_id'] not in {'aeep-evaluator', 'skillsbench'}:
            continue
        component['purpose'] = 'One controlled Prefix Cache engineering run'
        component['install_effects'] = ['Reuse the retained workers, protected grader and scoped Codex proxy.']
        component['source'].update(artifact_sha256=content_digest({
            'component': component['extension_id'], 'recipe': content_digest(recipe), 'pack': content_digest(pack.model_dump(mode='json')),
        }), data_rights=rights)
        if component['extension_id'] == 'aeep-evaluator':
            component['source']['revision'] = '675171daedccbaf599effae4dbd267b15c4b8e1c'
        policy['reviewed_dependency_manifests'].append(engine.manifest_digest(ExtensionManifest.model_validate(component)))
    policy['allowed_data_rights'].append(rights)
    policy['free_disk_bytes'] = shutil.disk_usage(ROOT).free
    for key, data in (('registry', registry), ('policy', policy)):
        path = DEFS / (key+'.json')
        save(path, data)
        workflow[key] = engine.binding(path)
    selected = workflow['configurations'][CONFIGURATION]
    selected.update(benchmark=engine.binding(DEFS/'pack.json'), asset_root=str(asset_root), task_ids=[TASK],
                    benchmark_recipe=engine.binding(DEFS/'recipe.json'), assessment=None, preparation=None)
    save(DEFS / 'workflow.json', workflow)


def draft_check(case):
    result = read(HERE/'cli-draft-check.json')
    assert result['unreviewed_rights_rejected'] and result['one_required_use_route']
    assert result['cli_plan_schema'] == 'assessment.plan.v7'
    assert result['model_turns'] == result['jobs_created'] == result['workers_started'] == 0
    assert not result['provider_transfer']
    for key, reviewed in (('recipe_digest','recipe_digest'), ('environment_digest','grader_environment_digest'),
                          ('case_set_digest','integration_case_set_digest')):
        assert result[key] == case[reviewed]
    return result['campaign_upper_allowance']


def freeze():
    rights, pack, recipe, pair, shared, env, cases, asset_root, public = definitions()
    DEFS.mkdir(mode=0o700)
    for name, value in (('rights', rights), ('pack', pack), ('recipe', recipe), ('pair', pair), ('environment', env),
                        (ROLE+'-integration-cases', cases)):
        save(DEFS / (name+'.json'), value.model_dump(mode='json'))
    save(DEFS / 'shared.json', shared)
    build_workflow(recipe, pack, asset_root)
    previous = read(PREVIOUS / 'operation-review.json')
    database = previous['database']
    grant = legacy['snapshot'](database)
    proxy = read(engine.PREVIOUS / 'operation-review.json')
    assert engine.proxy_state(proxy) == proxy['proxy_metadata'] == previous['proxy'] and not previous['proxy']['Running']
    now = utc_now()
    expiry = now + timedelta(hours=48)
    assert datetime.fromisoformat(grant['expires_at']) < now
    amendment = AssessmentBudgetAmendment(amendment_id=TAG+'-expiry', authorization_id='onboarding',
        authorization_digest=grant['root_sha256'], previous_amendment_digest=grant['amendment_sha256'],
        limits=AssessmentLimits.model_validate(grant['limits']), issued_at=now, expires_at=expiry)
    case = {'configuration': CONFIGURATION, 'role': ROLE, 'task_id': TASK, 'public_files': public,
            'public_archive_sha256': cases.cases[0].action.input['task_archive_sha256'],
            'public_archive_bytes': read(STAGE.parent/'task-pack-transport.json')['public_archive_bytes'],
            'rights': str(DEFS/'rights.json'), 'rights_review_ref': content_digest(rights),
            'recipe': str(DEFS/'recipe.json'), 'recipe_digest': content_digest(recipe),
            'pair': str(DEFS/'pair.json'), 'pair_digest': content_digest(pair), 'shared':str(DEFS/'shared.json'),
            'grader_environment': str(DEFS/'environment.json'), 'grader_image_id': env.container_image,
            'grader_environment_digest': content_digest(env), 'integration_case_set_digest': content_digest(cases)}
    skill = engine.prepared.SKILL
    paths = [Path(__file__), Path(legacy['__file__']), Path(owner['__file__']), Path(engine.__file__),
        Path(engine.prepared.__file__), Path(engine.previous.__file__), Path(engine.previous.prepared.__file__),
        Path(engine.budget.__file__), Path(engine.collector.__file__), Path(engine.evidence.__file__), TRIAL_AUDIT,
        engine.PREVIOUS/'operation-review.json', engine.PREVIOUS/'source.json', engine.BASE,
        C13/'pipeline-standing-authority-20261104.json', PREVIOUS/'operation-review.json',
        PREVIOUS/'completed-run-audit.json', STAGE/'proposed-disclosure.json', STAGE/'worker-draft.json',
        STAGE.parent/'task-pack.json', STAGE.parent/'task-pack-transport.json', STAGE.parent/'candidate-review.json',
        *[Path(read(STAGE/'worker-draft.json')[key]) for key in ('pair','shared')],
        GRADER/'operation-review.json', PROOF, GRADER/'result.json', GRADER/'ledger.json', GRADER/'environment.json',
        *[GRADER/name for name in read(PROOF)['receipt_sha256']], *sorted(DEFS.glob('*.json')),
        *sorted(p for p in skill.rglob('*') if p.is_file()), *[asset_root/name for name in sorted(rights.assets)],
        Path('/usr/local/bin/docker').resolve(), HERE/'check.py', HERE/'cli-draft-check.json']
    fixture_allowance = draft_check(case)
    preview = engine.cli('plan', '--workflow', DEFS/'workflow.json', *CONFIG)
    assert preview['blockers'] == ['canonical assessment preparation and applicable worker/grader evidence remain required']
    check = {'workflow_preview_sha256': preview['review_sha256'], 'blockers':preview['blockers'],
             'canonical_plan_requires_fresh_worker_readiness':True, 'workers_started':0, 'models':0,
             'provider_transfer':False, 'rights_registered_live':False}
    save(HERE/'preflight.json', check)
    review = {
        'scope':'One GPT-6.1 Sol medium Prefix Cache stack engineering turn after paired zero-turn conformance.',
        'source_sha256':verification_source_digest(ROOT), 'pins':{str(path):sha(path) for path in paths},
        'database':database, 'definitions':str(DEFS), 'work':str(WORK), 'proxy':previous['proxy'],
        'cases':[case], 'worker_image_ids':read(STAGE/'worker-draft.json')['worker_images'],
        'grant':grant, 'expiry_only_amendment':amendment.model_dump(mode='json'), 'expires_at':expiry.isoformat(),
        'destination':'codex', 'model':MODEL, 'reasoning_effort':'medium', 'fresh_worker_inspections':2,
        'sendable_inputs':['Three exact public files in cases[0].public_files, including the upstream task attribution',
                           'Bound first-party stack-check skill and private-workspace handoff instructions'],
        'protected_local':['reference solver and outputs','tests and oracle','license inventory and bundled upstream skills'],
        'offline_fixture_campaign_upper_allowance':fixture_allowance,
        'maximum_model_turns':1, 'maximum_operations':64, 'maximum_reserved_seconds':3900, 'maximum_cash_usd':'0',
        'minimum_free_gib':50, 'before_turn':'Both worker identities, catalogue, isolation and collector denial, then canonical CLI plan and allowance.',
        'after_turn':'Protected grading, receipt-linked token capture, ordinary CLI reports, restore the existing proxy to stopped.',
        'automatic_retries':False, 'model_fallback':False, 'comparison_execution':False, 'comparisons':'PAUSED',
        'downloads':False, 'installs':False, 'builds':0, 'existing_resources_removed':False,
        'workflow_preview_sha256':preview['review_sha256'], 'preflight_sha256':sha(HERE/'preflight.json'),
    }
    save(REVIEW,review)
    inspect(review, sha(REVIEW))
    print(sha(REVIEW))


def guard(review, identity):
    assert __debug__ and sha(REVIEW) == identity
    assert utc_now() < datetime.fromisoformat(review['expires_at'])
    assert shutil.disk_usage(ROOT).free >= review['minimum_free_gib']*1024**3
    assert verification_source_digest(ROOT) == review['source_sha256']
    assert all(sha(path) == digest for path, digest in review['pins'].items())
    assert review['maximum_model_turns'] == 1 and review['maximum_cash_usd'] == '0'
    assert review['destination'] == 'codex' and review['model'] == MODEL and review['reasoning_effort'] == 'medium'
    assert not any(review[key] for key in ('automatic_retries', 'model_fallback', 'comparison_execution'))
    assert review['comparisons'] == 'PAUSED'
    protected_grader()


def inspect(review, identity):
    guard(review, identity)
    assert not (HERE/'started.json').exists() and not WORK.exists()
    assert legacy['snapshot'](review['database']) == review['grant']
    amendment = AssessmentBudgetAmendment.model_validate(review['expiry_only_amendment'])
    assert amendment.authorization_digest == review['grant']['root_sha256']
    assert amendment.previous_amendment_digest == review['grant']['amendment_sha256']
    assert amendment.limits.model_dump(mode='json') == review['grant']['limits']
    assert amendment.expires_at.isoformat() == review['expires_at']
    proxy = read(engine.PREVIOUS/'operation-review.json')
    assert engine.proxy_state(proxy) == proxy['proxy_metadata'] == review['proxy'] and not review['proxy']['Running']
    rights, pack, recipe, pair, shared, env, cases, _, public = definitions()
    case, = review['cases']
    assert case['public_files'] == public and case['public_archive_sha256'] == cases.cases[0].action.input['task_archive_sha256']
    for key, value in (('rights_review_ref',rights), ('recipe_digest',recipe), ('pair_digest',pair),
                       ('grader_environment_digest',env), ('integration_case_set_digest',cases)):
        assert content_digest(value) == case[key]
    assert case['grader_image_id'] == env.container_image and case['task_id'] == TASK
    assert draft_check(case) == review['offline_fixture_campaign_upper_allowance']
    assert case['configuration'] == CONFIGURATION and case['role'] == ROLE
    for name, expected in (('rights',rights), ('pack',pack), ('recipe',recipe), ('pair',pair), ('environment',env),
                           (ROLE+'-integration-cases',cases)):
        assert read(DEFS/(name+'.json')) == expected.model_dump(mode='json')
    assert read(DEFS/'shared.json') == shared
    preview = engine.cli('plan','--workflow',DEFS/'workflow.json',*CONFIG)
    assert preview['review_sha256'] == review['workflow_preview_sha256']
    assert sha(HERE/'preflight.json') == review['preflight_sha256']
    assert engine.budget.self_check() == 7
    cfg = pair.treatment.managed_host_config()
    task = dict(cases.cases[0].action.input)
    encoded = task.pop(cfg.artifact.input_field)
    task.update(input_path='/workspace/'+cfg.artifact.input_name, output_path='/workspace/'+cfg.artifact.output_name)
    assert encoded not in str(render(cfg.instructions, {'input':task}))
    return proxy, (case,recipe,pair,shared), amendment


def audit_trial(service, plan, pair, target):
    audit = runpy.run_path(str(TRIAL_AUDIT))
    record = audit['audit'](engine, service, plan, pair)
    assert audit['passed'](record) and record['case_id'] == TASK
    bundle = EvidenceBundle.model_validate_json((target/'toolkit-evidence.json').read_bytes())
    run, = bundle.runs
    assert run.model == MODEL and run.effort == 'medium' and run.mode == 'forced_diagnostic'
    assert run.receipt_refs == (record['receipt_ref'],)
    assert run.retries == record['retries'] == 0 and run.status == 'completed'
    assert run.verification == ('pass' if record['task_grade'] else 'fail')
    assert run.tokens is not None and run.tokens.source_ref == record['receipt_ref']
    for key, value in record['token_counts_provider_reported'].items():
        if key in type(run.tokens).model_fields:
            assert getattr(run.tokens,key) == value
    summary = read(target/'summary.json')
    assert summary['outcome']=='NOT_ASSESSED' and summary['managed_analysis']['distinct_paired_cases']==0
    assert summary['managed_analysis']['unresolved_operations']==0
    assert summary['evidence_sha256']==content_digest(bundle.model_dump(mode='json'))
    return record | {'matched_token_delta':None, 'model':run.model,'reasoning_effort':run.effort}


async def execute(review, identity, proxy, selected, amendment):
    case, recipe, pair, shared = selected
    assert read(HERE/'operator-approval.json') == {'approved':True, 'review_sha256':identity}
    WORK.mkdir(mode=0o700)
    save(HERE/'started.json', {'review_sha256':identity,'comparisons':'PAUSED','automatic_retries':False})
    owner['configure'](engine,review,{ROLE:selected})
    engine.budget.require_room(review['grant']['counters'],review['grant']['counters'],
        AssessmentLimits(max_operations=4,max_elapsed_seconds=665),review)
    base = Manifest.model_validate(read(engine.BASE))
    assert str(base.database) == review['database']
    manifest = base.model_copy(update={'executors':[pair.control,pair.treatment]})
    engine.prepared.write(engine.MANIFEST,manifest.model_dump(mode='json'))
    with ReceiptStore(review['database']) as store:
        assert legacy['snapshot'](review['database']) == review['grant']
        AssessmentRepository(store).approve_budget_amendment(amendment)
    assert legacy['snapshot'](review['database']) == review['grant'] | {
        'amendment_sha256':content_digest(amendment),'expires_at':review['expires_at']}
    router = Router.from_manifest(engine.MANIFEST)
    service = AssessmentService(router,engine.CAMPAIGNS)
    repo = service.repository
    initial, pending = engine.previous.counters(repo), engine.reserved(repo)
    assert list(initial)==review['grant']['counters'] and len(pending)==review['grant']['prior_reservations']
    original_reserve = engine.budget.install(repo,repo.store._connection,initial,review)
    original_collect = engine.inspection.collect
    outcome = {'review_sha256':identity,'passed':False,'comparisons':'PAUSED','model_turns_reserved':0}
    overhead, proxy_started, excluded = None, False, 0.
    began = time.perf_counter()
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    phase = 'scope and public input review'
    try:
        subject = service.inspect_local(engine.prepared.SKILL, kind='skill')
        repo.put('recipe',recipe.recipe_id,recipe)
        local = AssessmentEnvironment(environment_id=TAG+'-local',kind='trusted_local',
                                       identity={'source_digest':review['source_sha256'],'review':identity})
        repo.put('environment',content_digest(local),local)
        bootstrap = engine.materialization(repo,TAG+'-overhead',subject,recipe,local)
        engine.scoped_approval(repo,[bootstrap])
        overhead=bootstrap.plan_id+':exclusive'
        repo.reserve(bootstrap,overhead,AssessmentLimits(max_operations=1,max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        repo.put('shared_environment_definition',content_digest(shared),engine.previous.Document(value=shared))
        rights = engine.cli('define-rights','--manifest',engine.MANIFEST,'--file',case['rights'],
                            output='define-rights-cli.json')
        assert rights == {'rights_review_ref':case['rights_review_ref'],'reviewed':False,'execution_authorized':False}
        repo.review(rights['rights_review_ref'])

        phase='worker and collector conformance'
        guard(review,identity)
        assert engine.proxy_state(proxy)==review['proxy']
        proxy_started=True
        engine.docker('start',proxy['proxy_name'])
        active=engine.proxy_state(proxy)
        assert active['Running'] and active['Id']==review['proxy']['Id'] and active['Image']==review['proxy']['Image']
        assert active['Networks']['aeep-reviewed-model-private']['IPAddress']=='172.18.0.2'
        ids=engine.worker_requests(service,ROLE,pair,recipe,subject,review['source_sha256'])
        engine.inspection.collect=engine.inspect_collector(original_collect)
        nested=time.perf_counter()
        try:
            observed=await engine.inspection.execute_pair(service,*ids)
        finally:
            excluded+=time.perf_counter()-nested
            engine.inspection.collect=original_collect
        facts=[repo.get('worker_pair_inspection','pair-inspection:'+request)['observations'] for request in ids]
        if any(row.get('cleanup_error_type') or not row.get('cleanup_confirmed') for row in facts):
            outcome['worker_cleanup_uncertain']=True
            raise RuntimeError('Worker cleanup unverified')
        assert observed['probes_match'] and observed['model_turns']==0
        assert all(row['inspection'].get('collector_boundary') == {'collector_connection_denied':True} for row in facts)
        boundary=engine.readiness(repo,ROLE,ids,pair,review['source_sha256'])

        phase='ordinary CLI canonical preparation'
        assert engine.grader_environment(ROLE)==protected_grader()
        plan, ref, accounting, bound, workflow_ref, allowance=engine.draft(
            service,ROLE,selected,subject,boundary,read(DEFS/'workflow.json'),review['source_sha256'],run_tag=TAG)
        ops,turns,seconds=engine.measure_allowance(allowance)
        assert turns==1 and plan.suite.cases[0].action.input['task_archive_sha256']==case['public_archive_sha256']
        engine.budget.require_room(engine.previous.counters(repo),initial,
            AssessmentLimits(max_operations=ops,max_model_turns=turns,max_elapsed_seconds=seconds),review)
        save(HERE/'dispatch-ready.json',{'plan_id':plan.plan_id,'plan_sha256':content_digest(plan),
             'engineering_review_ref':ref,'workflow_ref':workflow_ref,'worker_boundaries':2,'review_sha256':identity})
        phase='ordinary CLI run'
        guard(review,identity)
        assert set(engine.reserved(repo)) <= set(pending) | {overhead}
        common=('--workflow',bound,*CONFIG,'--manifest',engine.MANIFEST,'--directory',engine.CAMPAIGNS,
                '--reviewed-digest',workflow_ref,'--accounting',accounting)
        target=WORK/'prefix-cache-result'
        nested=time.perf_counter()
        try:
            engine.cli('run',*common,'--operation-id','execute','--output',target,'--engineering-review',ref,
                       output='run-cli.json',timeout=2100)
        finally:
            excluded+=time.perf_counter()-nested
        phase='receipt and protected grade audit'
        outcome['workload']=audit_trial(service,plan,pair,target)
        phase='ordinary CLI report'
        nested=time.perf_counter()
        try:
            engine.cli('report',*common,'--operation-id','render','--report-id',outcome['workload']['report_id'],
                       '--output',WORK/'prefix-cache-report',output='report-cli.json')
        finally:
            excluded+=time.perf_counter()-nested
        outcome['passed']=True
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        outcome.update(stopped_phase=phase,error_type=type(error).__name__)
    finally:
        try:
            if proxy_started and engine.proxy_state(proxy)['Running']:
                engine.docker('stop','--time','5',proxy['proxy_name'])
            outcome['proxy_restored_stopped']=engine.proxy_state(proxy)==review['proxy']
        except Exception:
            outcome['proxy_restored_stopped']=False
        if overhead and outcome['proxy_restored_stopped'] and not outcome.get('worker_cleanup_uncertain'):
            try:
                setup, records=engine.scoped_setups(repo,setup_before,subject,bootstrap)
                repo.finish_operation(overhead,elapsed_seconds=max(0.,time.perf_counter()-began-excluded-setup))
                outcome['setup_cost_ids']=records
            except Exception as error:
                outcome['accounting_error_type']=type(error).__name__
        after=engine.previous.counters(repo)
        outcome['grant_after']=list(after)
        outcome['new_unresolved_reservations']=sorted(set(engine.reserved(repo))-set(pending))
        ledger=legacy['snapshot'](review['database'])
        outcome['historical_reservations_preserved']=ledger['prior_reservations_sha256']==review['grant']['prior_reservations_sha256']
        outcome['model_turns_reserved']=after[1]-initial[1]
        outcome['passed'] &= (outcome['proxy_restored_stopped'] and not outcome['new_unresolved_reservations']
                              and outcome['historical_reservations_preserved'] and after[3]==initial[3]
                              and outcome['model_turns_reserved']==1
                              and after[0]-initial[0]<=review['maximum_operations']
                              and after[2]-initial[2]<=review['maximum_reserved_seconds'])
        repo.reserve=original_reserve
        try:
            await router.close()
        finally:
            save(HERE/'result.json',outcome)
    print(json.dumps(outcome))
    return outcome['passed']


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--freeze',action='store_true')
    mode.add_argument('--preflight')
    mode.add_argument('--execute-approved')
    args=parser.parse_args()
    if args.freeze:
        freeze()
    else:
        review=read(REVIEW)
        identity=args.preflight or args.execute_approved
        selected=inspect(review,identity)
        if args.preflight:
            print(json.dumps({'review_sha256':identity,'preflight_passed':True,'model_turns':0,'provider_transfer':False}))
        else:
            raise SystemExit(not asyncio.run(execute(review,identity,*selected)))
