"""Exercise the actual image-binding derivation in exclusively owned fixture data."""
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile

from aeep.assessment.models import AssessmentEnvironment, RecipeMaterializationRequest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def main():
    spec = importlib.util.spec_from_file_location('authored_derivation_fixture', HERE / 'derive-execution.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-git-binding-', dir=ROOT / '.aeep') as temp:
        fixture = Path(temp)
        out = fixture / 'runtime-execution'
        out.mkdir()
        for name in ('runtime-review.json', 'template-operation-review.json'):
            shutil.copyfile(HERE / name, fixture / name)
        sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        review = json.loads((fixture / 'runtime-review.json').read_text())
        image = 'sha256:' + 'f' * 64
        # These approvals/builds exist only in removed fixture data. No canonical
        # store, Docker call, real image, execution or human response is supplied.
        inputs = {
            'operator-approval.json': {'approved': True,
                'review_sha256': sha(fixture / 'runtime-review.json'),
                'source': 'SYNTHETIC FIXTURE: NOT AN OPERATOR APPROVAL'},
            'build-result.json': {'passed': True,
                'parent_review_sha256': sha(fixture / 'runtime-review.json'),
                'inherited_config_verified': True, 'parent_layers_verified': True,
                'image_id': image},
            'component-preparation.json': {'context_files': {}},
            'review-budget-anchor.json': {'grant_before': [100, 0, 1.0, '0.0']},
        }
        for name, value in inputs.items():
            (fixture / name).write_text(json.dumps(value))
        module.HERE, module.OUT, module.ROOT = fixture, out, ROOT
        module.main()
        actual = json.loads((out / 'operation-review.json').read_text())
        parent = json.loads((out / 'parent-runtime-review.json').read_text())
        env = AssessmentEnvironment.model_validate(next(v['document'] for v in parent['documents'].values() if v['kind'] == 'environment'))
        assert env.container_image == image and parent['image'] == image
        request = RecipeMaterializationRequest.model_validate(actual['request'])
        assert request.environment_digest in parent['documents']
        template = json.loads((HERE / 'template-operation-review.json').read_text())
        original_parent = json.loads((ROOT / template['parent_review']).read_text())
        assert parent['recipe'] == original_parent['recipe']
        for name in ('cases_file', 'records_file', 'active_case_ids', 'collections',
                     'probes', 'native_fixtures', 'expected_required_counts', 'method_sha256'):
            assert actual[name] == template[name]
        assert actual['maximum_operations'] == 26 and actual['maximum_reserved_seconds'] == 1335
        assert actual['maximum_contained_calls'] == 21
        assert json.loads((out / 'review-budget-anchor.json').read_text()) == inputs['review-budget-anchor.json']
        assert not json.loads((out / 'operator-approval.json').read_text())['new_human_reply_claimed']
        assert actual['parent_review_sha256'] == sha(out / 'parent-runtime-review.json')
    assert not fixture.exists()
    result = {'passed': True, 'actual_derivation_function_exercised': True,
        'synthetic_fixture_only_not_authority_or_benchmark': True,
        'new_image_binding_verified': True, 'programs_task_assertions_and_payloads_unchanged': True,
        'cumulative_build_budget_anchor_preserved': True,
        'no_new_human_response_claimed': True, 'all_owned_fixture_data_removed': True,
        'downloads_installs_builds_models_or_grant_charges': 0}
    (HERE / 'derivation-check.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
