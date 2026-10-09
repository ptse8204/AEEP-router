import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
os.chdir(ROOT)
REPORT=Path(__file__).resolve().parent
output=REPORT/'retained-output'
command=[sys.executable,'integrations/toolkit/evaluate.py']
options=['--candidate',str(ROOT/'examples/toolkit_offline/format-json'), '--suite',str(ROOT/'examples/toolkit_offline/suite.json'),'--source',str(ROOT/'examples/toolkit_offline/source.json'),'--runtime','/private/tmp/aeep-ase-c04-tt14mj6r/rebuild','--output',str(output),'--image','sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7','--docker','/usr/local/bin/docker','--socket','/Users/edwintse/.docker/run/docker.sock']
records=[]
def run(args,name):
 argv=command+args
 result=subprocess.run(argv,capture_output=True,text=True,env={**os.environ,'PYTHONPATH':str(ROOT/'src')})
 (REPORT/name).write_text(result.stdout+result.stderr)
 records.append({'argv':argv,'returncode':result.returncode,'log':name})
 (REPORT/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
 if result.returncode:raise SystemExit(result.returncode)
 return result.stdout
plan=json.loads(run(['plan',*options],'plan.json'))
run(['run',*options,'--reviewed-digest',plan['review_sha256']],'run.log')
run(['report','--output',str(output)],'verification.json')
print('Six synthetic workers completed; report verified.')
