"""Stage the exact original Spring reference inputs and pure verifier tools."""
import hashlib
import json
import shutil
import stat
import urllib.request
from io import BytesIO
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep/skillsbench-spring-reference-20261105'
ORIGINAL = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
SALES = ROOT / '.aeep/skillsbench-sales-reference-20261105'
PREV = HERE.parent / 'skillsbench-sales-reference-20261105'
WHEELS = {
    ('pytest', '8.4.1'): '539c70ba6fcead8e78eebbf1115e8b589e7565830d7d006a8723f19ac8a0afb7',
    ('pytest-json-ctrf', '0.3.5'): 'e82fd1d69be2f92385bc33540063e5ad7b17b36de67764c84f3ceb9815a895e9',
    ('pygments', '2.19.1'): '9ea1544ad55cecf4b8242fab6dd35a93bbce657034b0611ee383099054ab6d8c',
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def read(url, limit):
    with urllib.request.urlopen(url, timeout=20) as response:
        assert response.url.startswith(('https://pypi.org/', 'https://files.pythonhosted.org/'))
        result = response.read(limit + 1)
    assert len(result) <= limit
    return result


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('xb') as stream:
        stream.write(data)


pack = json.loads((HERE.parent/'skillsbench-transport-20261103/task-only-pack.json').read_bytes())
assert pack['source']['revision'] == '9a1f4dd5f7659f75707435da3ce854b6e48321d1'
task = next(x for x in pack['tasks'] if x['task_id']=='spring-boot-jakarta-migration')
for name in ('solve','protected','tools','wheels'):
    (WORK/name).mkdir(mode=0o700)
for asset in task['assets']:
    source = ORIGINAL/asset['path']
    raw = source.read_bytes()
    assert sha(raw)==asset['sha256'] and len(raw)==asset['bytes']
    if asset['role']=='input':
        relative = asset['path'].split('/workspace/',1)[1]
        write(WORK/'solve'/relative,raw)
    elif source.name in ('solve.sh','test_outputs.py'):
        write(WORK/'protected'/source.name,raw)
for name in ('observe.py', 'repository_suite_native_capture.py'):
    shutil.copyfile(SALES/'protected'/name, WORK/'protected'/name)
assert (WORK/'protected/observe.py').read_bytes() == (PREV/'observe.py').read_bytes()
packages=[]
for (name,version),expected in WHEELS.items():
    meta=json.loads(read(f'https://pypi.org/pypi/{name}/{version}/json',512*1024))
    selected=next(x for x in meta['urls'] if x['digests']['sha256']==expected)
    assert selected['filename'].endswith('-py3-none-any.whl')
    raw=read(selected['url'],2*1024**2)
    assert sha(raw)==expected and len(raw)==selected['size']
    write(WORK/'wheels'/selected['filename'],raw)
    packages.append({'project':name,'version':version,'filename':selected['filename'],'sha256':expected,
                     'url':selected['url'],'bytes':len(raw),'requires_dist':meta['info']['requires_dist']})
for row in json.loads((PREV/'wheel-closure.json').read_bytes()):
    if row['project'] not in WHEELS and row['project'] in ('packaging','pluggy','iniconfig'):
        raw=(SALES/'wheels'/row['filename']).read_bytes()
        assert sha(raw)==row['sha256']
        write(WORK/'wheels'/row['filename'],raw)
        packages.append(row)
assert len(packages)==6
for wheel in (WORK/'wheels').glob('*.whl'):
    with ZipFile(BytesIO(wheel.read_bytes())) as archive:
        entries=archive.infolist()
        assert sum(x.file_size for x in entries)<=16*1024**2
        for member in entries:
            name=PurePosixPath(member.filename)
            assert not name.is_absolute() and '..' not in name.parts and '\\' not in member.filename
            assert not stat.S_ISLNK(member.external_attr >> 16)
            if not member.is_dir():
                assert not member.filename.endswith('.pth')
                write(WORK/'tools'/str(name),archive.read(member))
result={'toolchain':packages,'protected_task_assets':17,'verifier_and_oracle_bytes_preserved':True,
        'no_package_code_executed':True,'maven_lock_ready':False}
with (HERE/'toolchain.json').open('x') as stream:
    json.dump(result,stream,indent=2)
    stream.write('\n')
print(json.dumps({'tools':len(packages),'input_files':17,'task_executed':False}))
