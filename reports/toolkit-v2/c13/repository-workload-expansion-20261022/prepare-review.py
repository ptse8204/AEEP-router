"""Prepare a finite image/dependency review; never build, install or run subjects."""
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

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PARENT = HERE.parent / 'repository-suite-integration-20261022/grader-operation-review.json'
PRIOR = HERE.parent / 'repository-screening-curation-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not (HERE / 'approval-bundle.json').exists()
    parent = json.loads(PARENT.read_text())
    assert verification_source_digest(ROOT) == parent['source_digest']
    assert runtime_dependencies() == parent['request']['runtime_dependencies']
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 128 * 1024**2
    previous_audit = json.loads((PRIOR / 'completion-audit.json').read_text())
    assert previous_audit['physical_receipt_integrity_passed'] and len(previous_audit['eligible_cases']) == 6
    metadata = json.loads((HERE / 'prepared-cases.json').read_text())
    assert metadata['prepared_cases'] == 2 and not metadata['errors']
    cases_path, variants_path = ROOT / metadata['cases_file'], ROOT / metadata['variants_file']
    cases = [RepositorySuiteCase.model_validate(item) for item in json.loads(cases_path.read_text())]
    variants = json.loads(variants_path.read_text())
    assert len(variants) == 4 and {case.input.family for case in cases} == {'multi-file-repair', 'contract-audit'}
    assert all(case.split == 'qualification' and not case.used_for_development for case in cases)
    previous_repositories = {item['repository'].casefold() for item in json.loads((PRIOR / 'prepared-cases.json').read_text())['cases']}
    development = {'delgan/loguru', 'pallets/click', 'marshmallow-code/marshmallow', 'pgmpy/pgmpy'}
    assert not {case.source_repository.casefold().removeprefix('https://github.com/') for case in cases} & (previous_repositories | development)
    wheel = json.loads((HERE / 'image-runtime-wheel-review.json').read_text())[0]
    assert wheel['project'] == 'setuptools' and wheel['version'] == '75.8.2'
    wheel_path = ROOT / wheel['private_cache']
    assert sha(wheel_path) == wheel['sha256']
    context = ROOT / '.aeep/repository-workload-expansion-20261022-image-context'
    context.mkdir(exist_ok=False)
    shutil.copyfile(wheel_path, context / wheel['filename'])
    requirements = '/opt/aeep-runtime/' + wheel['filename'] + ' --hash=sha256:' + wheel['sha256'] + '\n'
    (context / 'requirements.txt').write_text(requirements)
    dockerfile = ('FROM aeep-assessment-runtime:0.8\nUSER 0:0\nCOPY ' + wheel['filename'] +
        ' requirements.txt /opt/aeep-runtime/\n' +
        'RUN ["python3", "-m", "pip", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\n' +
        'USER 65534:65534\n')
    (context / 'Dockerfile').write_text(dockerfile)
    for path in context.iterdir():
        path.chmod(0o644)
    reference = subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        'aeep-assessment-runtime:0.8'], timeout=20)
    state = json.loads(reference)[0]
    assert state['Id'] == parent['image'] and state['Config'].get('OnBuild') in (None, [])
    (HERE / 'parent-image-inspection.json').write_bytes(reference)
    assets = {str(path.resolve()): sha(path) for path in [cases_path, variants_path, HERE / 'prepared-cases.json',
        HERE / 'source-review.json', HERE / 'audit-source-review.json', HERE / 'image-runtime-wheel-review.json',
        HERE / 'parent-image-inspection.json', PRIOR / 'completion-audit.json', *context.iterdir(),
        HERE / 'run-bundle.py', HERE / 'derive-execution.py', HERE / 'runtime-execution/run.py',
        HERE / 'runtime-execution/classify.py', HERE / 'runtime-execution/audit-execution.py']}
    records = {item['instance_id']: item for file in ('source-review.json', 'audit-source-review.json')
               for item in json.loads((HERE / file).read_text())['sources']}
    expectations = {}
    for case, description in zip(cases, metadata['cases'], strict=True):
        for asset in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            asset.read()
            assets[asset.path] = asset.sha256
        row_path = ROOT / records[description['original_issue_id']]['private_cache'] / 'row.json'
        row = json.loads(row_path.read_text())
        assets[str(row_path.resolve())] = sha(row_path)
        baseline = {key: 'FAILED' for key in row['FAIL_TO_PASS']}
        baseline.update({key: 'PASSED' for key in row['PASS_TO_PASS']})
        if case.origin_kind == 'authored_control':
            baseline['tests/test_aeep_preservation.py::test_snapshot_preserved'] = 'FAILED'
        required = case.truth.fail_to_pass + case.truth.pass_to_pass
        assert set(baseline) == set(required)
        expectations[case.input.task_id] = {
            'reference': {'exit_code': 0, 'valid': True, 'detail': '', 'statuses': {key: 'PASSED' for key in required}},
            'counterexample': {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': baseline}}
        for staged in (item for item in variants if item['case'] == case.input.task_id):
            path = ROOT / staged['payload']
            assert sha(path) == staged['sha256']
            assets[str(path.resolve())] = staged['sha256']

            class Captured(Exception):
                pass

            async def capture(payload):
                assert hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest() == staged['sha256']
                raise Captured()

            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), staged['artifact'], capture)
            except Captured:
                pass
            else:
                raise AssertionError('Preparation returned a grade')
    for name in ('run-bundle.py', 'derive-execution.py', 'runtime-execution/run.py', 'runtime-execution/audit-execution.py'):
        ast.parse((HERE / name).read_text())
    subject = AssessmentSubject(kind='command', location=str(context.resolve()), dependency_digests=assets,
        description='One offline exact-wheel image build and deterministic derived runtime review for three probes and two replacement cases.')
    before = RecipeMaterializationRequest.model_validate(parent['request'])
    request = RecipeMaterializationRequest(schema_version=before.schema_version, subject_digest=content_digest(subject),
        recipe_digest=before.recipe_digest, mapping_digest=before.mapping_digest, environment_digest=before.environment_digest,
        authorization_id='onboarding', seed=46, definition_digests=before.definition_digests, runtime_dependencies=before.runtime_dependencies)
    docs = {key: item for key, item in parent['documents'].items() if item['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    for kind, identity, value in [('subject', subject.subject_id, subject), ('recipe_materialization_request', request.plan_id, request)]:
        docs[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[before.recipe_digest], environment_digests=[before.environment_digest],
        reviewed_digests=list(docs))
    review = {'purpose': 'Fill the missing multi-file and authored audit screening slots through proper shared runtime reproduction. No campaign/model execution.',
        'source_digest': parent['source_digest'], 'parent_review': str(PARENT.relative_to(ROOT)), 'parent_review_sha256': sha(PARENT),
        'authorization_digest': parent['authorization_digest'], 'assets': assets, 'cases_file': metadata['cases_file'],
        'variants_file': metadata['variants_file'], 'active_case_ids': [case.input.task_id for case in cases],
        'case_summary': metadata['cases'], 'expectations': expectations,
        'parent_reference': 'aeep-assessment-runtime:0.8', 'parent_image': parent['image'],
        'target_tag': 'aeep-toolkit-v2/repository-grader:py313-setuptools-20261022', 'build_context': str(context.relative_to(ROOT)),
        'context_files': sorted(path.name for path in context.iterdir()), 'build_request': request.model_dump(mode='json'),
        'build_documents': docs, 'build_amendment': amendment.model_dump(mode='json'), 'host_canary': parent['host_canary'],
        'maximum_builds': 1, 'maximum_build_growth_bytes': 128 * 1024**2, 'maximum_contained_calls': 7,
        'maximum_operations': 10, 'maximum_reserved_seconds': 575, 'maximum_model_turns': 0, 'cash_usd': 0,
        'automatic_retry': False, 'runtime_dependency': wheel,
        'permissions': ['One local build from the verified existing local tag/image, network disabled and pulls disabled. Install exactly one cached hashed Setuptools75.8.2 wheel with no dependency resolution or host installation.',
            'Keep original image/configuration/layers. Verify exact inherited execution config and parent filesystem prefix, exactly two new layers and at most128MiB image growth; retain the new tagged image for remaining work.',
            'Derive and save only a new image-bound environment and finite request/amendment under standing definition authority. Bind the actual output image digest before any contained call. Parent approval covers only this deterministic derived review, not arbitrary new definitions.',
            'Run three fresh containment/state probes before at most four reference/counterexample calls. Stop common uncertainty; independently exclude nonreproducible cases without retry.',
            'Retain bounded raw replies, canonical receipts/attempts/ledgers and failures. Create/remove only the unchanged named nonsecret host canary and attempt-owned containers.',
            'No models, downloads, other packages, image pulls, package-wheel/doc checker reruns, credentials, new destinations, cash, activation, release, historical replay or retained-image deletion.'],
        'limitations': ['Six earlier cases have runtime reproduction evidence only; no model qualification or value evidence transfers to this changed image.',
            'Py3status LICENSE is BSD-3-Clause text despite its pyproject BSD-2-Clause metadata. Preserve actual license text and the discrepancy.',
            'Setuptools own license is MIT; bundled licenses include LGPL-3.0, Apache-2.0, BSD and PSF terms. Preserve all19 embedded license records. This local test does not authorize redistribution/release.',
            'The current source/archive bounds and optional plugin-autoload restriction are unchanged. Broader compiled/plugin runtimes and full141-case feasibility remain unverified.',
            'If both new cases reproduce, the eight candidates can meet3/3/2 screening family counts, but final8/28/105 freeze and qualification remain separate.'],
        'approval_reason': 'New exact dependency installation/image provisioning and third-party source/tests exceed the terminal eight-case approval and the user continuation excludes untrusted installation/execution. No architecture decision is needed.'}
    spec = importlib.util.spec_from_file_location('frozen_classifier', HERE / 'runtime-execution/classify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = {'passed': True, 'source_unchanged': True, 'cases': 2, 'payloads_verified': 4, 'assets_verified': len(assets),
        'classifier_checks_passed': module.self_check(), 'driver_syntax_passed': True, 'image_parent_present': True,
        'build_context_files': sorted(path.name for path in context.iterdir()), 'new_installs_or_builds': 0,
        'external_source_executed': False, 'new_models': 0, 'case_reference_required_tests': sum(len(case.truth.fail_to_pass + case.truth.pass_to_pass) for case in cases)}
    with (HERE / 'approval-bundle.json').open('x') as stream:
        json.dump(review, stream, indent=2)
        stream.write('\n')
    (HERE / 'preparation-checks.json').write_text(json.dumps(checks, indent=2) + '\n')
    print(json.dumps({'review_sha256': sha(HERE / 'approval-bundle.json'), **checks}))


if __name__ == '__main__':
    asyncio.run(main())
