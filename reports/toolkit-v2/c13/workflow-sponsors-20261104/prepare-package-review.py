"""Bind the newly built Sponsors wheel and the unchanged cached dependency closure."""

import hashlib
import json
import runpy
import shutil
from pathlib import Path

from component_context import HERE, ROOT

from aeep_toolkit.install_runtime import RuntimeInstallation, snapshot

PREVIOUS = HERE.parent / 'workflow-telemetry-20261104'
PREPARER = HERE.parent / 'workflow-skillrank-20261103' / 'prepare-package.py'


def read(p):
    return json.loads(Path(p).read_bytes())


def sha(p):
    with Path(p).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(p, value):
    with Path(p).open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


runpy.run_path(str(PREPARER))
plan = RuntimeInstallation.model_validate(read(HERE / 'package-installation.json'))
preparation = read(HERE / 'package-preparation.json')
old = read(PREVIOUS / 'operation-review.json')
work = HERE / 'package-execution/work'
inputs = [
    HERE / 'FUNDING.yml', HERE / 'sponsors-review.json',
    HERE.parent.parent / 'c12/developer-source/no-observations.json',
]
for item in inputs:
    shutil.copyfile(item, work / item.name)
wheel_paths = [Path(plan.wheelhouse) / wheel.filename for wheel in plan.wheels]
assert all(sha(path) == wheel.sha256 for path, wheel in zip(wheel_paths, plan.wheels, strict=True))
package = old['package'] | {
    'runtime': plan.destination,
    'installation_digest': preparation['installation_digest'],
    'installed_source': preparation['installed_source'],
    'required_bytes': preparation['required_bytes'],
    'prepared_workspace_sha256': snapshot(work),
    'scope': 'One installed Sponsors path, schema, source and review-drift check plus scoped boundary.',
}
source_checks = HERE / 'verification/checks.json'
pins = [
    *wheel_paths, *inputs, *(work / item.name for item in inputs),
    HERE / 'run-package.py', HERE / 'prepare-package-review.py', HERE / 'component_context.py',
    HERE / 'package-installation.json', HERE / 'package-preparation.json',
    HERE / 'package.sb', HERE / 'package-check.py', HERE / 'package-boundary.py',
    source_checks, PREPARER, PREVIOUS / 'run-components.py', PREVIOUS / 'source-snapshot.json',
    HERE.parent / 'pipeline-standing-authority-20261104.json',
]
review = {
    'purpose': 'Install and verify the new Sponsors wheel for the first time using the retained private dependency closure.',
    'source': preparation['source'], 'source_checks': str(source_checks),
    'expires_at': '2026-11-08T12:00:00Z',
    'executable_links': old['executable_links'],
    'package': package, 'component_assets': {'package': {str(p): sha(p) for p in pins}},
    'models': 0, 'cash_authority_usd': '0', 'downloads': 0, 'releases': 0,
    'automatic_retries': False, 'runtime_retained': True, 'comparisons': 'PAUSED',
}
path = HERE / 'operation-review.json'
write(path, review)
write(HERE / 'package-authority.json', {
    'review_sha256': sha(path), 'first_attempt': True,
    'authority': 'pipeline-standing-authority-20261104.json',
})
print(sha(path))
