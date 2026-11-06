"""Bind the first offline planner prompt capture to the retained EvoAgentX image."""

import hashlib
import json
import shutil
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = PARENT.parents[3]
PROPOSAL = PARENT/'proposal-runtime'
AFLOW = PARENT.parent/'proposal-optimizer-preparation-20261105/socket-boundary'
AUTHORITY = PARENT.parent/'pipeline-standing-authority-20261104.json'


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as out:
        out.write(json.dumps(value, indent=2) + '\n')


prior = read(PROPOSAL/'evoagentx-runtime-build-review.json')
result = read(PROPOSAL/'evoagentx-runtime-result.json')
assert result['passed'] and result['accounting_settled'] and result['observed']['actual_graph_builder_passed']
assert result['review_sha256'] == sha(PROPOSAL/'evoagentx-runtime-build-review.json')
assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
assert all(sha(path) == expected for path, expected in prior['assets'].items())
case = read(HERE/'case.json')
assert len(case['ports']) == 4 and len(case['goal']) < 256 and len(case['suggestion']) < 1024
work = ROOT/'.aeep'/PARENT.name/'planner-handoff'
work.mkdir(mode=0o700)
docker = prior['docker']
version = subprocess.check_output([*docker,'version','--format','{{.Server.Version}} {{.Server.GitCommit}}'],
                                  env=prior['environment'],text=True,timeout=10)
assert version.strip() == prior['docker_server']
name = 'aeep-evoagentx-planner-handoff-20261106'
argv = [item.replace(prior['container_name'],name) for item in prior['check_prefix']]
mounts = []
for source, target in (('planner-bridge.py','/opt/aeep-planner-bridge.py'),('case.json','/opt/aeep-reviewed-case.json')):
    mounts.extend(('--mount',f'type=bind,src={HERE/source},dst={target},readonly'))
argv[argv.index('--entrypoint'):argv.index('--entrypoint')] = mounts
argv.extend((result['runtime_image_id'],'-I','-B','/opt/aeep-planner-bridge.py','prepare'))

# Preserve the one-attempt ledger and ownership checks from the reviewed probe.
runner = (AFLOW/'run.py').read_text()
runner = runner.replace('aflow-runtime-socket-boundary-20261106','evoagentx-planner-handoff-20261106')
runner = runner.replace('aflow.runtime.namespace-check','evoagentx.runtime.planner-handoff')
runner = runner.replace('aflow_runtime_socket_boundary','evoagentx_planner_handoff')
runner = runner.replace('toolkit_aflow_runtime_scope','toolkit_evoagentx_planner_scope')
runner = runner.replace('One offline graph parser and namespace check','One offline actual planner handoff check')
runner = runner.replace('from pathlib import Path','from pathlib import Path\nimport os')
start = runner.index("            assert raw.output.get('generated_code_executed')")
end = runner.index("            result['passed']=True",start)
runner = runner[:start] + """            observed=raw.output
            assert observed['status']=='request_ready' and observed['relay_calls']==1
            messages=observed['messages']
            case=read(HERE/'case.json')
            assert [row['role'] for row in messages]==['system','user']
            assert all(set(row)=={'role','content'} for row in messages)
            assert case['goal'] in messages[1]['content'] and case['suggestion'] in messages[1]['content']
            data=json.dumps(messages,separators=(',',':'),sort_keys=True,allow_nan=False).encode()
            assert len(data)<=32768 and hashlib.sha256(data).hexdigest()==observed['request_sha256']
            assert observed['boundary']['local_unix_pair_verified'] and observed['boundary']['inherited_sockets']==0
            assert not containers()
            dest=Path(review['private_request'])
            with os.fdopen(os.open(dest,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600),'wb') as out:
                out.write(data)
            result.update(request_sha256=observed['request_sha256'],request_bytes=len(data),
                          relay_calls=1,boundary=observed['boundary'],cleanup_verified=True,
                          proposal_generated=False)
""" + runner[end:]
runner = runner.replace("parser.add_argument('--execute-approved',required=True)","parser.add_argument('--execute-delegated',required=True)")
runner = runner.replace("args.execute_approved==identity","args.execute_delegated==identity")
runner = runner.replace("assert read(HERE/'operator-approval.json')=={'approved':True,'review_sha256':identity}",
                        "authority=read(HERE/'delegated-authority.json')\n    assert authority['first_attempt'] and authority['review_sha256']==identity")
path = HERE/'run.py'
compile(runner,str(path),'exec')
with path.open('x') as out:out.write(runner)
assets = {**prior['assets'], **{str(path):sha(path) for path in (
    PROPOSAL/'evoagentx-runtime-build-review.json',PROPOSAL/'evoagentx-runtime-result.json',
    PROPOSAL/'evoagentx-runtime-ledger.json',PROPOSAL/'seccomp.json',AFLOW/'run.py',AUTHORITY,
    HERE/'case.json',HERE/'planner-bridge.py',Path(__file__),path,
)}}
review = {
    'scope':'First isolated capture of the actual EvoAgentX generate_plan request. No reply or model invocation.',
    'assets':assets,'image':result['runtime_image_id'],'docker':docker,'environment':prior['environment'],
    'argv':argv,'container_name':name,'ledger':prior['ledger'],
    'engine_version':version.split()[0],'engine_revision_short':version.split()[1],
    'private_request':str(work/'request.json'),'maximum_operations':1,'maximum_reserved_seconds':70,
    'expires_at':(datetime.now(UTC)+timedelta(hours=2)).isoformat(),
    'models':0,'cash_usd':'0','automatic_retries':False,'provider_disclosure':False,
}
path = HERE/'operation-review.json'
write(path,review)
identity = sha(path)
write(HERE/'delegated-authority.json',{'review_sha256':identity,'first_attempt':True,
                                      'standing_authority_sha256':sha(AUTHORITY)})
print(identity)
