"""Local hard-limit feasibility; no runtime alteration or containment claim."""
import hashlib,json,subprocess,sys,time
from pathlib import Path
from aeep.hosts.codex_sandbox import NativeSandboxConfig
root=Path(__file__).resolve().parent
owned=root/'native-coordinator-death-owned-288e'
original=json.loads((owned/'definition.json').read_text())
boundary=NativeSandboxConfig(binary=original['binary'],binary_sha256=original['binary_sha256'],project_root=str(owned),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(owned/'data')])
program='''import os,resource,json
r={'uid':os.getuid(),'before':resource.getrlimit(resource.RLIMIT_NPROC)}
try:
 resource.setrlimit(resource.RLIMIT_NPROC,(0,0)); r['limit_set']=True
except OSError as e: r['limit_set']=False; r['set_errno']=e.errno
r['after']=resource.getrlimit(resource.RLIMIT_NPROC)
try:
 resource.setrlimit(resource.RLIMIT_NPROC,(1,1)); r['hard_limit_raise_denied']=False
except (ValueError,OSError): r['hard_limit_raise_denied']=True
try:
 pid=os.fork()
 if pid==0: os._exit(0)
 os.waitpid(pid,0); r['fork_denied']=False
except OSError as e: r['fork_denied']=True; r['fork_errno']=e.errno
print(json.dumps(r))
'''
definition={'source_digest':original['source_digest'],'binary_sha256':original['binary_sha256'],'purpose':'kernel process-local RLIMIT_NPROC hard-zero feasibility inside installed native profile; no live model','program_sha256':hashlib.sha256(program.encode()).hexdigest(),'authority':'parent September 30 bounded feasibility instruction and existing finite test amendment delegation','timeout_seconds':5,'model_calls':0,'cash':0,'limitations':'one non-root local fork probe; no watchdog or arbitrary-executor support established'}
(root/'native-nproc-feasibility-review-288e.json').write_text(json.dumps(definition,indent=2))
t=time.monotonic(); p=subprocess.run(boundary.argv([sys.executable,'-I','-c',program]),capture_output=True,text=True,timeout=5)
result={'definition':definition,'exit_code':p.returncode,'elapsed_seconds':time.monotonic()-t,'result':json.loads(p.stdout) if p.returncode==0 else None,'stderr':p.stderr[:1000]}
(root/'native-nproc-feasibility-result-288e.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
