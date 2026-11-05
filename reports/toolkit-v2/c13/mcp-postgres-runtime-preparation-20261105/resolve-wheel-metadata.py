"""Read PyPI wheel metadata for the pinned Linux MCP and verifier runtime."""
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT/'.aeep'/HERE.name
WHEEL = ROOT/'.aeep/mcp-postgres-closure-20261104/postgres_mcp-0.3.0-py3-none-any.whl'
PIN = '455dd71ed8deab77a67af2468e6f059dd0f114e05c0031ab47306a7048dc30bf'
assert hashlib.sha256(WHEEL.read_bytes()).hexdigest() == PIN
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
WORK.mkdir(mode=0o700)
env = {'HOME':str(WORK),'PATH':'/usr/bin:/bin','LC_ALL':'C','PIP_CONFIG_FILE':'/dev/null',
       'PYTHONDONTWRITEBYTECODE':'1','TMPDIR':str(WORK)}
report = WORK/'pip-resolution.json'
args = [sys.executable,'-m','pip','--isolated','--disable-pip-version-check','--no-cache-dir',
        'install','--dry-run','--ignore-installed','--only-binary=:all:','--index-url','https://pypi.org/simple',
        '--timeout','10','--retries','0','--platform','manylinux_2_28_x86_64',
        '--platform','manylinux_2_17_x86_64','--platform','manylinux2014_x86_64',
        '--python-version','3.12','--implementation','cp','--abi','cp312',
        '--report',str(report),str(WHEEL),'psycopg2-binary==2.9.10']
started = time.perf_counter()
with (WORK/'pip.log').open('xb') as stream:
    outcome = subprocess.run(args,env=env,cwd=WORK,stdin=subprocess.DEVNULL,
                             stdout=stream,stderr=subprocess.STDOUT,timeout=120)
assert outcome.returncode == 0
raw = json.loads(report.read_bytes())
rows = []
for entry in raw['install']:
    metadata = entry['metadata']
    info = entry['download_info']
    url = urlsplit(info['url'])
    filename = unquote(url.path).split('/')[-1]
    assert filename.endswith('.whl') and not url.query and not url.fragment
    if url.scheme=='file':
        assert Path(unquote(url.path)) == WHEEL
        sha = PIN
    else:
        assert url.scheme=='https' and url.hostname=='files.pythonhosted.org' and not url.username
        sha = info['archive_info']['hashes']['sha256']
    assert len(sha) == 64
    rows.append({'name':metadata['name'],'version':metadata['version'],'filename':filename,'sha256':sha,
                 'origin':info['url'] if url.scheme=='https' else 'retained postgres_mcp wheel',
                 'requires_python':metadata.get('requires_python'),'requires_dist':metadata.get('requires_dist',[]),
                 'license_expression':metadata.get('license_expression'),'requested':entry['requested']})
assert 2 <= len(rows) <= 100
assert {row['name'].lower().replace('_','-') for row in rows if row['requested']} == {'postgres-mcp','psycopg2-binary'}
assert shutil.disk_usage(ROOT).free >= 50*1024**3
evidence = {'passed':True,'pip_version':raw['pip_version'],'target':'CPython 3.12 Linux amd64',
            'roots':{'postgres-mcp':'0.3.0','psycopg2-binary':'2.9.10'},
            'artifact_count':len(rows),'artifacts':sorted(rows,key=lambda item:item['name'].lower()),
            'duration_seconds':time.perf_counter()-started,'offline_installation_verified':False,
            'dependency_markers_require_linux_review':True,'packages_installed':0,'models':0,'services_started':False}
with (HERE/'wheel-candidate-lock.json').open('x') as stream:
    json.dump(evidence,stream,indent=2)
    stream.write('\n')
print(json.dumps({key:value for key,value in evidence.items() if key!='artifacts'}))
