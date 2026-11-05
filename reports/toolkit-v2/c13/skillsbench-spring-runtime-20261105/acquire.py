"""Fetch pinned portable Python and Maven root artifacts without running them."""
import hashlib
import json
import shutil
import tarfile
import urllib.parse
import urllib.request
from pathlib import Path, PurePosixPath

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep/skillsbench-spring-runtime-20261105'
PLAN = json.loads((HERE / 'artifacts.json').read_bytes())
CENTRAL = 'https://repo.maven.apache.org/maven2/'
RELEASE_HOSTS = {'github.com', 'release-assets.githubusercontent.com', 'objects.githubusercontent.com'}


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    def __init__(self, hosts):
        self.hosts = hosts

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        target = urllib.parse.urlsplit(newurl)
        if target.scheme != 'https' or target.hostname not in self.hosts or target.username or target.password:
            raise ValueError('unexpected artifact redirect')
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch(url, limit, hosts):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), RestrictedRedirect(hosts))
    with opener.open(url, timeout=45) as response:
        final = urllib.parse.urlsplit(response.url)
        assert final.scheme == 'https' and final.hostname in hosts
        raw = response.read(limit + 1)
    assert len(raw) <= limit
    return raw


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as out:
        out.write(raw)


assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
release = PLAN['python']
archive = fetch(release['url'], release['size'], RELEASE_HOSTS)
assert len(archive) == release['size'] and hashlib.sha256(archive).hexdigest() == release['sha256']
path = WORK / release['name']
save(path, archive)
expanded = WORK / 'interpreter'
expanded.mkdir(mode=0o700)
with tarfile.open(path, 'r:gz') as source:
    members = source.getmembers()
    assert len(members) <= 20000 and sum(m.size for m in members) <= 240 * 1024**2
    names = set()
    for member in members:
        n = PurePosixPath(member.name)
        assert n.parts[0] == 'python' and '..' not in n.parts and not n.is_absolute()
        assert n not in names and not (member.ischr() or member.isblk() or member.isfifo())
        names.add(n)
    source.extractall(expanded, members=members, filter='data')
binary = expanded / 'python/bin/python3.12'
assert binary.is_file() and binary.resolve().is_relative_to(expanded)
licenses = [
    {'path': str(f.relative_to(expanded)), 'sha256': hashlib.sha256(f.read_bytes()).hexdigest()}
    for f in sorted(expanded.rglob('*')) if f.is_file() and 'license' in f.name.casefold()
]
assert licenses
maven = []
for relative in PLAN['maven_origins']:
    expected = fetch(CENTRAL + relative + '.sha1', 1024, {'repo.maven.apache.org'}).decode().strip()
    raw = fetch(CENTRAL + relative, 5 * 1024**2, {'repo.maven.apache.org'})
    assert hashlib.sha1(raw).hexdigest() == expected
    save(WORK / 'maven-seed' / relative, raw)
    maven.append({'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(),
                  'publisher_sha1': expected, 'bytes': len(raw)})
result = {'python_archive_sha256': release['sha256'],
          'python_binary_sha256': hashlib.sha256(binary.read_bytes()).hexdigest(),
          'python_licenses': licenses, 'maven_artifacts': maven, 'maven_closure_verified': False,
          'third_party_programs_executed': False, 'models': 0, 'free_bytes_after': shutil.disk_usage(ROOT).free}
with (HERE / 'artifact-inventory.json').open('x') as f:
    json.dump(result, f, indent=2)
    f.write('\n')
print(json.dumps({'maven_roots': len(maven), 'python_sha256': result['python_binary_sha256'], 'executed': False}))
