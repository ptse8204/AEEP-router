"""Freeze the managed turn, reply sandbox and separate zero-model validator check."""

import argparse
import asyncio
import shutil
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import StrictModel, utc_now
from aeep.qualification import behavior_fingerprint
from aeep.store import ReceiptStore

import run as driver

HERE, ROOT, C13, HANDOFF = driver.HERE, driver.ROOT, driver.C13, driver.HANDOFF
WORK = driver.WORK.parent
CAPTURE = HANDOFF
PRIVATE = WORK / 'calibration-finite-cycle'
CERTIFICATE = PRIVATE / 'certificates.json'
SKILLSBENCH = driver.SKILLSBENCH
PRIOR = C13/'integration-snapshot-correction-20261103'
PILOT = C13/'repository-usefulness-pilot-20261029'
AUTHORITY = C13/'pipeline-standing-authority-20261104.json'
sha, read, write = driver.sha, driver.read, driver.write


def local_validation_binding(name):
    prior = read(CAPTURE / 'operation-review.json')
    captured = read(CAPTURE / 'result.json')
    assert sha(CAPTURE / 'operation-review.json') == captured['review_sha256'] and captured['passed']
    args = [item.replace(prior['container_name'], name).replace(str(CAPTURE / 'capture.py'), str(HERE / 'cycle.py'))
            for item in prior['argv']]
    assert args[-1] == '/opt/aeep-capture.py' and '--network=none' in args and '--read-only' in args
    args.insert(args.index('run') + 1, '-i')
    mounts = [
        (HERE / 'variants.py', '/opt/aeep-variants.py'),
        (HERE.parent / 'public-cases.json', '/opt/aeep-public-cases.json'),
        (CERTIFICATE, '/opt/aeep-certificates.json'),
    ]
    i = args.index('--entrypoint')
    for src, dst in mounts:
        args[i:i] = ['--mount', f'type=bind,src={src},dst={dst},readonly']
    return {'request_sha256': captured['request_sha256'], 'initial_grade_sha256': captured['initial_grade_sha256'],
            'finish_argv': args, 'local_validator_container': name, 'docker': prior['docker'],
            'docker_environment': prior['environment'], 'certificate_file': str(CERTIFICATE)}


def cycle_assets():
    prior = read(CAPTURE / 'operation-review.json')
    guest_paths = [Path(item.split(',')[1].removeprefix('src='))
                   for item in prior['argv'] if item.startswith('type=bind,')]
    return [
        HERE / 'cycle.py', HERE / 'run.py', Path(__file__), HERE / 'variants.py', HERE / 'certify.py',
        CERTIFICATE, HERE.parent / 'public-cases.json', HERE.parent / 'calibration-preparation.json',
        CAPTURE / 'result.json', CAPTURE / 'operation-review.json', CAPTURE / 'ledger.json', AUTHORITY,
        *guest_paths,
    ]


class FixtureScope(StrictModel):
    review_sha256: str


def prepare_fixture():
    fixture = local_validation_binding('aeep-aflow-local-reply-fixture-20261106')
    fixture.update(
        purpose='First offline completion-path check with an explicitly first-party response fixture.',
        image=read(CAPTURE / 'operation-review.json')['image'],
        maximum_operations=1, maximum_seconds=70, models=0, provider_disclosure=False, automatic_retries=False,
        expires_at=(utc_now()+timedelta(hours=3)).isoformat(),
        fixture_output=str(WORK / 'calibration-cycle-fixture'),
        assets={str(path): sha(path) for path in cycle_assets()},
        ledger=read(CAPTURE / 'operation-review.json')['ledger'],
    )
    reply = {'xml': '<modification>Reject repeated requested labels</modification>'
                    '<graph>reject_duplicate</graph><prompt></prompt>'}
    fixture['fixture_payload_sha256'] = content_digest(reply)
    path = HERE/'reply-fixture-review.json'
    write(path,fixture)
    identity = sha(path)
    write(HERE/'reply-fixture-authority.json',{'review_sha256':identity,'first_attempt':True,
                                              'standing_authority_sha256':sha(AUTHORITY)})
    return identity,reply


