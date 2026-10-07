"""Reviewed native Claude installation of an official skill-only plugin."""
import asyncio,json,os,subprocess
from pathlib import Path
from aeep.assessment.repository import AssessmentRepository
from aeep.component_setup import ComponentSetup,apply,define
from aeep.discovery import RegistryQuery
from aeep.marketplaces import MarketplaceAdapter
from aeep.onboarding import connect,initialize,known_marketplaces
from aeep.router import Router
report=Path(__file__).resolve().parent;metadata=json.loads((report/'claude-marketplace-metadata.json').read_text())
root=Path('/tmp/aeep-host-checks-20261007/claude-native-final').resolve();home,project=root/'home',root/'project';home.mkdir(parents=True,exist_ok=True);project.mkdir(exist_ok=True)
path=os.environ['PATH'];os.environ.clear();os.environ.update(PATH='/tmp/aeep-host-checks-20261007/bin:'+path,HOME=str(home),CLAUDE_CONFIG_DIR=str(home/'.claude'),AEEP_CONFIG_HOME=str(home/'aeep'),GIT_CONFIG_NOSYSTEM='1',GIT_CONFIG_GLOBAL='/dev/null',GIT_TERMINAL_PROMPT='0',CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
os.chdir(project);initialize();connection=connect('native','claude',project);router=Router.from_manifest(connection.manifest)
record={'scope':'Isolated native plugin installation, no model turn or sign-in','metadata':metadata}
try:
 candidates=asyncio.run(MarketplaceAdapter(metadata['catalog_url']).search(RegistryQuery(query='frontend-design')))
 candidate=next(c for c in candidates if c.name=='frontend-design');router.store.save_registry_candidate(candidate)
 plan=ComponentSetup(connection_id='native',candidate_id=candidate.registry_candidate_id,candidate_digest=candidate.raw_metadata_digest,kind='marketplace',package=metadata['source'],version=metadata['revision'],plugin='frontend-design',marketplace=metadata['marketplace'])
 preview=define(router,plan);(report/'claude-marketplace-preview.json').write_text(json.dumps(preview,indent=2)+'\n');AssessmentRepository(router.store).review(preview['digest'])
 record['setup']=apply(router,preview['digest'],retry_failed=True);assert record['setup']['status']=='installed'
 output=subprocess.check_output(['claude','plugin','list','--json'],cwd=project,text=True,timeout=30);record['plugins']=json.loads(output);assert 'frontend-design@'+preview['native_marketplace'] in output
 record['catalogs']=known_marketplaces('claude');assert record['catalogs'];assert apply(router,preview['digest'])==record['setup'];record['status']='passed'
except BaseException as e:record.update(status='failed',error=repr(e));raise
finally:asyncio.run(router.close());(report/'claude-marketplace-result.json').write_text(json.dumps(record,indent=2)+'\n')
