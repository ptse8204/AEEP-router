"""Free public HTTPS MCP check through the reviewed setup path."""
import asyncio,json,os
from pathlib import Path
from aeep.assessment.repository import AssessmentRepository
from aeep.component_setup import ComponentSetup,apply,define
from aeep.discovery import RegistryCandidate,_metadata_digest
from aeep.mcp.client import MCPHTTPClient
from aeep.models import utc_now
from aeep.onboarding import initialize,connect
from aeep.router import Router
report=Path(__file__).parent;root=Path('/tmp/aeep-host-checks-20261007/https').resolve();project=root/'project';project.mkdir(parents=True,exist_ok=True)
path=os.environ['PATH'];os.environ.clear();os.environ.update(PATH=path,HOME=str(root/'home'),AEEP_CONFIG_HOME=str(root/'home/aeep'))
initialize();connection=connect('https','deepseek-api',project);router=Router.from_manifest(connection.manifest)
metadata={'name':'Microsoft Learn MCP','url':'https://learn.microsoft.com/api/mcp','documentation':'https://learn.microsoft.com/en-us/training/support/mcp'}
record={'scope':'Public unauthenticated HTTPS MCP; no model, paid calls, credentials or admission','metadata':metadata,'attempts':[]}
async def check(mode):
 client=MCPHTTPClient(url=metadata['url'],protocol_mode=mode)
 try:
  listed=(await client.list_tools()).result;names=[t['name'] for t in listed['tools']];assert 'microsoft_docs_search' in names
  called=(await client.call_tool('microsoft_docs_search',{'query':'WSL installation'})).result;assert not called.get('isError')
  return {'status':'passed','mode':mode,'protocol':client.protocol_version,'tools':names,'read_only_call':'microsoft_docs_search','result_present':bool(called.get('content'))}
 finally:await client.close()
try:
 c=RegistryCandidate(registry_candidate_id='microsoft-learn-public',adapter_id='operator-public-metadata',name=metadata['name'],description='Public Microsoft documentation MCP',provenance={'metadata_url':metadata['documentation'],'availability':'unverified'},retrieved_at=utc_now(),raw_metadata_digest=_metadata_digest(metadata));router.store.save_registry_candidate(c)
 p=ComponentSetup(connection_id='https',candidate_id=c.registry_candidate_id,candidate_digest=c.raw_metadata_digest,kind='https-mcp',package=metadata['url']);preview=define(router,p);(report/'https-preview.json').write_text(json.dumps(preview,indent=2)+'\n');AssessmentRepository(router.store).review(preview['digest']);record['setup']=apply(router,preview['digest']);assert record['setup']['execution']=='not admitted; host connection only'
 for mode in ['auto','legacy']:
  try:record['attempts'].append(asyncio.run(check(mode)));break
  except Exception as e:record['attempts'].append({'status':'failed','mode':mode,'error':repr(e)})
 record['status']=record['attempts'][-1]['status']
finally:asyncio.run(router.close());(report/'https-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record,indent=2))
