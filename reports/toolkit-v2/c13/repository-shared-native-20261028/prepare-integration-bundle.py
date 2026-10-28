"""Bind the reviewed Git/runtime and current offline-docs components; no dispatch."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import sqlite3
import subprocess

from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    docs = ROOT / 'reports/toolkit-v2/integration-completion/lychee-shared-native-review-20261028'
    components = {
        'runtime': {'directory': str(HERE), 'review_file': 'runtime-review.json',
            'argv': [str(HERE / 'run-bundle.py')], 'maximum_driver_seconds': 1600,
            'result_file': 'execution-result.json', 'passed_field': 'batch_completed'},
        'package': {'directory': str(ROOT/'reports/toolkit-v2/integration-completion/package-review-shared-native-20261028'), 'review_file':'operation-review.json', 'argv':[str(ROOT/'reports/toolkit-v2/integration-completion/package-review-shared-native-20261028/run_review.py')], 'maximum_driver_seconds':1800, 'result_file':'execution/summary.json', 'passed_field':'runtime_removed'},
        'docs': {'directory': str(docs), 'review_file': 'operation-review.json',
            'argv': [str(docs / 'run-review.py')], 'maximum_driver_seconds': 600,
            'result_file': 'execution-result.json', 'passed_field': 'passed'}}
    runtime = json.loads((HERE / 'runtime-review.json').read_text())
    document_review = json.loads((docs / 'operation-review.json').read_text())
    source = verification_source_digest(ROOT)
    assert source == runtime['source_digest'] == document_review['source_digest']
    assert 'Summary: 0 issues' in (HERE / 'docs-lint-preparation.log').read_text()
    checks = ('preparation-audit.json','shared-default-control-check.json', 'component-check.json', 'execution-control-check.json',
        'derivation-check.json', 'integration-dispatch-check.json', 'static-tool-check.json')
    for name in checks:
        assert json.loads((HERE / name).read_text())['passed']
    assert json.loads((HERE / 'component-check.json').read_text())['downloads_builds_installs_containers_external_code_execution'] == 0
    documents = shlex.split(subprocess.check_output(['make', '-n', 'docs-links'], cwd=ROOT, text=True).splitlines()[-1])[3:]
    assert len(documents) == 69 and set(documents) == set(document_review['document_sha256'])
    assets = dict(runtime['assets'])
    for component in components.values():
        path = Path(component['directory']) / component['review_file']
        component['review_sha256'] = sha(path)
        assets[str(path)] = sha(path)
    for path in [*HERE.glob('*.py'), *(HERE / n for n in checks), HERE / 'README.md',
        HERE / 'independent-case-exclusions.json', HERE / 'withdrawn-preparation-draft.json',
        HERE / 'inventory-reader-correction.json',
        *(docs / n for n in ('run-review.py', 'sandbox-template.sb', 'sandbox-preflight.py', 'sandbox-preflight.json'))]:
        assets[str(path)] = sha(path)
        if path.suffix == '.py':
            ast.parse(path.read_text())
    package_dir=Path(components['package']['directory'])
    package_review=json.loads((package_dir/'operation-review.json').read_text())
    from aeep_toolkit.install_runtime import RuntimeInstallation,file_digest
    plan=RuntimeInstallation.model_validate_json((package_dir/'installation.json').read_text())
    assert package_review['source_digest']==source
    assert package_review['shared_default_program_sha256']=='1f099dfb9eee49db52c631a2c59f56c45f933e15bb6b4f1be35b86f5b8a84ba2'
    for path in package_dir.iterdir():
        if path.is_file():assets[str(path)]=sha(path)
    for name,expected in package_review['inputs'].items():assets[str(ROOT/name)]=expected
    for wheel in plan.wheels:
        path=Path(plan.wheelhouse)/wheel.filename;assert file_digest(path)==wheel.sha256;assets[str(path)]=wheel.sha256
    assets[document_review['archive_path']] = document_review['archive_sha256']
    for path, digest in document_review['document_sha256'].items():
        assets[str(ROOT / path)] = digest
    for path, digest in assets.items():
        assert Path(path).is_file() and not Path(path).is_symlink() and sha(Path(path)) == digest, path
    assert not (HERE / 'execution-started.json').exists()
    assert not (HERE / 'bundle-operator-approval.json').exists()
    assert not (ROOT / runtime['build_context']).exists()
    assert not (ROOT / runtime['component_cache']).exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 128 * 1024**2
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as con:
        counters = list(con.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert counters == [13304, 3755, 120080.87940059323, '0.0']
    bundle = {'purpose': 'Validate the shared native observer on frozen38-test Dead and171-test JSON-logger controls using the exact upstream Git local component,check the corrected wheel privately,and check current docs offline.',
        'source_digest': source, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'assets': assets, 'components': components, 'host_canary': runtime['host_canary'],
        'runtime_limits': {k: runtime[k] for k in ('parent_image', 'target_tag', 'maximum_builds',
            'maximum_build_growth_bytes', 'maximum_download_attempts', 'maximum_download_bytes_per_attempt',
            'maximum_contained_calls', 'maximum_operations', 'maximum_reserved_seconds', 'maximum_model_turns', 'cash_usd')},
        'runtime_permissions': runtime['permissions'], 'runtime_no_authority_for': runtime['no_authority_for'],
        'package_limits':{'corrected_wheel_sha256':package_review['wheel_sha256'],'wheel_bytes':package_review['wheel_bytes'],'cached_dependency_wheels':32,'installed_checks':20,'network':False,'global_activation':False,'remove_only_unchanged_owned_runtime_and_scratch':True},
        'docs_limits': {'checker': 'Lychee0.24.2', 'exact_cached_archive_sha256': document_review['archive_sha256'],
            'documents': 69, 'network': False, 'maximum_lychee_calls': 2,
            'new_standalone_version_calls': 0, 'remove_only_unchanged_owned_runtime': True},
        'failure_policy': runtime['failure_policy'],
        'independent_docs': 'Runtime case exclusions with canonical reconciliation do not block docs. The dispatcher stops on common uncertainty. After a known preparation/build-only failure, the operator agent may finish the separately approved docs component only after verifying canonical accounting, unchanged common bindings and absence of any started worker/canary;no Git replay or second build is implied.',
        'evidence_reuse': runtime['evidence_reuse'], 'approval_reason': runtime['approval_reason']+' The corrected b3d9c5d0wheel differs from terminal3791d8f7;the parent approval must explicitly cover this new artifact and the unchanged32cached dependencies. No architecture/budget decision.',
        'grant_before_preparation': counters, 'prepared_only': True,
        'actual_package_download_build_or_untrusted_execution': False,
        'scientific_qualification_usefulness_selection_resource_human_release': False}
    with (HERE / 'approval-bundle.json').open('x') as stream:
        json.dump(bundle, stream, indent=2)
        stream.write('\n')
    result = {'passed': True, 'bundle_sha256': sha(HERE / 'approval-bundle.json'),
        'assets_verified': len(assets), 'source_digest': source,
        'components': {k: v['review_sha256'] for k, v in components.items()},
        'new_source13gates_passed':True,'new_wheel20installed_checks_pending':True, 'Git_archive_not_downloaded': True,
        'no_image_build_or_new_container_or_third_party_execution': True,
        'grant_unchanged': counters, 'free_host_gib': shutil.disk_usage(ROOT).free / 1024**3}
    (HERE / 'final-preparation-audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
