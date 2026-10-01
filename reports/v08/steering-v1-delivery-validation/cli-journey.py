import hashlib,json,os,subprocess,sys,time
from datetime import timedelta
from pathlib import Path
from aeep.assessment.onboarding import reference_spec
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import Manifest,TaskScope,ExecutorKind,utc_now
from aeep.assessment.verification import verification_source_digest
root=Path.cwd()
project=(root/'reports/v08/steering-v1-delivery-validation/cli-project').resolve()
project.mkdir(exist_ok=True)
binary=Path('/Users/edwintse/.local/bin/codex').resolve()
with binary.open('rb') as stream: pin='sha256:'+hashlib.file_digest(stream,'sha256').hexdigest()
boundary=NativeSandboxConfig(binary=str(binary),binary_sha256=pin,project_root=str(project),read_roots=[str(Path(sys.prefix).resolve())])
spec=reference_spec('csv').model_copy(update={'kind':ExecutorKind.COMMAND,'config':{
'argv':[sys.executable,'-I','-c','import csv,io,json,sys; v=json.load(sys.stdin); print(json.dumps({"records":list(csv.DictReader(io.StringIO(v["text"]),delimiter=v["delimiter"]))}))'],
'argv_literal':True,'stdin_json':True,'timeout_seconds':10,'output':{'type':'json'},'native_sandbox':boundary.model_dump(mode='json')}})
manifest=project/'aeep.json'
manifest.write_text(Manifest(database=str(project/'.aeep'/'state.db'),executors=[spec]).model_dump_json(indent=2)+'\n')
scope=TaskScope(scope_id='cli-journey',project_root=str(project),executor_fingerprints={spec.id:executor_fingerprint(spec)},max_attempts=2,max_attempt_seconds=10,expires_at=utc_now()+timedelta(minutes=30))
file=project/'scope.json'
file.write_text(scope.model_dump_json(indent=2)+'\n')
rows=[]
env={**os.environ,'PYTHONPATH':str(root/'src')}
def run(args,success=True):
    argv=[sys.executable,'-m','aeep',*args]
    started=time.perf_counter()
    result=subprocess.run(argv,env=env,capture_output=True,text=True,timeout=30,check=False)
    assert (result.returncode==0)==success,(args,result.stdout,result.stderr)
    payload=json.loads(result.stdout)
    rows.append({'argv':argv,'exit_code':result.returncode,'seconds':time.perf_counter()-started,'result':payload,'stderr':result.stderr})
    return payload
base=['task','-m',str(manifest)]
defined=run([*base,'define',str(file)])
run(['assess','-m',str(manifest),'review',defined['digest']])
activation=run([*base,'activate',scope.scope_id])['activation_id']
call=['tool-call','aeep_csv','--profile','task','--task-activation',activation,'-m',str(manifest),'-a',json.dumps({'text':'name\nAda\n','delimiter':','})]
first=run(call)
assert first['ok'] and first['output']=={'records':[{'name':'Ada'}]}
run([*base,'control','pause',activation])
run(call,False)
run([*base,'control','resume',activation])
second=run(call)
assert second['ok']
run(call,False)
run([*base,'control','uninstall',activation])
state=run([*base,'control','inspect',activation])
assert state['attempts_used']==2 and state['overlay']=='absent' and state['accounting_retained']
report={'source_digest':verification_source_digest(root),'kind':'offline synthetic CLI journey through installed native launcher; no model calls','native_binary_sha256':pin,'commands':rows,'retained_project':str(project),'verified_successes':2,'expected_rejections':2,'receipt_ids':[first['receipts'][0]['receipt_id'],second['receipts'][0]['receipt_id']],'human_usability_test':False}
(root/'reports/v08/steering-v1-delivery-validation/cli-journey.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'commands':len(rows),'successes':2,'expected_rejections':2,'summary':first['summary'],'final_state':state},indent=2))
