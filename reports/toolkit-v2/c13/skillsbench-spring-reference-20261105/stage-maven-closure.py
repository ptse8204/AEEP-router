"""Stage only the project graph's missing JARs and the pinned Surefire provider."""
import hashlib
import json
import re
import shutil
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT/'.aeep'/HERE.name
OLD = ROOT/'.aeep/skillsbench-spring-maven-20261105/maven-cache'
BASE = 'https://repo.maven.apache.org/maven2/'
MIRROR = 'aeep-reviewed-central-relay'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


def snapshot(path):
    files = {}
    for entry in sorted(path.rglob('*')):
        assert not entry.is_symlink(), entry
        if not entry.is_dir():
            assert entry.is_file(), entry
            files[entry.relative_to(path).as_posix()] = sha(entry)
    return files


def artifact(group, name, version, extension, classifier=None):
    suffix = '-'+classifier if classifier else ''
    return f"{group.replace('.', '/')}/{name}/{version}/{name}-{version}{suffix}.{extension}"


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        raise ValueError('unexpected Maven Central redirect')


def collect(plan, cache):
    opener = build_opener(ProxyHandler({}), NoRedirect())
    rows = []
    started = time.perf_counter()
    current = None
    transferred = 0
    calls = 0

    def read(relative, limit):
        nonlocal transferred, calls
        assert re.fullmatch(r'[A-Za-z0-9_.+/-]+', relative) and '..' not in Path(relative).parts
        calls += 1
        assert calls <= plan['maximum_requests']
        with opener.open(BASE+relative, timeout=20) as response:
            data = response.read(limit+1)
        transferred += len(data)
        assert len(data) <= limit and transferred <= plan['maximum_transfer_bytes']
        return data

    try:
        for current in plan['artifact_paths']:
            assert shutil.disk_usage(ROOT).free >= 52*1024**3
            target = cache/current
            assert not target.exists()
            expected = read(current+'.sha1', 1024).decode().strip()
            assert re.fullmatch(r'[a-f0-9]{40}', expected)
            data = read(current, 5*1024**2)
            assert hashlib.sha1(data).hexdigest() == expected
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open('xb') as stream:
                stream.write(data)
            target.with_suffix(target.suffix+'.sha1').write_text(expected+'\n')
            with (target.parent/'_remote.repositories').open('a') as stream:
                stream.write(target.name+'>'+MIRROR+'=\n')
            rows.append({'path':current,'publisher_sha1':expected,'sha256':sha(target),'bytes':len(data)})
        assert all((cache/path).is_file() for path in plan['required_runtime_paths'])
    except Exception as error:
        write(HERE/'maven-acquisition-stopped.json',{
            'error_type':type(error).__name__,'http_status':error.code if isinstance(error,HTTPError) else None,
            'artifact':current,'completed':rows,'calls':calls,'bytes':transferred,
            'elapsed_seconds':time.perf_counter()-started,'automatic_retries':False})
        raise
    return {'passed':True,'completed':rows,'calls':calls,'bytes':transferred,
            'elapsed_seconds':time.perf_counter()-started,'models':0}


plan_path=HERE/'maven-acquisition-plan.json'
tree=HERE.parent/'skillsbench-spring-maven-tree-20261105/execution/resolved-graph.json'
plan=json.loads(plan_path.read_bytes())
assert sha(tree)==plan['graph_sha256'] and sha(Path(__file__))==plan['driver_sha256']
assert not (HERE/'maven-acquisition-started.json').exists()
initial=snapshot(OLD)
old_digest=hashlib.sha256(''.join(f'{path}\0{digest}\n' for path,digest in initial.items()).encode()).hexdigest()
assert old_digest==plan['prior_cache_sha256']
for relative,digest in initial.items():
    path=OLD/relative
    if path.suffix not in ('.pom','.jar'):
        continue
    sha1=initial.get(relative+'.sha1')
    if sha1 is None:
        fallback=path.with_suffix(path.suffix+'.md5')
        if fallback.is_file():
            assert hashlib.md5(path.read_bytes(),usedforsecurity=False).hexdigest()==fallback.read_text().strip()
        else:
            assert digest==plan['root_sha256'][relative]
    else:
        expected=(OLD/(relative+'.sha1')).read_text().strip()
        assert hashlib.sha1(path.read_bytes()).hexdigest()==expected
assert shutil.disk_usage(ROOT).free >= 52*1024**3
cache=WORK/'cache/solve'
assert not cache.exists()
write(HERE/'maven-acquisition-started.json',{'plan_sha256':sha(plan_path)})
shutil.copytree(OLD,cache,ignore=shutil.ignore_patterns('*.lastUpdated'))
result=collect(plan,cache)
files=snapshot(cache)
assert all(files[path]==digest for path,digest in initial.items()
           if not path.endswith(('.lastUpdated','_remote.repositories')))
for variant in ('reference','missing','legacy-namespace'):
    target=WORK/'cache'/variant
    shutil.copytree(cache,target)
    assert snapshot(target)==files
result.update({'cache_files':len(files),'cache_bytes':sum((cache/path).stat().st_size for path in files),
               'artifact_lock_sha256':hashlib.sha256(json.dumps(files,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
               'prior_cache_preserved':snapshot(OLD)==initial,'task_executed':False})
assert result['prior_cache_preserved']
write(HERE/'maven-acquisition-result.json',result)
write(WORK/'maven-cache-lock.json',files)
print(json.dumps({key:value for key,value in result.items() if key!='completed'}))
