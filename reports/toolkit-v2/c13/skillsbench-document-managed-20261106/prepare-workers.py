"""Bind retained capable document workers to the two exact approved task archives."""

import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
WORK = ROOT / '.aeep' / HERE.name / 'worker-definitions'
PRIOR = C13 / 'worker-readiness-correction-20261103'
APPROVED = C13 / 'skillsbench-document-rights-20261106'
FOLDER = ROOT / '.aeep' / APPROVED.name
OLD = C13 / 'skillsbench-managed-worker-preparation-20261105'

COMMON = (
    'Use the original SkillsBench instruction and input files from the supplied archive. '
    'Unpack skillsbench-task.zip into your private workspace with Python zipfile. '
    'Treat the original absolute task paths as private workspace paths. '
    'Use the supplied stack-check skill for isolation and output discipline. '
    'The artifact transport requires the output at its provided absolute output_path. '
    'Write the completed artifact there and check that it exists and is within the byte limit. '
    'Return the completion JSON only. Do not encode the output in the response. '
    'Do not install software, search for solutions, or contact other services. '
    'Task and artifact paths follow.\n{input}'
)
TASKS = (
    ('invoice', 'invoice-fraud-detection', 'report_b64', 'fraud_report.json', 65536),
    ('excel', 'exceltable-in-ppt', 'presentation_b64', 'results.pptx', 256000),
)


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def bind(path, data):
    assert not path.is_symlink()
    if path.exists():
        assert path.read_bytes() == data
    else:
        with path.open('xb') as stream:
            stream.write(data)
        path.chmod(0o400)


def put(path, value):
    bind(path, (json.dumps(value, indent=2) + '\n').encode())


def main():
    proof = read(APPROVED / 'result.json')
    assert proof['review_sha256'] == sha(APPROVED / 'operation-review.json') and proof['models'] == 0
    assert proof['dispatch_authorized'] is False
    scope = read(APPROVED / 'operation-review.json')
    old = read(OLD / 'engineering-dispatch-review.json')
    old_pair = read(ROOT / '.aeep' / OLD.name / 'engineering/sales-pair.json')
    old_shared = read(ROOT / '.aeep' / OLD.name / 'engineering/sales-shared.json')
    assert content_digest(old_shared) == old_pair['differential']['shared_definition_digest']
    source = verification_source_digest(ROOT)
    WORK.mkdir(mode=0o700)
    facts = {}
    for role, task_id, field, output_name, limit in TASKS:
        row = next(item for item in scope['tasks'] if item['task_id'] == task_id)
        bound_pack = FOLDER / (task_id + '-bound-pack.json')
        assert sha(bound_pack) == proof['records'][task_id]['bound_pack_sha256']
        pack = BenchmarkPack.model_validate(read(bound_pack))
        task = pack.task(task_id)
        assert task.rights_review_ref == proof['records'][task_id]['review_ref']
        value = task_input(pack, Path(row['pack_root']), task_id)
        assert value['task_archive_sha256'] == row['public_archive_sha256']
        properties = {key: {'const': item} for key, item in value.items() if key != 'task_archive_b64'}
        properties['task_archive_b64'] = {'type': 'string', 'maxLength': 400000}
        input_schema = {'type': 'object', 'additionalProperties': False, 'required': sorted(properties),
                        'properties': properties}
        output_schema = {'type': 'object', 'additionalProperties': False, 'required': [field],
                         'properties': {field: {'type': 'string', 'minLength': 1, 'maxLength': 4*((limit+2)//3)}}}
        pair = json.loads(json.dumps(old_pair))
        shared = old_shared | {
            'purpose': 'One protected document/data integration task',
            'source_sha256': source, 'task_id': task_id, 'public_archive_sha256': row['public_archive_sha256'],
            'input_schema_sha256': content_digest(input_schema), 'output_schema_sha256': content_digest(output_schema),
            'artifact_name': output_name, 'artifact_limit': limit,
        }
        shared_ref = content_digest(shared)
        inventory = pair['differential']['control_inventory'] | {'common_profile': shared_ref}
        pair['differential'].update(shared_definition_digest=shared_ref, control_inventory=inventory,
            treatment_inventory=inventory | pair['differential']['candidate_inventory'])
        instructions = (
            'Python already has openpyxl. The same pypdf wheel is available at '
            '/opt/aeep-task-tools/pypdf-6.21.4-py3-none-any.whl. '
            'Insert that exact path into sys.path to read PDF inputs. '
        ) + COMMON
        for arm in ('control', 'treatment'):
            spec = pair[arm]
            spec.update(id='skillsbench-document-' + role + '.' + arm,
                        capability='assessment.skillsbench.' + role + '@1',
                        input_schema=input_schema, output_schema=output_schema)
            cfg = spec['config']
            image = old['worker_image_ids']['sales-' + ('control' if arm == 'control' else 'candidate')]
            assert cfg['managed_worker']['image'] == image
            assert not cfg['store_prompt'] and not cfg['store_output']
            cfg.update(adapter_id='codex-app-server:document-' + role + '-' + arm,
                instructions=instructions, timeout_seconds=900,
                artifact={'input_field':'task_archive_b64', 'output_field':field, 'input_name':'skillsbench-task.zip',
                          'output_name':output_name, 'max_bytes':limit})
            cfg['managed_worker']['worker_id'] = 'skillsbench-document-' + role + '-' + arm
        checked = WorkerPairInspection.model_validate(pair)
        assert checked.control.managed_host_config().artifact == checked.treatment.managed_host_config().artifact
        put(WORK / (role + '-pair.json'), checked.model_dump(mode='json'))
        put(WORK / (role + '-shared.json'), shared)
        facts[role] = {
            'task_id': task_id, 'pair_sha256': content_digest(checked), 'shared_sha256': shared_ref,
            'input_schema_sha256': content_digest(input_schema), 'output_schema_sha256': content_digest(output_schema),
            'public_archive_sha256': row['public_archive_sha256'],
            'worker_images': {arm: pair[arm]['config']['managed_worker']['image'] for arm in ('control','treatment')},
            'rights_review_ref': task.rights_review_ref, 'output_name': output_name, 'maximum_output_bytes': limit,
        }
    put(HERE / 'worker-preparation.json', {'pairs': facts, 'source_sha256': source,
         'workers_started': 0, 'models': 0, 'fresh_containment_required': True, 'comparisons': 'PAUSED'})
    print(json.dumps({'prepared_pairs': len(facts), 'workers_started': 0, 'models': 0}))


if __name__ == '__main__':
    main()
