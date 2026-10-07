"""Export an inert SkillsBench adaptation through the existing recipe extension.

Export does not execute a program, materialize cases, review a definition or
qualify a candidate. Reference and grader source stay in the protected recipe
executors; task inputs contain only the pinned template, employee data and task.
"""
from __future__ import annotations

import base64
import hashlib
import inspect
import json
import sysconfig
from pathlib import Path

from ..errors import ConfigurationError
from ..models import ExecutorKind, ExecutorSpec
from . import skillsbench_offer_letter as existing
from .models import (
    ExecutableRecipeExtension,
    RecipeDefinition,
    RecipeFeatureRule,
    RecipeLiteralFixture,
)

VARIATIONS = ['relocation_yes', 'relocation_no', 'unicode_names', 'xml_escaping',
              'long_fields', 'numeric_boundaries', 'date_boundaries']
TASK = ('Fill every {{FIELD}} in the supplied DOCX template using employee_data, including '
        'placeholders split across runs, nested tables, headers and footers. When '
        'RELOCATION_PACKAGE is Yes, keep the relocation text and remove its IF/END markers. '
        'When it is No, remove the entire marked text, retaining the empty paragraph and '
        'existing run elements. Preserve all other text, paragraph/table/run elements, '
        'non-text XML properties and package members. Text may move between existing runs; '
        'xml:space may change on text nodes. Return only {"document_b64": "<base64 DOCX>"}.')
_ASSET_FILE = 'skillsbench-offer-letter-fixtures.json'


