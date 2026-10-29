"""Correct only unstarted task definitions; preserve original subjects and ceilings."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, repository_suite_recipe, _decode_suite_patch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
NAMES = ['prepare-worker-definitions.py', 'check-task-delivery.py', 'run-collector.py',
         'assemble-collector-boundary.py', 'review-budget.py', 'run-model-journey.py',
         'run-review.py', 'trial-evidence.py', 'audit-completion.py']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    original = json.loads((HERE / 'operation-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sha(HERE / 'operation-review.json')
    stopped = json.loads((HERE / 'stopped-accounting-audit.json').read_text())
    assert stopped['passed'] and stopped['all_operations_complete']
    censored = set(stopped['engineering_censored_cases'])
    all_cases = [RepositorySuiteCase.model_validate(value) for value in json.loads((HERE / 'cases.json').read_text())]
    groups = {'plain': [], 'gzip': []}
    for case in all_cases:
        if case.input.task_id not in censored:
            groups['gzip' if hasattr(case.truth, 'patch_encoding') else 'plain'].append(case)
    assert [len(groups[name]) for name in ('plain', 'gzip')] == [13, 6]
    parts = []
    for mode, cases in groups.items():
        target = HERE.parent / ('repository-usefulness-' + mode + '-20261029')
        target.mkdir(exist_ok=False)
        count, turns = len(cases), 2 * len(cases)
        wall, proxy, operations, seconds = (11000, 11500, 660, 45000) if mode == 'plain' else (4500, 5000, 255, 19000)
        for name in NAMES:
            source = (HERE / name).read_text()
            if name == 'prepare-worker-definitions.py':
                source = source.replace('len(cases)==21', f'len(cases)=={count}')
                source = source.replace('toolkit-repository-usefulness-20261029', 'toolkit-repository-usefulness-' + mode + '-20261029')
                source = source.replace('Twenty-one-pair development usefulness study only;21 distinct public repositories.', f'{count} unstarted tasks from the original21-slot development experiment;other started cases remain engineering-censored.')
                if mode == 'plain':
                    source = source.replace("'output_field':'patch_gzip_b64'", "'output_field':'patch_b64'")
                    source = source.replace("'output_name':'patch.json.gz'", "'output_name':'patch.json'")
                    source = source.replace('gzip-compressed UTF-8 JSON', 'UTF-8 JSON')
            if name == 'check-task-delivery.py':
                source = source.replace('len(observed)==42', f'len(observed)=={turns}')
                source = source.replace("len({r['instruction_sha256'] for r in observed})==21", f"len({{r['instruction_sha256'] for r in observed}})=={count}")
                source = source.replace("'distinct_case_instructions':21", f"'distinct_case_instructions':{count}")
                if mode == 'plain':
                    source = source.replace('/workspace/patch.json.gz', '/workspace/patch.json')
            if name == 'assemble-collector-boundary.py':
                source = source.replace('toolkit-repository-usefulness-20261029', 'toolkit-repository-usefulness-' + mode + '-20261029')
            if name == 'run-model-journey.py':
                source = source.replace('repository-usefulness-pilot-', 'repository-usefulness-' + mode + '-')
                source = source.replace('==21', f'=={count}').replace('==42', f'=={turns}')
                source = source.replace("'model_turn_ceiling':42", f"'model_turn_ceiling':{turns}")
                source = source.replace("'maximum_model_turns':42", f"'maximum_model_turns':{turns}")
                source = source.replace('max_elapsed_seconds=18000', f'max_elapsed_seconds={proxy}')
                source = source.replace('asyncio.timeout(17500)', f'asyncio.timeout({wall})')
            if name == 'run-review.py':
                source = source.replace("timeout=19000 if name=='run-model-journey.py' else 600", f"timeout={wall+500} if name=='run-model-journey.py' else 600")
            if name == 'review-budget.py':
                source = source.replace('    original=repo.reserve\n', "    import json\n    from pathlib import Path\n    config=json.loads((Path(__file__).parent/'component-config.json').read_text())\n    parent=json.loads(Path(config['parent_review']).read_text())\n    anchor=json.loads(Path(config['parent_started']).read_text())['grant_before']\n    original=repo.reserve\n")
                source = source.replace('        require_room(current,initial,limits,ceiling)\n', '        require_room(current,initial,limits,ceiling)\n        require_room(current,anchor,limits,parent)\n')
            (target / name).write_text(source)
        save(target / 'component-config.json', {'mode': mode, 'case_count': count, 'model_turns': turns,
            'parent_review': str(HERE / 'operation-review.json'), 'parent_started': str(HERE / 'execution-started.json'),
            'parent_review_sha256': approval['review_sha256'], 'original_cumulative_anchor': stopped['grant_before'],
            'excluded_started_cases': sorted(censored), 'no_started_invocation_retried': True})
        save(target / 'cases.json', [case.model_dump(mode='json') for case in cases])
        recipe = repository_suite_recipe(cases)
        save(target / 'recipe.json', recipe.model_dump(mode='json'))
        original_recipe = json.loads((HERE / 'recipe.json').read_text())
        assert recipe.extension.grader.config['argv'] == original_recipe['extension']['grader']['config']['argv']
        for case in cases:
            reference = json.loads(case.reference.read())
            _decode_suite_patch(case.truth, reference)
        for name in ('prepare-worker-definitions.py', 'check-task-delivery.py'):
            with (target / (name + '.log')).open('x') as log:
                subprocess.run([sys.executable, str(target / name)], cwd=ROOT, check=True, stdout=log, stderr=subprocess.STDOUT)
        proposal = json.loads((target / 'collector-definitions.json').read_text())
        pair = proposal['definitions'][proposal['pair_definition_digest']]
        collector = json.loads((HERE / 'collector-operation-review.json').read_text())
        collector.update(definitions_sha256=sha(target / 'collector-definitions.json'), runner_sha256=sha(target / 'run-collector.py'))
        save(target / 'collector-operation-review.json', collector)
        assets = dict(original['assets'])
        for path in [*target.glob('*.py'), *target.glob('*.json'), HERE / 'stopped-accounting-audit.json', Path(__file__)]:
            assets[str(path.resolve())] = sha(path)
        review = dict(original)
        review.update(assets=assets, pair_definition_digest=proposal['pair_definition_digest'],
            public_tasks=[value for value in original['public_tasks'] if value['task_id'] in {case.input.task_id for case in cases}],
            purpose=f'{count} unstarted original tasks with the existing {mode} artifact contract. No task/source/test/reference/model/permission change.',
            maximum_model_turns=turns, maximum_operations=operations, maximum_reserved_seconds=seconds,
            maximum_task_phase_wall_seconds=wall, original_cumulative_review=approval['review_sha256'],
            original_cumulative_anchor=stopped['grant_before'],
            authority='Delegated first-party definition/controller correction under the actual parent approval. This is not a new human answer. All external source,tests,references,wheels,images,model,destination,permissions and metrics remain. Only unstarted tasks run;started slots stay censored. Both local and original cumulative caps apply.')
        save(target / 'operation-review.json', review)
        parts.append({'mode': mode, 'directory': str(target), 'review_sha256': sha(target / 'operation-review.json'),
            'case_ids': [case.input.task_id for case in cases], 'maximum_model_turns': turns,
            'maximum_operations': operations, 'maximum_reserved_seconds': seconds})
    assert sum(part['maximum_model_turns'] for part in parts) + 3 <= original['maximum_model_turns']
    assert sum(part['maximum_operations'] for part in parts) + stopped['cumulative_operations'] <= original['maximum_operations']
    assert sum(part['maximum_reserved_seconds'] for part in parts) + stopped['charged_operation_seconds'] <= original['maximum_reserved_seconds']
    amendment = {'authority': 'Standing September25/27 first-party definition/scope delegation and the explicit routine_control_amendments clause in the actual bf8d62f2 approval.',
        'parent_review_sha256': approval['review_sha256'], 'parent_original_cumulative_anchor': stopped['grant_before'],
        'reason': 'My uniform-gzip definition was incompatible with original legacy plain-patch decoders. Select the existing correct artifact contract for each unstarted case;do not change source code,grader programs,reference bytes or assertions.',
        'original_intended_case_slots': 21, 'engineering_censored_started_cases': sorted(censored),
        'remaining_original_cases': 19, 'remaining_model_turns': 38, 'maximum_cumulative_model_turns': 41,
        'all_original_caps_preserved': True, 'no_model_or_source_invocation_restarted': True,
        'components': parts, 'source_digest': original['source_digest'], 'source_changes': False,
        'conditions': 'Keep plain and gzip component resource results separate. No replacement tasks or formal qualification. Three started turns remain charged and unusable for comparative value.'}
    save(HERE / 'codec-definition-amendment.json', amendment)
    print(json.dumps({'prepared': True, 'components': [{key: value for key, value in part.items() if key != 'case_ids'} for part in parts], 'maximum_cumulative_turns': 41}))


if __name__ == '__main__':
    main()
