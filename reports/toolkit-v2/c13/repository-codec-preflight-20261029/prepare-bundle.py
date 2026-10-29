"""Freeze the concrete current-wheel/docs review; never execute either component."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PACKAGE = ROOT / 'reports/toolkit-v2/integration-completion/package-review-codec-preflight-20261029'
DOCS = ROOT / 'reports/toolkit-v2/integration-completion/lychee-codec-preflight-review-20261029'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


assert not (HERE / 'approval-bundle.json').exists()
stability = json.loads((HERE / 'validation/source-stability.json').read_text())
assert stability['all_passed'] and stability['source_unchanged']
assert verification_source_digest(ROOT) == stability['source_digest']
package = json.loads((PACKAGE / 'operation-review.json').read_text())
docs = json.loads((DOCS / 'operation-review.json').read_text())
assert package['source_digest'] == docs['source_digest'] == stability['source_digest']
plan = RuntimeInstallation.model_validate_json((PACKAGE / 'installation.json').read_text())
assert package['installation_sha256'] == digest(plan)
assert len(plan.wheels) == 33 and not Path(plan.destination).exists()
for wheel in plan.wheels:
    path = Path(plan.wheelhouse) / wheel.filename
    assert path.is_file() and not path.is_symlink() and sha(path) == wheel.sha256
for name, expected in package['inputs'].items():
    assert sha(ROOT / name) == expected
for name, expected in docs['document_sha256'].items():
    assert sha(ROOT / name) == expected
assert sha(PACKAGE / 'run_review.py') == package['driver_sha256']
assert sha(DOCS / 'run-review.py') == docs['runner_sha256']
assert shutil.disk_usage(ROOT).free > 51 * 1024**3
bundle = {
    'purpose': 'Verify the changed installed codec-preflight guard and current offline documentation after completed real-task usefulness analysis.',
    'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
    'source_digest': stability['source_digest'],
    'runner_sha256': sha(HERE / 'run-bundle.py'),
    'components': {
        'package': {'review': str((PACKAGE / 'operation-review.json').relative_to(ROOT)),
            'review_file_sha256': sha(PACKAGE / 'operation-review.json'),
            'driver': str((PACKAGE / 'run_review.py').relative_to(ROOT)),
            'driver_sha256': sha(PACKAGE / 'run_review.py'),
            'argument_policy_digest': digest(package)},
        'docs': {'review': str((DOCS / 'operation-review.json').relative_to(ROOT)),
            'review_file_sha256': sha(DOCS / 'operation-review.json'),
            'driver': str((DOCS / 'run-review.py').relative_to(ROOT)),
            'driver_sha256': sha(DOCS / 'run-review.py')},
    },
    'package_wheel_sha256': package['wheel_sha256'],
    'package_checks': 3,
    'unchanged_cached_dependency_wheels': 32,
    'offline_document_count': len(docs['documents']),
    'limits': {'maximum_attempts_per_component': 1, 'maximum_package_seconds': 1800,
        'maximum_docs_seconds': 240, 'minimum_free_host_bytes': 50 * 1024**3,
        'private_runtime_margin_bytes': 1024**3, 'models': 0, 'cash_usd': 0,
        'downloads': 0, 'docker_calls': 0},
    'permissions': {'installation': 'One new private exact-wheel runtime only.',
        'execution': 'Pinned installed CLI and first-party fixtures; pinned cached offline docs checker and cached markdownlint.',
        'network': False, 'credentials': False, 'workers_or_services': False,
        'host_activation': False, 'release_or_publication': False,
        'cleanup': 'Only newly owned unchanged runtimes and scratch; retain caches, receipts, images, volumes, backups and user work.'},
    'authority': 'Pending new exact human approval. The completed comparison approval excludes installation; old package/docs approvals bind older source or inputs.',
    'failure_handling': 'Retain logs and terminal attempts. No automatic retries or approval transfer. Continue an independent unstarted component only if source, space and authority checks still pass.',
    'comparative_value_evidence': 'Completed19-pair study remains sourceb09911a0. This bundle supplies no models, qualification, new effectiveness result or positive selection benefit.',
    'execution_started': False,
}
(HERE / 'approval-bundle.json').write_text(json.dumps(bundle, indent=2) + '\n')
print(json.dumps({'bundle_file_sha256': sha(HERE / 'approval-bundle.json'),
    'package_wheel_sha256': package['wheel_sha256'], 'checks': 3,
    'documents': len(docs['documents']), 'execution_started': False}))
