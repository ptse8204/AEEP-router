"""Offline software checks for the adapted SkillsBench executable recipe.

These checks exercise only trusted, locally assembled recipe programs. They do
not run the official SkillsBench verifier or establish campaign evidence.
"""

from __future__ import annotations

import json
import subprocess
from collections import Counter
from pathlib import Path

import pytest

from aeep.assessment.models import content_digest
from aeep.assessment.skillsbench_recipe import skillsbench_offer_letter_recipe
from aeep.errors import ConfigurationError

pytestmark = pytest.mark.assessment_contract


def _run(executor, payload: dict) -> dict:
    result = subprocess.run(
        executor.config['argv'],
        input=json.dumps(payload, ensure_ascii=False).encode(),
        capture_output=True,
        timeout=30,
        check=True,
    )
    return json.loads(result.stdout)


def _generation_request(recipe, seed: int = 29) -> dict:
    return {
        'seed': seed,
        'stages': [
            {'split': 'qualification', 'count': 8},
            {'split': 'training', 'count': 28},
            {'split': 'holdout', 'count': 105},
        ],
        'variations': recipe.variations,
    }


def test_skillsbench_recipe_cases_are_deterministic_disjoint_and_balanced():
    recipe = skillsbench_offer_letter_recipe()
    extension = recipe.extension
    assert extension is not None
    assert recipe.generator_config['counts'] == {
        'screening': 8,
        'training': 28,
        'holdout': 105,
    }

    first = _run(extension.generator, _generation_request(recipe))['cases']
    second = _run(extension.generator, _generation_request(recipe))['cases']
    assert first == second
    assert len(first) == 141

    splits = (first[:8], first[8:36], first[36:])
    assert tuple(map(len, splits)) == (8, 28, 105)
    input_keys = [
        json.dumps(case['input'], sort_keys=True, ensure_ascii=False, separators=(',', ':'))
        for case in first
    ]
    assert len(set(input_keys)) == 141
    case_ids = [case['input']['employee_data']['DOC_ID'] for case in first]
    assert len(set(case_ids)) == 141
    for cases in splits:
        counts = Counter(case['variation'] for case in cases)
        assert set(counts) == set(recipe.variations)
        assert max(counts.values()) - min(counts.values()) <= 1


def test_skillsbench_reference_passes_and_declared_faults_fail_v3_grader():
    recipe = skillsbench_offer_letter_recipe()
    extension = recipe.extension
    assert extension is not None and extension.failure_codes is not None
    fixtures = [*extension.independent_fixtures, *extension.transformed_fixtures]
    reference = _run(extension.reference, {'inputs': [fixture.input for fixture in fixtures]})
    examples = [
        {'input': fixture.input, 'expected': fixture.output, 'output': output}
        for fixture, output in zip(fixtures, reference['outputs'], strict=True)
    ]
    assert all(fixture.grader_output is not None for fixture in fixtures)
    literal_examples = [
        {'input': fixture.input, 'expected': fixture.output, 'output': fixture.grader_output}
        for fixture in fixtures
    ]

    correct_examples = [*examples, *literal_examples]
    accepted = _run(extension.grader, {'examples': correct_examples})
    assert accepted == {
        'valid': [True] * len(correct_examples),
        'failure_codes': [None] * len(correct_examples),
    }

    faulty = [
        {**examples[0], 'output': output}
        for output in extension.fault_outputs
    ]
    rejected = _run(extension.grader, {'examples': faulty})
    assert rejected['valid'] == [False] * len(faulty)
    assert all(code in extension.failure_codes for code in rejected['failure_codes'])


def test_skillsbench_recipe_artifact_and_source_drift_change_reviewed_definition(tmp_path, monkeypatch):
    recipe = skillsbench_offer_letter_recipe()
    original_digest = content_digest(recipe)

    (tmp_path / 'offer_letter_template.docx').write_bytes(b'drifted artifact')
    with pytest.raises(ConfigurationError, match='digest changed'):
        skillsbench_offer_letter_recipe(tmp_path)

    read_text = Path.read_text

    def drift_source(path: Path, *args, **kwargs) -> str:
        source = read_text(path, *args, **kwargs)
        if path.name == 'skillsbench_offer_letter_program.py':
            return source + '\n# source drift requires a new reviewed definition\n'
        return source

    with monkeypatch.context() as patch:
        patch.setattr(Path, 'read_text', drift_source)
        drifted = skillsbench_offer_letter_recipe()

    assert content_digest(drifted) != original_digest
    assert drifted.extension is not None and recipe.extension is not None
    assert drifted.extension.generator.config['argv'] != recipe.extension.generator.config['argv']
