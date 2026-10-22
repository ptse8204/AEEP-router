"""Freeze an offline, no-model reproduction review without executing new subjects."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentScopeAmendment, AssessmentSubject,
    RecipeMaterializationRequest, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from classify import self_check

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIOR = HERE.parent / 'repository-suite-semantic-fault-20261022'
PARENT = HERE.parent / 'repository-suite-integration-20261022/grader-operation-review.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not (HERE / 'operation-review.json').exists()
    parent = json.loads(PARENT.read_text())
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    assert prepared['prepared_cases'] == 8 and not prepared['errors']
    assert verification_source_digest(ROOT) == parent['source_digest']
    assert runtime_dependencies() == parent['request']['runtime_dependencies']
    free = shutil.disk_usage(ROOT).free
    assert free > 50 * 1024**3 + 20 * 1024**2
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        parent['image'], '--format', '{{.Id}}'], timeout=20).decode().strip() == parent['image']
    cases_path, variants_path = ROOT / prepared['cases_file'], ROOT / prepared['variants_file']
    assert sha(cases_path) == prepared['cases_file_sha256']
    cases = [RepositorySuiteCase.model_validate(item) for item in json.loads(cases_path.read_text())]
    variants = json.loads(variants_path.read_text())
    assert len(cases) == 8 and len(variants) == 16
    assert len({case.source_repository.casefold() for case in cases}) == 8
    assert len({case.input.source_sha256 for case in cases}) == 8
    assert all(case.split == 'qualification' and not case.used_for_development for case in cases)
    assert all(case.source_repository.casefold().removeprefix('https://github.com/') not in
               {'delgan/loguru', 'pallets/click', 'marshmallow-code/marshmallow', 'pgmpy/pgmpy'} for case in cases)
    assert all(not item['adopted'] and not item['stage_assignment_frozen'] for item in prepared['cases'])
    records = []
    for filename in ('curation-source-batch.json', 'curation-source-batch2.json'):
        records.extend(json.loads((PRIOR / filename).read_text())['sources'])
    sources = {item['instance_id']: item for item in records}
    assets = {str(path.resolve()): sha(path) for path in (cases_path, variants_path, HERE / 'prepared-cases.json',
        PRIOR / 'composed-conformance.json', PRIOR / 'completion-audit.json',
        PRIOR / 'curation-source-batch.json', PRIOR / 'curation-source-batch2.json',
        PRIOR / 'curation-runtime-wheel-review.json')}
    # Bind all inherited physical receipt audits, including their failed terminal outcomes.
    for directory in ('repository-suite-integration-20261022', 'repository-suite-continuation-20261022'):
        path = HERE.parent / directory / 'completion-audit.json'
        audit = json.loads(path.read_text())
        assert audit['all_owned_containers_absent_from_running_and_stopped']
        assets[str(path)] = sha(path)
    conformance = json.loads((PRIOR / 'composed-conformance.json').read_text())
    assert conformance['passed'] and conformance['all_owned_containers_absent']
    expectations = {}
    for case, description in zip(cases, prepared['cases'], strict=True):
        assert case.input.task_id == description['id']
        source_record = sources[description['original_issue_id']]
        row_path = ROOT / source_record['private_cache'] / 'row.json'
        row = json.loads(row_path.read_text())
        assets[str(row_path.resolve())] = sha(row_path)
        for item in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            item.read()
            assets[item.path] = item.sha256
        required = case.truth.fail_to_pass + case.truth.pass_to_pass
        baseline = {name: 'FAILED' for name in row['FAIL_TO_PASS']}
        baseline.update({name: 'PASSED' for name in row['PASS_TO_PASS']})
        if case.origin_kind == 'authored_control':
            assert case.input.family == 'contract-audit' and not case.truth.fail_to_pass
            baseline['tests/test_aeep_preservation.py::test_snapshot_preserved'] = 'FAILED'
        assert set(baseline) == set(required)
        expectations[case.input.task_id] = {
            'reference': {'exit_code': 0, 'valid': True, 'detail': '', 'statuses': {name: 'PASSED' for name in required}},
            'counterexample': {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': baseline}}
        for label in ('reference', 'counterexample'):
            staged = [item for item in variants if item['case'] == case.input.task_id and item['variant'] == label]
            assert len(staged) == 1
            staged = staged[0]
            payload_path = ROOT / staged['payload']
            assert payload_path.stat().st_size == staged['bytes'] and sha(payload_path) == staged['sha256']
            assets[str(payload_path.resolve())] = staged['sha256']
            captured = []

            class Captured(Exception):
                pass

            async def capture(payload):
                captured.append(hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest())
                raise Captured()

            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'),
                                         staged['artifact'], capture)
            except Captured:
                pass
            else:
                raise AssertionError('Preparation unexpectedly returned a grade')
            assert captured == [staged['sha256']]
    previous = RecipeMaterializationRequest.model_validate(parent['request'])
    subject = AssessmentSubject(kind='command', location=str(cases_path.parent.resolve()), dependency_digests=assets,
        description='Eight provisional repository workloads: fixed reference and counterexample reproduction only; no campaign, models or adoption.')
    request = RecipeMaterializationRequest(schema_version=previous.schema_version, subject_digest=content_digest(subject),
        recipe_digest=previous.recipe_digest, mapping_digest=previous.mapping_digest,
        environment_digest=previous.environment_digest, authorization_id=previous.authorization_id,
        seed=43, definition_digests=previous.definition_digests, runtime_dependencies=previous.runtime_dependencies)
    docs = {key: item for key, item in parent['documents'].items() if item['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new_docs = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
                for kind, identity, value in [('subject', subject.subject_id, subject),
                    ('recipe_materialization_request', request.plan_id, request)]}
    docs.update(new_docs)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[previous.recipe_digest],
        environment_digests=[previous.environment_digest], reviewed_digests=list(docs))
    driver_files = {name: sha(HERE / name) for name in ('run.py', 'classify.py')}
    review = {'purpose': 'Pre-adoption runtime reproduction of eight new source-grounded cases. Continue independent case exclusions, stop on any common identity/authority/accounting/cleanup uncertainty.',
        'source_digest': parent['source_digest'], 'parent_review': str(PARENT.relative_to(ROOT)),
        'parent_review_sha256': sha(PARENT), 'driver_files': driver_files, 'request': request.model_dump(mode='json'),
        'new_documents': new_docs, 'reviewed_document_digests': list(docs), 'amendment': amendment.model_dump(mode='json'),
        'authorization_digest': parent['authorization_digest'], 'assets': assets,
        'cases_file': str(cases_path.relative_to(ROOT)), 'variants_file': str(variants_path.relative_to(ROOT)),
        'active_case_ids': [case.input.task_id for case in cases], 'case_summary': prepared['cases'], 'expectations': expectations,
        'maximum_contained_calls': 16, 'maximum_operations': 18, 'maximum_reserved_seconds': 710,
        'maximum_model_turns': 0, 'cash_usd': 0, 'automatic_retry': False,
        'network': 'none', 'image': parent['image'], 'environment_digest': previous.environment_digest,
        'envelope': 'Reuse the exact reviewed development observer recipe as an operator-only execution envelope. Do not materialize it or register these eight cases as a complete campaign. New cases remain provisional qualification data, not relabeled development cases.',
        'inherited_containment': {'source_digest': parent['source_digest'], 'environment_digest': previous.environment_digest,
            'image': parent['image'], 'probes': 3, 'physical_receipts_audited': 13,
            'conformance_summary': str((PRIOR / 'composed-conformance.json').relative_to(ROOT))},
        'execution_policy': ['One batch, at most reference plus counterexample per case; no retry. Skip a counterexample if its reference cannot reproduce.',
            'Retain bounded raw public-test replies before grader protocol validation, canonical receipts and all operation charges.',
            'A reproducible case needs every required reference test PASSED and every negative test at its frozen expected status, pytest exit0/1 respectively, and correct valid/invalid grades.',
            'An isolated reference, counterexample or protocol failure makes that case ineligible; continue other cases only after canonical attempt completion and container cleanup are verified.',
            'Stop all dispatch on source/asset/authority/receipt/accounting/cleanup uncertainty. Never infer inner status from outer process success.',
            'No models, installations, downloads, image builds/pulls, docs binary, credentials, cash, activation, release, historical replay or retained-resource cleanup. Remove only new attempt-owned containers.'],
        'limitations': ['Adapted Python3.13/pytest8.3.5 and explicit pure wheels are not official benchmark runtime equivalence; missing runtime dependencies cause exclusion, not silent installation.',
            'Two audits are authored controls starting from a published corrected snapshot with an additional byte-preservation guard, not unmodified upstream repair issues.',
            'No new model correctness/value/selection/resource acceptance evidence or admission. Full independent8/28/105 stage freeze remains open.',
            'Reproduction results may exclude nonreproducible cases before any model outcomes. Do not tune the grader, thresholds or tests to force eligibility.'],
        'approval_reason': 'New untrusted repository/test/wheel bytes and newly provisioned disposable calls are outside all terminal exact approvals. CONTINUATION.md and the user continuation reserve this execution for specific approval; routine finite scope definition uses standing delegation.',
        'execution_started': False}
    static = {'passed': True, 'source_unchanged': True, 'prepared_cases': 8, 'staged_payloads_verified': 16,
        'classifier_checks_passed': self_check(), 'all_assets_verified': len(assets), 'maximum_payload_bytes': max(item['bytes'] for item in variants),
        'distinct_repositories': 8, 'development_repositories_excluded': 4, 'authored_audits': 2,
        'public_reference_tests': sum(len(case.truth.fail_to_pass) + len(case.truth.pass_to_pass) for case in cases),
        'free_bytes': free, 'reserve_bytes': 50 * 1024**3, 'external_code_executed': False,
        'containers_started': 0, 'models': 0, 'cases_adopted': 0, 'stage_assignment_frozen': False}
    with (HERE / 'operation-review.json').open('x') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    (HERE / 'preparation-checks.json').write_text(json.dumps(static, indent=2) + '\n')
    print(json.dumps({'review_sha256': sha(HERE / 'operation-review.json'), **static}))


if __name__ == '__main__':
    asyncio.run(main())
