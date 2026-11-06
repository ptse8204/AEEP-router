"""Inspect only metadata from the never-started dependency audit image."""

import hashlib
import io
import json
import subprocess
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
review = json.loads((HERE / 'operation-review.json').read_bytes())
result = json.loads((HERE / 'summary.json').read_bytes())
task = next(row for row in review['tasks'] if row['task_id'] == 'software-dependency-audit')
record = next(row for row in result['containers'] if row['task_id'] == task['task_id'])
assert record['created_only'] and record['retained'] and not result['guest_code_executed']
prefix = [review['docker'], '--config', review['docker_config'], '--host', 'unix://' + review['docker_socket']]
assert hashlib.sha256((Path(review['docker_config']) / 'config.json').read_bytes()).hexdigest() == review['pins'][str(Path(review['docker_config']) / 'config.json')]
env = {'HOME': review['docker_config'], 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
cid = record['id']
template = '{{.Image}} {{.State.Status}} {{json .Mounts}} {{.HostConfig.NetworkMode}}'
state = subprocess.check_output([*prefix, 'inspect', '--format', template, cid], env=env, timeout=10, text=True)
assert state.strip() == f"{task['image_id']} created [] none"
selectors = ('/root/.cache/trivy/db/metadata.json', '/root/.cache/trivy/java-db/metadata.json')
observations = {}
for path in selectors:
    proc = subprocess.run([*prefix, 'cp', f'{cid}:{path}', '-'], env=env, timeout=10, capture_output=True)
    if proc.returncode:
        observations[path] = {'available': False, 'exit_code': proc.returncode,
                              'diagnostic_sha256': hashlib.sha256(proc.stderr).hexdigest()}
        continue
    assert len(proc.stdout) <= 128 * 1024
    with tarfile.open(fileobj=io.BytesIO(proc.stdout), mode='r:*') as archive:
        entry, = archive.getmembers()
        assert entry.name == 'metadata.json' and entry.isfile() and 0 < entry.size <= 16384
        stream = archive.extractfile(entry)
        assert stream is not None
        raw = stream.read()
    value = json.loads(raw)
    observed = {key: value[key] for key in ('Version', 'UpdatedAt', 'NextUpdate', 'DownloadedAt') if key in value}
    assert observed and all(type(item) in (int, str) for item in observed.values())
    observations[path] = {'available': True, 'sha256': hashlib.sha256(raw).hexdigest(), 'declared_metadata': observed}
with (HERE / 'trivy-metadata.json').open('x') as file:
    json.dump({'image_id': task['image_id'], 'container_id': cid, 'retained': True,
               'selectors': observations, 'database_contents_retained': False, 'guest_code_executed': False,
               'models': 0, 'source_license_cleared': False},file,indent=2)
    file.write('\n')
print(json.dumps(observations))
