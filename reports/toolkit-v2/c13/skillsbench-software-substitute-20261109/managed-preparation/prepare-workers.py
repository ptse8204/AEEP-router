"""Prepare the private Prefix Cache worker definition and proposed disclosure record."""

import json
import runpy
from pathlib import Path

from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.templates import render
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.workflow_preparation import TaskRightsReview

HERE = Path(__file__).resolve().parent
stage = runpy.run_path(str(HERE / 'prepare.py'))
read, sha, write = (stage[key] for key in ('read', 'sha', 'write'))
REACT = stage['IMAGE'] / 'sol-permitted-path-live-20261109'
WORK = stage['WORK']
TASK = stage['TASK']

INSTRUCTIONS = (
    'Use the original SkillsBench instructions in the task archive. '
    'Unpack the archive with Python zipfile in your private /workspace. '
    'The original trace.jsonl and config.json are in the archive environment directory. '
    'Read those copies in place of the original /root paths. '
    'Write only the requested report.json at the supplied output_path. '
    'Use the reviewed stack-check skill if it is available. '
    'Check that the report exists and is at most 262144 bytes. '
    'Return only the completion JSON {"completed":true} after saving the file. '
    'Do not include the artifact in your response or contact other services.\n{input}'
)


def main():
    draft = read(HERE / 'result.json')
    recipe = RecipeDefinition.model_validate(read(Path(draft['recipe'])))
    assert content_digest(recipe) == draft['recipe_digest']
    pack_file = HERE.parent / 'task-pack.json'
    pack = BenchmarkPack.model_validate(read(pack_file))
    task = pack.task(TASK)
    rights = TaskRightsReview.model_validate(read(HERE.parent / 'local-rights-draft.json'))
    assert rights.local_execution_allowed and not rights.provider_disclosure_allowed
    assert rights.assets == {asset.path: asset.sha256 for asset in task.assets}
    proposed = rights.model_copy(update={'provider_disclosure_allowed': True})
    value = task_input(pack, Path(read(HERE.parent / 'task-pack-transport.json')['pack_root']), TASK)
    assert value['task_archive_sha256'] == draft['public_archive_sha256']
    assert value['benchmark_pack_sha256'] == draft['draft_pack_digest']
    review = read(REACT / 'operation-review.json')
    result = read(REACT / 'completed-run-audit.json')
    assert result['review_sha256'] == sha(REACT / 'operation-review.json')
    assert result['model'] == 'gpt-6.1-sol' and result['reasoning_effort'] == 'medium'
    source, = review['cases']
    pair_path = Path(source['pair'])
    pair = read(pair_path)
    assert content_digest(WorkerPairInspection.model_validate(pair)) == source['pair_digest']
    parent_shared = read(Path(source['shared']))
    assert content_digest(parent_shared) == pair['differential']['shared_definition_digest']
    shared = parent_shared | {'task_id': TASK, 'public_archive_sha256': value['task_archive_sha256'],
                              'artifact': draft['artifact'], 'reference_pair': source['pair_digest']}
    shared_ref = content_digest(shared)
    differential = pair['differential']
    inventory = differential['control_inventory'] | {'common_profile': shared_ref}
    differential.update(shared_definition_digest=shared_ref, control_inventory=inventory,
                        treatment_inventory=inventory | differential['candidate_inventory'])
    for arm in ('control', 'treatment'):
        spec = pair[arm]
        config = spec['config']
        assert config['managed_worker']['image'] == review['worker_image_ids'][arm]
        assert config['model_constraints']['allowed_model_ids'] == ['gpt-6.1-sol']
        assert config['reasoning_efforts'] == ['medium']
        assert not config['store_prompt'] and not config['store_output']
        spec.update(id='skillsbench-prefix-cache.' + arm, capability=recipe.capability,
                    input_schema=recipe.input_schema, output_schema=recipe.output_schema)
        config.update(adapter_id='codex-app-server:prefix-cache-' + arm, instructions=INSTRUCTIONS,
                      artifact=draft['artifact'])
        config['managed_worker']['worker_id'] = 'skillsbench-prefix-cache-' + arm
    validated = WorkerPairInspection.model_validate(pair)
    value.pop('task_archive_b64')
    value.update(input_path='/workspace/skillsbench-task.zip', output_path='/workspace/report.json')
    instruction = str(render(INSTRUCTIONS, {'input': value}))
    assert '262144 bytes' in instruction and value['output_path'] in instruction

    write(WORK / 'pair.json', validated.model_dump(mode='json'))
    write(WORK / 'shared.json', shared)
    write(HERE / 'worker-draft.json', {
        'task': TASK, 'pair_sha256': content_digest(validated), 'shared_sha256': shared_ref,
        'prior_pair_sha256': source['pair_digest'], 'worker_images': review['worker_image_ids'],
        'pair': str(WORK / 'pair.json'), 'shared': str(WORK / 'shared.json'),
        'model': result['model'], 'reasoning_effort': result['reasoning_effort'],
        'fresh_readiness_required': True, 'models': 0, 'dispatch_authorized': False,
    })
    write(HERE / 'proposed-disclosure.json', {
        'status': 'PENDING_OPERATOR_REVIEW',
        'task': TASK,
        'candidate_review_sha256': sha(HERE.parent / 'candidate-review.json'),
        'local_pack_digest': draft['draft_pack_digest'],
        'public_archive_sha256': draft['public_archive_sha256'],
        'public_files': read(HERE.parent / 'task-pack-transport.json')['public_files'],
        'destination': 'codex',
        'model': result['model'], 'reasoning_effort': result['reasoning_effort'],
        'proposed_rights': proposed.model_dump(mode='json'),
        'rights_record_ref': content_digest(proposed),
        'rights_registered': False, 'provider_disclosure_approved': False,
        'protected_assets_in_worker_archive': False, 'models': 0,
    })


if __name__ == '__main__':
    main()
