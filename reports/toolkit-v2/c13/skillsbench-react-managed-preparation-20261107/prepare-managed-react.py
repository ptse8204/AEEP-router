"""Bind the verified React grader and worker pair to one inert managed definition."""

import json
import runpy
import shutil
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment, IntegrationCaseSet, RecipeDefinition, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.registry import validate_json
from aeep.templates import render
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
GRADER = HERE.parent / 'skillsbench-react-readonly-grader-20261108'
PREVIOUS = ROOT / '.aeep/skillsbench-managed-worker-preparation-20261105/engineering'
ORIGINAL = ROOT / '.aeep/skillsbench-contained-graders-20261105/rights-bound'
DEFINITIONS = WORK / 'managed-definitions'
read = lambda path: json.loads(path.read_bytes())
helpers = runpy.run_path(str(HERE.parent / 'skillsbench-document-managed-20261106/prepare-workers.py'))
put, sha = helpers['put'], helpers['sha']
TASK = 'react-performance-debugging'
INSTRUCTIONS = (
    'Use the exact upstream SkillsBench task from the supplied task JSON. Unpack skillsbench-task.zip '
    'into a private workspace using Python zipfile. The original public project is under environment/website '
    'within the selected task tree. Treat original absolute paths as private workspace paths. '
    'Use the supplied stack-check skill for isolation and output discipline. Both workers have identical read-only '
    'Node modules at /opt/aeep-task-tools/react/node_modules. Link that directory into your private website '
    'and use node with its typescript/bin/tsc or next/dist/bin/next for local checks. '
    'The protected simulator and browser assertions run only during grading. '
    'Write UTF-8 JSON to the provided absolute output_path. Its base_sha256 must equal task_archive_sha256. '
    'Its files object maps only changed source paths relative to the website, starting with src/, '
    'to their complete replacement text. Include only .ts, .tsx or .css paths. '
    'Check the file exists, parses as JSON and is at most 500000 bytes. Return only the completion JSON. '
    'Keep original attribution. Do not install packages, search for answers, contact other services or '
    'put encoded artifact data into the response. Task and artifact paths follow.\n{input}'
)


