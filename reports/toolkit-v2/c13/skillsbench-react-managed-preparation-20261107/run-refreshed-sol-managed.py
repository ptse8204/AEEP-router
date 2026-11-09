"""Bind the verified 0.159.1 workers to the existing Sol-only engineering runner."""

import argparse
import asyncio
import runpy
from datetime import datetime, timedelta
from pathlib import Path

from aeep.assessment.extensions import require_environment
from aeep.assessment.models import AssessmentBudgetAmendment, AssessmentEnvironment, AssessmentLimits, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
runner = runpy.run_path(str(HERE / 'run-sol-managed.py'))
engine, read, sha, save = (runner[name] for name in ('engine', 'read', 'sha', 'save'))
WORK, ORIGINAL = runner['WORK'], runner['REVIEW']
LIVE = HERE / 'sol-01591-live-20261109'
REVIEW = LIVE / 'operation-review.json'
DEFS = WORK / 'sol-01591-live-definitions'
EXEC = WORK / 'sol-01591-live-execution'
TAG = 'react-sol-01591-20261109'
MODEL = 'gpt-6.1-sol'
DELEGATION = HERE.parent / 'pipeline-standing-authority-20261104.json'


def grader_current():
    environment = AssessmentEnvironment.model_validate(read(DEFS / 'react-environment.json'))
    proof = read(HERE / 'self-contained-result.json')
    assert proof['passed'] and proof['accounting_settled'] and proof['image']['id'] == environment.container_image
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', environment.container_image) == environment.container_image
    return environment


def configure_runner():
    entry = runner['execute']
    entry.__globals__.update(HERE=LIVE, DEFS=DEFS, EXEC=EXEC, REVIEW=REVIEW, grader_current=grader_current)
    materialization, draft = engine.materialization, engine.draft

    def scoped_materialization(repo, identity, subject, recipe, environment, **kwargs):
        if identity == 'react-sol-managed-overhead-20261108':
            identity = TAG + '-overhead'
        return materialization(repo, identity, subject, recipe, environment, **kwargs)

    def scoped_draft(*args, run_tag):
        assert run_tag == 'react-sol-20261108'
        return draft(*args, run_tag=TAG)

    engine.materialization = scoped_materialization
    engine.draft = scoped_draft
    return entry


