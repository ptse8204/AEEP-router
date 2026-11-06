"""Freeze the bounded private AFlow image context from reviewed inputs."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
import tarfile
from datetime import UTC, datetime, timedelta
from pathlib import Path, PurePosixPath

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
CONTEXT = WORK / 'aflow-linux-build-context'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
DOCKER = Path('/Applications/Docker.app/Contents/Resources/bin/docker')
BUILDX = Path('/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx')
CONFIG = ROOT / '.aeep/skillsbench-contained-graders-20261105/buildx-docker-config'
BASE = 'python:3.13-slim'
TAG = 'aeep-toolkit-v2/aflow:3f457218-cp312-arm64-20261105'
NAME = 'aeep-aflow-runtime-first-check-20261105'
SOCKET = '/Users/edwintse/.docker/run/docker.sock'

spec = importlib.util.spec_from_file_location('aflow_driver',HERE/'run-aflow-runtime.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
sha, read, write = driver.sha, driver.read, driver.write

assert shutil.disk_usage(ROOT).free >= 54 * 1024**3
subprocess.run(['/usr/bin/codesign','--verify',str(BUILDX)],check=True,timeout=10)
docker = [str(DOCKER),'--config',str(CONFIG),'--host','unix://'+SOCKET]
env = {'PATH':'/usr/bin:/bin','HOME':str(WORK),'LC_ALL':'C','DOCKER_BUILDKIT':'1'}
subprocess.run([*docker,'buildx','version'],env=env,check=True,timeout=15,capture_output=True)
subprocess.run([*docker,'buildx','inspect'],env=env,check=True,timeout=20,capture_output=True)
fmt = '{{json .Id}} {{json .Architecture}} {{json .Os}} {{json .RootFS.Layers}}'
parts = subprocess.check_output([*docker,'image','inspect','--format',fmt,BASE],env=env,timeout=10,text=True)
base = json.loads('['+parts.replace(' "arm64" ', ',"arm64",').replace('"linux" ', '"linux",')+']')
assert base[:3] == ['sha256:8d9d0b8bcf6506481eae4907c18f5e3e7902e629f5f6d684f9e7c32e85e3ddf0','arm64','linux']
usage = subprocess.check_output([*docker,'system','df','--format','{{.Type}} {{.Size}}'],env=env,timeout=30,text=True).splitlines()
assert len(usage)==4

inputs = read(HERE/'aflow-runtime-inputs-result.json')
wheel_audit = read(HERE/'aflow-wheel-acquisition-result.json')
closure = read(HERE/'aflow-source-closure.json')
assert inputs['passed'] and wheel_audit['passed']
assert closure['not_in_wheel_lock_or_standard_library'] == ['data']
assert closure['source_revision'] == inputs['source_revision']
CONTEXT.mkdir(mode=0o700)
python_archive = Path(inputs['portable_python']['artifact'])
assert sha(python_archive) == inputs['portable_python']['sha256']
with tarfile.open(python_archive,'r:gz') as archive:
    members = archive.getmembers()
    assert sum(member.size for member in members) <= 256*1024**2
    for member in members:
        path = PurePosixPath(member.name)
        assert not path.is_absolute() and '..' not in path.parts and path.parts[0]=='python'
        assert member.isdir() or member.isfile() or member.issym() or member.islnk()
    for member in members:
        tarfile.data_filter(member, '/opt/portable')
shutil.copyfile(python_archive, CONTEXT / 'cpython.tar.gz')

wheels = CONTEXT/'wheels'
wheels.mkdir()
requirements = []
for row in wheel_audit['artifacts']:
    name = row['filename']
    file = WORK/'aflow-wheelhouse'/name
    assert sha(file) == row['sha256'] and file.stat().st_size == row['bytes']
    shutil.copyfile(file,wheels/name)
    requirements.append(f'{row["name"]}=={row["version"]} --hash=sha256:{row["sha256"]}')
assert len(requirements)==31
(CONTEXT/'requirements.lock').write_text('\n'.join(sorted(requirements))+'\n')
source_hashes = {**inputs['verified_source_files'],
                 **{name:row['sha256'] for name,row in closure['source_files'].items()}}
source = WORK/'aflow-runtime-inputs/source'
for name, digest in source_hashes.items():
    if name == 'run.py':
        continue  # The upstream entry point downloads its standard datasets.
    target = CONTEXT/'source'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    assert sha(source/name) == digest
    shutil.copyfile(source/name,target)
shutil.copyfile(HERE/'check-aflow-runtime.py',CONTEXT/'check-aflow-runtime.py')
extract = [
    "/usr/local/bin/python3", "-I", "-B", "-c",
    "import tarfile; tarfile.open('/opt/cpython.tar.gz').extractall('/opt/portable', filter='data')",
]
install = [
    "/opt/portable/python/bin/python3.12", "-I", "-B", "-m", "pip", "--isolated", "install",
    "--no-index", "--no-deps", "--no-compile", "--disable-pip-version-check", "--require-hashes",
    "--find-links=/opt/wheels", "--target=/opt/aflow-dependencies", "-r", "/opt/requirements.lock",
]
(CONTEXT/'Dockerfile').write_text("\n".join([
    "FROM " + BASE,
    "COPY cpython.tar.gz /opt/cpython.tar.gz",
    "RUN " + json.dumps(extract),
    "COPY wheels/ /opt/wheels/",
    "COPY requirements.lock /opt/requirements.lock",
    "RUN " + json.dumps(install),
    "COPY source/ /opt/aflow-source/",
    "COPY check-aflow-runtime.py /opt/check-aflow-runtime.py",
    "USER 65534:65534",
    "WORKDIR /tmp",
    "",
]))
assets = [
    HERE/'run-aflow-runtime.py',HERE/'prepare-aflow-runtime.py',HERE/'check-aflow-runtime.py',
    HERE/'aflow-runtime-inputs-result.json',HERE/'aflow-wheel-acquisition-result.json',
    HERE/'aflow-source-closure.json',AUTHORITY,DOCKER,BUILDX,CONFIG/'config.json',
]
review = {
    'purpose':'First offline build and bounded actual AFlow graph-parser check. No optimizer cycle or model authority.',
    'implementation_source':verification_source_digest(ROOT),
    'upstream_revision':inputs['source_revision'],'context':str(CONTEXT),
    'context_inventory_sha256':content_digest(driver.inventory(CONTEXT)),
    'base_reference':BASE,'base_identity':base,'docker':docker,'environment':env,
    'tag':TAG,'container_name':NAME,'docker_usage':usage,
    'assets':{str(p):sha(p) for p in assets},
    'build_command':[*docker,'build','--pull=false','--network=none','--platform=linux/arm64',
                    '--provenance=false','--sbom=false','--tag',TAG,str(CONTEXT)],
    'check_prefix':[*docker,'run','--pull=never','--rm','--name',NAME,'--network=none',
                    '--read-only','--user','65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges',
                    '--cpus=1','--memory=512m','--memory-swap=512m','--pids-limit=64',
                    '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=32m','--workdir','/tmp',
                    '--entrypoint','/opt/portable/python/bin/python3.12'],
    'check_args':['-I','-B','/opt/check-aflow-runtime.py'],
    'ledger':read(HERE.parent/'skillsbench-prebuilt-acquisition-20261104/operation-review.json')['ledger'],
    'expires_at':(datetime.now(UTC)+timedelta(hours=2)).isoformat(),
    'cash_usd':'0','models':0,'automatic_retries':False,
    'retention':'Keep new runtime and existing resources. Remove only the new disposable check container.',
}
path = HERE/'aflow-runtime-build-review.json'
write(path,review)
write(HERE/'aflow-runtime-build-authority.json',{'review_sha256':sha(path),'first_attempt':True,
      'standing_authority_sha256':sha(AUTHORITY)})
print(sha(path))
