import hashlib,json,os,subprocess,sys,time
from datetime import timedelta
from pathlib import Path
from aeep.assessment.onboarding import reference_spec
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import Manifest,TaskScope,ExecutorKind,utc_now
from aeep.assessment.verification import verification_source_digest
root=Path.cwd()
project=(root/'reports/v08/steering-v1-delivery-validation/final/mcp-project').resolve()
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
serve=[sys.executable,'-m','aeep','serve','--transport','stdio','--profile','task','--task-activation',activation,'-m',str(manifest)]
messages=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{}},{'jsonrpc':'2.0','method':'notifications/initialized','params':{}},{'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}},{'jsonrpc':'2.0','id':3,'method':'tools/call','params':{'name':'aeep_csv','arguments':{'text':'name\\nAda\\n','delimiter':','}}}]
messages[-1]['params']['arguments']['text']='name'+chr(10)+'Ada'+chr(10)
result=subprocess.run(serve,input=''.join(json.dumps(m)+chr(10) for m in messages),env=env,capture_output=True,text=True,timeout=30,check=False)
assert result.returncode==0,(result.stdout,result.stderr)
responses=[json.loads(line) for line in result.stdout.splitlines()]
assert len(responses)==3 and all('error' not in value for value in responses)
assert [tool['name'] for tool in responses[1]['result']['tools']]==['aeep_csv']
outcome=responses[2]['result']['structuredContent']
assert outcome['ok'] and outcome['output']=={'records':[{'name':'Ada'}]}
state=run([*base,'control','uninstall',activation])
assert state['overlay']=='absent' and state['attempts_used']==1
report={'source_digest':verification_source_digest(root),'kind':'actual native command through stdio MCP; no model or Codex UI claim','setup_and_cleanup_commands':rows,'server_argv':serve,'exit_code':result.returncode,'stderr':result.stderr,'responses':responses,'only_protocol_json_on_stdout':True}
(root/'reports/v08/steering-v1-delivery-validation/final/mcp-journey.json').write_text(json.dumps(report,indent=2)+chr(10))
print(json.dumps({'protocol_responses':3,'task_ok':True,'visible_tools':['aeep_csv'],'summary':outcome['summary'],'overlay':state['overlay']}))
