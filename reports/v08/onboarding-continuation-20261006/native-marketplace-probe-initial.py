"""Actual pinned marketplace installation into an isolated Codex home."""
import asyncio
import json
import os
import subprocess
from pathlib import Path

from aeep.assessment.repository import AssessmentRepository
from aeep.component_setup import ComponentSetup, apply, define
from aeep.discovery import RegistryQuery
from aeep.marketplaces import MarketplaceAdapter
from aeep.onboarding import connect, initialize
from aeep.router import Router

report=Path(__file__).parent
metadata=json.loads((report/'native-marketplace-metadata.json').read_text())
root=Path('/tmp/aeep-onboarding-continuation/native-marketplace').resolve()
root.mkdir(exist_ok=False)
home,project=root/'home',root/'project';home.mkdir();project.mkdir()
path=os.environ['PATH'];os.environ.clear()
os.environ.update({'PATH':path,'HOME':str(home),'CODEX_HOME':str(home/'.codex'),'AEEP_CONFIG_HOME':str(home/'aeep'),
                   'GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null','GIT_TERMINAL_PROMPT':'0'})
initialize();connection=connect('native','codex',project)
router=Router.from_manifest(connection.manifest)
try:
 candidates=asyncio.run(MarketplaceAdapter(metadata['catalog_url']).search(RegistryQuery(query='aeep')))
 assert len(candidates)==1
 candidate=candidates[0];router.store.save_registry_candidate(candidate)
 plan=ComponentSetup(connection_id='native',candidate_id=candidate.registry_candidate_id,candidate_digest=candidate.raw_metadata_digest,
                     kind='marketplace',package=metadata['source'],version=metadata['revision'],plugin='aeep',marketplace='aeep-router')
 preview=define(router,plan)
 (report/'native-marketplace-preview.json').write_text(json.dumps(preview,indent=2)+'\n')
 AssessmentRepository(router.store).review(preview['digest'])
 installed=apply(router,preview['digest'])
 assert installed['status']=='installed'
 assert apply(router,preview['digest'])==installed
 output=subprocess.check_output(['codex','plugin','marketplace','list','--json'],text=True,timeout=30)
 (report/'native-marketplace-inventory.json').write_text(output)
 assert 'aeep-router' in output
 result={'status':'passed','workspace':str(root),'source_revision':metadata['revision'],'installed_plugin_version':'0.8.1',
         'setup':installed,'scope':'Native Codex marketplace/package installation only; no plugin tool call, model request, production home or new release publication'}
 (report/'native-marketplace-result.json').write_text(json.dumps(result,indent=2)+'\n')
finally:
 asyncio.run(router.close())
