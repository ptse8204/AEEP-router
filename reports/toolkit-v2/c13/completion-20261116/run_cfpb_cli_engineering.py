"""Prepare or run one explicitly approved CFPB ordinary CLI engineering task."""
import argparse
import asyncio
import base64
import hashlib
import io
import json
import math
import runpy
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

from aeep.assessment.extensions import grader_name, require_environment
from aeep.assessment.models import AssessmentEnvironment, AssessmentLimits, IntegrationCaseSet, RecipeDefinition, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCase
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import ActionRequest, Manifest, ValidationSpec, utc_now
from aeep.registry import validate_json
from aeep.router import Router
from aeep.templates import render
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.models import EvidenceBundle, ExtensionManifest
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
WORK = ROOT/'.aeep/completion-20261116/cfpb-managed-engineering-20261117'
PROPOSAL = WORK.parent/'cfpb-ordinary-proposal-20261117'
SELECTED = WORK/'definitions'
LIVE = WORK/'execution'
REVIEW = WORK/'operation-review.json'
PREFIX = C13/'skillsbench-software-substitute-20261109/managed-preparation/managed-engineering'
PRIOR = runpy.run_path(str(PREFIX/'run.py'))
engine, read, sha, save = (PRIOR[key] for key in ('engine','read','sha','save'))
SEAL = runpy.run_path(str(WORK/'seal_images.py'))
TASK = 'short--cfpb-closing-disclosure-filled-sample-ec900645b7'
ROLE = 'cfpb'
CONFIG = 'cfpb-document-data'
TAG = 'cfpb-cli-engineering-20261117'
MODEL = 'gpt-6.1-sol'
PDF_PATH, PDF_SHA = (SEAL[key] for key in ('WHEEL_PATH','WHEEL_SHA'))
CARRIER = WORK.parent/'extractbench-cfpb-workflow-bound'
PROTECTED = CARRIER/'protected-context'
ASSETS = CARRIER/'pack-assets'
DATABASE = str(engine.BASE.parent/'aeep.sqlite3')
PROXY_REVIEW = engine.PREVIOUS/'operation-review.json'
SOURCE_RECORD = engine.PREVIOUS/'source.json'
AUDIT = PRIOR['TRIAL_AUDIT']
RIGHTS = PROPOSAL/'proposed-rights'/f'{TASK}.json'
PUBLIC = {'instruction.md','environment/document.pdf','environment/schema.json'}
PROMPT = (
    "Extract the public sample Closing Disclosure using the original instruction.md in the archive. "
    "Use Python zipfile to unpack the supplied archive inside /workspace. "
    "Read environment/document.pdf and environment/schema.json from that directory. "
    f"For local PDF text and layout, add {PDF_PATH} to sys.path before importing pypdf. "
    "Use local inspection and shell commands and keep temporary files inside /workspace. "
    "Write the requested JSON object only to the supplied output_path. Verify that the file is valid JSON "
    "and at most 200000 bytes. Return only {\"completed\":true} after saving it. "
    "Keep document contents out of the final message. Use the reviewed stack-check skill if available.\n{input}"
)
PDF_PROBE = f"""import hashlib, io, json, sys
from pathlib import Path
wheel = Path({PDF_PATH!r})
digest = hashlib.sha256(wheel.read_bytes()).hexdigest()
if digest != {PDF_SHA!r}:
    raise SystemExit(2)
sys.path.insert(0, str(wheel))
import pypdf
assert str(pypdf.__file__).startswith(str(wheel) + '/')
writer = pypdf.PdfWriter()
writer.add_blank_page(width=100, height=100)
stream = io.BytesIO()
writer.write(stream)
stream.seek(0)
print(json.dumps({{'pypdf':pypdf.__version__,'wheel_sha256':digest,'synthetic_pages':len(pypdf.PdfReader(stream).pages)}}))
"""
PDF_OBSERVATION = {'pypdf':'6.21.4','wheel_sha256':PDF_SHA,'synthetic_pages':1}


