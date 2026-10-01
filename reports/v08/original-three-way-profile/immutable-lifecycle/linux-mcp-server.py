"""Fixed zero-model synthetic lifecycle diagnostic. Protocol stdout only."""
import json, os, pathlib, resource, subprocess, sys, time
PRIVATE=pathlib.Path('/workspace/private')
PRIVATE.mkdir();(PRIVATE/'state.json').write_bytes(b'aeep-lifecycle-canary-v1')
for name in ('input','output'):(pathlib.Path('/workspace/task')/name).mkdir(parents=True,exist_ok=True)
TOOL={'name':'lifecycle_probe','description':'Observe a fixed synthetic Linux child lifecycle.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
GUARD='''import os,resource,sys,json
if sys.platform!='linux' or os.geteuid()==0:raise RuntimeError('unsupported guard host')
resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
if resource.getrlimit(resource.RLIMIT_NPROC)!=(0,0):raise RuntimeError('guard limit missing')
print(json.dumps({'pid':os.getpid(),'ppid':os.getppid(),'sid':os.getsid(0),'pgid':os.getpgrp(),'uid':os.geteuid()}),flush=True)
if os.read(0,1)!=b'\\x00':raise RuntimeError('incomplete guard handshake')
os.execve('/usr/local/bin/python3',['/usr/local/bin/python3','-c',sys.argv[1]],{'PATH':'/usr/local/bin:/usr/bin:/bin'})
'''
PAYLOAD='''import json,os,pathlib,resource,subprocess,time
r={'limits_after_exec':list(resource.getrlimit(resource.RLIMIT_NPROC)),'pid_after_exec':os.getpid()}
for name,call in [('fork',os.fork),('spawn',lambda:subprocess.run(['/usr/local/bin/python3','-c','pass'])),('raise_limit',lambda:resource.setrlimit(resource.RLIMIT_NPROC,(1,1)))]:
 try:
  value=call();r[name+'_denied']=False
  if name=='fork' and value==0:os._exit(0)
  if name=='fork':os.waitpid(value,0)
 except (OSError,ValueError,PermissionError) as e:r[name+'_denied']=True;r[name+'_error_type']=type(e).__name__
for name in ('/workspace/private/state.json','/workspace/task/input'):
 for op in ('read','write'):
  if name.endswith('/input') and op=='read':continue
  try:
   p=pathlib.Path(name if not name.endswith('/input') else name+'/forbidden');p.read_bytes() if op=='read' else p.write_bytes(b'changed');r[name+':'+op+'_denied']=False
  except OSError:r[name+':'+op+'_denied']=True
pathlib.Path('/workspace/task/output/marker.json').write_text('ok')
r['output_written']=True
print(json.dumps(r),flush=True)
'''
LINGER="import time;time.sleep(30)"
OWNED=[]
def start(payload):
 argv=['/opt/codex/codex','sandbox','--permission-profile','aeep-task-child','--include-managed-config','--cd','/workspace/task','--','/usr/local/bin/python3','-c',GUARD,payload]
 p=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
 OWNED.append(p)
 ready=json.loads(p.stdout.readline())
 pid=ready['pid'];chain=[];current=pid
 for _ in range(12):
  try:
   status=pathlib.Path(f'/proc/{current}/status').read_text();parent=int(next(x.split(':')[1] for x in status.splitlines() if x.startswith('PPid:')));chain.append(current)
  except (OSError,StopIteration,ValueError):break
  if current==p.pid:break
  current=parent
 ready['coordinator_visible_owned_chain']=p.pid in chain
 ready['reported_session_group_matches_leader']=ready['pid']==ready['sid']==ready['pgid']
 p.stdin.write(b'\x00');p.stdin.flush()
 return p,ready

def observe():
 p,ready=start(PAYLOAD);stdout,stderr=p.communicate(timeout=5)
 facts={'guard':ready,'exit_code':p.returncode,'stderr_bytes':len(stderr),'payload':json.loads(stdout) if p.returncode==0 else None}
 p,linger=start(LINGER)
 facts['linger_guard']=linger;facts['linger_live_before_cleanup']=p.poll() is None
 facts['private_state_unchanged']=(PRIVATE/'state.json').read_bytes()==b'aeep-lifecycle-canary-v1'
 return facts
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m:continue
 method=m.get('method')
 if method=='initialize':r={'protocolVersion':m.get('params',{}).get('protocolVersion','2025-11-25'),'serverInfo':{'name':'linux-lifecycle-diagnostic','version':'1'},'capabilities':{'tools':{}}}
 elif method=='tools/list':r={'tools':[TOOL]}
 elif method=='tools/call' and m.get('params',{}).get('name')=='lifecycle_probe' and m.get('params',{}).get('arguments',{})=={}:
  try:facts=observe();r={'content':[{'type':'text','text':json.dumps(facts)}],'structuredContent':facts,'isError':False}
  except Exception as e:r={'content':[{'type':'text','text':type(e).__name__}],'structuredContent':{'error_type':type(e).__name__},'isError':True}
 else:
  print(json.dumps({'jsonrpc':'2.0','id':m['id'],'error':{'code':-32601,'message':'Unsupported fixed diagnostic request'}}),flush=True);continue
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)
