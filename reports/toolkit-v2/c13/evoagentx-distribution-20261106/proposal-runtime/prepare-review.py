"""Pin a COPY-only repeat for the proposal-only import repair."""

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
PARENT = HERE.parent
ROOT = PARENT.parents[3]
WORK = ROOT / '.aeep' / PARENT.name
CONTEXT = WORK / 'proposal-runtime-context'
AFLOW = PARENT.parent / 'proposal-optimizer-preparation-20261105/socket-boundary'
NAME = 'aeep-evoagentx-proposal-runtime-20261106'
TAG = 'aeep-toolkit-v2/evoagentx:d77fd6b9-proposal-arm64-20261106'


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def put(path, text):
    with path.open('x') as out:
        out.write(text)


def write(path, obj):
    put(path, json.dumps(obj, indent=2) + '\n')


old_path = PARENT/'evoagentx-runtime-build-review.json'
old, diagnosis = read(old_path), read(PARENT/'evoagentx-runtime-diagnosis.json')
assert diagnosis['review_sha256'] == sha(old_path) and diagnosis['first_missing_module'] == 'docker'
overlay_path = HERE/'overlay-report.json'
overlay = read(overlay_path)
assert overlay['planner_and_graph_source_unchanged'] and not overlay['after']['missing_static_modules']
assert len(overlay['changed_support_files']) == 5
assert shutil.disk_usage(ROOT).free >= 54 * 1024**3

docker, env = old['docker'], old['environment']
fmt = '{{json .Id}} {{json .Architecture}} {{json .Os}} {{json .RootFS.Layers}}'
base = diagnosis['image']
tag = read(PARENT/'evoagentx-runtime-result.json')['runtime_image_tag']
raw = subprocess.check_output([*docker,'image','inspect','--format',fmt,tag],env=env,text=True,timeout=10)
decoder, fields = json.JSONDecoder(), []
while raw.strip():
    value, end = decoder.raw_decode(raw.strip())
    fields.append(value)
    raw = raw.strip()[end:]
assert fields[:3] == [base,'arm64','linux']
assert fields[3][:len(old['base_identity'][3])] == old['base_identity'][3]
usage = subprocess.check_output([*docker,'system','df','--format','{{.Type}} {{.Size}}'],
                                env=env,text=True,timeout=30).splitlines()
assert len(usage) == 4

source_profile = AFLOW/'seccomp.json'
profile = read(source_profile)
assert profile['defaultAction'] == 'SCMP_ACT_ERRNO'
names = {name for rule in profile['syscalls'] for name in rule['names']}
assert not names & {'socket','socketcall','socketpair','connect','bind','listen','sendmsg','pidfd_getfd'}
profile['syscalls'] += [
    {'names':['socketpair'], 'action':'SCMP_ACT_ALLOW',
     'args':[{'index':0,'value':1,'op':'SCMP_CMP_EQ'}]},
    {'names':['sendto','recvfrom'], 'action':'SCMP_ACT_ALLOW'},
]
profile_path = HERE/'seccomp.json'
write(profile_path, profile)

source_check = (AFLOW/'check.py').read_text()
start = source_check.index('def socket_boundary():')
end = source_check.index('\n\ndef main():',start)
probe = source_check[start:end]
start = probe.index('    try:\n        socket.socketpair()')
end = probe.index('    ipv4 =',start)
probe = probe[:start] + """    try:
        socket.socketpair(socket.AF_INET)
        raise RuntimeError('non-Unix socketpair unexpectedly succeeded')
    except PermissionError as error:
        assert error.errno == errno.EPERM
    left, right = socket.socketpair(socket.AF_UNIX)
    with left, right:
        assert left.send(b'aeep') == 4 and right.recv(4) == b'aeep'
""" + probe[end:]
probe = probe.replace("'socketpair_denied': True",
                      "'non_unix_socketpair_denied': True, 'local_unix_pair_verified': True")
probe = 'import os\nimport socket\nfrom pathlib import Path\n\n\n' + probe + '\n'
probe_path = HERE/'check_socket_boundary.py'
compile(probe,str(probe_path),'exec')
put(probe_path,probe)

