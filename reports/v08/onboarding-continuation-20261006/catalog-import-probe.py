"""Setup imports an actual marketplace reported by the installed Codex CLI."""
import json
import os
import subprocess
import sys
from pathlib import Path

report=Path(__file__).parent
root=Path('/tmp/aeep-onboarding-continuation/native-marketplace').resolve()
env={'PATH':os.environ['PATH'],'HOME':str(root/'home'),'CODEX_HOME':str(root/'home/.codex'),'AEEP_CONFIG_HOME':str(root/'home/aeep')}
command=[sys.executable,'-I','-m','aeep']
result=subprocess.run([*command,'setup','--agent','codex','--project',str(root/'project')],input='y\n\ny\n',text=True,
                      env=env,cwd=root/'project',stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
(report/'catalog-import.log').write_text(result.stdout)
result.check_returncode()
assert 'Also search existing codex catalog aeep-router?' in result.stdout
configuration=json.loads((root/'home/aeep/discovery.json').read_text())
imports=[s for s in configuration['sources'] if s['source_id'].startswith('imported-')]
assert len(imports)==1 and Path(imports[0]['path']).is_dir()
search=subprocess.run([*command,'discover','aeep','--source',imports[0]['source_id'],'--json'],env=env,cwd=root/'project',
                      text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=30)
search.check_returncode();found=json.loads(search.stdout)
assert any(c['name']=='aeep' for c in found['candidates'])
(report/'catalog-import-result.json').write_text(json.dumps({'status':'passed','source':imports[0],'candidate_names':[c['name'] for c in found['candidates']],
    'checks':['supported native inventory offered existing catalog','wizard imported location','metadata search returned plugin'],'scope':'isolated host; candidate metadata only'},indent=2)+'\n')
