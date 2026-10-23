"""Review a Python-version truth adaptation using retained observations only."""
import asyncio
import hashlib
import json
from pathlib import Path
import time

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteAsset, decode_patch, grade_suite_output, patch_artifact
from aeep.assessment.repository_tasks import RepositoryPatch

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = ROOT / '.aeep/repository-beniget-py313-truth-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    began = time.perf_counter()
    review = json.loads((HERE / 'operation-review.json').read_text())
    execution = json.loads((HERE / 'execution-result.json').read_text())
    audit = json.loads((HERE / 'completion-audit.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    identity = 'serge-sans-paille__beniget-121-declared-tests'
    old = next(x for x in json.loads((ROOT / review['cases_file']).read_text()) if x['input']['task_id'] == identity)
    case = RepositorySuiteCase.model_validate(old)
    observations = {x['name']: x for x in execution['observations']}
    responses = {}
    for label in ('reference', 'counterexample'):
        observed = observations[identity + '-' + label]
        path = HERE / observed['raw_file']
        assert sha(path) == observed['raw_sha256']
        responses[label] = json.loads(path.read_text())['output']
    required = case.truth.fail_to_pass + case.truth.pass_to_pass
    positive, negative = responses['reference'], responses['counterexample']
    assert positive['exit_code'] == 0 and negative['exit_code'] == 1
    assert set(positive['statuses']) == set(negative['statuses']) == set(required)
    assert set(positive['statuses'].values()) == {'PASSED'}
    assert set(negative['statuses'].values()) == {'PASSED', 'FAILED'}
    assert all(negative['statuses'][name] == 'PASSED' for name in case.truth.pass_to_pass)
    failed = [name for name in required if negative['statuses'][name] == 'FAILED']
    moved = [name for name in case.truth.fail_to_pass if negative['statuses'][name] == 'PASSED']
    assert len(failed) == len(moved) == 3
    assert all(name.endswith('::test_WindowsError_builtin_name') for name in failed)
    assert all(name.endswith('::test_newer_Python_version_builtin_name') for name in moved)
    OUT.mkdir(exist_ok=False)
    value = case.model_dump(mode='json')
    value['input']['task_id'] += '-py313-truth'
    binding = content_digest(value['input'])
    value['independent_case_id'] = value['input']['task_id']
    value['truth'].update(input_sha256=binding, fail_to_pass=failed, pass_to_pass=[name for name in required if name not in failed])
    reference = decode_patch(json.loads(case.reference.read()))
    reference.base_sha256 = binding
    ref = OUT / 'reference.json'
    ref.write_text(json.dumps(patch_artifact(reference), separators=(',', ':')))
    value['reference'] = SuiteAsset(path=str(ref.resolve()), sha256=sha(ref), size_bytes=ref.stat().st_size).model_dump(mode='json')
    for fault in value['fault_outputs']:
        patch = decode_patch(fault)
        patch.base_sha256 = binding
        fault.update(patch_artifact(patch))
    value['provenance'] += ' Separate pre-freeze Python3.13 truth adaptation under standing definition authority: every422 required assertion remains. Three newer-builtin identities already pass on the original source in this runtime and become preservation checks; three WindowsError checks remain fail-to-pass. Old six-failure metadata/classifier outcome remains failed. Exact physical payload hashes and completed receipts are reused, not replayed. No model result informed this adaptation.'
    adapted = RepositorySuiteCase.model_validate(value)
    variants = json.loads((ROOT / review['variants_file']).read_text())
    grades, payload_proofs = {}, []
    for label, output in [('reference', patch_artifact(reference)), ('counterexample', patch_artifact(RepositoryPatch(base_sha256=binding, files={})) )]:
        original = next(x for x in variants if x['case'] == identity and x['variant'] == label)
        async def retained(payload):
            digest = hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest()
            assert digest == original['sha256']
            payload_proofs.append({'variant': label, 'unchanged_physical_payload_sha256': digest, 'raw_observation': observations[identity + '-' + label]})
            return responses[label]
        grade = await grade_suite_output(adapted.input.model_dump(mode='json'), adapted.truth.model_dump(mode='json'), output, retained)
        assert grade.valid == (label == 'reference') and grade.detail == ('' if label == 'reference' else 'test_failure')
        grades[label] = grade.model_dump(mode='json')
    cases = OUT / 'cases.json'
    cases.write_text(json.dumps([adapted.model_dump(mode='json')], indent=2) + '\n')
    result = {'passed': True, 'authority': 'September25/27 standing finite test-definition delegation; no new untrusted execution.',
              'old_case_id': identity, 'new_case_id': adapted.input.task_id, 'old_batch_result_changed': False,
              'cases_file': str(cases.relative_to(ROOT)), 'cases_file_sha256': sha(cases),
              'old_expected_bug_failures': 6, 'current_fail_to_pass': failed, 'moved_to_preservation': moved,
              'required_identities_before': len(required), 'required_identities_after': len(required),
              'assertions_source_image_observer_and_wheels_unchanged': True, 'physical_payload_proofs': payload_proofs, 'grades': grades,
              'new_external_calls': 0, 'new_model_turns': 0, 'new_canonical_execution_operations': 0,
              'analysis_elapsed_seconds': time.perf_counter() - began, 'analysis_scope': 'Local first-party retained-data engineering check; no external source execution.',
              'cases_adopted': 0, 'stages_frozen': False, 'qualification': False, 'comparative_usefulness': False,
              'limitation': 'Adapted task metadata/runtime reproduction only. No official benchmark result, frozen model holdout, admission, cost/savings or whole-project resource claim.'}
    (HERE / 'beniget-truth-adaptation.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: result[k] for k in ('passed', 'required_identities_after', 'old_batch_result_changed', 'new_external_calls', 'cases_file')}))


if __name__ == '__main__':
    asyncio.run(main())
