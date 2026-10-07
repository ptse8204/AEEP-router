"""Rosetta x86_64 installer check, explicitly not evidence from physical Intel hardware."""
import json
import os
import subprocess
from pathlib import Path

repo=Path(__file__).resolve().parents[3]
report=Path(__file__).parent
root=Path('/tmp/aeep-onboarding-continuation/macos-x86')
root.mkdir(exist_ok=False)
home,project=root/'home',root/'project'
home.mkdir();project.mkdir()
env={'PATH':os.environ['PATH'],'HOME':str(home),'AEEP_DATA_HOME':str(home/'data'),'AEEP_CONFIG_HOME':str(home/'config'),'UV_PYTHON_PREFERENCE':'only-managed'}
release=repo/'dist/v0.8.2-onboarding-continuation'
with (report/'macos-x86.log').open('w') as log:
 subprocess.run(['arch','-x86_64','/bin/sh',str(release/'install.sh'),'--bundle',str(release/'bundle'),'--agent','deepseek-api','--project',str(project),'--yes'],env=env,cwd=project,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=300)
 python=home/'data/venv/bin/python'
 architecture=subprocess.check_output([str(python),'-c','import platform; print(platform.machine())'],env=env,text=True).strip()
 assert architecture=='x86_64',architecture
 subprocess.run([str(python),str(repo/'scripts/check_installer.py'),'--release',str(release),'--workspace',str(root/'journey')],env=env,cwd=project,check=True,stdout=log,stderr=subprocess.STDOUT,timeout=600)
record={'status':'passed','scope':'macOS x86_64 under Rosetta on Apple Silicon; physical Intel hardware unverified','runtime_architecture':architecture,'workspace':str(root),'journey':json.loads((root/'journey/result.json').read_text())}
(report/'macos-x86-result.json').write_text(json.dumps(record,indent=2)+'\n')
