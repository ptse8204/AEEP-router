"""Review one exact isolated EvoAgentX build and graph-builder smoke check."""

import hashlib
import importlib.util
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT / '.aeep' / HERE.name
PREVIOUS = HERE.parent / 'proposal-optimizer-preparation-20261105'
AUTHORITY = HERE.parent / 'pipeline-standing-authority-20261104.json'
PARENT = PREVIOUS / 'aflow-runtime-build-review.json'
PROBE = PREVIOUS / 'socket-boundary'
CONTEXT = WORK / 'runtime-context'
TAG = 'aeep-toolkit-v2/evoagentx:d77fd6b9-cp312-arm64-20261106'
NAME = 'aeep-evoagentx-first-runtime-20261106'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')


def stage(src, dst, expected):
    assert src.is_file() and not src.is_symlink() and sha(src) == expected
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


old = read(PARENT)
sandbox = read(PROBE / 'operation-review.json')
proof = read(PROBE / 'result.json')
assert proof['passed'] and proof['cleanup_verified'] and proof['review_sha256'] == sha(PROBE/'operation-review.json')
assert sandbox['assets'][str(PROBE/'seccomp.json')] == sha(PROBE/'seccomp.json')
assert shutil.disk_usage(ROOT).free >= 54 * 1024**3
docker, env = old['docker'], {**old['environment'], 'HOME': str(WORK)}
usage = subprocess.check_output([*docker, 'system', 'df', '--format', '{{.Type}} {{.Size}}'],
                                env=env, timeout=25, text=True).splitlines()
assert len(usage) == 4
subprocess.run([*docker, 'buildx', 'version'], check=True, env=env, capture_output=True, timeout=10)
subprocess.run([*docker, 'buildx', 'inspect'], check=True, env=env, capture_output=True, timeout=20)
version = subprocess.check_output([*docker, 'version', '--format', '{{.Server.Version}} {{.Server.GitCommit}}'],
                                   env=env, timeout=15, text=True).strip()
assert version.split() == [sandbox['engine_version'], sandbox['engine_revision_short']]

# Reuse the checked canonical build/check runner with this component's distinct
# identifiers and result contract. Retain the exact derived program with its review.
parent_driver = PREVIOUS / 'run-aflow-runtime.py'
assert sha(parent_driver) == old['assets'][str(parent_driver)]
runner = parent_driver.read_text()
runner = runner.replace('aflow-runtime-20261105', 'evoagentx-runtime-20261106')
runner = runner.replace('aflow', 'evoagentx').replace('AFlow', 'EvoAgentX')
runner = runner.replace("parsed['actual_graph_parser_passed'] is True and parsed['optimizer_calibration'] == 'UNSTARTED'",
                        "parsed['actual_graph_builder_passed'] is True and parsed['actual_proposal_generation'] is False")
line = "    assert inspect(review['base_reference']) == review['base_identity']\n"
assert runner.count(line) == 2
runner = runner.replace(line, line + """
    version = subprocess.check_output([*docker, 'version', '--format', '{{.Server.Version}} {{.Server.GitCommit}}'],
                                      env=env, timeout=10, text=True)
    assert version.strip() == review['docker_server']
""", 1)
runner_path = HERE / 'run-runtime.py'
compile(runner, str(runner_path), 'exec')
with runner_path.open('x') as stream:
    stream.write(runner)
spec = importlib.util.spec_from_file_location('evoagentx_runtime_driver', runner_path)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

source = read(HERE / 'source-result.json')
wheels = read(HERE / 'acquisition-result.json')
inputs = read(PREVIOUS / 'aflow-runtime-inputs-result.json')
assert wheels['passed'] and len(wheels['artifacts']) == 87 and len(source['source_sha256']) == 262
assert all(not row['startup_hooks'] for row in wheels['artifacts'])
assert {row['name'] for row in wheels['artifacts'] if not row['notice_sha256']} == {
    'loguru', 'overdue', 'tokenizers', 'tqdm',
}
assert inputs['passed']
CONTEXT.mkdir(mode=0o700)
python = inputs['portable_python']
stage(Path(python['artifact']), CONTEXT/'cpython.tar.gz', python['sha256'])
for name, digest in source['source_sha256'].items():
    stage(Path(source['source_root'])/name, CONTEXT/'source'/name, digest)
requirements = []
for row in wheels['artifacts']:
    name = row['filename']
    stage(WORK/'wheelhouse'/name, CONTEXT/'wheels'/name, row['sha256'])
    requirements.append(f'{row["name"]}=={row["version"]} --hash=sha256:{row["sha256"]}')
