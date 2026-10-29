"""Verify actual backend evidence and source/controller guards without task execution."""
import ast
import copy
from datetime import timedelta
import importlib.util
import json
from pathlib import Path
import sys
import tempfile

from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment, AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(HERE / 'runtime-execution'))
from reuse_conformance import verify_reuse
from native_scope import expand


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    review = json.loads((HERE / 'operation-review.json').read_text())
    reused = verify_reuse(review, ROOT)
    assert reused['canonical_completed_receipt_chains_reopened'] == 19
    checks = ['actual_exact_backend_19canonical_receipts_reopened']
    for field in ('source_digest',):
        altered = copy.deepcopy(review)
        altered[field] = '0' * 64
        try:
            verify_reuse(altered, ROOT)
        except AssertionError:
            pass
        else:
            raise AssertionError('Changed backend source accepted')
    checks.append('source_drift_rejected')
    with tempfile.TemporaryDirectory(prefix='aeep-source-audit-binding-') as temporary:
        path = Path(temporary) / 'parent.json'
        parent = json.loads((ROOT / review['parent_review']).read_text())
        parent['recipe']['extension']['grader']['config']['timeout_seconds'] = 999
        path.write_text(json.dumps(parent))
        altered = copy.deepcopy(review)
        altered['parent_review'] = str(path)
        try:
            verify_reuse(altered, ROOT)
        except AssertionError:
            pass
        else:
            raise AssertionError('Changed executor configuration accepted')
    checks.append('executor_configuration_drift_rejected')
    # Exercise exact definitions and operation ceilings only in removed fixture DB.
    parent = json.loads((ROOT / review['parent_review']).read_text())
    documents = {**parent['documents'], **review['new_documents']}
    models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
        'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
    request = RecipeMaterializationRequest.model_validate(review['request'])
    budget = load('source_audit_budget_fixture', HERE / 'runtime-execution/review-budget.py')
    assert budget.self_check() == 7
    with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-source-budget-', dir=ROOT / '.aeep') as temporary:
        store = ReceiptStore(Path(temporary) / 'fixture-only.sqlite3')
        try:
            repo = AssessmentRepository(store)
            grant = AssessmentAuthorization(authorization_id='onboarding', subject_digests=[request.subject_digest],
                recipe_digests=[request.recipe_digest], environment_digests=[request.environment_digest],
                limits=AssessmentLimits(max_operations=100, max_elapsed_seconds=2000), expires_at=utc_now() + timedelta(minutes=5))
            repo.grant(grant)
            for digest, item in documents.items():
                assert repo.put(item['kind'], item['id'], models[item['kind']].model_validate(item['document'])) == digest
            amendment = copy.deepcopy(review['amendment'])
            amendment['authorization_digest'] = content_digest(grant)
            repo.approve_bundle(AssessmentScopeAmendment.model_validate(amendment), {k: v['document'] for k, v in documents.items()})
            repo.authorize(request)
            budget.install(repo, store._connection, [0, 0, 0.0, '0'], review)
            for index in range(8):
                operation = 'SYNTHETIC-no-dispatch-' + str(index)
                repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='synthetic_no_dispatch')
                repo.finish_operation(operation, elapsed_seconds=.001)
            try:
                repo.reserve(request, 'SYNTHETIC-operation9', AssessmentLimits(max_operations=1, max_elapsed_seconds=1), stage='synthetic_no_dispatch')
            except RuntimeError:
                pass
            else:
                raise AssertionError('Ninth operation exceeded reviewed bound')
        finally:
            store.close()
    assert not Path(temporary).exists()
    checks.append('exact_definitions_authorized_only_in_removed_synthetic_store')
    checks.append('actual_bound_guard_rejects_operation9')
    assert expand(['tests/test_x.py::test_x[value'], [], ['tests/test_x.py::test_x[value one]', 'tests/test_x.py::test_x[value two]'], ['tests/test_x.py'])[0] == ['tests/test_x.py::test_x[value one]', 'tests/test_x.py::test_x[value two]']
    for aliases, native in [(['tests/test_x.py::missing'], ['tests/test_x.py::other']),
        (['tests/test_x.py::x', 'tests/test_x.py::x'], ['tests/test_x.py::x'])]:
        try:
            expand(aliases, [], native, ['tests/test_x.py'])
        except ValueError:
            pass
        else:
            raise AssertionError('Missing or overlapping alias accepted')
    checks.append('unchanged_exhaustive_mapping_guards_pass')
    for name in ('run.py', 'audit-execution.py'):
        text = (HERE / 'runtime-execution' / name).read_text()
        ast.parse(text)
        assert 'verify_reuse(review' in text and "new_runtime_probes" in text
        assert 'shared_probe' not in text and 'runtime-support' not in text
    checks.append('actual_drivers_have_no_runtime_probe_or_control_replay')
    with (HERE / 'preparation-check.json').open('x') as output:
        json.dump({'passed': True, 'checks': checks, 'backend_evidence': reused,
            'new_subjects_executed': False, 'actual_new_models_builds_installs_downloads_or_grant_charges': 0,
            'synthetic_budget_fixture_not_authority_or_benchmark': True}, output, indent=2)
        output.write('\n')
    print(json.dumps({'passed': True, 'checks': len(checks), 'canonical_prior_chains_reopened': 19}))


if __name__ == '__main__':
    main()