def freeze():
    old = read(ORIGINAL)
    stopped = read(HERE / 'sol-managed-result.json')
    assert stopped['review_sha256'] == sha(ORIGINAL) and not stopped['passed']
    assert stopped['model_turns_reserved'] == 0 and stopped['proxy_restored_stopped']
    assert stopped['historical_reservations_preserved'] and not stopped['new_unresolved_reservations']
    refresh = read(HERE / 'sol-client-worker-result.json')
    assert refresh['review_sha256'] == sha(HERE / 'sol-client-worker-renewal.json')
    assert refresh['passed'] and refresh['accounting_settled'] and refresh['operations'] == 4 and refresh['models'] == 0
    context = read(HERE / 'sol-client-context.json')
    current = runner['first']['snapshot'](old['database'])
    assert current['counters'] == stopped['grant_after']
    assert datetime.fromisoformat(current['expires_at']) < utc_now()
    expiry = utc_now() + timedelta(hours=48)
    amendment = AssessmentBudgetAmendment(
        amendment_id='skillsbench-react-sol-01591-expiry-20261109', authorization_id='onboarding',
        authorization_digest=current['root_sha256'], previous_amendment_digest=current['amendment_sha256'],
        limits=AssessmentLimits.model_validate(current['limits']), issued_at=utc_now(), expires_at=expiry,
    )
    renewed = current | {'amendment_sha256': content_digest(amendment), 'expires_at': expiry.isoformat()}

    case, = old['cases']
    old_pair = read(case['pair'])
    pair = read(case['pair'])
    old_defs = runner['DEFS']
    images = {}
    for arm, role in (('control', 'control'), ('treatment', 'candidate')):
        catalogue = refresh['catalogues'][role]
        assert catalogue['visible_sol_models'] == 1 and catalogue['medium_supported']
        assert catalogue['network_denied'] and not catalogue['account_read'] and catalogue['model_turns'] == 0
        image = refresh['images'][role]['id']
        assert context['roles'][role]['parent']['id'] == old['worker_image_ids'][arm]
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image
        cfg = pair[arm]['config']
        assert cfg['model_constraints']['allowed_model_ids'] == [MODEL] and cfg['reasoning_efforts'] == ['medium']
        assert cfg['argv'][1:] == ['app-server']
        pair[arm]['id'] = f'skillsbench-react-sol-01591.{arm}'
        cfg['argv'][0] = context['new_binary']
        cfg['adapter_id'] = f'codex-app-server:skillsbench-react-sol-01591-{arm}'
        cfg['adapter_options']['expected_user_agent'] = catalogue['protocol_version']
        cfg['managed_worker'].update(image=image, binary=context['new_binary'], binary_sha256=context['binary_sha256'],
                                     worker_id=f'skillsbench-react-sol-01591-{arm}')
        images[arm] = image

    shared = read(case['shared']) | {'client_version': context['source_version'], 'worker_images': images,
                                     'client_binary_sha256': context['binary_sha256']}
    common = pair['differential']['control_inventory'] | {'common_profile': content_digest(shared)}
    pair['differential'].update(shared_definition_digest=content_digest(shared), control_inventory=common,
        treatment_inventory=common | pair['differential']['candidate_inventory'])
    validated = WorkerPairInspection.model_validate(pair)
    for arm in ('control', 'treatment'):
        expected = old_pair[arm]['config']['managed_worker']
        updated = pair[arm]['config']['managed_worker']
        changed = {key for key in expected if expected[key] != updated[key]}
        assert changed == {'image', 'binary', 'binary_sha256', 'worker_id'}
        assert pair[arm]['config']['artifact'] == old_pair[arm]['config']['artifact']

    LIVE.mkdir()
    DEFS.mkdir(mode=0o700)
    for name in ('react-recipe.json', 'react-environment.json', 'react-integration-cases.json', 'workflow.json'):
        save(DEFS / name, read(old_defs / name))
    save(DEFS / 'react-pair.json', validated.model_dump(mode='json'))
    save(DEFS / 'react-shared.json', shared)
    recipe = runner['RecipeDefinition'].model_validate(read(DEFS / 'react-recipe.json'))
    require_environment(recipe, grader_current())
    case.update(recipe=str(DEFS / 'react-recipe.json'), pair=str(DEFS / 'react-pair.json'),
        pair_digest=content_digest(validated), shared=str(DEFS / 'react-shared.json'),
        grader_environment=str(DEFS / 'react-environment.json'))
    paths = [Path(__file__).resolve(), ORIGINAL, HERE / 'sol-managed-result.json', HERE / 'sol-managed-model-blocker.json',
             HERE / 'sol-client-worker-result.json', HERE / 'sol-client-worker-renewal.json',
             HERE / 'sol-client-context.json', DELEGATION, *sorted(DEFS.glob('*.json'))]
    review = old | {
        'scope': 'Fresh account and boundary verification on the refreshed workers, then one unstarted React Sol turn.',
        'previous_review_sha256': sha(ORIGINAL), 'offline_review_sha256': refresh['review_sha256'],
        'pins': old['pins'] | {str(path): sha(path) for path in paths}, 'cases': [case],
        'definitions': str(DEFS), 'work': str(EXEC), 'worker_image_ids': images,
        'client_version': context['source_version'], 'grant_before_expiry_amendment': current,
        'expiry_amendment': amendment.model_dump(mode='json'), 'grant': renewed, 'expires_at': expiry.isoformat(),
        'maximum_operations': 67, 'maximum_reserved_seconds': 3850,
    }
    assert runner['verification_source_digest'](runner['ROOT']) == review['source_sha256']
    proxy = read(engine.PREVIOUS / 'operation-review.json')
    assert engine.proxy_state(proxy) == review['proxy']
    assert all(sha(path) == digest for path, digest in review['pins'].items())
    save(REVIEW, review)
    print(sha(REVIEW))


def execute(identity):
    review = read(REVIEW)
    assert sha(REVIEW) == identity
    assert read(LIVE / 'sol-managed-approval.json') == {'approved': True, 'review_sha256': identity}
    assert not (LIVE / 'expiry-amendment-started.json').exists()
    assert not (LIVE / 'sol-managed-started.json').exists() and not EXEC.exists()
    assert utc_now() < datetime.fromisoformat(review['expires_at'])
    assert runner['verification_source_digest'](runner['ROOT']) == review['source_sha256']
    assert all(sha(path) == digest for path, digest in review['pins'].items())
    previous = review['grant_before_expiry_amendment']
    assert runner['first']['snapshot'](review['database']) == previous
    amendment = AssessmentBudgetAmendment.model_validate(review['expiry_amendment'])
    assert amendment.limits.model_dump(mode='json') == previous['limits']
    assert amendment.previous_amendment_digest == previous['amendment_sha256']
    assert amendment.authorization_digest == previous['root_sha256']
    assert review['grant'] == previous | {'amendment_sha256': content_digest(amendment),
                                         'expires_at': amendment.expires_at.isoformat()}
    with ReceiptStore(review['database']) as store:
        repo = AssessmentRepository(store)
        save(LIVE / 'expiry-amendment-started.json', {'review_sha256': identity, 'model_turns': 0})
        repo.approve_budget_amendment(amendment)
    assert runner['first']['snapshot'](review['database']) == review['grant']
    save(LIVE / 'expiry-amendment-result.json', {
        'review_sha256': identity, 'amendment_sha256': content_digest(amendment),
        'counters_unchanged': True, 'limits_unchanged': True, 'model_turns': 0,
    })
    return asyncio.run(configure_runner()(identity))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    else:
        raise SystemExit(not execute(args.execute_approved))
