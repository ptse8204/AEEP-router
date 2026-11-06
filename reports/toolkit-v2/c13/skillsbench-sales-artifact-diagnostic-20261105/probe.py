"""Exercise the existing worker file protocol with synthetic bytes only."""

import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

program = sys.argv[1]
work = Path('/workspace')
name = 'demographic_analysis.xlsx'
data = b'SYNTHETIC WORKBOOK TRANSPORT\n' * 6500
limit = 300000


def call(operation, filename, value=None):
    request = {'operation': operation, 'name': filename, 'limit': limit,
               'data': base64.b64encode(value).decode() if value is not None else None, 'files': None}
    return subprocess.run([sys.executable, '-I', '-B', '-c', program], input=json.dumps(request).encode(),
                          capture_output=True, timeout=5)


assert call('read', name).returncode != 0
put = call('write', name, data)
assert put.returncode == 0
received = call('read', name)
assert received.returncode == 0
reply = json.loads(received.stdout)
assert base64.b64decode(reply['data'], validate=True) == data
assert reply['sha256'] == hashlib.sha256(data).hexdigest() and reply['size'] == len(data)
assert call('write', name, b'conflict').returncode != 0
(work/'oversized.xlsx').write_bytes(b'x' * (limit + 1))
assert call('read', 'oversized.xlsx').returncode != 0
(work/'alias.xlsx').symlink_to(name)
assert call('read', 'alias.xlsx').returncode != 0
print(json.dumps({'synthetic_roundtrip_bytes': len(data), 'sha256': reply['sha256'],
                  'missing_denied': True, 'overwrite_denied': True, 'oversized_denied': True,
                  'symlink_denied': True, 'artifact_limit': limit}))
