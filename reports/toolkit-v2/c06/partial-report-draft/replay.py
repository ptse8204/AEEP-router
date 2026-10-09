import json,os,shutil,subprocess,sys,tempfile
from pathlib import Path
ROOT=Path('/Users/edwintse/Documents/aeep-toolkit-v2')
DRAFT=Path(__file__).parent
layout=Path(tempfile.mkdtemp(prefix='aeep-toolkit-partial-layout-',dir=ROOT.parent))
integration=layout/'integrations/toolkit'
shutil.copytree(ROOT/'integrations/toolkit',integration,ignore=shutil.ignore_patterns('__pycache__'))
for name in ('controlled.py','controlled_report.py','verify_controlled.py'):
 shutil.copyfile(DRAFT/name,integration/name)
core=layout/'src/aeep_toolkit';core.mkdir(parents=True)
for name in ('candidate.py','__init__.py'):shutil.copyfile(ROOT/'src/aeep_toolkit'/name,core/name)
suite=json.loads((ROOT/'examples/toolkit_offline/suite.json').read_text())
suite.pop('retain_outputs')
suite['evals']=suite['evals'][:1]
suite['evals'][0]['prompt']='AEEP_SYNTHETIC_EDIT_V1\n'+json.dumps({'files':{'file.txt':'repeat repeat'},'replacements':[{'file':'file.txt','old':'repeat','new':'changed'}]})
(layout/'suite.json').write_text(json.dumps(suite))
output=layout/'failure-output'
args=['--candidate',str(ROOT/'examples/toolkit_offline/format-json'),'--suite',str(layout/'suite.json'),'--source',str(ROOT/'examples/toolkit_offline/source.json'),'--runtime','/private/tmp/aeep-ase-c04-tt14mj6r/rebuild','--output',str(output),'--image','sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7','--docker','/usr/local/bin/docker','--socket','/Users/edwintse/.docker/run/docker.sock']
env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
command=[sys.executable,str(integration/'evaluate.py')]
plan=subprocess.run(command+['plan',*args],env=env,text=True,capture_output=True,check=True)
(layout/'plan.json').write_text(plan.stdout)
review=json.loads(plan.stdout)['review_sha256']
run=subprocess.run(command+['run',*args,'--reviewed-digest',review],env=env,text=True,capture_output=True)
(layout/'run.log').write_text(run.stdout+run.stderr)
assert run.returncode != 0
verify=subprocess.run(command+['report','--output',str(output)],env=env,text=True,capture_output=True)
(layout/'verify.log').write_text(verify.stdout+verify.stderr)
print(json.dumps({'layout':str(layout),'run_returncode':run.returncode,'verify_returncode':verify.returncode,'verification':verify.stdout,'diagnostic':verify.stderr},indent=2))
