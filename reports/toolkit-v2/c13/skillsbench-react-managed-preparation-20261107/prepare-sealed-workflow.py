"""Bind the existing React task and worker evidence to the self-contained grader."""

import json
import runpy
import sqlite3
from pathlib import Path

from aeep.assessment.extensions import require_environment
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentSetupRequest, IntegrationCaseSet, RecipeDefinition, content_digest,
)

HERE = Path(__file__).resolve().parent
previous = runpy.run_path(str(HERE / 'continue-managed-react.py'))
read, sha, save, engine = (previous[key] for key in ('read', 'sha', 'save', 'engine'))
ROOT = previous['root']
WORK = previous['work']
SEALED = WORK / 'sealed-managed-definitions'
CONFIGURATION = previous['CONFIGURATION']
RUN_TAG = 'react-sealed-20261108'


def definitions():
    runtime = read(HERE / 'self-contained-result.json')
    assert runtime['passed'] and runtime['accounting_settled'] and runtime['operations'] == 9
    original = read(HERE / 'managed-continuation-review.json')
    old = read(previous['ORIGINAL'] / 'react-setup.json')
    source = RecipeDefinition.model_validate(read(WORK / 'sealed-react-recipe.json'))
    assert content_digest(source) == read(HERE / 'self-contained-operation-review.json')['recipe_digest']
    recipe = source.model_copy(update={'recipe_id': 'skillsbench-react-protected-sealed-v1'})
    assert source.extension == recipe.extension
    carrier = AssessmentEnvironment.model_validate(read(HERE / 'self-contained-environment.json'))
    assert carrier.container_image == runtime['image']['id']
    with sqlite3.connect(Path(original['database']).as_uri() + '?mode=ro', uri=True) as db:
        current = AssessmentEnvironment.model_validate(previous['load_record'](db, 'environment', old['environment_id']))
        cases = IntegrationCaseSet.model_validate(previous['load_record'](db, 'integration_case_set', old['integration_case_set_id']))
    env = carrier.model_copy(update={
        'environment_id': RUN_TAG + '-grader',
        'identity': carrier.identity | {'source_digest': original['source_sha256']},
        'conformance_digests': current.conformance_digests,
        'differential_conformance_digest': current.differential_conformance_digest,
    })
    require_environment(recipe, env)
    updated = cases.model_copy(update={'request_id': RUN_TAG + '-cases',
        'recipe_digest': content_digest(recipe), 'environment_digest': content_digest(env)})
    assert updated.cases == cases.cases
    request = AssessmentSetupRequest.model_validate(old | {
        'recipe_id': recipe.recipe_id, 'environment_id': env.environment_id, 'integration_case_set_id': content_digest(updated),
    })
    return recipe, env, updated, request


def freeze():
    recipe, env, cases, request = definitions()
    workflow = read(previous['CORRECTED'])
    SEALED.mkdir(mode=0o700)
    recipe_path, request_path = SEALED / 'recipe.json', SEALED / 'request.json'
    for path, model in ((recipe_path, recipe), (request_path, request), (SEALED/'environment.json', env), (SEALED/'cases.json', cases)):
        save(path, model.model_dump(mode='json'))
        path.chmod(0o400)
    selected = workflow['configurations'][CONFIGURATION]
    selected['benchmark_recipe'] = engine.binding(recipe_path)
    selected['preparation']['request'] = engine.binding(request_path)
    save(SEALED / 'workflow.json', workflow)
    preview = engine.cli('plan', '--workflow', SEALED/'workflow.json', '--configuration', CONFIGURATION)
    assert preview['blockers'] == ['canonical plan preparation is selected but has not been performed']
    save(HERE / 'sealed-managed-definition.json', {
        'configuration': CONFIGURATION, 'preview_sha256': preview['review_sha256'],
        'recipe_sha256': content_digest(recipe), 'environment_sha256': content_digest(env),
        'case_set_sha256': content_digest(cases), 'setup_request_sha256': content_digest(request),
        'grader_image': env.container_image, 'no_extra_host_mounts': not env.read_only_roots,
        'provider_transfer': False, 'models': 0, 'comparisons': 'PAUSED',
    })
    print(json.dumps({'sealed_managed_definition': True, 'models': 0}))


if __name__ == '__main__':
    freeze()
