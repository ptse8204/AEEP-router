"""Fixed synthetic App Server command lifecycle observation. No model methods."""
import base64,errno,json,os,pathlib,re,select,signal,subprocess,sys,time
PRIVATE=pathlib.Path('/workspace/private');PRIVATE.mkdir(parents=True,exist_ok=True)
STATE=PRIVATE/'state.json';STATE.write_bytes(b'aeep-lifecycle-canary-v1')
HELD=STATE.open('rb')
for n in ('input','output'):(pathlib.Path('/workspace/task')/n).mkdir(parents=True,exist_ok=True)
TOOL={'name':'lifecycle_probe','description':'Observe a fixed synthetic Linux child lifecycle.','inputSchema':{'type':'object','properties':{},'additionalProperties':False}}
GUARD='''import json,os,resource,sys
if os.getpid()!=os.getsid(0) or os.getpid()!=os.getpgrp():os.setsid()
if os.getpid()!=os.getsid(0) or os.getpid()!=os.getpgrp():raise RuntimeError('guard session identity invalid')
if sys.platform!='linux' or os.geteuid()==0:raise RuntimeError('unsupported guard host')
resource.setrlimit(resource.RLIMIT_NPROC,(0,0))
if resource.getrlimit(resource.RLIMIT_NPROC)!=(0,0):raise RuntimeError('guard limit missing')
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
 try:
  if any(status(pid)[k]!=s[k] for k in ('ppid','nstgid','nspid','sid','pgid','starttime')) or pid not in descendants(root):raise RuntimeError('owned_identity_changed')
 except Exception:os.close(fd);raise
 return pid,s,fd

def alive(pid,start):
 try:s=status(pid);return s['starttime']==start and s['state']!='Z'
 except OSError:return False
def safe_error(data):
 text=data.decode('utf-8',errors='replace');r={'bytes':len(data)}
 r['categories']=[name for name in ('PermissionError','FileNotFoundError','RuntimeError','NotADirectoryError','OSError') if name in text]
 if re.search(r'\b(auth|authentication|authorization|login|token|credential|bearer|password|secret|cookie|oauth|account)\b',text,re.I):r['excerpt_withheld']='authentication_related'
 elif any(k in text.lower() for k in ('error','bwrap','permission','traceback','configuration','invalid','missing')):
  text=re.sub(r'https?://[^\s]+','[redacted-url]',text)
  text=re.sub(r'/[^\s\"\',;:)]+',lambda m:m.group(0) if m.group(0) in {'/opt/codex/codex','/workspace/task','/workspace/private/state.json'} else '[redacted-path]',text)
  text=re.sub(r'[A-Za-z0-9_-]{32,}','[redacted-long-value]',text)
  r['sanitized_excerpt']=text.encode()[:2048].decode(errors='ignore')
 elif data:r['excerpt_withheld']='unknown_text'
 return r
class Transport:
 def __init__(self):
  self.p=subprocess.Popen(['/opt/codex/codex','app-server','--stdio'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  self.buf=b'';self.responses={};self.output=b'';self.serial=0;self.stderr=b'';self.command_stderr=b'';self.stderr_open=True
 def send(self,method,params):
  self.serial+=1;self.p.stdin.write((json.dumps({'id':self.serial,'method':method,'params':params})+'\n').encode());self.p.stdin.flush();return self.serial
 def poll(self,timeout):
  surfaces=[self.p.stdout]+([self.p.stderr] if self.stderr_open else [])
  ready=select.select(surfaces,[],[],timeout)[0]
  if self.p.stderr in ready:
   chunk=os.read(self.p.stderr.fileno(),4096)
   if not chunk:self.stderr_open=False
   else:self.stderr=(self.stderr+chunk)[:8192]
  if self.p.stdout not in ready:return
  data=os.read(self.p.stdout.fileno(),65536)
  if not data:raise RuntimeError('inner_appserver_eof')
  self.buf+=data
  if len(self.buf)>131072:raise RuntimeError('inner_protocol_limit')
  while b'\n' in self.buf:
   line,self.buf=self.buf.split(b'\n',1);m=json.loads(line)
   if 'method' in m:
    if m['method']=='command/exec/outputDelta' and m.get('params',{}).get('processId')=='owned-guard' and m['params'].get('stream')=='stderr':self.command_stderr=(self.command_stderr+base64.b64decode(m['params']['deltaBase64'],validate=True))[:8192]
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
  try:self.p.wait(timeout=2);return {'natural_exit':True,'exit_code':self.p.returncode,'forced_kill':False}
  except subprocess.TimeoutExpired:self.p.kill();self.p.wait(timeout=1);return {'natural_exit':False,'exit_code':self.p.returncode,'forced_kill':True}

def case(mode,deadline):
 t=Transport();pid=fd=None;facts={'mode':mode};started=time.monotonic()
 def remain(seconds):
  value=min(seconds,deadline-time.monotonic())
  if value<=0:raise TimeoutError('shared_inner_deadline')
  return value
 try:
  t.wait(t.send('initialize',{'clientInfo':{'name':'aeep-lifecycle-diagnostic','version':'1'},'capabilities':{'experimentalApi':True}}),remain(3))
  t.p.stdin.write(b'{"method":"initialized"}\n');t.p.stdin.flush()
  paths={'private':'/workspace/private/state.json','fd_alias':f'/proc/{os.getpid()}/fd/{HELD.fileno()}'}
  payload='PATHS='+repr(paths)+'\n'+PAYLOAD if mode=='normal' else "import json,os,time;print(json.dumps({'linger_started':True,'pid':os.getpid()}),flush=True);time.sleep(30)"
  request=t.send('command/exec',{'command':['/usr/local/bin/python3','-I','-c',GUARD,payload],'processId':'owned-guard','permissionProfile':'aeep-task-child','cwd':'/workspace/task','streamStdin':True,'streamStdoutStderr':True,'outputBytesCap':8192,'timeoutMs':1500 if mode=='timeout' else 10000})
  ready_deadline=time.monotonic()+remain(3)
  while b'\n' not in t.output:
   if time.monotonic()>=ready_deadline:raise TimeoutError('guard_readiness_timeout')
   t.poll(.05)
  line,t.output=t.output.split(b'\n',1);ready=json.loads(line)
  if ready['pid']!=ready['sid'] or ready['pid']!=ready['pgid']:raise RuntimeError('inner_session_identity_invalid')
  pid,s,fd=map_owned(t.p.pid,ready);facts.update(namespace_pid=ready['pid'],outer_pid=pid,mapping_unique=True,owned_identity_verified=True)
  if status(pid)['starttime']!=s['starttime'] or pid not in descendants(t.p.pid):raise RuntimeError('owned_identity_changed_before_stdin')
  signal.pidfd_send_signal(fd,0)
  t.wait(t.send('command/exec/write',{'processId':'owned-guard','deltaBase64':base64.b64encode(b'\x00').decode(),'closeStdin':True}),remain(2))
  facts['stdin_released_after_identity']=True
  if mode!='normal':
   marker_deadline=time.monotonic()+remain(2)
   while b'\n' not in t.output:
    if time.monotonic()>=marker_deadline:raise TimeoutError('postexec_marker_missing')
    t.poll(.02)
   marker=json.loads(t.output.split(b'\n',1)[0]);facts['postexec_linger_started']=marker=={'linger_started':True,'pid':ready['pid']}
   facts['postexec_child_live']=alive(pid,s['starttime'])
   if not facts['postexec_linger_started'] or not facts['postexec_child_live']:raise RuntimeError('postexec_linger_not_live')
  if mode=='eof':
   t.p.stdin.close();t.p.wait(timeout=remain(3));facts['natural_eof_host_exit']=True;facts['host_exit_code']=t.p.returncode
  else:
   result=t.wait(request,remain(4));facts['exit_code']=result.get('exitCode')
   if mode=='normal':facts['payload']=json.loads(t.output)
  death_deadline=time.monotonic()+remain(2)
  while alive(pid,s['starttime']) and time.monotonic()<death_deadline:time.sleep(.02)
  facts['child_dead_before_container_cleanup']=not alive(pid,s['starttime'])
 except Exception as e:facts['error_type']=type(e).__name__;facts['known_error']=str(e) if str(e) in {'owned_namespace_mapping_not_unique','owned_identity_changed','owned_identity_changed_before_stdin','inner_session_identity_invalid','guard_readiness_timeout','inner_request_timeout','inner_appserver_eof','inner_request_rejected_-32602'} else 'unclassified'
 finally:
  if fd is not None:
   try:
    if pid is not None and alive(pid,s['starttime']):
     try:signal.pidfd_send_signal(fd,signal.SIGKILL);facts['fallback_owned_kill_used']=True
     except ProcessLookupError:facts['child_exit_race_observed']=True
   finally:os.close(fd)
  facts['transport_cleanup']=t.close()
  facts['elapsed_seconds']=time.monotonic()-started
  if 'error_type' in facts or facts.get('exit_code',0)!=0:facts['safe_error']=safe_error(t.stderr+t.command_stderr)
 return facts

def observe():
 facts={'cases':[],'coordinator_pid':os.getpid(),'coordinator_fd':HELD.fileno()};deadline=time.monotonic()+25
 for mode in ('normal','timeout','eof'):
  observed=case(mode,deadline);facts['cases'].append(observed)
  if 'error_type' in observed or observed.get('fallback_owned_kill_used') or observed.get('transport_cleanup',{}).get('forced_kill') or not observed.get('child_dead_before_container_cleanup'):break
 facts['private_state_unchanged']=STATE.read_bytes()==b'aeep-lifecycle-canary-v1'
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
