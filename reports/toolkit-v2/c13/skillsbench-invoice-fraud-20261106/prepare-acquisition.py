"""Prepare one first-attempt image pull with the existing acquisition driver."""

import hashlib
import json
import shutil
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PRIOR = C13 / 'skillsbench-financial-audit-acquisition-20261105'
AUTHORITY = C13 / 'pipeline-standing-authority-20261104.json'
GIB = 1024**3


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


old = read(PRIOR / 'operation-review.json')
assert read(PRIOR / 'acquisition/summary.json')['passed']
candidate = read(HERE / 'runtime-candidate.json')
asset_use = read(HERE / 'asset-use.json')
assert candidate['revision'] == asset_use['revision']
assert candidate['task_id'] == asset_use['task_id'] == 'invoice-fraud-detection'
assert asset_use['local_engineering_use'] == 'CLEARED_FOR_PINNED_CONTRIBUTION_FILES'
assert candidate['configuration']['Volumes'] is None
assert candidate['image']['compressed_layer_bytes'] <= 350_000_000
assert digest(Path(old['docker_config']) / 'config.json') == old['docker_config_sha256']
free = shutil.disk_usage(ROOT).free
assert free >= 55 * GIB
docker = [old['docker'], '--config', old['docker_config'], '--host', 'unix://' + old['docker_socket']]
usage = subprocess.check_output(
    [*docker, 'system', 'df', '--format', '{{.Type}} {{.Size}} {{.Active}} {{.TotalCount}}'],
    text=True, timeout=30,
).splitlines()
assert len(usage) == 4

sys.path.insert(0, str(Path(old['coordinator_source_snapshot']) / 'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.verification import verification_source_digest

assert verification_source_digest(Path(old['coordinator_source_snapshot'])) == old['source']
work = ROOT / '.aeep' / HERE.name / 'acquisition'
work.mkdir(mode=0o700)
review_home = work / 'review'
review_home.mkdir(mode=0o700)
driver = review_home / 'run.py'
assert digest(PRIOR / 'run.py') == old['assets'][str(PRIOR / 'run.py')]
shutil.copyfile(PRIOR / 'run.py', driver)
assert digest(driver) == digest(PRIOR / 'run.py')

plan = {
    'purpose': 'First acquire and inspect one pinned Invoice Fraud task environment.',
    'images': [candidate['image']], 'storage_free_bytes': free, 'docker_usage': usage,
    'maximum_operations': 3, 'maximum_reserved_seconds': 340,
    'models': 0, 'cash_authority_usd': '0', 'automatic_retries': False,
    'no_guest_execution': True,
}
scopes = {role: {'role': role, 'plan_sha256': content_digest(plan)}
          for role in ('subject', 'recipe', 'environment', 'mapping')}
refs = {role: content_digest(value) for role, value in scopes.items()}
grant = AssessmentAuthorization(
    authorization_id=HERE.name + '-acquisition', subject_digests=[refs['subject']],
    recipe_digests=[refs['recipe']], environment_digests=[refs['environment']],
    limits=AssessmentLimits(max_operations=3, max_elapsed_seconds=340),
    expires_at=datetime.now(UTC) + timedelta(hours=3), allowed_destinations=['local'],
    remote_disclosure=False,
)
request = RecipeMaterializationRequest(
    plan_id=grant.authorization_id, subject_digest=refs['subject'], recipe_digest=refs['recipe'],
    mapping_digest=refs['mapping'], environment_digest=refs['environment'],
    authorization_id=grant.authorization_id, definition_digests=list(refs.values()), seed=0,
)
prepared = review_home / 'prepared.json'
write(prepared, {
    'scopes': {refs[role]: value for role, value in scopes.items()},
    'grant': grant.model_dump(mode='json'), 'request': request.model_dump(mode='json'), 'applied': False,
})
assets = [Path(__file__).resolve(), prepared, driver, AUTHORITY,
          HERE / 'asset-use.json', HERE / 'runtime-candidate.json', HERE / 'source-inventory.json',
          Path(old['docker']), Path(old['docker_config']) / 'config.json']
review = {key: old[key] for key in (
    'source', 'coordinator_source_snapshot', 'ledger', 'docker',
    'docker_config', 'docker_config_sha256', 'docker_socket',
)}
review.update(plan, assets={str(p): digest(p) for p in assets}, work=str(work),
              expires_at=grant.expires_at.isoformat(), minimum_start_free_bytes=55 * GIB,
              minimum_free_bytes=50 * GIB, stop_before_reserve_bytes=52 * GIB,
              retention='Retain the image and all existing Docker resources.',
              source_driver=str(PRIOR / 'run.py'))
path = review_home / 'operation-review.json'
write(path, review)
write(review_home / 'delegated-authority.json', {
    'review_sha256': digest(path), 'first_attempt': True,
    'standing_authority_sha256': digest(AUTHORITY),
    'reason': 'New first-attempt acquisition for the approved substitute task.',
})
for name in ('operation-review.json', 'delegated-authority.json', 'prepared.json'):
    shutil.copyfile(review_home / name, HERE / ('acquisition-' + name))
print(digest(path))
