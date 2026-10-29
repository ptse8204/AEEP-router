"""Read-only preparation audit; never install, run checker, or dispatch models."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import tarfile
import zipfile

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


bundle = json.loads((HERE / 'approval-bundle.json').read_text())
assert verification_source_digest(ROOT) == bundle['source_digest']
assert sha(HERE / 'run-bundle.py') == bundle['runner_sha256']
documents = wheels = 0
for name, component in bundle['components'].items():
    path = ROOT / component['review']
    review = json.loads(path.read_text())
    assert sha(path) == component['review_file_sha256']
    assert sha(ROOT / component['driver']) == component['driver_sha256']
    assert not (path.parent / 'operator-approval.json').exists()
    assert not (path.parent / 'execution-started.json').exists()
    assert review['source_digest'] == bundle['source_digest']
    if name == 'package':
        assert digest(review) == component['argument_policy_digest']
        plan = RuntimeInstallation.model_validate_json((path.parent / 'installation.json').read_text())
        assert digest(plan) == review['installation_sha256']
        assert not Path(plan.destination).exists()
        assert len(plan.wheels) == 33
        for wheel in plan.wheels:
            archive = Path(plan.wheelhouse) / wheel.filename
            assert archive.is_file() and not archive.is_symlink() and sha(archive) == wheel.sha256
            wheels += 1
            if wheel.extension_id == 'aeep-agent-router':
                with zipfile.ZipFile(archive) as package:
                    for module, expected in review['installed_module_hashes'].items():
                        assert hashlib.sha256(package.read(module.replace('.', '/') + '.py')).hexdigest() == expected
        for filename, expected in review['inputs'].items():
            assert sha(ROOT / filename) == expected
        wheelhouse = plan.wheelhouse
    else:
        for filename, expected in review['document_sha256'].items():
            assert sha(ROOT / filename) == expected
            documents += 1
        for field, filename in [('sandbox_template_sha256', 'sandbox-template.sb'),
                                ('sandbox_preflight_sha256', 'sandbox-preflight.py')]:
            assert sha(path.parent / filename) == review[field]
        assert sha(ROOT / 'Makefile') == review['makefile_sha256']
        assert sha(ROOT / '.lychee.toml') == review['config_sha256']
        assert sha(Path(review['archive_path'])) == review['archive_sha256']
        with tarfile.open(review['archive_path'], 'r:gz') as archive:
            member = archive.getmember(review['binary_member'])
            assert member.isfile() and member.size == review['binary_bytes']
            assert hashlib.sha256(archive.extractfile(member).read()).hexdigest() == review['binary_sha256']
for path in [HERE / 'prepare-bundle.py', HERE / 'run-bundle.py',
             *ROOT.glob('reports/toolkit-v2/integration-completion/*codec-preflight*/*.py')]:
    ast.parse(path.read_text())
database = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3')
with sqlite3.connect(database.as_uri() + '?mode=ro', uri=True) as connection:
    counters = list(connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
assert counters == [13656, 3796, 125269.06508910004, '0.0']
record = {'passed': True, 'bundle_file_sha256': sha(HERE / 'approval-bundle.json'),
    'source_digest': bundle['source_digest'], 'components_verified': 2,
    'document_hashes_verified': documents, 'exact_cached_wheels_verified': wheels,
    'binary_bytes_read_and_verified_without_execution': True,
    'installed_checks_planned': 3, 'new_models_or_installations_or_checker_executions': 0,
    'grant_counters_unchanged': counters, 'private_wheel_cache': wheelhouse,
    'private_runtime_not_created': True, 'free_host_bytes': shutil.disk_usage(ROOT).free,
    'image_mutations_performed': 0, 'auditor_sha256': sha(Path(__file__))}
(HERE / 'preparation-audit.json').write_text(json.dumps(record, indent=2) + '\n')
print(json.dumps({key: value for key, value in record.items() if key != 'private_wheel_cache'}))
