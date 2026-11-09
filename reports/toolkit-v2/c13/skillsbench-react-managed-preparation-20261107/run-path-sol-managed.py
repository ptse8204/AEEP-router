"""Rebind only the verified worker paths for the still-unstarted Sol journey."""

import argparse
import asyncio
import json
import math
import runpy
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, content_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import utc_now

HERE = Path(__file__).resolve().parent
previous = runpy.run_path(str(HERE / 'run-refreshed-sol-managed.py'))
runner = previous['runner']
engine, read, sha, save = (runner[name] for name in ('engine', 'read', 'sha', 'save'))
WORK = runner['WORK']
PRIOR = HERE / 'sol-01591-live-20261109'
OFFLINE_CONTROL = HERE / 'sol-sandbox-path-20261109'
OFFLINE_CANDIDATE = HERE / 'sol-sandbox-candidate-20261109'
LIVE = HERE / 'sol-permitted-path-live-20261109'
REVIEW = LIVE / 'operation-review.json'
DEFS = WORK / 'sol-permitted-path-live-definitions'
EXEC = WORK / 'sol-permitted-path-live-execution'
TAG = 'react-sol-permitted-path-20261109'
BINARY = '/opt/codex/0.159.1/bin/codex'


def graded_environment():
    proof = read(HERE / 'self-contained-result.json')
    environment = runner['AssessmentEnvironment'].model_validate(read(DEFS / 'react-environment.json'))
    assert proof['passed'] and proof['accounting_settled'] and proof['image']['id'] == environment.container_image
    assert engine.docker('image', 'inspect', '--format', '{{.Id}}', environment.container_image) == environment.container_image
    return environment


def bind_runner():
    entry = runner['execute']
    entry.__globals__.update(HERE=LIVE, DEFS=DEFS, EXEC=EXEC, REVIEW=REVIEW, grader_current=graded_environment)
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


def offline_images():
    result = read(OFFLINE_CONTROL / 'result.json')
    candidate = read(OFFLINE_CANDIDATE / 'result.json')
    assert result['review_sha256'] == sha(OFFLINE_CONTROL / 'operation-review.json')
    assert candidate['review_sha256'] == sha(OFFLINE_CANDIDATE / 'operation-review.json')
    assert all(row['accounting_settled'] and row['operations'] == 2 and row['models'] == 0
               for row in (result, candidate))
    assert result['error_type'] == 'AssertionError' and candidate['passed']
    control = result['roles']['control']
    assert control['build']['id'] == candidate['retained_control']
    images = {}
    for arm, item in (('control', control), ('treatment', candidate)):
        sandbox = item['sandbox']
        assert sandbox['canary']['exit_code'] == sandbox['original_probe']['exit_code'] == 0
        assert sandbox['canary']['observation'] == {'canary_matched': True}
        assert sandbox['original_probe']['observation'] == {'workspace_write': True,
            'configuration_write': 'absent', 'proxy': 'denied', 'direct': 'denied'}
        assert sandbox['cleanup_confirmed'] and all(row['matches'] for row in sandbox['configRequirements/read'].values())
        image = item['build']['id']
        assert engine.docker('image', 'inspect', '--format', '{{.Id}}', image) == image
        images[arm] = image
    return images


