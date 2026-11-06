"""Bind the next balanced SkillsBench pair to public image metadata."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLDER = HERE.parent / 'skillsbench-prebuilt-acquisition-20261104'
CANDIDATES = HERE.parent / 'skillsbench-prebuilt-runtime-20261104/runtime-candidates.json'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
REGISTRY = 'https://ghcr.io/v2/benchflow-ai/skillsbench-task-env/'
TASKS = ('financial-modeling-qa', 'software-dependency-audit')


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def digest(path):
    return sha(Path(path).read_bytes())


def write(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def fetch(url, headers):
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=20) as response:
        raw = response.read(1024**2 + 1)
    assert len(raw) <= 1024**2
    return raw


old = read(OLDER / 'operation-review.json')
assert digest(HERE / 'run.py') == digest(OLDER / 'run.py')
assert read(OLDER / 'acquisition/summary.json')['passed']
assert digest(Path(old['docker_config']) / 'config.json') == old['docker_config_sha256']
sys.path.insert(0, str(Path(old['coordinator_source_snapshot']) / 'src'))
from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.verification import verification_source_digest

assert verification_source_digest(Path(old['coordinator_source_snapshot'])) == old['source']
free = shutil.disk_usage(ROOT).free
assert free >= 55 * 1024**3
docker = [old['docker'], '--config', old['docker_config'], '--host', 'unix://' + old['docker_socket']]
usage = subprocess.check_output(
    [*docker, 'system', 'df', '--format', '{{.Type}} {{.Size}} {{.Active}} {{.TotalCount}}'],
    text=True, timeout=30,
).splitlines()
assert len(usage) == 4
anonymous = json.loads(fetch(
    'https://ghcr.io/token?scope=repository%3Abenchflow-ai%2Fskillsbench-task-env%3Apull&service=ghcr.io',
    {},
))['token']
headers = {'Authorization': 'Bearer ' + anonymous,
           'Accept': 'application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json'}
known = {task['task_id']: task for task in read(CANDIDATES)['tasks']}
images = []
for name in TASKS:
    task = known[name]
    assert task['platform'] == {'architecture': 'amd64', 'os': 'linux'}
    assert all(item['matches_pinned_dockerfile'] for item in task['dockerfile_comparison'])
    manifest_id = task['platform_manifest']
    raw = fetch(REGISTRY + 'manifests/' + manifest_id, headers)
    assert 'sha256:' + sha(raw) == manifest_id
    manifest = json.loads(raw)
    cfg = manifest['config']['digest']
    assert cfg == task['config_sha256']
    raw = fetch(REGISTRY + 'blobs/' + cfg, headers)
    assert 'sha256:' + sha(raw) == cfg
    config = json.loads(raw)
    assert (config['os'], config['architecture']) == ('linux', 'amd64')
    compressed = sum(layer['size'] for layer in manifest['layers'])
    assert compressed == task['compressed_layer_bytes']
    images.append({
        'task_id': name, 'reference': 'ghcr.io/benchflow-ai/skillsbench-task-env@' + manifest_id,
        'allowed_engine_ids': [cfg, manifest_id], 'diff_ids': config['rootfs']['diff_ids'],
        'compressed_layer_bytes': compressed,
    })
assert sum(row['compressed_layer_bytes'] for row in images) <= 510_000_000
assert [row['task_id'] for row in images] == list(TASKS)
work = ROOT / '.aeep' / HERE.name
work.mkdir(mode=0o700)
plan = {
    'purpose': 'First acquire the pinned Financial Modeling QA and Dependency Audit images for private static inspection.',
    'images': images, 'compressed_layer_bytes_total': sum(i['compressed_layer_bytes'] for i in images),
    'storage_free_bytes': free, 'docker_usage': usage, 'no_guest_execution': True,
    'rights': 'Private acquisition and inspection only. Task execution, disclosure, publishing and redistribution are outside this scope.',
    'maximum_operations': 5, 'maximum_reserved_seconds': 650, 'models': 0,
    'cash_authority_usd': '0', 'automatic_retries': False,
}
write(HERE / 'plan.json', plan)
scopes = {role: {'role': role, 'plan_sha256': content_digest(plan)}
          for role in ('subject', 'recipe', 'environment', 'mapping')}
refs = {role: content_digest(item) for role, item in scopes.items()}
now = datetime.now(UTC)
grant = AssessmentAuthorization(
    authorization_id=HERE.name, subject_digests=[refs['subject']], recipe_digests=[refs['recipe']],
    environment_digests=[refs['environment']], limits=AssessmentLimits(max_operations=5, max_elapsed_seconds=650),
    expires_at=now + timedelta(hours=2), allowed_destinations=['local'], remote_disclosure=False,
)
request = RecipeMaterializationRequest(
    plan_id=HERE.name, subject_digest=refs['subject'], recipe_digest=refs['recipe'],
    mapping_digest=refs['mapping'], environment_digest=refs['environment'], authorization_id=HERE.name,
    definition_digests=list(refs.values()), seed=0,
)
write(HERE / 'prepared.json', {
    'scopes': {refs[role]: value for role, value in scopes.items()},
    'grant': grant.model_dump(mode='json'), 'request': request.model_dump(mode='json'), 'applied': False,
})
assets = [HERE / name for name in ('run.py', 'prepare.py', 'prepared.json', 'plan.json')]
assets += [CANDIDATES, AUTHORITY, Path(old['docker']), Path(old['docker_config']) / 'config.json']
review = {key: old[key] for key in (
    'source', 'coordinator_source_snapshot', 'ledger', 'docker', 'docker_config', 'docker_config_sha256', 'docker_socket',
)}
review.update(plan)
review.update(assets={str(p): digest(p) for p in assets}, work=str(work),
              expires_at=grant.expires_at.isoformat(), minimum_start_free_bytes=55 * 1024**3,
              minimum_free_bytes=50 * 1024**3, stop_before_reserve_bytes=52 * 1024**3,
              retention='Retain both exact images and all existing containers, images and volumes.')
path = HERE / 'operation-review.json'
write(path, review)
write(HERE / 'delegated-authority.json', {
    'review_sha256': digest(path), 'first_attempt': True,
    'standing_authority_sha256': digest(AUTHORITY),
    'reason': 'New digest-pinned images for the next two required task integrations. No earlier task pipeline is replayed.',
})
print(digest(path))