def skillsbench_offer_letter_recipe(asset_root: Path | None = None) -> RecipeDefinition:
    """Freeze bundled, pinned assets and contained programs into a reviewable definition."""
    root = Path(__file__).resolve().parents[3] / 'integrations' / 'assessment-runtime'
    if not root.is_dir():
        root = Path(sysconfig.get_path('data')) / 'share' / 'aeep' / 'integrations' / 'assessment-runtime'
    try:
        asset_bytes = (root / _ASSET_FILE).read_bytes()
        if len(asset_bytes) > 1_000_000:
            raise ConfigurationError('SkillsBench recipe assets exceed their bound')
        assets = json.loads(asset_bytes)
        template = base64.b64decode(assets['template_b64'], validate=True)
        data_bytes = assets['employee_data_json'].encode()
        if (hashlib.sha256(template).hexdigest() != existing.TEMPLATE_SHA256
                or hashlib.sha256(data_bytes).hexdigest() != existing.DATA_SHA256):
            raise ConfigurationError('bundled SkillsBench inputs changed')
        if asset_root is not None:
            existing._pinned_bytes(asset_root / 'offer_letter_template.docx', existing.TEMPLATE_SHA256, 150000)
            existing._pinned_bytes(asset_root / 'employee_data.json', existing.DATA_SHA256, 10000)
            for name in ('LICENSE', 'NOTICE', 'provenance.json'):
                existing._pinned_bytes(asset_root / name,
                    hashlib.sha256(assets['original_files'][name].encode()).hexdigest(), 20000)
        data = json.loads(data_bytes)
        program = (root / 'skillsbench_offer_letter_program.py').read_text(encoding="utf-8")
        grader = (root / 'skillsbench_offer_letter_grader.py').read_text(encoding="utf-8")
        literals = assets['fixtures']
        fixtures = []
        for item in literals:
            value = {'template_b64': assets['template_b64'], 'employee_data': item['employee_data'],
                     'task': TASK, 'variation': item['variation']}
            truth = {'input_sha256': hashlib.sha256(json.dumps(value, sort_keys=True,
                ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()}
            fixtures.append(RecipeLiteralFixture(input=value, output=truth,
                grader_output={'document_b64': item['document_b64']}))
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise ConfigurationError('installed SkillsBench recipe assets are unavailable or invalid') from exc

    # Only repository-owned source is assembled; external package code is never
    # imported. Frozen source and asset bytes are covered by the recipe digest.
    constants = ('import json\nASSETS = json.loads(' + repr(json.dumps({
        'template_b64': assets['template_b64'], 'employee_data': data})) + ')\n'
        + 'VARIATIONS = ' + repr(VARIATIONS) + '\nTASK = ' + repr(TASK) + '\n')
    reader = ('import base64, io, re, zipfile\nfrom xml.etree import ElementTree as ET\n'
        'class ConfigurationError(ValueError): pass\n'
        + '_W = ' + repr(existing._W) + '\n_SPLIT_FIELDS = ' + repr(existing._SPLIT_FIELDS)
        + '\n_NESTED_FIELDS = ' + repr(existing._NESTED_FIELDS) + '\n'
        + inspect.getsource(existing._document) + '\n' + inspect.getsource(existing.grade_artifact) + '\n')

    def executor(name: str, source: str) -> ExecutorSpec:
        return ExecutorSpec(id='skillsbench.offer_letter.' + name, capability='assessment.offer_letter@1',
            kind=ExecutorKind.COMMAND, description='Contained SkillsBench offer-letter adaptation ' + name,
            config={'argv': ['python3', '-I', '-c', constants + source, name],
                    'argv_literal': True, 'stdin_json': True, 'timeout_seconds': 30,
                    'max_output_bytes': 16_000_000, 'output': {'type': 'json'}})

    employee_schema = {'type': 'object', 'required': sorted(data), 'additionalProperties': False,
        'properties': {key: ({'enum': ['Yes', 'No']} if key == 'RELOCATION_PACKAGE'
            else {'type': 'string', 'minLength': 1, 'maxLength': 256, 'pattern': r'^[^\u0000-\u001f]*$'})
            for key in data}}
    return RecipeDefinition(schema_version='assessment.recipe.v2', recipe_id='skillsbench-offer-letter-adapted-v1',
        capability='assessment.offer_letter@1',
        description='Bounded pinned SkillsBench offer-letter adaptation; seven synthetic variations of one template, not an official upstream reproduction.',
        input_schema={'type': 'object', 'required': ['template_b64', 'employee_data', 'task', 'variation'],
            'additionalProperties': False, 'properties': {'template_b64': {'const': assets['template_b64']},
                'employee_data': employee_schema, 'task': {'const': TASK}, 'variation': {'enum': VARIATIONS}}},
        output_schema={'type': 'object', 'required': ['document_b64'], 'additionalProperties': False,
            'properties': {'document_b64': {'type': 'string', 'maxLength': 200000}}},
        generator='contained_json:1', grader='contained_json:1', extractor='structural_json:1',
        generator_config={'upstream': json.loads(assets['original_files']['provenance.json']),
            'license': 'Apache-2.0', 'license_text': assets['original_files']['LICENSE'],
            'notice': assets['original_files']['NOTICE'], 'adaptation_version': 1,
            'changes': 'Synthetic employee data; explicit No-relocation acceptance; preservation of original XML structure; no upstream verifier execution.',
            'fixture_provenance': assets['fixture_provenance'],
            'counts': {'screening': 8, 'training': 28, 'holdout': 105},
            'seed_range': [0, 2**63-1], 'official_reproduction': False},
        dependencies={'pinned_template': existing.TEMPLATE_SHA256, 'pinned_employee_data': existing.DATA_SHA256,
            'recipe_assets': hashlib.sha256(asset_bytes).hexdigest()},
        variations=VARIATIONS, exclusions=['arbitrary templates', 'official SkillsBench score or upstream verifier reproduction',
            'visual pagination or typography claims', 'changing run/table/paragraph structures', 'macros, embedded objects, external relationships',
            'employee strings over 256 characters or with control characters', 'statistical independence across template families'],
        extension=ExecutableRecipeExtension(schema_version='assessment.recipe-extension.v3',
            generator=executor('generate', program), reference=executor('reference', program), grader=executor('grade', reader + grader),
            truth_schema={'type': 'object', 'required': ['input_sha256'], 'additionalProperties': False,
                'properties': {'input_sha256': {'type': 'string', 'pattern': '^[0-9a-f]{64}$'}}},
            independent_fixtures=fixtures[:2], transformed_fixtures=fixtures[2:],
            fault_outputs=[{'document_b64': 'invalid'}, {'document_b64': assets['template_b64']}, *assets['fault_outputs']],
            failure_codes=['input_binding', 'output_contract', 'text_preserved', 'document_structure',
                'relocation_yes', 'relocation_no', 'package_members', 'preserved_parts', 'invalid_document'],
            feature_rules={'variation': RecipeFeatureRule(path='/variation', operation='enum', values=[*VARIATIONS]),
                'relocation': RecipeFeatureRule(path='/employee_data/RELOCATION_PACKAGE', operation='enum', values=['Yes', 'No'])},
            variation_features={name: {'variation': name, 'relocation': 'No' if name == 'relocation_no' else 'Yes'} for name in VARIATIONS},
            template_families=['skillsbench-offer-letter:pinned-template']))


if __name__ == '__main__':
    # Definition-only check; never launches the contained programs or a trial.
    from ..registry import validate_json

    recipe = skillsbench_offer_letter_recipe()
    assert recipe.extension is not None
    assert recipe.extension.truth_schema is not None
    fixtures = [*recipe.extension.independent_fixtures, *recipe.extension.transformed_fixtures]
    assert {item.input['employee_data']['RELOCATION_PACKAGE'] for item in fixtures} == {'Yes', 'No'}
    for fixture in fixtures:
        validate_json(fixture.input, recipe.input_schema, label='offer-letter literal input')
        validate_json(fixture.output, recipe.extension.truth_schema, label='offer-letter literal truth')
        validate_json(fixture.grader_output, recipe.output_schema, label='offer-letter literal output')
    for executor in (recipe.extension.generator, recipe.extension.reference, recipe.extension.grader):
        compile(executor.config['argv'][3], executor.id, 'exec')
