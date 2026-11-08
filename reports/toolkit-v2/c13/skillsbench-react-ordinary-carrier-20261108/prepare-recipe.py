"""Prepare the React v6 recipe privately using the existing SkillsBench builder."""

import base64
import hashlib
import json
import runpy
from pathlib import Path

from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.models import ExecutorSpec
from aeep.registry import validate_json

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
BUILDER = HERE.parent / 'skillsbench-contained-graders-20261105/prepare-recipes.py'


def main():
    helper = runpy.run_path(str(BUILDER))
    controls = json.loads((WORK/'controls.json').read_bytes())
    value = controls['input']
    variants = {row['name']: row for row in controls['variants']}
    good, fault = [base64.b64decode(variants[name]['artifact']['patch_b64'], validate=True)
                   for name in ('reference','destructive')]
    binding = {'task_id':value['task_id'],'output_field':'patch_b64','max_output_bytes':500_000,
               'archive_sha256':value['task_archive_sha256']}
    recipe = helper['recipe_for']('react',binding,value,good,fault)
    spec = ExecutorSpec(id='skillsbench.react.grader',capability='assessment.skillsbench.react@1',
        kind='command',description='Original React verifier on a bounded source artifact',
        side_effect='read',config={'argv':['/usr/bin/python3','-I','-B',
            '/opt/aeep-react-reference/grade.py',str(ROOT/'src')],'argv_literal':True,'stdin_json':True,
            'timeout_seconds':60,'max_output_bytes':32768,'output':{'type':'json'}})
    raw=recipe.model_dump(mode='json')
    raw['extension']['grader']=spec.model_dump(mode='json')
    recipe=RecipeDefinition.model_validate(raw)
    validate_json(value,recipe.input_schema,label='original public React input')
    for variant in ('reference','incomplete','destructive','outside_source'):
        validate_json(variants[variant]['artifact'],recipe.output_schema,label='bounded React artifact')
    target=WORK/'react-recipe.json'
    helper['save'](target,recipe.model_dump(mode='json'))
    evidence={
        'recipe_path':str(target),'recipe_digest':content_digest(recipe),
        'grader_spec_digest':content_digest(spec),'benchmark_pack_ref':value['benchmark_pack_sha256'],
        'task_archive_sha256':value['task_archive_sha256'],
        'reference_output_sha256':hashlib.sha256(good).hexdigest(),
        'protected_reference_in_private_recipe':True,'runtime_verification_required':True,
        'dispatch_authorized':False,'models':0,
    }
    helper['save'](HERE/'recipe-preparation.json',evidence)
    print(json.dumps({'passed':True,'schema':recipe.extension.schema_version,'models':0}))


if __name__ == '__main__':
    main()
