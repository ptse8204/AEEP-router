"""Freeze two unexecuted audits for the retained runtime; no installer or model."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentScopeAmendment, AssessmentSubject,
    RecipeMaterializationRequest, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OUT = HERE / 'runtime-execution'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not (OUT / 'operation-review.json').exists()
    parent_path = HERE / 'observer-envelope.json'; parent = json.loads(parent_path.read_text())
    before = RecipeMaterializationRequest.model_validate(parent['request'])
    assert verification_source_digest(ROOT) == parent['source_digest']
    assert runtime_dependencies() == before.runtime_dependencies
    assert shutil.disk_usage(ROOT).free > 50 * 1024 ** 3
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        parent['image'], '--format', '{{.Id}}'], text=True, timeout=20).strip() == parent['image']
    previous_audit = HERE.parent / 'repository-supported-suites-20261027/runtime-execution/completion-audit.json'
    audit = json.loads(previous_audit.read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    metadata = json.loads((HERE / 'prepared-cases.json').read_text())
    assert metadata['prepared_cases'] == 2 and not metadata['errors']
    cases_path = ROOT / metadata['cases_file']; variants_path = ROOT / metadata['variants_file']
    assert sha(cases_path) == metadata['cases_file_sha256']
    cases = [RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants = json.loads(variants_path.read_text()); assert len(variants) == 4
    assert all(c.origin_kind == 'authored_control' and c.input.family == 'contract-audit' for c in cases)
    assets = {str(p.resolve()): sha(p) for p in [parent_path, cases_path, variants_path, previous_audit,
        HERE / 'prepared-cases.json', HERE / 'pure-wheel-review.json', HERE / 'review-budget.py',
        HERE / 'source-review.json', HERE / 'prepare-cases.py', HERE / 'prepare-review.py',
        *(OUT / n for n in ('run.py', 'audit-execution.py', 'classify.py'))]}
    labels, expectations, checks = {}, {}, 0
    for case, description in zip(cases, metadata['cases'], strict=True):
        assert case.input.task_id == description['id']
        row_path = ROOT / description['source_record'] / 'row.json'; row = json.loads(row_path.read_text())
        assets[str(row_path.resolve())] = sha(row_path)
        for item in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            item.read(); assets[item.path] = item.sha256
        for license in description['license_records']:
            path = ROOT / license['path']; assert sha(path) == license['sha256']; assets[str(path.resolve())] = sha(path)
        required = case.truth.fail_to_pass + case.truth.pass_to_pass
        negative = {n: 'FAILED' for n in row['FAIL_TO_PASS']}
        negative.update({n: 'PASSED' for n in row['PASS_TO_PASS']})
        negative['tests/test_aeep_preservation.py::test_snapshot_preserved'] = 'FAILED'
        assert set(negative) == set(required)
        labels[case.input.task_id] = ['reference', 'counterexample']
        expectations[case.input.task_id] = {
            'reference': {'exit_code': 0, 'valid': True, 'detail': '', 'statuses': {n: 'PASSED' for n in required}, 'required_identities': required},
            'counterexample': {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': negative, 'required_identities': required}}
        own = [v for v in variants if v['case'] == case.input.task_id]
        assert [v['variant'] for v in own] == labels[case.input.task_id]
        for variant in own:
            path = ROOT / variant['payload']; assert sha(path) == variant['sha256']; assets[str(path.resolve())] = sha(path)
            class Captured(Exception):
                pass
            captured = []
            async def capture(payload):
                captured.append(hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest())
                raise Captured()
            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), variant['artifact'], capture)
            except Captured:
                pass
            assert captured == [variant['sha256']]
        for kind in ('pass', 'exit', 'missing', 'error', 'skip'):
            async def fake(payload):
                statuses = {n: 'PASSED' for n in required}
                if kind == 'missing': statuses.pop(required[0])
                if kind in ('error', 'skip'): statuses[required[0]] = 'ERROR' if kind == 'error' else 'SKIPPED'
                return {'exit_code': 1 if kind == 'exit' else 0, 'statuses': statuses,
                    'archive_sha256': payload['archive_sha256'], 'python': payload['python'], 'pytest': payload['pytest']}
            grade = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), own[0]['artifact'], fake)
            assert grade.valid == (kind == 'pass'); checks += 1
    for n in ['prepare-cases.py', 'prepare-review.py', 'runtime-execution/run.py', 'runtime-execution/audit-execution.py']:
        ast.parse((HERE / n).read_text())
    classifier_spec = importlib.util.spec_from_file_location('existing_reproduction_classifier', OUT / 'classify.py')
    classifier = importlib.util.module_from_spec(classifier_spec); classifier_spec.loader.exec_module(classifier)
    budget_spec = importlib.util.spec_from_file_location('existing_review_budget', HERE / 'review-budget.py')
    budget = importlib.util.module_from_spec(budget_spec); budget_spec.loader.exec_module(budget)
    subject = AssessmentSubject(kind='command', location=str(cases_path.parent), dependency_digests=assets,
        description='Two authored public corrected-snapshot audits; no new dependency installation, model or stage adoption.')
    request = RecipeMaterializationRequest(schema_version=before.schema_version,
        subject_digest=content_digest(subject), recipe_digest=before.recipe_digest, mapping_digest=before.mapping_digest,
        environment_digest=before.environment_digest, authorization_id='onboarding', seed=86,
        definition_digests=before.definition_digests, runtime_dependencies=before.runtime_dependencies)
    documents = {k: v for k, v in parent['documents'].items() if v['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new = {}
    for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe_materialization_request', request.plan_id, request)]:
        new[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    documents.update(new)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[before.recipe_digest],
        environment_digests=[before.environment_digest], reviewed_digests=list(documents))
    review = {'purpose': 'Two authored current-snapshot audits, each checked against its original-source regression; no model evidence.',
        'parent_review': str(parent_path.relative_to(ROOT)), 'parent_review_sha256': sha(parent_path),
        'source_digest': parent['source_digest'], 'authorization_digest': parent['authorization_digest'],
        'assets': assets, 'cases_file': metadata['cases_file'], 'variants_file': metadata['variants_file'],
        'active_case_ids': [c.input.task_id for c in cases], 'variant_labels': labels, 'expectations': expectations,
        'probes': [], 'request': request.model_dump(mode='json'), 'new_documents': new,
        'reviewed_document_digests': list(documents), 'amendment': amendment.model_dump(mode='json'),
        'driver_files': {n: sha(OUT / n) for n in ('run.py', 'audit-execution.py', 'classify.py')},
        'maximum_contained_calls': 4, 'maximum_operations': 6, 'maximum_reserved_seconds': 290,
        'maximum_model_turns': 0, 'cash_usd': 0, 'automatic_retry': False,
        'retained_image': parent['image'], 'applicable_containment_audit': str(previous_audit.relative_to(ROOT)),
        'permissions': ['At most4 offline contained reference/regression observations for CrossGL257 and Marshmallow-SQLAlchemy640, two explicitly authored corrected-snapshot audits. Keep all71 original identities plus two byte-preservation guards.',
            'Reuse exact retainedf60342e9 image, existing reviewed observer/service/accounting and applicable completed containment evidence. Load the already-cached pure Marshmallow3.25.1 wheel privately for conversion tests. No project installer, package installation, new dependency or download.',
            'At most6 existing-grant operations/290 reserved seconds:30 setup +120 analysis +4 times35. Hard review budget checked before every reservation. No model turns or cash.',
            'Reference must pass all required identities; original-source regression must be rejected with the declared preserved-test results. Isolated incompatibility excludes a case only after completed canonical accounting and verified cleanup; common uncertainty stops dispatch.',
            'No automatic retry or reuse of unstarted slots. Keep all images, volumes, historical evidence and charges. Remove only new attempt-owned containers. No fresh probes or host canaries.',
            'No builds/pulls, installs, downloads, credentials, new external services/destinations, model disclosure, package/docs reruns, host configuration, activation, publication or release.'],
        'limits': ['Reproduction is not qualification, usefulness, selection, arbitrary repository preservation or an official upstream benchmark result. No case is adopted or stage frozen.',
            'Marshmallow-SQLAlchemy selected conversion tests, package imports and conftest use no pytest-lazy-fixtures plugin. That optional dependency belongs to other modules, is not loaded and is not installed. SQLAlchemy2.0.44 stays in the exact inherited image.',
            'CrossGL uses its source package and Python standard library. Packaging setup.py is not executed.',
            'C++ hooks142 is excluded because required tests can invoke real pip. No fixture/assertion is removed to avoid that boundary. The four unresolved diagnostics remain excluded and are not replayed.'],
        'approval_reason': 'The continuation reserves new untrusted source execution; CONTINUATION.md requires applicable provisioning authority. Terminalfaa10772 covers different diagnostic programs and binds no new audits. Routine finite preparation is delegated; actual exact execution needs approval. No architecture, budget or infrastructure decision is needed.'}
    with (OUT / 'operation-review.json').open('x') as stream:
        json.dump(review, stream, indent=2); stream.write('\n')
    output = {'prepared_only': True, 'review_sha256': sha(OUT / 'operation-review.json'), 'assets': len(assets),
        'cases': 2, 'payloads': 4, 'required_identities': sum(len(c.truth.pass_to_pass) for c in cases),
        'grader_guards': checks, 'classifier_guards': classifier.self_check(), 'budget_guards': budget.self_check(),
        'source_unchanged': True, 'new_installs': 0, 'new_models': 0, 'subject_execution': False}
    assert output['required_identities'] == 73
    (HERE / 'preparation-checks.json').write_text(json.dumps(output, indent=2) + '\n')
    print(json.dumps(output))


if __name__ == '__main__':
    asyncio.run(main())
