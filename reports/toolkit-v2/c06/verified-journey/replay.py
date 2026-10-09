"""Bounded, zero-turn replays of the public synthetic suite; no installation."""
import json,os,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
REPORT=Path(__file__).resolve().parent
os.chdir(ROOT)
records=[]
for mode in ('retained','private','failure'):
 suite=json.loads((ROOT/'examples/toolkit_offline/suite.json').read_text())
 if mode!='retained':suite.pop('retain_outputs')
 if mode=='failure':
  suite['evals']=suite['evals'][:1]
  suite['evals'][0]['prompt']='AEEP_SYNTHETIC_EDIT_V1\n'+json.dumps({'files':{'file.txt':'repeat repeat'},'replacements':[{'file':'file.txt','old':'repeat','new':'changed'}]})
 suite_path=REPORT/(mode+'-suite.json')
 suite_path.write_text(json.dumps(suite,indent=2)+'\n')
 output=REPORT/mode
 options=['--candidate',str(ROOT/'examples/toolkit_offline/format-json'),'--suite',str(suite_path),'--source',str(ROOT/'examples/toolkit_offline/source.json'),'--runtime','/private/tmp/aeep-ase-c04-tt14mj6r/rebuild','--output',str(output),'--image','sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7','--docker','/usr/local/bin/docker','--socket','/Users/edwintse/.docker/run/docker.sock']
 command=[sys.executable,'integrations/toolkit/evaluate.py']
 env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
 def run(args,suffix,expected):
  result=subprocess.run(command+args,env=env,text=True,capture_output=True)
  (REPORT/(mode+'-'+suffix)).write_text(result.stdout+result.stderr)
  records.append({'mode':mode,'argv':command+args,'returncode':result.returncode,'expected_returncode':expected})
  (REPORT/'commands.json').write_text(json.dumps(records,indent=2)+'\n')
  assert result.returncode==expected
  return result.stdout
 plan=json.loads(run(['plan',*options],'plan.json',0))
 run(['run',*options,'--reviewed-digest',plan['review_sha256']],'run.log',1 if mode=='failure' else 0)
 verified=json.loads(run(['report','--output',str(output)],'verification.json',0))
 assert verified['verified_trials']==(0 if mode=='failure' else 6)
 assert verified['recorded_trials']==(1 if mode=='failure' else 6)
 print(mode,verified['execution_state'],flush=True)
