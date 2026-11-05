"""Complete the unstarted Maven root downloads from the exact artifact plan."""
import hashlib
import json
import re
import tarfile
import urllib.request
from collections import defaultdict
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep/skillsbench-spring-runtime-20261105'
PLAN = json.loads((HERE / 'artifacts.json').read_bytes())
CENTRAL = 'https://repo.maven.apache.org/maven2/'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('unexpected Maven Central redirect')


def read(relative, maximum):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
    with opener.open(CENTRAL + relative, timeout=20) as response:
        data = response.read(maximum + 1)
    assert len(data) <= maximum
    return data


release = PLAN['python']
path = WORK / release['name']
assert path.stat().st_size == release['size']
with path.open('rb') as stream:
    assert hashlib.file_digest(stream, 'sha256').hexdigest() == release['sha256']
with tarfile.open(path, 'r:gz') as archive:
    members = archive.getmembers()
    collisions = defaultdict(set)
    for member in members:
        name = PurePosixPath(member.name)
        assert name.parts[0] == 'python' and '..' not in name.parts and not name.is_absolute()
        collisions[str(name).casefold()].add(str(name))
    groups = [sorted(values) for values in collisions.values() if len(values) > 1]
    assert groups and all(x.startswith('python/share/terminfo/') for group in groups for x in group)
rows = []
for relative in PLAN['maven_origins']:
    path = WORK / 'maven-seed' / relative
    assert not path.exists()
    expected = read(relative + '.sha1', 1024).decode().strip()
    assert re.fullmatch(r'[a-f0-9]{40}', expected)
    raw = read(relative, 5 * 1024**2)
    assert hashlib.sha1(raw).hexdigest() == expected
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(raw)
    rows.append({'path': relative, 'bytes': len(raw),
                 'publisher_sha1': expected, 'sha256': hashlib.sha256(raw).hexdigest()})
data = {'retained_python_archive': release, 'case_fold_collision_groups': len(groups),
        'collision_examples': groups[:5], 'archive_member_count': len(members),
        'archive_regular_and_link_bytes': sum(x.size for x in members),
        'maven_roots': rows, 'maven_transitive_closure_verified': False,
        'python_extraction_status': 'HOST_EXTRACTION_PARTIAL_PRESERVED',
        'next_python_stage': 'Unpack the verified archive inside the case-sensitive isolated Linux guest.',
        'guest_code_executed': False, 'models': 0}
with (HERE / 'staged-roots.json').open('x') as stream:
    json.dump(data, stream, indent=2)
    stream.write('\n')
print(json.dumps({'case_fold_collision_groups': len(groups), 'maven_roots': len(rows),
                  'bytes': sum(x['bytes'] for x in rows), 'guest_code_executed': False}))
