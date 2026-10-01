"""Fixed synthetic App Server command lifecycle observation. No model methods."""
import base64,errno,json,os,pathlib,select,signal,subprocess,sys,time
PRIVATE=pathlib.Path('/workspace/private');PRIVATE.mkdir(parents=True,exist_ok=True)
STATE=PRIVATE/'state.json';STATE.write_bytes(b'aeep-lifecycle-canary-v1')
HELD=STATE.open('rb')
for n in ('input','output'):(pathlib.Path('/workspace/task')/n).mkdir(parents=True,exist_ok=True)
TOOL={'name':'lifecycle_probe','description':'Observe a fixed synthetic Linux child lifecycle.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
GUARD='''import json,os,resource,sys
os.setsid()
if sys.platform!='linux' or os.geteuid()==0:raise RuntimeError('unsupported guard host')
resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
print(json.dumps({'pid':os.getpid(),'sid':os.getsid(0),'pgid':os.getpgrp(),'uid':os.geteuid()}),flush=True)
if os.read(0,1)!=b'\\x00':raise RuntimeError('incomplete guard handshake')
os.execve('/usr/local/bin/python3',['/usr/local/bin/python3','-c',sys.argv[1]],{'PATH':'/usr/local/bin:/usr/bin:/bin'})
'''
PAYLOAD='''import errno,json,os,pathlib,resource,time
r={'limits_after_exec':list(resource.getrlimit(resource.RLIMIT_NPROC)),'pid_after_exec':os.getpid()}
for name,call in [('fork',os.fork),('posix_spawn',lambda:os.posix_spawn('/usr/local/bin/python3',['/usr/local/bin/python3','-c','pass'],{'PATH':'/usr/local/bin:/usr/bin:/bin'}))]:
 try:
  pid=call();r[name+'_denied']=False
  if name=='fork' and pid==0:os._exit(0)
  os.waitpid(pid,0)
 except OSError as e:r[name+'_denied']=e.errno==errno.EAGAIN;r[name+'_errno']=e.errno
try:resource.setrlimit(resource.RLIMIT_NPROC,(1,1));r['raise_limit_denied']=False
except (OSError,ValueError):r['raise_limit_denied']=True
for label,path in PATHS.items():
 for op in ('read','write'):
  try:
   p=pathlib.Path(path);p.read_bytes() if op=='read' else p.write_bytes(b'changed');r[label+'_'+op+'_denied']=False
  except OSError as e:r[label+'_'+op+'_denied']=True;r[label+'_'+op+'_errno']=e.errno
pathlib.Path('/workspace/task/output/marker.json').write_text('ok')
r['output_written']=True
print(json.dumps(r),flush=True)
'''
def status(pid):
 text=pathlib.Path(f'/proc/{pid}/status').read_text();f={a:b.strip() for a,b in (x.split(':',1) for x in text.splitlines() if ':' in x)}
 stat=pathlib.Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()
 return {'ppid':int(f['PPid']),'nstgid':list(map(int,f['NStgid'].split())),'nspid':list(map(int,f['NSpid'].split())),'sid':int(stat[3]),'pgid':int(stat[2]),'starttime':int(stat[19]),'state':stat[0]}
def descendants(root):
 result=set();queue=[root]
 while queue and len(result)<64:
  pid=queue.pop()
  try:
   children=[]
   for task in pathlib.Path(f'/proc/{pid}/task').iterdir():children.extend(map(int,(task/'children').read_text().split()))
  except OSError:continue
  for child in children:
   if child not in result:result.add(child);queue.append(child)
 return result

def map_owned(root,ready):
 matches=[]
 for pid in descendants(root):
  try:s=status(pid)
  except (OSError,ValueError,KeyError):continue
  if s['nstgid'][-1]==ready['pid'] and s['nspid'][-1]==ready['pid'] and s['sid']==s['pgid']==pid:matches.append((pid,s))
 if len(matches)!=1:raise RuntimeError('owned_namespace_mapping_not_unique')
 pid,s=matches[0];fd=os.pidfd_open(pid)
 if any(status(pid)[k]!=s[k] for k in ('ppid','nstgid','nspid','sid','pgid','starttime')) or pid not in descendants(root):os.close(fd);raise RuntimeError('owned_identity_changed')
 return pid,s,fd

def alive(pid,start):
 try:s=status(pid);return s['starttime']==start and s['state']!='Z'
 except OSError:return False
class Transport:
 def __init__(self):
  self.p=subprocess.Popen(['/opt/codex/codex','app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
  self.buf=b'';self.responses={};self.output=b'';self.serial=0
 def send(self,method,params):
  self.serial+=1;self.p.stdin.write((json.dumps({'id':self.serial,'method':method,'params':params})+'\n').encode());self.p.stdin.flush();return self.serial
 def poll(self,timeout):
  if not select.select([self.p.stdout],[],[],timeout)[0]:return
  data=os.read(self.p.stdout.fileno(),65536)
  if not data:raise RuntimeError('inner_appserver_eof')
  self.buf+=data
  if len(self.buf)>131072:raise RuntimeError('inner_protocol_limit')
  while b'\n' in self.buf:
   line,self.buf=self.buf.split(b'\n',1);m=json.loads(line)
   if 'method' in m:
    if m['method']=='command/exec/outputDelta' and m.get('params',{}).get('processId')=='owned-guard' and m['params'].get('stream')=='stdout':
     self.output+=base64.b64decode(m['params']['deltaBase64'],validate=True)
     if len(self.output)>8192:raise RuntimeError('inner_output_limit')
   elif 'id' in m:self.responses[m['id']]=m
 def wait(self,id,seconds):
  deadline=time.monotonic()+seconds
  while id not in self.responses:
   if time.monotonic()>=deadline:raise TimeoutError('inner_request_timeout')
   self.poll(min(.1,deadline-time.monotonic()))
  m=self.responses[id]
  if 'error' in m:raise RuntimeError('inner_request_rejected_'+str(m['error'].get('code')))
  return m['result']
 def close(self):
  if self.p.stdin and not self.p.stdin.closed:self.p.stdin.close()
  try:self.p.wait(timeout=2)
  except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=1)

def case(mode):
 t=Transport();pid=fd=None;facts={'mode':mode}
 try:
  t.wait(t.send('initialize',{'clientInfo':{'name':'aeep-lifecycle-diagnostic','version':'1'},'capabilities':{'experimentalApi':True}}),3)
  t.p.stdin.write(b'{"method":"initialized"}\n');t.p.stdin.flush()
  paths={'private':'/workspace/private/state.json','fd_alias':f'/proc/{os.getpid()}/fd/{HELD.fileno()}'}
  payload='PATHS='+repr(paths)+'\n'+PAYLOAD if mode=='normal' else 'import time;time.sleep(30)'
  request=t.send('command/exec',{'command':['/usr/local/bin/python3','-I','-c',GUARD,payload],'processId':'owned-guard','permissionProfile':'aeep-task-child','cwd':'/workspace/task','streamStdin':True,'streamStdoutStderr':True,'outputBytesCap':8192,'timeoutMs':1500 if mode=='timeout' else 10000})
  deadline=time.monotonic()+3
  while b'\n' not in t.output:
   if time.monotonic()>=deadline:raise TimeoutError('guard_readiness_timeout')
   t.poll(.05)
  line,t.output=t.output.split(b'\n',1);ready=json.loads(line)
  if ready['pid']!=ready['sid'] or ready['pid']!=ready['pgid']:raise RuntimeError('inner_session_identity_invalid')
  pid,s,fd=map_owned(t.p.pid,ready);facts.update(namespace_pid=ready['pid'],outer_pid=pid,mapping_unique=True,owned_identity_verified=True)
  if status(pid)['starttime']!=s['starttime'] or pid not in descendants(t.p.pid):raise RuntimeError('owned_identity_changed_before_stdin')
  signal.pidfd_send_signal(fd,0)
  t.wait(t.send('command/exec/write',{'processId':'owned-guard','deltaBase64':base64.b64encode(b'\x00').decode(),'closeStdin':True}),2)
  if mode=='eof':t.p.stdin.close();t.p.wait(timeout=3)
  else:
   result=t.wait(request,4);facts['exit_code']=result.get('exitCode')
   if mode=='normal':facts['payload']=json.loads(t.output)
  deadline=time.monotonic()+2
  while alive(pid,s['starttime']) and time.monotonic()<deadline:time.sleep(.02)
  facts['child_dead_before_container_cleanup']=not alive(pid,s['starttime'])
 except Exception as e:facts['error_type']=type(e).__name__;facts['known_error']=str(e) if str(e) in {'owned_namespace_mapping_not_unique','owned_identity_changed','owned_identity_changed_before_stdin','inner_session_identity_invalid','guard_readiness_timeout','inner_request_timeout','inner_appserver_eof','inner_request_rejected_-32602'} else 'unclassified'
 finally:
  if fd is not None:
   if pid is not None and alive(pid,s['starttime']):
    signal.pidfd_send_signal(fd,signal.SIGKILL);facts['fallback_owned_kill_used']=True
   os.close(fd)
  t.close()
 return facts

def observe():
 facts={'cases':[case(mode) for mode in ('normal','timeout','eof')],'coordinator_pid':os.getpid(),'coordinator_fd':HELD.fileno(),'private_state_unchanged':STATE.read_bytes()==b'aeep-lifecycle-canary-v1'}
 return facts
for line in sys.stdin:
 m=json.loads(line)
 if 'id' not in m:continue
 if m.get('method')=='initialize':r={'protocolVersion':m.get('params',{}).get('protocolVersion','2025-11-25'),'serverInfo':{'name':'linux-lifecycle-diagnostic','version':'2'},'capabilities':{'tools':{}}}
 elif m.get('method')=='tools/list':r={'tools':[TOOL]}
 elif m.get('method')=='tools/call' and m.get('params',{}).get('name')=='lifecycle_probe' and m.get('params',{}).get('arguments',{})=={}:
  facts=observe();r={'content':[{'type':'text','text':json.dumps(facts)}],'structuredContent':facts,'isError':False}
 else:
  print(json.dumps({'jsonrpc':'2.0','id':m['id'],'error':{'code':-32601,'message':'Unsupported fixed diagnostic request'}}),flush=True);continue
 print(json.dumps({'jsonrpc':'2.0','id':m['id'],'result':r}),flush=True)