async def run_fixture(fixture, identity, reply):
    assert sha(HERE/'reply-fixture-review.json') == identity
    assert fixture['fixture_payload_sha256'] == content_digest(reply)
    assert all(sha(path) == digest for path,digest in fixture['assets'].items())
    assert datetime.fromisoformat(fixture['expires_at']) > utc_now()
    assert shutil.disk_usage(ROOT).free >= 50*1024**3
    assert driver.docker(fixture,'image','inspect','--format','{{.Id}}',fixture['image']) == fixture['image']
    private = Path(fixture['fixture_output'])
    private.mkdir(mode=0o700)
    write(HERE/'reply-fixture-started.json',{'review_sha256':identity,'models':0})
    ref = content_digest(FixtureScope(review_sha256=identity))
    grant = AssessmentAuthorization(authorization_id='aflow-local-reply-fixture-20261106',
        subject_digests=[ref],recipe_digests=[ref],environment_digests=[ref],allowed_destinations=['local'],
        limits=AssessmentLimits(max_operations=1,max_elapsed_seconds=70),
        expires_at=utc_now()+timedelta(hours=2))
    scope = RecipeMaterializationRequest(plan_id=grant.authorization_id,authorization_id=grant.authorization_id,
        subject_digest=ref,recipe_digest=ref,mapping_digest=ref,environment_digest=ref,definition_digests=[ref],seed=0)
    result = {'review_sha256':identity,'kind':'first_party_contract_fixture','passed':False,'models':0,
              'provider_reply_validated':False,'provider_disclosure':False}
    with ReceiptStore(fixture['ledger']) as store:
        repo = AssessmentRepository(store)
        document = FixtureScope(review_sha256=identity)
        repo.put('toolkit_aflow_reply_fixture',ref,document)
        repo.approve_bundle(grant,{ref:document.model_dump(mode='json')})
        try:
            result['validation'] = await driver.validate_reply(fixture,repo,scope,reply,preflight=True)
            result['passed'] = True
        except BaseException as exc:
            result['error_type'] = type(exc).__name__
        finally:
            ledger = repo.operation_ledger(scope.plan_id).model_dump(mode='json')
            result['accounting_settled'] = len(ledger['operations']) == 1 and all(
                op['elapsed_seconds'] is not None for op in ledger['operations'])
            result['cleanup_verified'] = driver.named_container_absent(fixture,fixture['local_validator_container'])
            result['passed'] = result['passed'] and result['accounting_settled'] and result['cleanup_verified']
            write(HERE/'reply-fixture-result.json',result)
            write(HERE/'reply-fixture-ledger.json',ledger)
            receipt = private/'validation-receipt.json'
            if receipt.exists():
                write(HERE/'reply-fixture-receipt.json',read(receipt))
    return result