def image_check():
    record = read(WORK/'images.json')
    original = read(WORK/'image-build-review.json')
    assert record['build_review_sha256'] == sha(WORK/'image-build-review.json')
    assert record['continuation_review_sha256'] == sha(WORK/'seal-continuation-review.json')
    images = record['images']
    assert set(images) == {'grader','control','treatment'}
    for row in original['builds']:
        image = images[row['role']]
        facts = SEAL['image'](image['id'])
        assert all(facts[key] == image[key] for key in ('id','layers','config_sha256'))
        assert facts['layers'][:-1] == row['parent']['layers'] and facts['config_sha256'] == row['parent']['config_sha256']
        assert all(sha(Path(path)) == digest for path,digest in row['files'].items())
    return images


def definitions():
    rights = TaskRightsReview.model_validate(read(RIGHTS))
    pack = BenchmarkPack.model_validate(read(PROPOSAL/'pack.json'))
    task = pack.task(TASK)
    assert rights.task_id == TASK and rights.source_revision == pack.source.revision
    assert rights.assets == {asset.path:asset.sha256 for asset in task.assets}
    assert rights.provider_disclosure_allowed and rights.local_execution_allowed
    assert content_digest(rights) == task.rights_review_ref
    value = task_input(pack,ASSETS,TASK)
    raw = base64.b64decode(value['task_archive_b64'],validate=True)
    with ZipFile(io.BytesIO(raw)) as archive:
        public = {name:hashlib.sha256(archive.read(name)).hexdigest() for name in archive.namelist()}
        assert len(archive.infolist()) == 3 and set(public) == PUBLIC
    previous = read(PROPOSAL/'preparation-result.json')
    listed, = [row for row in previous['sendable_archives'] if row['task_id'] == TASK]
    assert public == listed['public_files'] and len(raw) == listed['archive_bytes']
    assert hashlib.sha256(raw).hexdigest() == value['task_archive_sha256'] == listed['archive_sha256']
    images = image_check()
    recipe = RecipeDefinition.model_validate(read(PROPOSAL/'recipe.json'))
    validate_json(value,recipe.input_schema,label='disclosure-bound CFPB input')
    environment = AssessmentEnvironment.model_validate(read(PROPOSAL/'retained-environment.json')).model_copy(update={
        'environment_id':TAG+'-grader','container_image':images['grader']['id'],
    })
    require_environment(recipe,environment)
    # Reference mode only reads and returns the already reviewed oracle bytes.
    guest = runpy.run_path(str(HERE/'extractbench_recipe_guest.py'))
    aliases = read(PROPOSAL/'overlay/bindings.json')
    selected_alias = aliases[content_digest(value)]
    assert selected_alias['case'] == TASK
    reference = guest['evaluate']('reference',{'inputs':[value]},aliases,PROTECTED,None)['outputs'][0]
    validate_json(reference,recipe.output_schema,label='protected CFPB output shape')

    old = read(PRIOR['DEFS']/'pair.json')
    old_pair = WorkerPairInspection.model_validate(old)
    shared = {'purpose':'One CFPB ordinary CLI engineering task', 'task_id':TASK,
              'recipe':content_digest(recipe),'public_archive_sha256':value['task_archive_sha256'],
              'source_sha256':verification_source_digest(ROOT),'pdf_wheel_sha256':PDF_SHA,
              'worker_images':{role:images[role]['id'] for role in ('control','treatment')},
              'reference_pair':content_digest(old_pair)}
    diff = old['differential']
    common = diff['control_inventory'] | {'common_profile':content_digest(shared),'pypdf':PDF_SHA}
    diff.update(shared_definition_digest=content_digest(shared),control_inventory=common,
                treatment_inventory=common | diff['candidate_inventory'])
    output = {'input_field':'task_archive_b64','input_name':'cfpb-task.zip','output_field':'prediction_b64',
              'output_name':'output.json','max_bytes':200000}
    for role in ('control','treatment'):
        spec = old[role]
        spec.update(id='extractbench-cfpb.'+role,capability=recipe.capability,
                    input_schema=recipe.input_schema,output_schema=recipe.output_schema)
        config = spec['config']
        config.update(instructions=PROMPT,artifact=output)
        binding = config['managed_worker']
        binding.update(worker_id=TAG+'-'+role,image=images[role]['id'])
        binding['reviewed_files'][PDF_PATH] = PDF_SHA
    pair = WorkerPairInspection.model_validate(old)
    for role in ('control','treatment'):
        cfg = getattr(pair,role).managed_host_config()
        assert tuple(cfg.model_constraints.allowed_model_ids) == (MODEL,) and tuple(cfg.reasoning_efforts) == ('medium',)
        assert not cfg.store_prompt and not cfg.store_output
    truth = {'input_sha256':content_digest(value)}
    case = BenchmarkCase(case_id=TASK,split='qualification',variation=TASK,template_family='extractbench:cfpb-closing-disclosure',
        action=ActionRequest(action_id=TASK,capability=recipe.capability,input=value),
        validators=[ValidationSpec(kind='callback',config={'name':grader_name(value,truth),'expected':truth})])
    cases = IntegrationCaseSet(request_id=TAG+'-cases',recipe_digest=content_digest(recipe),
                               environment_digest=content_digest(environment),benchmark_pack_digest=value['benchmark_pack_sha256'],
                               seed=0,cases=[case])
    prompt_fields = {key:item for key,item in value.items() if key!='task_archive_b64'}
    prompt_fields.update(input_path='/workspace/cfpb-task.zip',output_path='/workspace/output.json')
    instruction = str(render(PROMPT,{'input':prompt_fields}))
    assert value['task_archive_b64'] not in instruction and '/Users/' not in instruction
    disclosure = {'archive_sha256':value['task_archive_sha256'],'archive_bytes':len(raw),
                  'public_files':public,'prompt_sha256':hashlib.sha256(instruction.encode()).hexdigest(),
                  'task_id':TASK, 'instruction_field_sha256':hashlib.sha256(value['task'].encode()).hexdigest()}
    return rights,pack,recipe,pair,shared,environment,cases,ASSETS,disclosure