def main():
    source = verification_source_digest(ROOT)
    review = read(HERE / 'operation-review.json')
    task = review['tasks'][0]
    rights = TaskRightsReview.model_validate(read(HERE / 'proposed-rights.json'))
    rights_ref = read(HERE / 'result.json')['records'][TASK]
    assert rights.local_execution_allowed and rights.provider_disclosure_allowed
    assert content_digest(rights) == rights_ref['review_ref']
    bound = WORK / (TASK + '-bound-pack.json')
    assert sha(bound) == rights_ref['bound_pack_sha256']
    pack = BenchmarkPack.model_validate(read(bound))
    case = task_input(pack, Path(task['pack_root']), TASK)
    assert case['task_archive_sha256'] == task['public_archive_sha256']
    assert read(GRADER / 'result.json')['passed']
    assert read(HERE / 'candidate-smoke-result.json')['passed']
    control = read(HERE / 'worker-continuation-result.json')
    assert control['smokes']['control']['typecheck_exit'] == 0
    parity = read(HERE / 'worker-image-parity.json')
    assert parity['identical_dependency_bytes_modes_and_ownership']
    assert parity['matches_frozen_context']
    images = {arm: parity['images'][role]['id'] for arm, role in (
        ('control', 'control'), ('treatment', 'candidate'),
    )}
    recipe_path = ROOT / '.aeep' / GRADER.name / 'react-recipe.json'
    recipe = RecipeDefinition.model_validate(read(recipe_path))
    grader = AssessmentEnvironment.model_validate(read(GRADER / 'environment.json'))
    grader_review = read(GRADER / 'operation-review.json')
    assert content_digest(recipe) == grader_review['recipe_digest']
    assert content_digest(grader) == grader_review['environment_digest']
    validate_json(case, recipe.input_schema, label='reviewed React input')
    handoff = read(HERE / 'managed-toolchain-audit.json')['managed_handoff']

    pair = read(PREVIOUS / 'sales-pair.json')
    shared = read(PREVIOUS / 'sales-shared.json')
    assert content_digest(shared) == pair['differential']['shared_definition_digest']
    shared.update(purpose='One protected React engineering task', source_sha256=source,
                  recipe=content_digest(recipe), archive_sha256=case['task_archive_sha256'],
                  worker_images=images, shared_react_dependency_inventory=parity['filesystem_inventory_sha256'])
    common = pair['differential']['control_inventory'] | {'common_profile': content_digest(shared)}
    pair['differential'].update(shared_definition_digest=content_digest(shared), control_inventory=common,
                                treatment_inventory=common | pair['differential']['candidate_inventory'])
    for arm in ('control', 'treatment'):
        spec = pair[arm]
        spec.update(id='skillsbench-react.' + arm, capability=recipe.capability,
                    input_schema=recipe.input_schema, output_schema=recipe.output_schema)
        cfg = spec['config']
        assert not cfg['store_prompt'] and not cfg['store_output']
        cfg.update(adapter_id='codex-app-server:skillsbench-react-' + arm, artifact=handoff,
                   instructions=INSTRUCTIONS, timeout_seconds=900)
        cfg['managed_worker'].update(worker_id='skillsbench-react-' + arm, image=images[arm])
    pair = WorkerPairInspection.model_validate(pair)
    a, b = (getattr(pair, arm).managed_host_config() for arm in ('control', 'treatment'))
    assert a.artifact == b.artifact and a.instructions == b.instructions
    prompt = dict(case)
    prompt.pop(handoff['input_field'])
    prompt.update(input_path='/workspace/' + handoff['input_name'], output_path='/workspace/' + handoff['output_name'])
    wire = str(render(INSTRUCTIONS, {'input': prompt}))
    assert case['task_archive_b64'] not in wire

    case_set = read(ORIGINAL / 'spring-integration-cases.json')
    case_set.update(request_id='skillsbench-react-engineering-preparation-20261108',
                    recipe_digest=content_digest(recipe), environment_digest=content_digest(grader),
                    benchmark_pack_digest=case['benchmark_pack_sha256'])
    row, = case_set['cases']
    row.update(case_id=TASK, variation=TASK, template_family='skillsbench:' + TASK)
    row['action'].update(action_id=TASK, capability=recipe.capability, input=case)
    row['validators'][0]['config']['expected'] = {'task_archive_sha256': case['task_archive_sha256']}
    cases = IntegrationCaseSet.model_validate(case_set)

    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    DEFINITIONS.mkdir(mode=0o700)
    put(DEFINITIONS / 'react-pair.json', pair.model_dump(mode='json'))
    put(DEFINITIONS / 'react-shared.json', shared)
    put(DEFINITIONS / 'react-integration-cases.json', cases.model_dump(mode='json'))
    put(DEFINITIONS / 'workflow.json', read(ORIGINAL / 'workflow.json'))
    put(HERE / 'managed-definition-preflight.json', {
        'task_id': TASK, 'configuration': 'software-engineering', 'source_sha256': source,
        'recipe_digest': content_digest(recipe), 'environment_digest': content_digest(grader),
        'pair_digest': content_digest(pair), 'case_set_digest': content_digest(cases),
        'rights_review_ref': content_digest(rights), 'public_archive_sha256': case['task_archive_sha256'],
        'public_prompt_bytes': len(wire.encode()), 'worker_images': images,
        'workers_started': 0, 'model_turns': 0, 'provider_transfer': False, 'comparisons': 'PAUSED',
    })
    print(json.dumps({'verified_definition': True, 'configuration': 'software-engineering', 'model_turns': 0}))


if __name__ == '__main__':
    main()
