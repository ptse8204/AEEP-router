"""Connection-bound application dispatch; no model request or credentials."""
import asyncio,json,os
from pathlib import Path
from aeep.integrations.connected_tools import ConnectedTools
from aeep.onboarding import initialize,connect
from aeep.access import change_access
root=Path('/tmp/aeep-host-checks-20261007/api').resolve();project=root/'project';project.mkdir(parents=True,exist_ok=True)
path=os.environ['PATH'];os.environ.clear();os.environ.update(PATH=path,HOME=str(root/'home'),AEEP_CONFIG_HOME=str(root/'config'))
initialize();connect('api','deepseek-api',project);change_access('api','aeep_discovery_status',True);path=root/'config/connections/api.json'
r={'scope':'Actual application bridge dispatch; no model request or provider credentials'}
async def check():
 bridge=ConnectedTools(path)
 try:
  r['before']=[t['function']['name'] for t in bridge.declarations()];assert 'aeep_discovery_status' in r['before'];result=await bridge.call('aeep_discovery_status',{});assert not result.get('isError')
  await asyncio.to_thread(change_access,'api','aeep_discovery_status',False)
  r['after']=[t['function']['name'] for t in bridge.declarations()];assert 'aeep_discovery_status' not in r['after']
  try:denied=await bridge.call('aeep_discovery_status',{})
  except Exception as exc:r['denied']=str(exc)
  else:assert denied.get('isError');r['denied']=denied
 finally:await bridge.close()
try:asyncio.run(check());r['status']='passed'
except BaseException as e:r.update(status='failed',error=repr(e));raise
finally:(Path(__file__).parent/'api-result.json').write_text(json.dumps(r,indent=2)+'\n');print(r)