def build_workflow(recipe):
    definitions = read(PROPOSAL/'workflow.json')
    registry = read(PROPOSAL/'registry.json')
    previous_registry = read(PRIOR['DEFS']/'registry.json')
    previous_policy = read(PRIOR['DEFS']/'policy.json')
    evaluator = next(item for item in previous_registry['extensions'] if item['extension_id']=='aeep-evaluator')
    extractor = next(item for item in registry['extensions'] if item['extension_id']=='extractbench')
    rights = 'Proposed: three exact public CFPB sample files for one Codex engineering run.'
    for item in (evaluator,extractor):
        item.update(status='experimental',blockers=[],disk_bytes=0,purpose='One controlled CFPB engineering run',
                    install_effects=['Reuse the sealed local images and existing scoped Codex proxy.'])
        item['source'].update(data_rights=rights,
             artifact_sha256=content_digest({'component':item['extension_id'],'recipe':content_digest(recipe)}))
    previous_policy['allowed_data_rights'] = [rights]
    previous_policy['free_disk_bytes'] = 50*2**30
    previous_policy['reviewed_dependency_manifests'] = [
        engine.manifest_digest(ExtensionManifest.model_validate(item)) for item in (evaluator,extractor)]
    save(SELECTED/'registry.json',{'schema_version':'aeep.toolkit.registry.v1','extensions':[evaluator,extractor]})
    save(SELECTED/'policy.json',previous_policy)
    definitions.update(registry=engine.binding(SELECTED/'registry.json'),policy=engine.binding(SELECTED/'policy.json'))
    target = definitions['configurations'][CONFIG]
    target.update(candidate={'path':str(engine.prepared.SKILL),'sha256':read(SOURCE_RECORD)['artifact_sha256']},
                  task_ids=[TASK],assessment=None,preparation=None)
    save(SELECTED/'workflow.json',definitions)


