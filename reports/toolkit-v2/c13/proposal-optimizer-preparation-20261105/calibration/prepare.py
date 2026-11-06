"""Freeze a public AFlow calibration set and an isolated existing AEEP reference."""

import hashlib
import json
import shutil
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.recipes import reference_text, shipped_recipe
from aeep.registry import validate_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PARENT = HERE.parent
WORK = ROOT/'.aeep'/PARENT.name/'protected-calibration'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2)+'\n')


assert shutil.disk_usage(ROOT).free >= 50*1024**3
case_path = HERE/'public-cases.json'
cases = read(case_path)['cases']
assert len(cases) == len({item['id'] for item in cases}) == 3
recipe = shipped_recipe('text')
runtime = read(PARENT/'socket-boundary/result.json')
assert runtime['passed'] and runtime['observed']['optimizer_imported'] and not runtime['models']
source = read(PARENT/'source-contracts.json')['components']['aflow']
definitions = []
for case in cases:
    validate_json(case['input'],recipe.input_schema,label='public AFlow calibration case')
    expected = reference_text(**case['input'])
    validate_json(expected,recipe.output_schema,label='protected AFlow calibration reference')
    definitions.append({'case_id':case['id'],'input_sha256':content_digest(case['input']),
                        'validator':{'kind':'exact_match','config':{'expected':expected}}})
assert [sorted(item['validator']['config']['expected']) for item in definitions] == [
    ['fields'], ['fields'], ['error'],
]
WORK.mkdir(mode=0o700)
protected = WORK/'reference.json'
write(protected,{'case_sha256':sha(case_path),'recipe_sha256':content_digest(recipe),'definitions':definitions})
protected.chmod(0o400)
report = {
    'scope':'engineering_calibration_only', 'source_revision':source['revision'],
    'runtime_image_id':runtime['runtime_image_id'],'runtime_result_sha256':sha(PARENT/'socket-boundary/result.json'),
    'upstream_optimizer_sha256':source['files']['scripts/optimizer.py']['sha256'],
    'public_cases_sha256':sha(case_path),'protected_reference_sha256':sha(protected),
    'recipe_id':recipe.recipe_id,'recipe_sha256':content_digest(recipe),'case_count':len(definitions),
    'cases_used_in_comparisons':False,'candidate_or_optimizer_executed':False,'models':0,
    'cycle_design':{'maximum_optimizer_rounds':1,'maximum_proposal_requests':1,'maximum_grade_batches':2,
                    'optimizer_fallback':'disabled at reviewed provider boundary',
                    'reference_mount':'protected grader only','generated_code':'separate reviewed sandbox only'},
}
write(HERE/'calibration-preparation.json',report)
print(json.dumps(report))
