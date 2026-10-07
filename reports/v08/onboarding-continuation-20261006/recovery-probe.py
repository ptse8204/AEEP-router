"""Resume a real install after setup fails, preserving operator edits and runtime."""
import json
import os
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parents[3]
report=Path(__file__).parent
root=Path('/tmp/aeep-onboarding-continuation/recovery')
root.mkdir(exist_ok=False)
home,project=root/'home',root/'project'
home.mkdir();project.mkdir()
env={'PATH':os.environ['PATH'],'HOME':str(home),'AEEP_DATA_HOME':str(home/'data'),'AEEP_CONFIG_HOME':str(home/'config'),'UV_PYTHON_PREFERENCE':'only-managed'}
release=repo/'dist/v0.8.2-onboarding-continuation'
base=['sh',str(release/'install.sh'),'--bundle',str(release/'bundle'),'--agent','deepseek-api','--yes','--project']
with (report/'recovery-failure.log').open('w') as log:
 failed=subprocess.run([*base,str(root/'missing-project')],env=env,cwd=project,stdout=log,stderr=subprocess.STDOUT,timeout=300)
assert failed.returncode!=0
manifest=home/'config/config.yaml'
assert manifest.exists()
manifest.write_bytes(manifest.read_bytes()+b'\n# preserve during recovery\n')
saved=manifest.read_bytes()
active=(home/'data/venv').resolve()
with (report/'recovery-resume.log').open('w') as log:
 subprocess.run([*base,str(project)],env=env,cwd=project,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=300)
assert manifest.read_bytes()==saved
assert (home/'data/venv').resolve()==active
connection=json.loads((home/'config/connections/deepseek-api.json').read_text())
assert connection['enabled']
result={'status':'passed','scope':'Recovery after real setup failure, not arbitrary process-death recovery','initial_exit_code':failed.returncode,'workspace':str(root),'checks':['retained installed runtime after invalid project setup','preserved operator manifest edit','rerun configured valid project','active runtime preserved']}
(report/'recovery-result.json').write_text(json.dumps(result,indent=2)+'\n')