def fixtures(parts):
    # Exercise the existing inert ordinary-CLI draft, replacing its frozen input definitions.
    fixture = runpy.run_path(str(PREFIX/'check.py'))
    check, config = fixture['check'], fixture['RUN']
    rights,pack,recipe,pair,shared,environment,cases,assets,disclosure = parts
    config.update(definitions=lambda:(rights,pack,recipe,pair,shared,environment,cases,assets,disclosure['public_files']),
                  DEFS=SELECTED,CONFIGURATION=CONFIG,CONFIG=('--configuration',CONFIG))
    # The fixture only writes its own temporary DB, within the reviewed work tree.
    scratch = WORK/'offline-cli-fixture'
    scratch.mkdir(mode=0o700)
    result = check(scratch)
    assert result['unreviewed_rights_rejected'] and not result['provider_transfer']
    assert result['model_turns'] == result['jobs_created'] == result['workers_started'] == 0
    assert engine.budget.self_check() == 7
    return result


def pins():
    initial = [
        Path(__file__), PREFIX/'run.py', PREFIX/'check.py', Path(PRIOR['legacy']['__file__']),
        Path(PRIOR['owner']['__file__']), Path(engine.__file__), Path(engine.prepared.__file__),
        Path(engine.previous.__file__), Path(engine.previous.prepared.__file__), Path(engine.budget.__file__),
        Path(engine.collector.__file__), Path(engine.evidence.__file__), AUDIT, engine.BASE, SOURCE_RECORD,
        PROXY_REVIEW, Path('/usr/local/bin/docker').resolve(), WORK/'images.json', WORK/'image-build-review.json',
        WORK/'seal-continuation-review.json', WORK/'seal_images.py', WORK/'continue_seal.py',
        WORK/'seal/ledger.json', WORK/'draft-check.json', RIGHTS, PROPOSAL/'pack.json', PROPOSAL/'recipe.json',
        PROPOSAL/'preparation-result.json', PROPOSAL/'overlay/bindings.json', PROPOSAL/'workflow.json',
        PRIOR['DEFS']/'pair.json', PRIOR['DEFS']/'registry.json', PRIOR['DEFS']/'policy.json',
        HERE/'extractbench-cfpb-source-review.json', HERE/'cfpb-local-component-result-20261117.json',
        HERE/'extractbench_recipe_guest.py', C13/'pipeline-standing-authority-20261104.json',
    ]
    return {str(path):sha(path) for path in [
        *initial, *SELECTED.glob('*.json'), *[p for p in engine.prepared.SKILL.rglob('*') if p.is_file()],
        *[ASSETS/'tasks'/TASK/name for name in sorted(PUBLIC)],
    ]}


