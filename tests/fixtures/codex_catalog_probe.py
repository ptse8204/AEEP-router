"""Owned synthetic Responses fixture; no credentials or remote/model calls."""

PROGRAM = r'''
import json,os,subprocess,queue,threading,time,signal,sys
from pathlib import Path
from http.server import HTTPServer,BaseHTTPRequestHandler
allowed={'codex.thread.skills.enabled_total','codex.thread.skills.kept_total','codex.thread.skills.truncated','codex.skill.injected','codex.thread.started','codex.thread.start'}
received=[];stats={'requests':0,'parse_failures':0,'other_metric_count':0,'fixture_requests':0,'full_skill_marker_seen':False,'skill_description_in_request':False,'tool_names':[],'request_keys':[]}
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_POST(self):
  size=int(self.headers.get('Content-Length','0'))
  if self.path=='/v1/responses':
   if not 0<size<=1_000_000:self.send_error(413);return
   body=self.rfile.read(size);stats['fixture_requests']+=1
   if self.headers.get('Content-Encoding')=='gzip':
    import gzip
    body=gzip.decompress(body)
   stats['full_skill_marker_seen'] |= b'OFFLINE_SKILL_CONTENT_MARKER' in body
   stats['skill_description_in_request'] |= b'Harmless offline metrics fixture.' in body
   decoded=json.loads(body);stats['request_keys']=sorted(decoded.keys())
   for tool in decoded.get('tools',[]):
    for entry in tool.get('tools',[tool]):
     name=entry.get('name')
     if isinstance(name,str) and len(name)<80 and name not in stats['tool_names']:stats['tool_names'].append(name)
   message={'id':'msg_fixture','type':'message','role':'assistant','status':'completed','content':[{'type':'output_text','text':'fixture','annotations':[]}]}
   result={'id':'resp_fixture','object':'response','status':'completed','output':[message],'usage':{'input_tokens':1,'output_tokens':1,'total_tokens':2}}
   events=[{'type':'response.created','response':dict(result,status='in_progress',output=[])},{'type':'response.output_item.added','output_index':0,'item':dict(message,status='in_progress',content=[])},{'type':'response.content_part.added','item_id':'msg_fixture','output_index':0,'content_index':0,'part':{'type':'output_text','text':'','annotations':[]}},{'type':'response.output_text.delta','item_id':'msg_fixture','output_index':0,'content_index':0,'delta':'fixture'},{'type':'response.output_item.done','output_index':0,'item':message},{'type':'response.completed','response':result}]
   wire=''.join('event: '+event['type']+'\n'+'data: '+json.dumps(dict(event,sequence_number=i))+'\n\n' for i,event in enumerate(events)).encode()
   self.send_response(200);self.send_header('Content-Type','text/event-stream');self.send_header('Content-Length',str(len(wire)));self.end_headers();self.wfile.write(wire);return
  if self.path!='/v1/metrics' or not 0<size<=1_000_000:
   self.send_error(413);return
  try:
   data=json.loads(self.rfile.read(size));stats['requests']+=1
   for resource in data.get('resourceMetrics',[]):
    for scope in resource.get('scopeMetrics',[]):
     for metric in scope.get('metrics',[]):
      name=metric.get('name')
      if name not in allowed:stats['other_metric_count']+=1;continue
      for kind in ('sum','histogram','gauge'):
       for point in metric.get(kind,{}).get('dataPoints',[]):
        safe={'name':name,'kind':kind,'attribute_keys':sorted(a.get('key','') for a in point.get('attributes',[]))}
        for attribute in point.get('attributes',[]):
         key=attribute.get('key');value=attribute.get('value',{}).get('stringValue')
         if key in {'skill','status','service_name','invoke_type','catalog_surface'} and isinstance(value,str) and len(value)<80:safe[key]=value
        for key in ('asInt','asDouble','count','sum','min','max'):
         value=point.get(key)
         if isinstance(value,(str,int,float)) and not isinstance(value,bool):safe[key]=value
        received.append(safe)
   self.send_response(200);self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{}')
  except (ValueError,TypeError):stats['parse_failures']+=1;self.send_error(400)
server=HTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
home=Path('/tmp/metrics-probe');home.mkdir();work=Path('/workspace');work.mkdir(exist_ok=True)
skill=home/'skills/synthetic';skill.mkdir(parents=True);(skill/'SKILL.md').write_text('---\nname: synthetic\ndescription: Harmless offline metrics fixture.\n---\nOFFLINE_SKILL_CONTENT_MARKER: Return the literal word fixture when explicitly requested.\n')
config='model_provider = "aeep_offline_fixture"\n[model_providers.aeep_offline_fixture]\nname = "Offline protocol fixture; no model"\nbase_url = "http://127.0.0.1:PORT/v1"\nwire_api = "responses"\nrequires_openai_auth = false\nrequest_max_retries = 0\nstream_max_retries = 0\n[analytics]\nenabled = ANALYTICS\n[otel]\nexporter = "none"\ntrace_exporter = "none"\nlog_user_prompt = false\nmetrics_exporter = { otlp-http = { endpoint = "http://127.0.0.1:PORT/v1/metrics", protocol = "json" } }\n'.replace('ANALYTICS',str(ANALYTICS).lower()).replace('PORT',str(server.server_port))
(home/'config.toml').write_text(config)
env=dict(os.environ,CODEX_HOME=str(home),HOME='/tmp',OTEL_METRIC_EXPORT_INTERVAL='1000',OTEL_METRIC_EXPORT_TIMEOUT='1000')
proc=subprocess.Popen([sys.executable,'-c',"import sys; sys.path.insert(0,'/opt/aeep'); from codex_metrics import relay; raise SystemExit(relay(['/opt/codex/codex','app-server','--strict-config','--stdio'],'aeep-metrics-ffffffffffffffffffffffffffffffff'))"],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,env=env)
messages=queue.Queue(); relay_snapshots=[]
def read():
 for line in proc.stdout:
  try:
   item=json.loads(line)
   if item.get('method')=='aeep/catalogMetrics':relay_snapshots.append(item['params'])
   else:messages.put(item)
  except ValueError:pass
threading.Thread(target=read,daemon=True).start()
def send(method,params,identity=None):
 msg={'method':method,'params':params}
 if identity is not None:msg['id']=identity
 proc.stdin.write(json.dumps(msg)+'\n');proc.stdin.flush()
thread_id=None;skill_inventory={};network_probe={}
def response(identity):
 global thread_id,skill_inventory,network_probe
 deadline=time.monotonic()+15
 while time.monotonic()<deadline:
  try:msg=messages.get(timeout=max(.01,deadline-time.monotonic()))
  except queue.Empty:return {'timeout':True}
  if msg.get('id')==identity and identity==5:
   value=msg.get('result',{});network_probe={'exit_code':value.get('exitCode'),'outcome':value.get('stdout','')[:100].strip(),'error':msg.get('error')}
  if msg.get('id')==identity and identity==4:
   entries=[s for group in msg.get('result',{}).get('data',[]) for s in group.get('skills',[])]
   skill_inventory={'count':len(entries),'synthetic_found':any(s.get('name')=='synthetic' for s in entries),'synthetic_enabled':any(s.get('name')=='synthetic' and s.get('enabled') is True for s in entries),'errors':sum(len(g.get('errors',[])) for g in msg.get('result',{}).get('data',[]))}
  if msg.get('id')==identity and identity==2:thread_id=msg.get('result',{}).get('thread',{}).get('id')
  if msg.get('id')==identity:return {'success':'result' in msg,'error':msg.get('error')}
 return {'timeout':True}
send('initialize',{'clientInfo':{'name':'aeep-offline-metrics-probe','version':'0.8'},'capabilities':{'experimentalApi':False}},1);init=response(1)
send('initialized',{})
send('skills/list',{'cwds':[str(work)],'forceReload':True},4);response(4)
send('thread/start',{'serviceName':'aeep-metrics-ffffffffffffffffffffffffffffffff','config':{'features.code_mode_host':False,'features.shell_tool':True,'features.unified_exec':True},'model':'gpt-6-astra','cwd':str(work),'ephemeral':True,'approvalPolicy':'never','sandbox':'read-only'},2);thread=response(2)
ports=[int(line.split()[1].split(':')[1],16) for line in Path('/proc/net/tcp').read_text().splitlines()[1:] if line.split()[1].split(':')[0]=='0100007F' and line.split()[3]=='0A']
collector_ports=[port for port in ports if port!=server.server_port]
assert len(collector_ports)==1,collector_ports
collector_port=collector_ports[0]
program='import socket\ntry:\n s=socket.create_connection(("127.0.0.1",'+str(collector_port)+'),timeout=2);s.close();print("connected")\nexcept PermissionError:print("denied")\nexcept OSError:print("unreachable")'
send('command/exec',{'command':['python3','-c',program],'cwd':str(work),'timeoutMs':5000,'outputBytesCap':1024},5);response(5)
send('turn/start',{'threadId':thread_id,'input':[{'type':'text','text':'Return the literal word fixture.'}]+([{'type':'skill','name':'synthetic','path':str(skill/'SKILL.md')}] if EXPLICIT else [])},3)
turn=response(3);terminal=None;deadline=time.monotonic()+15
while time.monotonic()<deadline:
 try:message=messages.get(timeout=max(.01,deadline-time.monotonic()))
 except queue.Empty:break
 if message.get('method')=='turn/completed':terminal=message.get('params',{}).get('turn',{}).get('status');break
proc.stdin.close()
try:proc.wait(timeout=10);stopped='stdin_eof'
except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=5);stopped='sigterm'
time.sleep(.1);server.shutdown()
print(json.dumps({'collector_sha256':__import__('hashlib').sha256(Path('/opt/aeep/codex_metrics.py').read_bytes()).hexdigest(),'relay_analytics_enabled':True,'relay_snapshots':relay_snapshots,'initialize':init,'thread_start':thread,'turn_start':turn,'terminal_status':terminal,'collector_access_from_sandbox':network_probe,'skill_inventory':skill_inventory,'synthetic_turns':1,'explicit_skill':EXPLICIT,'model_calls':0,'requests':stats,'selected_metrics':received,'stop':stopped,'exit_code':proc.returncode,'requested_export_interval_ms':1000,'observation_seconds_after_turn':0.1}))
'''
