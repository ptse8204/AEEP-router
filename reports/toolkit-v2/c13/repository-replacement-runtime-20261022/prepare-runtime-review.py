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
PARENT = HERE / 'observer-envelope.json'
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
    metadata = json.loads((HERE / 'prepared-plugin-cases.json').read_text())
    assert metadata['prepared_cases'] == 8 and not metadata['errors']
    cases_path, variants_path = ROOT / metadata['cases_file'], ROOT / metadata['variants_file']
    cases = [RepositorySuiteCase.model_validate(item) for item in json.loads(cases_path.read_text())]
    variants = json.loads(variants_path.read_text())
    assert len(variants) == 22 and {case.input.family for case in cases} == {'single-file-repair', 'multi-file-repair', 'contract-audit'}
    assert all(case.split == 'qualification' and not case.used_for_development for case in cases)
    previous_repositories = {item['repository'].casefold() for item in json.loads((PRIOR / 'prepared-cases.json').read_text())['cases']}
    development = {'delgan/loguru', 'pallets/click', 'marshmallow-code/marshmallow', 'pgmpy/pgmpy'}
    assert not {case.source_repository.casefold().removeprefix('https://github.com/') for case in cases} & development
    assert len({case.source_repository.casefold() for case in cases}) == 8
    closure = json.loads((HERE / 'runtime-wheel-review.json').read_text())
    assert closure['complete_static_dependency_closure'] and len(closure['pins']) == 25
    context = ROOT / '.aeep/repository-replacement-runtime-20261022-image-context-v4'
    context.mkdir(exist_ok=False)
    for wheel in closure['pins']:
        wheel_path = ROOT / wheel['private_cache']
        assert sha(wheel_path) == wheel['sha256']
        shutil.copyfile(wheel_path, context / wheel['filename'])
    requirements = ''.join('/opt/aeep-runtime/' + wheel['filename'] + ' --hash=sha256:' + wheel['sha256'] + '\n' for wheel in closure['pins'])
    (context / 'requirements.txt').write_text(requirements)
    dockerfile = ('FROM aeep-assessment-runtime:0.8\nUSER 0:0\nCOPY ' + ' '.join(wheel['filename'] for wheel in closure['pins']) +
        ' requirements.txt /opt/aeep-runtime/\n' +
        'RUN ["python3", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\n' +
        'USER 65534:65534\n')
    (context / 'Dockerfile').write_text(dockerfile)
    for path in context.iterdir():
        path.chmod(0o644)
    reference = subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        'aeep-assessment-runtime:0.8'], timeout=20)
    state = json.loads(reference)[0]
    assert state['Id'] == parent['image'] and state['Config'].get('OnBuild') in (None, [])
    (HERE / 'parent-image-inspection.json').write_bytes(reference)
    assets = {str(path.resolve()): sha(path) for path in [cases_path, variants_path, HERE / 'prepared-plugin-cases.json',
        HERE / 'source-review.json', HERE / 'audit-source-review.json', HERE / 'runtime-wheel-review.json',
        HERE / 'parent-image-inspection.json', PRIOR / 'completion-audit.json', *context.iterdir(),
        HERE / 'run-bundle.py', HERE / 'derive-execution.py', HERE / 'runtime-execution/run.py',
        HERE / 'runtime-execution/classify.py', HERE / 'runtime-execution/audit-execution.py']}
    for path in (HERE / 'licenses').rglob('*'):
        if path.is_file(): assets[str(path.resolve())] = sha(path)
    family_audit = HERE.parent / 'repository-workload-expansion-20261022/source-family-audit.json'
    assets[str(family_audit.resolve())] = sha(family_audit)
    for name in ('diagnostic-source-scope-review.json','diagnostic-prepared-source-review.json',
            'current-case-family-audit.json','runtime-operation-resource-bound.json','prepared-additional-cases.json'):
        assets[str((HERE/name).resolve())]=sha(HERE/name)
    records = {item['instance_id']: item for file in ('source-review.json', 'audit-source-review.json')
               for item in json.loads((HERE / file).read_text())['sources']}
    records.update({item['instance_id']:item for item in json.loads((HERE / 'diagnostic-prepared-source-review.json').read_text())['sources']})
    old_expectations = json.loads((PRIOR / 'operation-review.json').read_text())['expectations']
    expectations = {}
    for case, description in zip(cases, metadata['cases'], strict=True):
        for asset in (case.truth.source, case.truth.tests, case.reference, *case.truth.wheels):
            asset.read()
            assets[asset.path] = asset.sha256
        if case.input.task_id in old_expectations:
            expectations[case.input.task_id] = old_expectations[case.input.task_id]
            for staged in (item for item in variants if item['case'] == case.input.task_id):
                path = ROOT / staged['payload']
                assert sha(path) == staged['sha256']
                assets[str(path.resolve())] = staged['sha256']
            continue
        row_path = ROOT / records[description['original_issue_id']]['private_cache'] / 'row.json'
        row = json.loads(row_path.read_text())
        assets[str(row_path.resolve())] = sha(row_path)
        baseline = {key: 'FAILED' for key in case.truth.fail_to_pass}
        baseline.update({key: 'PASSED' for key in case.truth.pass_to_pass})
        if case.origin_kind == 'authored_control':
            baseline.update({key:'FAILED' for key in row['FAIL_TO_PASS']})
            baseline['tests/test_aeep_preservation.py::test_snapshot_preserved'] = 'FAILED'
        required = case.truth.fail_to_pass + case.truth.pass_to_pass
        assert set(baseline) == set(required)
        expectations[case.input.task_id] = {
            'reference': {'exit_code': 0, 'valid': True, 'detail': '', 'statuses': {key: 'PASSED' for key in required}},
            'counterexample': {'exit_code': 1, 'valid': False, 'detail': 'test_failure', 'statuses': baseline}}
        for item in (value for value in variants if value['case']==case.input.task_id and value['variant'].startswith('partial-')):
            expectations[case.input.task_id][item['variant']]={'exit_code':1,'valid':False,'detail':'test_failure',
                'statuses':{key:'PASSED' for key in case.truth.pass_to_pass},'at_least_one_failed':case.truth.fail_to_pass}
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
        description='One offline exact-wheel image build and deterministic derived runtime review for three probes and eight provisional cases.')
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
    review = {'purpose': 'Check all eight provisional screening workloads on one new explicit-plugin runtime, including two replacements. No campaign/model execution.',
        'source_digest': parent['source_digest'], 'parent_review': str(PARENT.relative_to(ROOT)), 'parent_review_sha256': sha(PARENT),
        'authorization_digest': parent['authorization_digest'], 'assets': assets, 'cases_file': metadata['cases_file'],
        'variants_file': metadata['variants_file'], 'active_case_ids': [case.input.task_id for case in cases],
        'case_summary': metadata['cases'], 'expectations': expectations,
        'variant_labels':{case.input.task_id:[item['variant'] for item in variants if item['case']==case.input.task_id] for case in cases},
        'parent_reference': 'aeep-assessment-runtime:0.8', 'parent_image': parent['image'],
        'target_tag': 'aeep-toolkit-v2/repository-grader:py313-explicit-plugins-20261022', 'build_context': str(context.relative_to(ROOT)),
        'context_files': sorted(path.name for path in context.iterdir()), 'build_request': request.model_dump(mode='json'),
        'build_documents': docs, 'build_amendment': amendment.model_dump(mode='json'), 'host_canary': parent['host_canary'],
        'maximum_builds': 1, 'maximum_build_growth_bytes': 192 * 1024**2, 'maximum_contained_calls': 25,
        'maximum_operations': 28, 'maximum_reserved_seconds': 1205, 'maximum_model_turns': 0, 'cash_usd': 0,
        'automatic_retry': False, 'runtime_dependencies_review': closure,
        'permissions': ['One local build from the verified existing local tag/image, network disabled and pulls disabled. Install exactly the25 cached hashed wheels with no dependency resolution or host installation. Setuptools is not included.',
            'Keep original image/configuration/layers. Verify exact inherited execution config and parent filesystem prefix, exactly two new layers and at most192MiB image growth; retain the new tagged image for remaining work. This is an operation safety cap, not a product resource acceptance target.',
            'Derive and save only a new image-bound environment and finite request/amendment under standing definition authority. Bind the actual output image digest before any contained call. Parent approval covers only this deterministic derived review, not arbitrary new definitions.',
            'Run three fresh containment/state probes, including pinned runtime imports and the actual mocker fixture, before at most22 source observations. Eight reference/original-or-counterexample pairs and six partial repairs cover the three genuine multi-file cases. Stop common uncertainty; independently exclude nonreproducible cases without retry. Four earlier cases receive fresh current-runtime observations; historical outcomes remain unchanged.',
            'Retain bounded raw replies, canonical receipts/attempts/ledgers and failures. Create/remove only the unchanged named nonsecret host canary and attempt-owned containers.',
            'No models, downloads, other packages, image pulls, credentials, new destinations, cash, activation, release, historical replay or retained-image deletion. Separate wheel/docs components require their exact combined-bundle authority.'],
        'limitations': ['Four retained cases have runtime reproduction evidence only; no model qualification or value evidence transfers to this changed image. Dissect.cstruct/Mockito remain historically reproduced but cannot fill multi-file slots.',
            'AbsaOSS has two executable Python source-body changes; earlier Py3status proposal was withdrawn because two of its three file edits only changed docstrings.',
            'The runtime closure includes LGPL PyGithub and compiled cryptography/PyNaCl/cffi/PyYAML/NumPy/orjson/psutil wheels. Foamlib task source is GPL3 and remains private; retain source and embedded wheel licenses. This private test does not authorize redistribution or release.',
            'Foamlib and Leanclient retain all selected upstream assertions and add one protected behavior check each, derived from the public issue, to cover the second changed function. Report them as authored additions, not upstream benchmark evidence.',
            'Leanclient task source omits unrelated docs/examples/CI from its complete pinned source archive; every omission is recorded. The Python/test trees and root license/configuration remain. Runtime archive and transport limits are unchanged.',
            'The current source/archive bounds remain unchanged. Version2 explicitly declares pytest_mock; automatic plugin discovery remains disabled. Full141-case feasibility remains unverified.',
            'Only if all eight cases and their declared variants reproduce can this batch supply3/3/2 provisional screening counts. Full8/28/105 freeze, qualification and value remain separate.'],
        'approval_reason': 'New exact dependency installation/image provisioning and third-party source/tests exceed the terminal eight-case approval and the user continuation excludes untrusted installation/execution. No architecture decision is needed.'}
    spec = importlib.util.spec_from_file_location('frozen_classifier', HERE / 'runtime-execution/classify.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    checks = {'passed': True, 'source_unchanged': True, 'cases': 8, 'payloads_verified': 22, 'assets_verified': len(assets),
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