def freeze():
    parts = definitions()
    rights,pack,recipe,pair,shared,environment,cases,assets,disclosure = parts
    SELECTED.mkdir(mode=0o700)
    for name,value in (('rights',rights),('recipe',recipe),('pair',pair),('environment',environment),
                       (ROLE+'-integration-cases',cases)):
        save(SELECTED/(name+'.json'),value.model_dump(mode='json'))
    save(SELECTED/'shared.json',shared)
    build_workflow(recipe)
    preview = engine.cli('plan','--workflow',SELECTED/'workflow.json','--configuration',CONFIG)
    assert preview['blockers'] == ['canonical assessment preparation and applicable worker/grader evidence remain required']
    fixture = fixtures(parts)
    save(WORK/'draft-check.json',fixture)
    grant = PRIOR['legacy']['snapshot'](DATABASE)
    proxy_ref = read(PROXY_REVIEW)
    proxy = engine.proxy_state(proxy_ref)
    assert proxy == proxy_ref['proxy_metadata'] and not proxy['Running']
    expiry = min(utc_now()+timedelta(hours=48),datetime.fromisoformat(grant['expires_at']))
    assert expiry > utc_now()
    scope = {'maximum_operations':64,'maximum_model_turns':1,'maximum_reserved_seconds':3900,'maximum_cash_usd':'0'}
    counters = grant['counters']
    for current, key, bound in zip(counters[:3],('max_operations','max_model_turns','max_elapsed_seconds'),
                                  (64,1,3900),strict=True):
        assert current+bound <= grant['limits'][key]
    review = {
        'schema_version':'aeep.c13.cfpb-engineering-operation-review.v1',
        'scope':'One ordinary CLI CFPB filled-sample engineering task, one skill route.',
        'stop_conditions':['artifact, source, grant or proxy drift','worker, PDF or collector probe failed',
                           'allowance unavailable','uncertain cleanup or accounting'],
        'pins':pins(), 'source_sha256':verification_source_digest(ROOT),
        'disclosure':disclosure | {'destination':'codex','rights_review_ref':content_digest(rights),
            'retained_skill_files':{str(p.relative_to(engine.prepared.SKILL)):sha(p)
                                   for p in sorted(engine.prepared.SKILL.rglob('*')) if p.is_file()},
            'protected_local':['grader image and protected reference, tests, assets and other tasks'],
            'source_revision':pack.source.revision},
        'recipe_digest':content_digest(recipe),'pair_digest':content_digest(pair),
        'grader_environment_digest':content_digest(environment),'case_set_digest':content_digest(cases),
        'image_ids':{role:image['id'] for role,image in image_check().items()},
        'database':DATABASE,'grant':grant,'expires_at':expiry.isoformat(),'grant_amendment':None,
        'proxy':proxy,'model':MODEL,'reasoning_effort':'medium','fresh_worker_checks':2,
        'checks':['fresh paired zero-turn worker, catalogue, boundaries, PDF and collector denial',
                  'ordinary CLI prepare, one required-skill route and verified allowance',
                  'protected native F1 and exact-match grade, receipt-bound tokens, Markdown and HTML reports',
                  'settled operation ledger and restoration of the existing proxy to stopped'],
        'fixture_allowance':fixture['campaign_upper_allowance'],'workflow_preview_sha256':preview['review_sha256'],
        'minimum_free_gib':50,'downloads':0,'image_builds':0,'installations':0,'automatic_retries':False,
        'model_fallback':False,'comparisons_paused':True,'waza_excluded':True,'release':False,
    } | scope
    save(REVIEW,review)
    inspect(sha(REVIEW))
    print(sha(REVIEW))


def guard(review,exact):
    assert __debug__ and sha(REVIEW)==exact and verification_source_digest(ROOT)==review['source_sha256']
    assert utc_now() < datetime.fromisoformat(review['expires_at']) and shutil.disk_usage(ROOT).free >= 50*2**30
    assert pins()==review['pins'] and review['model']==MODEL and review['reasoning_effort']=='medium'
    assert review['maximum_model_turns']==1 and review['maximum_cash_usd']=='0'
    assert review['comparisons_paused'] and review['waza_excluded']
    assert not any(review[name] for name in ('model_fallback','automatic_retries','image_builds','downloads','installations','release'))
    assert {role:row['id'] for role,row in image_check().items()} == review['image_ids']


def inspect(exact):
    review = read(REVIEW)
    guard(review,exact)
    assert not LIVE.exists() and PRIOR['legacy']['snapshot'](DATABASE)==review['grant']
    proxy_ref = read(PROXY_REVIEW)
    assert engine.proxy_state(proxy_ref)==review['proxy']==proxy_ref['proxy_metadata'] and not review['proxy']['Running']
    rights,pack,recipe,pair,shared,environment,cases,assets,disclosure = definitions()
    for key,expected in (('recipe_digest',recipe),('pair_digest',pair),
                         ('grader_environment_digest',environment),('case_set_digest',cases)):
        assert content_digest(expected)==review[key]
    assert review['disclosure']['rights_review_ref']==content_digest(rights)
    assert all(review['disclosure'][key]==value for key,value in disclosure.items())
    for name,value in (('rights',rights),('recipe',recipe),('pair',pair),('environment',environment),
                       (ROLE+'-integration-cases',cases)):
        assert read(SELECTED/(name+'.json'))==value.model_dump(mode='json')
    assert read(SELECTED/'shared.json')==shared
    assert read(WORK/'draft-check.json')['campaign_upper_allowance']==review['fixture_allowance']
    preview = engine.cli('plan','--workflow',SELECTED/'workflow.json','--configuration',CONFIG)
    assert preview['review_sha256']==review['workflow_preview_sha256']
    return review, proxy_ref, (recipe,pair,shared,environment)


