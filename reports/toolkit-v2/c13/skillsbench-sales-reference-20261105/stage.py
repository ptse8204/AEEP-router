"""Stage only the exact original task files and pure verifier wheels as data."""
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
WORK = ROOT / '.aeep/skillsbench-sales-reference-20261105'
ORIGINAL = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
TASK = 'sales-pivot-analysis'
PIN = '9a1f4dd5f7659f75707435da3ce854b6e48321d1'
WHEELS = {
    ('pytest', '8.3.4'): '50e16d954148559c9a74109af1eaf0c945ba2d8f30f0a3d3335edde19788b6f6',
    ('pytest-json-ctrf', '0.3.6'): '82231614ff52b5eec14e214761eb2d785b45c062775b315a67b44659a42f5a2d',
    ('packaging', '25.0'): '29572ef2b1f17581046b3a2227d5c611fb25ec70ca1ba8554b24b0e69331a484',
    ('pluggy', '1.6.0'): 'e920276dd6813095e9377c0bc5566d94c932c33b27a3e3945d8389c374dd4746',
    ('iniconfig', '2.1.0'): '9deba5723312380e77435581c6bf4935c94cbfab9b1ed33ef8d238ea168eb760',
}


def sha(value):
    return hashlib.sha256(value).hexdigest()


def fetch(url, limit):
    with urllib.request.urlopen(url, timeout=15) as response:
        assert response.url.startswith(('https://pypi.org/', 'https://files.pythonhosted.org/'))
        data = response.read(limit + 1)
    assert len(data) <= limit
    return data


def write(path, data):
    with path.open('xb') as stream:
        stream.write(data)


assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
pack_path = HERE.parent / 'skillsbench-transport-20261103/task-only-pack.json'
pack = json.loads(pack_path.read_bytes())
assert pack['source']['revision'] == PIN
task = next(t for t in pack['tasks'] if t['task_id'] == TASK)
for name in ('solve', 'missing', 'wrong-workbook', 'protected', 'tools', 'wheels'):
    (WORK / name).mkdir(mode=0o700)
for asset in task['assets']:
    path = ORIGINAL / asset['path']
    data = path.read_bytes()
    assert len(data) == asset['bytes'] and sha(data) == asset['sha256']
    if asset['role'] == 'input':
        for variant in ('solve', 'missing', 'wrong-workbook'):
            write(WORK / variant / path.name, data)
    elif path.name == 'solve.sh':
        write(WORK / 'protected/solve.sh', data)
    elif path.name == 'test_outputs.py':
        write(WORK / 'protected/test_outputs.py', data)
write(WORK / 'wrong-workbook/demographic_analysis.xlsx', (WORK / 'wrong-workbook/income.xlsx').read_bytes())
write(WORK / 'protected/observe.py', (HERE / 'observe.py').read_bytes())
write(WORK / 'protected/repository_suite_native_capture.py',
      (ROOT / 'integrations/assessment-runtime/repository_suite_native_capture.py').read_bytes())
rows = []
for (project, version), expected in WHEELS.items():
    response = json.loads(fetch(f'https://pypi.org/pypi/{project}/{version}/json', 512*1024))
    artifact = next(row for row in response['urls'] if row['digests']['sha256'] == expected)
    assert artifact['filename'].endswith('-py3-none-any.whl')
    raw = fetch(artifact['url'], 512*1024)
    assert sha(raw) == expected and len(raw) == artifact['size']
    write(WORK / 'wheels' / artifact['filename'], raw)
    with ZipFile(BytesIO(raw)) as archive:
        total = 0
        for member in archive.infolist():
            name = PurePosixPath(member.filename)
            assert not name.is_absolute() and '..' not in name.parts and '\\' not in member.filename
            assert not stat.S_ISLNK(member.external_attr >> 16)
            if member.is_dir():
                continue
            total += member.file_size
            assert total <= 8 * 1024**2 and not member.filename.endswith('.pth')
            target = WORK / 'tools' / str(name)
            target.parent.mkdir(parents=True, exist_ok=True)
            write(target, archive.read(member))
    rows.append({'project': project, 'version': version, 'filename': artifact['filename'],
                 'sha256': expected, 'size': len(raw), 'url': artifact['url'],
                 'requires_dist': response['info']['requires_dist']})
with (HERE / 'wheel-closure.json').open('x') as out:
    json.dump(rows, out, indent=2)
    out.write('\n')