(CONTEXT/'requirements.lock').write_text('\n'.join(sorted(requirements))+'\n')
stage(HERE/'check-runtime.py', CONTEXT/'check-runtime.py', sha(HERE/'check-runtime.py'))
stage(PROBE/'check.py', CONTEXT/'check_socket_boundary.py', sandbox['assets'][str(PROBE/'check.py')])
extract = ['/usr/local/bin/python3','-I','-B','-c',
           "import tarfile; tarfile.open('/opt/cpython.tar.gz').extractall('/opt/portable', filter='data')"]
install = ['/opt/portable/python/bin/python3.12','-I','-B','-m','pip','--isolated','install',
           '--no-index','--no-deps','--no-compile','--disable-pip-version-check','--require-hashes',
           '--find-links=/opt/wheels','--target=/opt/evoagentx-dependencies','-r','/opt/requirements.lock']
(CONTEXT/'Dockerfile').write_text('\n'.join((
    'FROM '+old['base_reference'], 'COPY cpython.tar.gz /opt/cpython.tar.gz', 'RUN '+json.dumps(extract),
    'COPY wheels/ /opt/wheels/', 'COPY requirements.lock /opt/requirements.lock', 'RUN '+json.dumps(install),
    'COPY source/ /opt/evoagentx-source/', 'COPY check-runtime.py check_socket_boundary.py /opt/',
    'USER 65534:65534', 'WORKDIR /tmp', '',
)))
assets = [PARENT, parent_driver, runner_path, Path(__file__), AUTHORITY, HERE/'check-runtime.py',
          HERE/'source-result.json', HERE/'acquisition-result.json', HERE/'verified-candidates.json',
          PROBE/'operation-review.json', PROBE/'result.json', PROBE/'seccomp.json', PROBE/'check.py',
          PREVIOUS/'aflow-runtime-inputs-result.json']
assets.extend(Path(path) for path in old['assets'] if path.endswith(('docker','docker-buildx','config.json')))
review = {
    'purpose':'First private offline source-based EvoAgentX build and typed graph-builder smoke check.',
    'implementation_source':verification_source_digest(ROOT), 'upstream_revision':source['revision'],
    'context':str(CONTEXT), 'context_inventory_sha256':content_digest(driver.inventory(CONTEXT)),
    'base_reference':old['base_reference'], 'base_identity':old['base_identity'],
    'docker':docker, 'environment':env, 'tag':TAG, 'container_name':NAME, 'docker_usage':usage,
    'docker_server':version, 'assets':{str(p):sha(p) for p in assets},
    'build_command':[*docker,'build','--pull=false','--network=none','--platform=linux/arm64',
                     '--provenance=false','--sbom=false','--tag',TAG,str(CONTEXT)],
    'check_prefix':[*docker,'run','--pull=never','--rm','--name',NAME,'--network=none','--read-only',
                    '--user','65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges',
                    '--security-opt=seccomp='+str(PROBE/'seccomp.json'),
                    '--env','HOME=/tmp','--env','OPENBLAS_NUM_THREADS=1',
                    '--env','LITELLM_LOCAL_MODEL_COST_MAP=True','--env','LITELLM_TELEMETRY=False',
                    '--env','DO_NOT_TRACK=1','--env','PYTHONDONTWRITEBYTECODE=1',
                    '--cpus=1','--memory=1g','--memory-swap=1g','--pids-limit=64',
                    '--tmpfs','/tmp:rw,noexec,nosuid,nodev,size=32m','--workdir','/tmp',
                    '--entrypoint','/opt/portable/python/bin/python3.12'],
    'check_args':['-I','-B','/opt/check-runtime.py'], 'ledger':old['ledger'],
    'expires_at':(datetime.now(UTC)+timedelta(hours=2)).isoformat(),
    'max_operations':2, 'max_reserved_seconds':340, 'cash_usd':'0','models':0,'automatic_retries':False,
    'retention':'Retain the runtime and existing resources. Auto-remove only the new check container.',
    'disposition':'Private engineering only. Wheel notices retained. No distribution, activation or actual proposal generation.',
}
path = HERE/'evoagentx-runtime-build-review.json'
write(path,review)
write(HERE/'evoagentx-runtime-build-authority.json',{
    'review_sha256':sha(path),'first_attempt':True,'standing_authority_sha256':sha(AUTHORITY),
})
print(sha(path))