def audited_trial(service,plan,pair,destination):
    module = runpy.run_path(str(AUDIT))
    record = module['audit'](engine,service,plan,pair)
    engine.evidence.require_complete(record)
    assert record['case_id']==TASK and record['artifact_transferred'] and record['retries']==0
    assert record['job_state']=='complete' and record['job_error_code'] is None
    score = record['score']
    assert type(score) in (float,int) and math.isfinite(score) and 0<=score<=1
    assert record['task_grade'] is (score==1.0)
    assert record['candidate_loading']['instructions_loaded'] is True
    bundle = EvidenceBundle.model_validate_json((destination/'toolkit-evidence.json').read_bytes())
    run, = bundle.runs
    assert run.receipt_refs==(record['receipt_ref'],) and run.model==MODEL and run.effort=='medium'
    assert run.status=='completed' and run.mode=='forced_diagnostic' and run.retries==0
    assert run.verification==('pass' if record['task_grade'] else 'fail')
    assert run.tokens is not None and run.tokens.source_ref==record['receipt_ref']
    for key, count in record['token_counts_provider_reported'].items():
        if key in type(run.tokens).model_fields:
            assert getattr(run.tokens,key)==count
    summary = read(destination/'summary.json')
    assert summary['outcome']=='NOT_ASSESSED' and summary['managed_analysis']['distinct_paired_cases']==0
    assert summary['managed_analysis']['unresolved_operations']==0
    assert summary['evidence_sha256']==content_digest(bundle.model_dump(mode='json'))
    return record


