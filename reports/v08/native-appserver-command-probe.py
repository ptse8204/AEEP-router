import asyncio,hashlib,json,sys,time
from pathlib import Path
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.hosts.codex_app_server import CodexAppServerTransport,AppServerOptions
R=Path(__file__).resolve().parent; W=R/'native-coordinator-death-owned-288e'; D=json.loads((W/'definition.json').read_text()); B=D['binary']; data=W/'data'
async def main():
 b=NativeSandboxConfig(binary=B,binary_sha256=D['binary_sha256'],project_root=str(W),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(data)])
 argv=(B,'app-server','--stdio',*b.permission_overrides())
 t=CodexAppServerTransport(argv,cwd=str(W),executable_sha256=D['binary_sha256'],options=AppServerOptions(experimental_api=True))
 changes=[]
 def event(method,params):
  if method=='command/exec/outputDelta':changes.append(params)
 t.subscribe(event)
 review={'binary_sha256':D['binary_sha256'],'authority':'parent direct native command method feasibility instruction September30','model_calls':0,'method':'command/exec','permissionProfile':'aeep-native-task','program':'report PID/PGID/SID; hardNPROC0; attempt setsid; print facts','timeout_seconds':5}
 (R/'native-appserver-command-review.json').write_text(json.dumps(review,indent=2))
 try:
  p='import os,resource,json; resource.setrlimit(resource.RLIMIT_NPROC,(0,0));r={"pid":os.getpid(),"pgid":os.getpgrp(),"sid":os.getsid(0)};\ntry:os.setsid();r["setsid_denied"]=False\nexcept OSError:r["setsid_denied"]=True\nprint(json.dumps(r))'
  response=await t.request('command/exec',{'command':[sys.executable,'-I','-c',p],'permissionProfile':'aeep-native-task','cwd':str(W),'timeoutMs':3000},timeout=5)
  result={'review':review,'response':response,'events':changes}
 except Exception as e:result={'review':review,'error':type(e).__name__,'detail':str(e),'safe_request_error':getattr(e,'error',None)}
 finally:await t.close()
 (R/'native-appserver-command-result.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
asyncio.run(main())
