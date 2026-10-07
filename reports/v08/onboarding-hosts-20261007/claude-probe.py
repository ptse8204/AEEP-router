"""Actual Claude control protocol, empty home, no user/model request."""
import asyncio,json,os,subprocess
from pathlib import Path
from aeep.onboarding import initialize,connect,disconnect
from aeep.access import change_access,adopt_filter
root=Path('/tmp/aeep-host-checks-20261007/claude'); report=Path(__file__).parent
path=os.environ['PATH'];os.environ.clear();os.environ.update(PATH='/tmp/aeep-host-checks-20261007/bin:'+path,HOME=str(root/'home'),CLAUDE_CONFIG_DIR=str(root/'home/.claude'),AEEP_CONFIG_HOME=str(root/'home/aeep'),CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
initialize();connect('alpha','claude',root/'project');connect('beta','claude',root/'project');change_access('beta','aeep_discovery_status',False)
(root/'project/.claude/settings.local.json').write_text(json.dumps({'enabledMcpjsonServers':['aeep_alpha','aeep_beta']}))
record={'host_version':'2.1.292','scope':'Actual Claude MCP inventory control calls only; no model turn or sign-in','checks':[]}
async def inventory():
 p=await asyncio.create_subprocess_exec('claude','-p','--input-format','stream-json','--output-format','stream-json','--verbose','--no-session-persistence',cwd=root/'project',stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
 async def request(n,body):
  p.stdin.write((json.dumps({'type':'control_request','request_id':str(n),'request':body})+'\n').encode());await p.stdin.drain()
  while True:
   line=await asyncio.wait_for(p.stdout.readline(),60)
   if not line: raise RuntimeError('Claude exited before control response')
   r=json.loads(line)
   if r.get('type')=='control_response' and r['response'].get('request_id')==str(n):
    if r['response']['subtype']!='success':raise RuntimeError(r)
    return r['response'].get('response',{})
 try:
  await request(1,{'subtype':'initialize','hooks':None})
  for i in range(30):
   r=await request(i+2,{'subtype':'mcp_status'})
   if len(r.get('mcpServers',[]))==2 and all(x['status']=='connected' for x in r['mcpServers']):return r
   await asyncio.sleep(1)
  return r
 finally:
  p.terminate();await asyncio.wait_for(p.wait(),15)
def names(r,server):return [t['name'] for s in r['mcpServers'] if s['name']==server for t in s.get('tools',[])]
try:
 record['initial']=asyncio.run(inventory());assert 'aeep_discovery_status' in names(record['initial'],'aeep_alpha');assert 'aeep_discovery_status' not in names(record['initial'],'aeep_beta');record['checks'].append('distinct inventories in actual Claude host')
 change_access('alpha','aeep_discovery_status',False);adopt_filter('alpha','aeep_alpha','aeep_list_capabilities',deny=True)
 record['denied']=asyncio.run(inventory());assert 'aeep_discovery_status' not in names(record['denied'],'aeep_alpha');record['checks'].append('AEEP denial absent after host reload; native permission details retained')
 adopt_filter('alpha','aeep_alpha','aeep_list_capabilities',deny=False);change_access('alpha','aeep_discovery_status',True)
 record['restored']=asyncio.run(inventory());assert 'aeep_discovery_status' in names(record['restored'],'aeep_alpha');assert 'aeep_discovery_status' not in names(record['restored'],'aeep_beta');record['checks'].append('restore preserves other connection denial')
 disconnect('alpha');disconnect('beta');record['status']='passed'
except BaseException as e:record.update(status='failed',error=repr(e));raise
finally:(report/'claude-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