async def execute(exact):
    review,proxy,selected = inspect(exact)
    approval = WORK/'operator-approval.json'
    if not approval.is_file() or read(approval) != {'approved':True,'review_sha256':exact}:
        raise ValueError('exact CFPB disclosure and engineering approval required')
    recipe,pair,shared,environment = selected
    LIVE.mkdir(mode=0o700)
    save(LIVE/'started.json',{'review_sha256':exact,'automatic_retry':False})
    engine.WORK,engine.MANIFEST,engine.CAMPAIGNS = LIVE,LIVE/'aeep.json',LIVE/'campaigns'
    engine.prepared.DEFINITIONS = SELECTED
    engine.emit = lambda name,value: save(LIVE/name,value)
    engine.grader_environment = lambda role: environment
    spec = Manifest.model_validate(read(engine.BASE)).model_copy(update={'executors':[pair.control,pair.treatment]})
    assert str(spec.database)==DATABASE and PRIOR['legacy']['snapshot'](DATABASE)==review['grant']
    save(engine.MANIFEST,spec.model_dump(mode='json'))
    router = Router.from_manifest(engine.MANIFEST)
    service = AssessmentService(router,engine.CAMPAIGNS)
    repo = service.repository
    initial = engine.previous.counters(repo)
    pending = engine.reserved(repo)
    assert list(initial)==review['grant']['counters'] and len(pending)==review['grant']['prior_reservations']
    original_reserve = engine.budget.install(repo,repo.store._connection,initial,review)
    original_collect = engine.inspection.collect
    result = {'review_sha256':exact,'passed':False,'comparisons_paused':True,'waza_excluded':True}
    overhead, excluded, proxy_attempted = None,0.0,False
    worker_probe_started, worker_cleanup_verified = False,False
    start = time.perf_counter()
    setup_before = {row[0] for row in repo.store._connection.execute("SELECT id FROM assessment_records WHERE kind='setup_cost'")}
    phase = 'scope and asset-use registration'
    try:
        subject = service.inspect_local(engine.prepared.SKILL,kind='skill')
        repo.put('recipe',recipe.recipe_id,recipe)
        local = AssessmentEnvironment(environment_id=TAG+'-local',kind='trusted_local',
                                      identity={'source_digest':review['source_sha256'],'review':exact})
        repo.put('environment',content_digest(local),local)
        bootstrap = engine.materialization(repo,TAG+'-overhead',subject,recipe,local)
        engine.scoped_approval(repo,[bootstrap])
        overhead = bootstrap.plan_id+':exclusive'
        repo.reserve(bootstrap,overhead,AssessmentLimits(max_operations=1,max_elapsed_seconds=180),
                     stage='owned_workflow_preparation_and_proxy_overhead')
        repo.put('shared_environment_definition',content_digest(shared),engine.previous.Document(value=shared))
        rights = engine.cli('define-rights','--manifest',engine.MANIFEST,'--file',RIGHTS,output='define-rights.json')
        rights_ref = review['disclosure']['rights_review_ref']
        assert rights=={'rights_review_ref':rights_ref,'reviewed':False,'execution_authorized':False}
        repo.review(rights_ref)

        phase = 'worker, PDF and collector readiness'
        guard(review,exact)
        assert engine.proxy_state(proxy)==review['proxy']
        proxy_attempted = True
        engine.docker('start',proxy['proxy_name'])
        active = engine.proxy_state(proxy)
        assert active['Running'] and active['Id']==review['proxy']['Id'] and active['Image']==review['proxy']['Image']
        assert active['Networks']['aeep-reviewed-model-private']['IPAddress']=='172.18.0.2'
        ids = engine.worker_requests(service,ROLE,pair,recipe,subject,review['source_sha256'])
        collector = engine.inspect_collector(original_collect)
        async def collect(adapter,config,journal,recheck):
            facts = await collector(adapter,config,journal,recheck)
            if facts.get('inspection_complete'):
                recheck()
                observed = await engine.inspection.command(adapter,PDF_PROBE)
                assert observed==PDF_OBSERVATION
                journal.append('artifact.created','cfpb-synthetic-pdf-read',evidence_ref=content_digest(observed))
                facts['cfpb_pdf_reader'] = observed
            return facts
        engine.inspection.collect = collect
        nested = time.perf_counter()
        try:
            worker_probe_started = True
            pair_result = await engine.inspection.execute_pair(service,*ids)
        finally:
            excluded += time.perf_counter()-nested
            engine.inspection.collect = original_collect
        facts = [repo.get('worker_pair_inspection','pair-inspection:'+request)['observations'] for request in ids]
        worker_cleanup_verified = all(f['cleanup_confirmed'] and not f.get('cleanup_error_type') for f in facts)
        assert worker_cleanup_verified and pair_result['probes_match'] and pair_result['model_turns']==0
        assert all(f['inspection'].get('collector_boundary')=={'collector_connection_denied':True}
                   and f['inspection'].get('cfpb_pdf_reader')==PDF_OBSERVATION for f in facts)
        boundary = engine.readiness(repo,ROLE,ids,pair,review['source_sha256'])

        phase = 'canonical CLI prepare and allowance'
        case = {'configuration':CONFIG,'task_id':TASK}
        plan,eng_ref,accounting,bound,workflow_ref,allowance = engine.draft(
            service,ROLE,(case,recipe,pair,shared),subject,boundary,read(SELECTED/'workflow.json'),
            review['source_sha256'],run_tag=TAG)
        ops,turns,seconds = engine.measure_allowance(allowance)
        assert turns==1 and plan.suite.cases[0].case_id==TASK
        assert plan.suite.cases[0].action.input['task_archive_sha256']==review['disclosure']['archive_sha256']
        engine.budget.require_room(engine.previous.counters(repo),initial,
                                   AssessmentLimits(max_operations=ops,max_model_turns=turns,max_elapsed_seconds=seconds),review)
        save(LIVE/'dispatch-ready.json',{'plan_digest':content_digest(plan),'plan_id':plan.plan_id,
             'review_sha256':exact,'engineering_ref':eng_ref,'workflow_ref':workflow_ref,'worker_inspections':2})

        phase = 'one ordinary CLI engineering task'
        guard(review,exact)
        assert read(WORK/'operator-approval.json')=={'approved':True,'review_sha256':exact}
        assert set(engine.reserved(repo)) <= set(pending) | {overhead}
        common = ('--workflow',bound,'--configuration',CONFIG,'--manifest',engine.MANIFEST,'--directory',engine.CAMPAIGNS,
                  '--reviewed-digest',workflow_ref,'--accounting',accounting)
        destination = LIVE/'cfpb-result'
        nested = time.perf_counter()
        try:
            engine.cli('run',*common,'--operation-id','execute','--output',destination,
                       '--engineering-review',eng_ref,output='run-cli.json',timeout=2100)
        finally:
            excluded += time.perf_counter()-nested
        phase = 'receipt, native grade and reporting'
        result['trial'] = audited_trial(service,plan,pair,destination)
        nested = time.perf_counter()
        try:
            engine.cli('report',*common,'--operation-id','render','--report-id',result['trial']['report_id'],
                       '--output',LIVE/'cfpb-report',output='report-cli.json')
        finally:
            excluded += time.perf_counter()-nested
        result['passed'] = True
    except (Exception,asyncio.CancelledError,KeyboardInterrupt) as error:
        result.update(stopped_phase=phase,error_type=type(error).__name__)
        raise
    finally:
        try:
            if proxy_attempted and engine.proxy_state(proxy)['Running']:
                engine.docker('stop','--time','5',proxy['proxy_name'])
            result['proxy_restored_stopped'] = engine.proxy_state(proxy)==review['proxy']
        except Exception:
            result['proxy_restored_stopped'] = False
        result['worker_cleanup_uncertain'] = worker_probe_started and not worker_cleanup_verified
        if (overhead and result['proxy_restored_stopped'] and not result['worker_cleanup_uncertain']
                and set(engine.reserved(repo)) <= set(pending) | {overhead}):
            try:
                setup,records = engine.scoped_setups(repo,setup_before,subject,bootstrap)
                repo.finish_operation(overhead,elapsed_seconds=max(0.0,time.perf_counter()-start-excluded-setup))
                result['setup_cost_ids'] = records
            except Exception as error:
                result['accounting_error_type'] = type(error).__name__
        after = engine.previous.counters(repo)
        result['grant_after'] = list(after)
        result['new_unresolved_reservations'] = sorted(set(engine.reserved(repo))-set(pending))
        restored = PRIOR['legacy']['snapshot'](DATABASE)
        result['historical_reservations_preserved'] = restored['prior_reservations_sha256']==review['grant']['prior_reservations_sha256']
        result['model_turns_reserved'] = after[1]-initial[1]
        result['passed'] &= (result['proxy_restored_stopped'] and not result['new_unresolved_reservations']
                             and result['historical_reservations_preserved'] and after[3]==initial[3]
                             and result['model_turns_reserved']==1 and after[0]-initial[0]<=review['maximum_operations']
                             and after[2]-initial[2]<=review['maximum_reserved_seconds'])
        repo.reserve = original_reserve
        try:
            await router.close()
        finally:
            save(LIVE/'result.json',result)
    return result['passed']


if __name__=='__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--freeze',action='store_true')
    modes.add_argument('--preflight')
    modes.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        inspect(args.preflight)
        print(json.dumps({'review_sha256':args.preflight,'preflight_passed':True,'model_turns':0,'provider_transfer':False}))
    else:
        raise SystemExit(not asyncio.run(execute(args.execute_approved)))
