"""Hash selected task inputs from never-started images without extracting files."""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
import time
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


parser = argparse.ArgumentParser()
parser.add_argument('--execute-delegated', required=True)
args = parser.parse_args()
raw = (HERE / 'operation-review.json').read_bytes()
review = json.loads(raw)
identity = sha(raw)
authority = json.loads((HERE / 'delegated-authority.json').read_bytes())
assert args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']
assert datetime.now(UTC) < datetime.fromisoformat(review['expires_at'])
assert shutil.disk_usage(ROOT).free >= 51 * 1024**3
for path, digest in review['pins'].items():
    assert sha(Path(path).read_bytes()) == digest, path
with (HERE / 'execution-started.json').open('x') as f:
    json.dump({'review_sha256': identity}, f)
prefix = [review['docker'], '--config', review['docker_config'], '--host',
          'unix://' + review['docker_socket']]
env = {'HOME': review['docker_config'], 'PATH': '/usr/bin:/bin', 'LC_ALL': 'C'}
operations = []


def invoke(*argv):
    assert len(operations) < review['maximum_commands']
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    began = time.perf_counter()
    reply = subprocess.run([*prefix, *argv], env=env, capture_output=True, timeout=20)
    operations.append({'verb': argv[0], 'exit_code': reply.returncode,
                       'wall_seconds': time.perf_counter() - began,
                       'stderr_sha256': sha(reply.stderr)})
    assert reply.returncode == 0
    return reply.stdout.decode().strip()


def assets(cid, selector, expected):
    # These selected upstream trees fit comfortably below the bounded pipe.
    began = time.perf_counter()
    reply = subprocess.run([*prefix, 'cp', cid + ':' + selector, '-'],
                           env=env, capture_output=True, timeout=20)
    operations.append({'verb': 'cp', 'exit_code': reply.returncode,
                       'wall_seconds': time.perf_counter() - began,
                       'stderr_sha256': sha(reply.stderr)})
    assert reply.returncode == 0 and len(reply.stdout) <= 4 * 1024**2
    from io import BytesIO

    found = {}
    extras = 0
    with tarfile.open(fileobj=BytesIO(reply.stdout), mode='r:*') as tar:
        for entry in tar:
            path = PurePosixPath(entry.name)
            assert not path.is_absolute() and '..' not in path.parts
            if entry.isdir():
                continue
            key = str(path)
            if key not in expected:
                extras += 1
                continue
            assert key not in found and entry.isfile() and entry.size == expected[key]['bytes']
            content = tar.extractfile(entry)
            assert content is not None
            found[key] = sha(content.read(entry.size + 1))
    assert found == {key: value['sha256'] for key, value in expected.items()}
    return {'matched': found, 'extra_entries': extras, 'raw_assets_retained': False}


result = {'passed': False, 'models': 0, 'guest_code_executed': False,
          'comparisons': 'PAUSED', 'containers': [], 'task_rights_cleared': False}
try:
    for task in review['tasks']:
        image = task['reference']
        name = task['name']
        assert not invoke('ps', '-aq', '--filter', 'name=^/'+name+'$')
        volumes = json.loads(invoke('image', 'inspect', '--format', '{{json .Config.Volumes}}', image))
        assert not volumes, 'Image-declared volumes are outside this static audit'
        cid = invoke('create', '--platform', 'linux/amd64', '--pull', 'never',
                     '--network', 'none', '--read-only', '--cap-drop', 'ALL',
                     '--security-opt', 'no-new-privileges:true', '--pids-limit', '16',
                     '--memory', '64m', '--entrypoint', '/bin/false', '--name', name,
                     '--label', 'com.aeep.engineering.owner='+name, image)
        assert re.fullmatch(r'[a-f0-9]{64}', cid)
        item = {'task_id': task['task_id'], 'id': cid, 'retained': True}
        result['containers'].append(item)
        template = '{{json .Image}} {{json .State.Status}} {{json .Mounts}} {{json .HostConfig.NetworkMode}}'
        row = invoke('inspect', '--format', template, cid)
        decoder = json.JSONDecoder()
        fields = []
        while row:
            value, end = decoder.raw_decode(row)
            fields.append(value)
            row = row[end:].strip()
        assert fields == [task['image_id'], 'created', [], 'none']
        item['created_only'] = True
        item['assets'] = {key: assets(cid, key, expected)
                          for key, expected in task['selectors'].items()}
    result['passed'] = True
except Exception as error:
    result['error_type'] = type(error).__name__
finally:
    result['operator_preparation_intervals'] = operations
    result['canonical_scope'] = 'Static operator byte inspection. Per-command elapsed time is observed; assessment and model accounting are not involved.'
    (HERE / 'summary.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k != 'operator_preparation_intervals'}))
raise SystemExit(not result['passed'])