def freeze():
    old = read(PRIOR / 'operation-review.json')
    stopped = read(PRIOR / 'sol-managed-result.json')
    assert stopped['review_sha256'] == sha(PRIOR / 'operation-review.json') and not stopped['passed']
    assert stopped['model_turns_reserved'] == 0 and stopped['proxy_restored_stopped']
    assert stopped['historical_reservations_preserved'] and not stopped['new_unresolved_reservations']
    current = runner['first']['snapshot'](old['database'])
    assert current['counters'] == stopped['grant_after'] and current['limits'] == old['grant']['limits']
    assert current['amendment_sha256'] == old['grant']['amendment_sha256']
    assert datetime.fromisoformat(current['expires_at']) > utc_now()
    assert current['expires_at'] == old['grant']['expires_at']
    assert runner['verification_source_digest'](runner['ROOT']) == old['source_sha256']
    images = offline_images()
    case, = old['cases']
    pair = read(case['pair'])
    for arm in ('control', 'treatment'):
        config = pair[arm]['config']
        worker = config['managed_worker']
        assert config['argv'] == [worker['binary'], 'app-server']
        assert config['model_constraints']['allowed_model_ids'] == ['gpt-6.1-sol']
        assert config['reasoning_efforts'] == ['medium']
        assert worker['binary'] == '/opt/codex-0.159.1/bin/codex' and worker['permissions_profile'] == 'aeep'
        pair[arm]['id'] = f'skillsbench-react-sol-permitted.{arm}'
        config['argv'][0] = BINARY
        config['adapter_id'] = f'codex-app-server:skillsbench-react-sol-permitted-{arm}'
        worker.update(image=images[arm], binary=BINARY, worker_id=f'skillsbench-react-sol-permitted-{arm}')
    shared = read(case['shared']) | {'worker_images': images, 'client_binary': BINARY}
    common = pair['differential']['control_inventory'] | {'common_profile': content_digest(shared)}
    pair['differential'].update(shared_definition_digest=content_digest(shared), control_inventory=common,
        treatment_inventory=common | pair['differential']['candidate_inventory'])
    validated = WorkerPairInspection.model_validate(pair)
    old_pair = read(case['pair'])
    for arm in ('control', 'treatment'):
        before, after = (item[arm]['config']['managed_worker'] for item in (old_pair, pair))
        assert {key for key in before if before[key] != after[key]} == {'binary', 'image', 'worker_id'}
        assert old_pair[arm]['config']['artifact'] == pair[arm]['config']['artifact']

    LIVE.mkdir()
    DEFS.mkdir(mode=0o700)
    for name in ('react-recipe.json', 'react-environment.json', 'react-integration-cases.json', 'workflow.json'):
        save(DEFS / name, read(Path(old['definitions']) / name))
    save(DEFS / 'react-pair.json', validated.model_dump(mode='json'))
    save(DEFS / 'react-shared.json', shared)
    case.update(recipe=str(DEFS / 'react-recipe.json'), pair=str(DEFS / 'react-pair.json'),
        pair_digest=content_digest(validated), shared=str(DEFS / 'react-shared.json'),
        grader_environment=str(DEFS / 'react-environment.json'))
    pins = [Path(__file__).resolve(), PRIOR / 'operation-review.json', PRIOR / 'sol-managed-result.json',
            PRIOR / 'sol-managed-sandbox-blocker.json', OFFLINE_CONTROL / 'operation-review.json',
            OFFLINE_CONTROL / 'result.json', OFFLINE_CANDIDATE / 'operation-review.json', OFFLINE_CANDIDATE / 'result.json',
            *sorted(DEFS.glob('*.json'))]
    prior_ops, prior_seconds = current['counters'][0] - old['grant']['counters'][0], current['counters'][2] - old['grant']['counters'][2]
    assert prior_ops == 4 and 12 < prior_seconds < 14
    review = {key: value for key, value in old.items() if key not in ('expiry_amendment', 'grant_before_expiry_amendment')}
    review.update(scope='One Sol-only React engineering turn after current paired account and sandbox conformance.',
        previous_review_sha256=sha(PRIOR / 'operation-review.json'),
        pins=old['pins'] | {str(path): sha(path) for path in pins}, cases=[case], definitions=str(DEFS),
        work=str(EXEC), worker_image_ids=images, client_binary=BINARY, grant=current, maximum_operations=old['maximum_operations']-prior_ops,
        maximum_reserved_seconds=math.floor(old['maximum_reserved_seconds']-prior_seconds),
        maximum_model_turns=1, expires_at=current['expires_at'], additional_grant_amendment=False)
    assert review['maximum_operations'] == 63 and review['maximum_reserved_seconds'] == 3837
    counters = (*current['counters'][:3], Decimal(current['counters'][3]))
    engine.budget.require_room(counters, counters, AssessmentLimits(max_operations=4, max_elapsed_seconds=665), review)
    bind_runner().__globals__['inspect_selected'](review)
    save(REVIEW, review)
    print(sha(REVIEW))


def execute(identity):
    assert sha(REVIEW) == identity and read(LIVE / 'sol-managed-approval.json') == {'approved': True, 'review_sha256': identity}
    review = read(REVIEW)
    assert not (LIVE / 'sol-managed-started.json').exists() and not EXEC.exists()
    assert offline_images() == review['worker_image_ids']
    assert review['model'] == 'gpt-6.1-sol' and review['reasoning_effort'] == 'medium'
    assert review['no_model_fallback'] and not review['automatic_retries']
    return asyncio.run(bind_runner()(identity))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    flags = parser.add_mutually_exclusive_group(required=True)
    flags.add_argument('--freeze', action='store_true')
    flags.add_argument('--preflight', action='store_true')
    flags.add_argument('--execute-approved')
    args = parser.parse_args()
    if args.freeze:
        freeze()
    elif args.preflight:
        review = read(REVIEW)
        assert offline_images() == review['worker_image_ids']
        bind_runner().__globals__['inspect_selected'](review)
        print(json.dumps({'review_sha256': sha(REVIEW), 'preflight_passed': True, 'executed': False}))
    else:
        raise SystemExit(not execute(args.execute_approved))
