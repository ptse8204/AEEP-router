"""Bind one exact finite source reproduction batch; never execute the subjects."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentScopeAmendment, AssessmentSubject, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest
from classify import self_check

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
PARENT = HERE / 'parent-runtime-review.json'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not (HERE / 'operation-review.json').exists()
    parent = json.loads(PARENT.read_text())
    before = RecipeMaterializationRequest.model_validate(parent['request'])
    stability = json.loads((HERE / 'validation/source-stability.json').read_text())
    assert stability['all_passed'] and stability['source_unchanged']
    assert stability['source_digest'] == verification_source_digest(ROOT) == parent['source_digest']
    assert runtime_dependencies() == before.runtime_dependencies
    free = shutil.disk_usage(ROOT).free
    assert free > 50 * 1024**3 + 20 * 1024**2
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect', parent['image'], '--format', '{{.Id}}'], timeout=20).decode().strip() == parent['image']
    prior = HERE.parent / 'repository-replacement-runtime-20261022/runtime-execution/completion-audit.json'
    audit = json.loads(prior.read_text())
    assert audit['all_owned_containers_absent'] and audit['physical_receipt_integrity_passed']
    for probe in parent['probes']:
        assert hashlib.sha256(json.dumps(probe['payload'], separators=(',', ':')).encode()).hexdigest() == probe['payload_sha256']
    assert len(parent['probes']) == 3
    prepared = json.loads((HERE / 'prepared-cases.json').read_text())
    assert prepared['prepared_cases'] == 5 and not prepared['errors']
    cases_path, variants_path = ROOT / prepared['cases_file'], ROOT / prepared['variants_file']
    assert sha(cases_path) == prepared['cases_file_sha256']
    cases = [RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants = json.loads(variants_path.read_text())
    assert len(cases) == 5 and len(variants) == 19
    assert len({x.source_repository.casefold() for x in cases}) == 2
    assert len({(x.source_repository.casefold(), x.source_revision) for x in cases}) == 5
    assert len({x.input.source_sha256 for x in cases}) == 5
    excluded = {x['repository'].casefold() for x in json.loads((HERE.parent / 'repository-declared-tests-20261022/composed-screening-reproduction.json').read_text())['cases']}
    excluded |= {'https://github.com/delgan/loguru', 'https://github.com/pallets/click', 'https://github.com/marshmallow-code/marshmallow', 'https://github.com/pgmpy/pgmpy'}
    assert not {x.source_repository.casefold() for x in cases} & excluded
    assets = {str(path.resolve()): sha(path) for path in [cases_path, variants_path, prior, *(HERE / name for name in ('prepared-cases.json', 'source-review.json', 'source-data-audit-v2.json', 'source-scope-review.json', 'git-tree-source-scopes.json', 'pure-wheel-review.json', 'run.py', 'classify.py', 'audit-execution.py', 'validation/source-stability.json'))]}
    expectations, labels, guard_count = {}, {}, 0
    for case, description in zip(cases, prepared['cases'], strict=True):
        assert case.input.task_id == description['id']
        for item in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            item.read()
            assets[item.path] = item.sha256
        row_path = ROOT / description['source_record'] / 'row.json'
        assets[str(row_path.resolve())] = sha(row_path)
        row = json.loads(row_path.read_text())
        for record in description['license_records']:
            p = ROOT / record['path']
            assert sha(p) == record['sha256']
            assets[str(p.resolve())] = record['sha256']
        required = case.truth.fail_to_pass + case.truth.pass_to_pass
        statuses = {n: 'FAILED' for n in row['FAIL_TO_PASS']}
        statuses.update({n: 'PASSED' for n in row['PASS_TO_PASS']})
        if case.origin_kind == 'authored_control':
            statuses['tests/test_aeep_preservation.py::test_snapshot_preserved'] = 'FAILED'
        assert set(statuses) == set(required)
        positive = {'exit_code': 0, 'valid': True, 'detail': '', 'statuses': {n: 'PASSED' for n in required}, 'required_identities': required}
        negative = {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': statuses, 'required_identities': required}
        partial = {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': {}, 'at_least_one_failed': required, 'required_identities': required}
        labels[case.input.task_id] = [v['variant'] for v in variants if v['case'] == case.input.task_id]
        expectations[case.input.task_id] = {label: positive if label == 'reference' else negative if label == 'counterexample' else partial for label in labels[case.input.task_id]}
        for variant in [v for v in variants if v['case'] == case.input.task_id]:
            payload_path = ROOT / variant['payload']
            assert payload_path.stat().st_size == variant['bytes'] and sha(payload_path) == variant['sha256']
            assets[str(payload_path.resolve())] = variant['sha256']
            captured = []
            class Captured(Exception):
                pass
            async def capture(payload):
                captured.append(hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest())
                raise Captured()
            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), variant['artifact'], capture)
            except Captured:
                pass
            else:
                raise AssertionError('Static payload verification returned a grade')
            assert captured == [variant['sha256']]
        # Exercise actual first-party grader acceptance/rejection without running external pytest/repository code.
        good_artifact = next(v['artifact'] for v in variants if v['case'] == case.input.task_id and v['variant'] == 'reference')
        for kind in ('pass', 'exit', 'missing', 'error', 'skip'):
            async def fake(payload):
                observed = {n: 'PASSED' for n in required}
                if kind == 'missing':
                    observed.pop(required[0])
                if kind in ('error', 'skip'):
                    observed[required[0]] = 'ERROR' if kind == 'error' else 'SKIPPED'
                return {'exit_code': 1 if kind == 'exit' else 0, 'statuses': observed, 'archive_sha256': payload['archive_sha256'], 'python': payload['python'], 'pytest': payload['pytest']}
            grade = await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), good_artifact, fake)
            assert grade.valid == (kind == 'pass')
            guard_count += 1
    subject = AssessmentSubject(kind='command', location=str(cases_path.parent.resolve()), dependency_digests=assets,
        description='Five compact-transport source/runtime cases, including a previously oversized three-file SQL repair, plus three mandatory fresh containment/state/runtime probes; no model or adopted campaign.')
    request = RecipeMaterializationRequest(schema_version=before.schema_version, subject_digest=content_digest(subject), recipe_digest=before.recipe_digest, mapping_digest=before.mapping_digest, environment_digest=before.environment_digest,
        authorization_id='onboarding', seed=61, definition_digests=before.definition_digests, runtime_dependencies=before.runtime_dependencies)
    documents = {k: x for k, x in parent['documents'].items() if x['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')} for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe_materialization_request', request.plan_id, request)]}
    documents.update(new)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=parent['authorization_digest'], subject_digests=[content_digest(subject)], recipe_digests=[before.recipe_digest], environment_digests=[before.environment_digest], reviewed_digests=list(documents))
    review = {'purpose': 'One fresh current-source compact-transport check: three containment/state/runtime probes and nineteen exact case variants from five task origins/two repositories; no model or stage adoption.',
        'source_digest': parent['source_digest'], 'parent_review': str(PARENT.relative_to(ROOT)), 'parent_review_sha256': sha(PARENT), 'authorization_digest': parent['authorization_digest'],
        'assets': assets, 'cases_file': str(cases_path.relative_to(ROOT)), 'variants_file': str(variants_path.relative_to(ROOT)), 'active_case_ids': [c.input.task_id for c in cases],
        'case_summary': prepared['cases'], 'variant_labels': labels, 'expectations': expectations, 'driver_files': {n: sha(HERE / n) for n in ('run.py', 'classify.py', 'audit-execution.py')},
        'request': request.model_dump(mode='json'), 'new_documents': new, 'reviewed_document_digests': list(documents), 'amendment': amendment.model_dump(mode='json'),
        'image': parent['image'], 'environment_digest': before.environment_digest, 'maximum_contained_calls': 22, 'maximum_operations': 24, 'maximum_reserved_seconds': 920,
        'maximum_model_turns': 0, 'cash_usd': 0, 'probes': parent['probes'], 'automatic_retry': False,
        'fresh_containment': {'source_digest': parent['source_digest'], 'image': parent['image'], 'required_probes': 3, 'old_conformance_transferred': False},
        'permissions': ['At most22 offline calls:3 mandatory boundary/state/runtime probes,4 SQL reference/original pairs,9 per-file SQL regressions,and1 Circuitbreaker reference/original pair. At most24 existing-grant operations/920 reserved seconds. No counter reset or refund.',
            'Use the existing image and four unchanged core pytest wheels; Circuitbreaker also uses the exact cached pytest-asyncio1.2.0 wheel and explicitly declares the already installed pytest_mock plugin. No new software bytes beyond the separately bound current first-party source and case artifacts.',
            'No models, downloads, image changes/builds/pulls, installers, services, credentials, cash, package/docs execution, activation, release or retained-resource cleanup. Remove only new attempt-owned containers.'],
        'failure_handling': 'One batch, no automatic replay. Skip later variants for a case after reference/protocol/counterexample failure. Continue independent cases only after canonical completion/accounting/cleanup verification; stop dispatch on common binding/authority/receipt/accounting/lifecycle uncertainty. Retain bounded raw observations before protocol validation and preserve all charges.',
        'partial_repair_criterion': 'Each regressed executable source file must produce invalid/test_failure at exit1 with every declared identity observed as PASSED or FAILED and at least one failure. A preservation regression also establishes a rejected partial repair; it cannot pass the grader or relax original/reference requirements.',
        'limitations': ['Current-source engineering/runtime conformance only; no model qualification, useful-selection evidence, resource acceptance or full8/28/105 cohort.',
            'The v3 format uses bounded standard-library gzip over replacement-file JSON. It adds no parser/executable/dependency; legacy v1/v2 contracts retain exact recipe digests. Source/runtime measurements do not imply token/time/cash savings.',
            'Existing task assertions stay unchanged and declared-node selectors compose prior hooks. SQL5256 retains its earlier successful v1 observations; the separate v3 check cannot rewrite them. Earlier Circuitbreaker fixture errors remain failed; exact exception was not retained.',
            'All new source-bound probes must pass before any subject call. No old-source containment, installed-wheel or docs evidence transfers automatically.'],
        'approval_reason': 'The pasted continuation excludes untrusted software execution; CONTINUATION.md requires applicable container-provisioning authority. Terminalab120327 covers different source and artifacts and cannot authorize these new repository/test/wheel bytes. Finite definition review uses standing delegation; no architecture decision is needed.'}
    with (HERE / 'operation-review.json').open('x') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    checks = {'passed': True, 'source_unchanged': True, 'existing_image_verified': True, 'cases': len(cases), 'distinct_repositories': 2, 'payloads': len(variants), 'assets': len(assets),
              'classifier_checks': self_check(), 'actual_first_party_grader_guard_cases': guard_count, 'maximum_payload_bytes': max(v['bytes'] for v in variants), 'free_bytes': free,
              'review_sha256': sha(HERE / 'operation-review.json'), 'external_code_executed': False, 'model_turns': 0, 'cases_adopted': 0}
    (HERE / 'static-audit.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps(checks))


if __name__ == '__main__':
    asyncio.run(main())
