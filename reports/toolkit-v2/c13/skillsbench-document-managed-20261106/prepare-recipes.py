"""Prepare two recipes using the existing contained SkillsBench recipe builder."""

import hashlib
import json
import runpy
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
WORK = ROOT / '.aeep' / HERE.name
RIGHTS = C13 / 'skillsbench-document-rights-20261106'
BOUND = ROOT / '.aeep' / RIGHTS.name


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def put(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + chr(10))
    path.chmod(0o400)


def prepare():
    builder = C13 / 'skillsbench-contained-graders-20261105/prepare-recipes.py'
    helper = runpy.run_path(builder)
    approved = read(RIGHTS / 'operation-review.json')
    applied = read(RIGHTS / 'result.json')
    pairs = read(HERE / 'worker-preparation.json')
    prepared = {}
    folder = WORK / 'recipes'
    folder.mkdir(mode=0o700)
    for role, facts in pairs['pairs'].items():
        task_id = facts['task_id']
        row = next(item for item in approved['tasks'] if item['task_id'] == task_id)
        pack_path = BOUND / (task_id + '-bound-pack.json')
        assert sha(pack_path) == applied['records'][task_id]['bound_pack_sha256']
        pack = BenchmarkPack.model_validate(read(pack_path))
        value = task_input(pack, Path(row['pack_root']), task_id)
        field = 'presentation_b64' if role == 'excel' else 'report_b64'
        if role == 'excel':
            root = ROOT / '.aeep/skillsbench-document-substitute-20261106'
            good = (root / 'reference.pptx').read_bytes()
            fault = (root / 'environment/input.pptx').read_bytes()
            assert hashlib.sha256(good).hexdigest() == read(C13 / 'skillsbench-document-substitute-20261106/reference-static-result.json')['output_sha256']
        else:
            good = (BOUND / 'invoice-protected-reference.json').read_bytes()
            proof = read(C13 / 'skillsbench-invoice-fraud-20261106/continuation/reference-execution/result.json')
            assert hashlib.sha256(good).hexdigest() == proof['oracle_report_sha256']
            fault = b'[]'
        binding = {'task_id':task_id, 'output_field':field, 'max_output_bytes':facts['maximum_output_bytes'],
                   'archive_sha256':facts['public_archive_sha256']}
        recipe = helper['recipe_for'](role, binding, value, good, fault)
        if role == 'excel':
            extension = recipe.extension
            grader = extension.grader
            cfg = {**grader.config, 'argv':['/opt/portable/python/bin/python3.12', '-I', '-B',
                                          '/opt/aeep-skillsbench-excel/grade.py']}
            recipe = recipe.model_copy(update={'extension':extension.model_copy(update={
                'grader':grader.model_copy(update={'config':cfg})})})
        validate_json(value, recipe.input_schema, label='approved original task')
        pair = read(WORK / 'worker-definitions' / (role + '-pair.json'))
        assert pair['control']['input_schema'] == recipe.input_schema
        assert pair['control']['output_schema'] == recipe.output_schema
        target = folder / (role + '-recipe.json')
        put(target, recipe.model_dump(mode='json'))
        prepared[role] = {'task_id':task_id, 'recipe_path':str(target), 'recipe_sha256':content_digest(recipe),
                          'pack_path':str(pack_path), 'pack_sha256':content_digest(pack.model_dump(mode='json')),
                          'archive_sha256':value['task_archive_sha256'], 'reference_sha256':hashlib.sha256(good).hexdigest(),
                          'protected_reference_in_private_recipe':True, 'grader_image_pending':True}
    put(HERE / 'recipe-preparation.json', {'recipes':prepared, 'builder_sha256':sha(builder),
        'rights_review_applied':applied['review_sha256'], 'models':0, 'programs_executed':0})
    print(json.dumps({'prepared_recipes':len(prepared), 'models':0, 'programs_executed':0}))


if __name__ == '__main__':
    prepare()
