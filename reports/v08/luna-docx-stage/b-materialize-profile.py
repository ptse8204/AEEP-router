"""Build inert current B profiles from the successfully created native project."""
from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.workers import ManagedWorkerBinding

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = '449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad'
ASSEMBLER = OUT / 'b-current-profile-assembler-v2.py'
ASSEMBLER_SHA = '779e82268861ab8db604fa6573c6fe084e73d8bb34655a523cc3baabe1efa84d'
SETUP_REVIEW_SHA = 'ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5'
HISTORICAL = ROOT / 'reports/v08/original-three-way-profile/current-composed-profiles.json'
HISTORICAL_SHA = '7d030283cb32280916ee6740ef7971eab8441e51fbeb232cc96690c05616dd5f'
SKILL = '/opt/dependencies/plugin/skills/spreadsheets/SKILL.md'
INSTRUCTIONS = (
    'Complete the workbook task described in {input}. Read the supplied input workbook '
    'and write the requested output workbook. You may use available local tools, skills '
    'or workbook helpers as useful. Preserve the content required by the task. '
    'Return only {"completed": true} once the output workbook is written and checked, '
    'or {"completed": false} if you cannot complete the task. '
    'Do not include workbook bytes or base64 in your final answer.'
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    destination = OUT / 'b-current-profile.json'
    if destination.exists():
        raise ValueError('preserve existing profile assembly')
    if (verification_source_digest(ROOT) != SOURCE or sha(ASSEMBLER) != ASSEMBLER_SHA
            or sha(HISTORICAL) != HISTORICAL_SHA
            or sha(OUT / 'b-native-setup-v3-review.json') != SETUP_REVIEW_SHA):
        raise ValueError('current source or exact prepared inputs changed')
    result_path = OUT / 'b-native-setup-v3-result.json'
    result = json.loads(result_path.read_text())
    if (result.get('setup_complete') is not True or result.get('operation_settled') is not True
            or result.get('source_digest') != SOURCE or result.get('review_sha256') != SETUP_REVIEW_SHA
            or any(result.get(key) != 0 for key in ('model_turns', 'task_calls', 'worker_launches'))):
        raise ValueError('exact completed zero-turn native setup is required')
    historical = json.loads(HISTORICAL.read_text())['pair']
    callbacks = result['callback_documents_by_role']
    workers = {role: ManagedWorkerBinding.model_validate(value)
               for role, value in result['worker_documents'].items()}
    if set(workers) != {'control', 'treatment'} or set(callbacks) != set(workers):
        raise ValueError('two exact setup workers and callback documents required')
    fixed_names = {tool['name'] for tool in callbacks['control']['tools']}
    added = [tool for tool in callbacks['treatment']['tools'] if tool['name'] not in fixed_names]
    if len(fixed_names) != 1 or len(added) != 1:
        raise ValueError('one common fixed helper and one added AEEP tool required')
    pair = {}
    for role, name in (('control', 'discovery'), ('treatment', 'aeep')):
        value = copy.deepcopy(historical['treatment'])
        value['id'] = 'b.luna.' + name
        config = value['config']
        config.update(adapter_id='codex-app-server:b-luna-' + name,
            model_constraints={'allowed_model_ids': ['gpt-6-luna']}, reasoning_efforts=['xhigh'],
            instructions=INSTRUCTIONS, managed_worker=workers[role].model_dump(mode='json'),
            artifact=result['artifact'])
        invocation = {'mode': 'turn' if role == 'control' else 'dynamic_tool',
            'local_profile': 'capable_local', 'native_catalog': False,
            'supporting_skills': [{'name': 'Spreadsheets', 'path': SKILL,
                'sha256': workers[role].reviewed_files[SKILL]}],
            'dynamic_tools_digest': content_digest(callbacks[role])}
        if role == 'treatment':
            invocation.update(server=callbacks[role]['namespace'], tool=added[0]['name'],
                tool_sha256=contract_digest(added[0]), exposure='required')
        config['invocation'] = invocation
        pair[role] = value
    shared = {'schema_version': 'assessment.b-shared-spreadsheets.v1',
        'image_digest': workers['control'].image, 'skill_path': SKILL,
        'alias_path': '/etc/codex/skills/spreadsheets/SKILL.md',
        'runtime_path': '/opt/dependencies/runtime',
        'skill_sha256': workers['control'].reviewed_files[SKILL],
        'alias_paths': {'Spreadsheets': SKILL}, 'shared_versions': historical['shared_versions'],
        'dependency_expectations': {'authoring_helper': True, 'artifact_tool_csv': True}}
    module_spec = importlib.util.spec_from_file_location('aeep_b_profile_assembler_v2', ASSEMBLER)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    profile = {'source_digest': SOURCE, 'pair': pair, 'callback_documents_by_role': callbacks}
    assembled = module.assemble_current_profile(profile_document=profile,
        spreadsheets_definition=shared,
        shared_physical_skill_inventory={role: {SKILL: shared['skill_sha256']} for role in ('discovery', 'aeep')},
        selected_worker=workers['treatment'].digest(), qualification_exposure='required', source_root=ROOT)
    assembled.update(callback_documents_by_role=callbacks,
        native_setup_result_sha256=sha(result_path), native_project=result['project'],
        task_instructions=INSTRUCTIONS, metadata_reference_sha256=HISTORICAL_SHA)
    with destination.open('x') as stream:
        json.dump(assembled, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'profile': str(destination), 'sha256': sha(destination),
        'component_digest': assembled['component_digest'], 'execution_authorized': False}))


if __name__ == '__main__':
    main()