def prepare_turn():
    validated = read(HERE/'reply-fixture-result.json')
    assert validated['passed'] and validated['kind']=='first_party_contract_fixture'
    assert not validated['provider_reply_validated'] and validated['accounting_settled']
    assert validated['review_sha256'] == sha(HERE/'reply-fixture-review.json')
    assert shutil.disk_usage(ROOT).free >= 52*1024**3
    handoff, request_path, prompt, schema, wire = driver.payload()
    pair, shared = driver.pair_for(schema)
    prior = read(PRIOR/'operation-review.json')
    stopped = prior['proxy_metadata']
    assert not stopped['Running']
    database = read(driver.SOURCE_MANIFEST)['database']
    state = driver.grant_snapshot(database)
    deadline = min(utc_now()+timedelta(hours=16),datetime.fromisoformat(state['expires_at'])-timedelta(seconds=900))
    assert deadline > utc_now()
    assets = [
        *cycle_assets(), request_path,
        HERE / 'reply-fixture-review.json', HERE / 'reply-fixture-result.json', HERE / 'reply-fixture-receipt.json',
        driver.SOURCE_MANIFEST, driver.SOURCE_PAIR, driver.PRIOR_WORK / 'spring-shared.json',
        SKILLSBENCH / 'run-engineering.py', SKILLSBENCH / 'prepare-engineering.py',
        PRIOR / 'operation-review.json', PRIOR / 'run.py', PILOT / 'review-budget.py',
        PILOT / 'run-collector.py', PILOT / 'trial-evidence.py',
        C13 / 'evoagentx-distribution-20261106/managed-turn/reconciled-result.json',
    ]
    worker_images = {}
    for role in ('control','treatment'):
        spec = getattr(pair,role)
        runtime = driver.binding_from_config(spec.managed_host_config().managed_worker)
        assert runtime is not None
        assets.append(Path(runtime.runtime).resolve())
        worker_images[role] = runtime.image
    validation = local_validation_binding('aeep-aflow-managed-reply-20261106')
    assets.append(Path(validation['docker'][0]).resolve())
    review = {
        **validation,
        'scope':'One managed AFlow calibration turn, two zero-turn worker and collector inspections, and one protected offline optimization cycle.',
        'source_sha256':verification_source_digest(ROOT),'database':database,'grant':state,
        'model':'gpt-6-astra','reasoning_effort':'medium','allowed_provider_destination':'codex',
        'request_bytes':handoff['request_bytes'],'provider_text_sha256':wire,
        'provider_text_bytes':len((prompt+'\nReturn only JSON satisfying this output schema:\n'+driver.encode(schema)).encode()),
        'provider_output_schema_sha256':content_digest(schema),
        'pair_sha256':content_digest(pair),'shared_sha256':content_digest(shared),
        'turn_executor_fingerprint':behavior_fingerprint(pair.control),
        'worker_images':worker_images,
        'aflow_image':read(CAPTURE / 'operation-review.json')['image'],
        'proxy_id':stopped['Id'],'proxy_inspect_format':prior['proxy_inspect_format'],
        'stopped_proxy':stopped,'private_network':'aeep-reviewed-model-private','proxy_ip':'172.18.0.2',
        'maximum_operations':5,'maximum_reserved_seconds':880,'maximum_model_turns':1,'maximum_cash_usd':'0',
        'expires_at':deadline.isoformat(),'assets':{str(path):sha(path) for path in assets},
        'automatic_retries':False,'comparisons':'PAUSED','accounting_mode':'Existing onboarding grant, no ceiling or expiry change',
        'operator_notes':[
            'Use only the retained control worker for the model turn. Its named local profile keeps ordinary local tools available. The prompt forbids their use and any recorded tool call rejects the reply.',
            'The treatment worker participates in zero-turn containment only. No candidate skill or task artifact is supplied to the model turn.',
            'Disclose the captured public synthetic optimizer request, two permitted policy names and schema through the existing Codex proxy. Protected reference and score certificates stay local.',
            'Parse the actual reply with the pinned AFlow formatter and execute only the selected first-party workflow in the offline sandbox. Verify its output hash against the separately protected grading certificate. No model-authored code runs.',
            'Keep the prior reservations, return the proxy to stopped, and stop after one attempt on drift, failure, uncertainty or invalid reply.',
        ],
    }
    assert state['counters'][0]+review['maximum_operations'] <= state['limits']['max_operations']
    assert state['counters'][1]+review['maximum_model_turns'] <= state['limits']['max_model_turns']
    assert state['counters'][2]+review['maximum_reserved_seconds'] <= state['limits']['max_elapsed_seconds']
    assert Decimal(state['counters'][3])==0
    assert driver.proxy_state(review)==stopped
    path=HERE/'operation-review.json'
    write(path,review)
    return sha(path)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--first-local-fixture',action='store_true')
    mode.add_argument('--prepare-turn',action='store_true')
    args=parser.parse_args()
    if args.first_local_fixture:
        identity,reply=prepare_fixture()
        result=asyncio.run(run_fixture(read(HERE/'reply-fixture-review.json'),identity,reply))
        print(driver.encode(result))
        raise SystemExit(not result['passed'])
    print(prepare_turn())
