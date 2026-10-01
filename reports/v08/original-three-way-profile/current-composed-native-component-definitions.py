"""Exact native component programs; imports start no service or process."""
import copy,errno,json
from pathlib import Path
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.models import content_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig,native_backend_digest
from aeep.models import ExecutorKind,SideEffect
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
PROJECT=ROOT/'.aeep/current-composed-workbook-ade3'
READY=b'native_composed_read_linger_ready\n'
def definitions():
 setup=json.loads((OUT/'current-native-producer-setup-result.json').read_text())
 native=NativeSandboxConfig.model_validate(setup['native']);native.validate_single_process();native.argv([])
 if native.project_root!=str(PROJECT.resolve()):raise ValueError('exact existing native backend project required')
 canary=PROJECT/'.aeep/composed-private-witness';database=PROJECT/'.aeep/state.db'
 program=("import os,resource,json,socket; r={'hard_nproc':':'.join(map(str,resource.getrlimit(resource.RLIMIT_NPROC))),'session_leader':str(os.getpid()==os.getpgid(0)==os.getsid(0)).lower(),'marker':'post_exec'};\n"
  'try:os.fork();r["fork_errno"]="unexpected"\nexcept OSError as e:r["fork_errno"]=str(e.errno)\n'
  'try:os.posix_spawn("/usr/bin/true",["/usr/bin/true"],{});r["spawn_errno"]="unexpected"\nexcept OSError as e:r["spawn_errno"]=str(e.errno)\n'
  'try:resource.setrlimit(resource.RLIMIT_NPROC,(1,1));r["raise_denied"]="false"\nexcept (OSError,ValueError):r["raise_denied"]="true"\n'
  f'try:open({str(canary)!r}).read();r["private_denied"]="false"\nexcept PermissionError:r["private_denied"]="true"\n'
  f'try:open({str(database)!r},"rb").read(1);r["database_denied"]="false"\nexcept PermissionError:r["database_denied"]="true"\n'
  's=socket.socket();s.settimeout(.25)\ntry:s.connect(("127.0.0.1",9));r["network_denied"]="false"\nexcept PermissionError:r["network_denied"]="true"\nexcept OSError:r["network_denied"]="false"\nfinally:s.close()\n'
  'print(json.dumps({"records":[r]}))')
 expected={'hard_nproc':'0:0','session_leader':'true','marker':'post_exec','fork_errno':str(errno.EAGAIN),'spawn_errno':str(errno.EAGAIN),'raise_denied':'true','private_denied':'true','database_denied':'true','network_denied':'true'}
 text=','.join(expected)+'\n'+','.join(expected.values())+'\n'
 values={}
 for name,payload in [('guard',program),('read_cancel','import os,json,time;print(json.dumps({"native_composed_ready":True,"pid":os.getpid()}),flush=True);time.sleep(30)')]:
  spec=reference_spec('csv').model_copy(deep=True);spec.id='native.composed.component.'+name;spec.kind=ExecutorKind.COMMAND;spec.side_effect=SideEffect.READ;spec.idempotent=True
  spec.config={'argv':[native.python_binary,'-I','-c',payload],'argv_literal':True,'stdin_json':False,'output':{'type':'json'},'timeout_seconds':10,'max_output_bytes':16384,'native_sandbox':native.model_dump(mode='json')}
  values[name]={'spec':spec.model_dump(mode='json'),'fingerprint':executor_fingerprint(spec),'input':{'text':text,'delimiter':','},'native_backend_digest':native_backend_digest(native)}
 return {'guard':values['guard'],'read_cancel':values['read_cancel'],'canary':str(canary),'witness':'synthetic-private-witness','expected':expected,'provenance':'actual protected fixed-service calls and native command; actual native-host callback is separately retained','full_conformance':False}