check = (PARENT/'check-runtime.py').read_text()
line = '        from evoagentx.workflow.workflow_generator import WorkFlowGenerator\n'
assert check.count(line) == 1
check = check.replace(line, '').replace('        from evoagentx.actions.task_planning', line + '        from evoagentx.actions.task_planning',1)
line = '        port = Parameter('
assert check.count(line) == 1
check = check.replace(line, """        from typing import Literal
        from evoagentx.agents.agent import Agent
        from evoagentx import tools
        assert Agent.model_fields['use_long_term_memory'].annotation == Literal[False]
        assert tools.__all__ == ['Tool', 'Toolkit']
""" + line,1)
check_path = HERE/'check-runtime.py'
compile(check,str(check_path),'exec')
put(check_path,check)

prior = PARENT/'run-runtime.py'
assert sha(prior) == old['assets'][str(prior)]
driver_path = HERE/'run-runtime.py'
runner = prior.read_text()
runner = runner.replace('ROOT = HERE.parents[3]','ROOT = HERE.parents[4]')
runner = runner.replace('evoagentx-runtime-20261106','evoagentx-proposal-runtime-20261106')
runner = runner.replace("parser.add_argument('--execute-delegated',required=True)","parser.add_argument('--execute-approved',required=True)")
runner = runner.replace("authority = read(HERE/'evoagentx-runtime-build-authority.json')","authority = read(HERE/'operator-approval.json')")
runner = runner.replace("args.execute_delegated == identity == authority['review_sha256'] and authority['first_attempt']",
                        "args.execute_approved == identity == authority['review_sha256'] and authority['approved'] is True")
compile(runner,str(driver_path),'exec')
put(driver_path,runner)
spec = importlib.util.spec_from_file_location('evoagentx_proposal_runner',driver_path)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)

CONTEXT.mkdir(mode=0o700)
copies = []
for name, record in overlay['changed_support_files'].items():
    source = WORK/'proposal-overlay'/name
    assert sha(source) == record['overlay_sha256']
    target = CONTEXT/'overlay'/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    copies.append(f'COPY overlay/{name} /opt/evoagentx-source/{name}')
for source in (check_path,probe_path):
    shutil.copyfile(source,CONTEXT/source.name)
put(CONTEXT/'Dockerfile','\n'.join((
    'FROM '+tag,*copies,'COPY check-runtime.py check_socket_boundary.py /opt/','',
)))
assert not any(line.startswith('RUN ') for line in (CONTEXT/'Dockerfile').read_text().splitlines())
check_prefix = [arg.replace(old['container_name'],NAME).replace(str(source_profile),str(profile_path))
                for arg in old['check_prefix']]
assets = {**old['assets'],**{str(path):sha(path) for path in (
    Path(__file__),old_path,overlay_path,HERE/'prepare-overlay.py',PARENT/'evoagentx-runtime-diagnosis.json',
    PARENT/'evoagentx-runtime-result.json',PARENT/'evoagentx-runtime-ledger.json',
    AFLOW/'profile-source.json',AFLOW/'MOBY-LICENSE',driver_path,profile_path,probe_path,check_path,
)}}
review = {
    **old,'purpose':'One explicit EvoAgentX repeat with a source-bound proposal-only overlay.',
    'implementation_source':verification_source_digest(ROOT),'context':str(CONTEXT),
    'context_inventory_sha256':content_digest(driver.inventory(CONTEXT)),
    'base_reference':tag,'base_identity':fields,'tag':TAG,'container_name':NAME,'docker_usage':usage,
    'assets':assets,'build_command':[*docker,'build','--pull=false','--network=none','--platform=linux/arm64',
        '--provenance=false','--sbom=false','--tag',TAG,str(CONTEXT)],
    'check_prefix':check_prefix,'expires_at':(datetime.now(UTC)+timedelta(days=2)).isoformat(),
    'previous_review_sha256':sha(old_path),'previous_settled_operations':diagnosis['settled_operations'],
    'copy_only_build':True,'install':False,'model_turns':0,'cash_usd':'0',
    'scope':'Retain source and wheels. Adapt five support files. Permit private Unix socketpairs only. '
            'No external connection, toolkits, persistent memory, model-backed proposal or generated code.',
}
path = HERE/'evoagentx-runtime-build-review.json'
write(path,review)
print(sha(path))
