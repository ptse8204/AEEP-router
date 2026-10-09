"""Exercise the installed upstream parser and command builder; never run Codex."""
import hashlib,json,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'integrations/toolkit'))
from stack import manifest,sandbox,verify_runtime
RUNTIME=Path('/private/tmp/aeep-ase-c04-tt14mj6r/rebuild')
OUTPUT=Path(__file__).with_name('result.json')
assert not OUTPUT.exists()
facts=verify_runtime(RUNTIME,manifest())
program='''import json
from pathlib import Path
from agent_skill_eval.harnesses import CodexHarness
h=CodexHarness(Path.cwd(),model='synthetic-model',reasoning_effort='low',timeout=5,max_retries=0)
observations=[]
for label,raw in [('no_events',''),('missing_usage',json.dumps({'type':'turn.completed'})),('partial_usage',json.dumps({'type':'turn.completed','usage':{'input_tokens':7}}))]:
 _,timing=h.parse_output(raw,'')
 observations.append({'fixture':label,'parsed':timing.model_dump()})
print(json.dumps({'parser_fixtures':observations,'built_command_only':h.build_command('public synthetic prompt',Path.cwd()),'default_environment_is_inherited':h._build_env() is None,'model_calls':0}))
'''
started=time.monotonic()
with tempfile.TemporaryDirectory(prefix='aeep-ase-codex-parser-') as directory:
 root=Path(directory).resolve()
 prefix,env=sandbox(root,RUNTIME)
 code=root/'probe.py';code.write_text(program)
 result=subprocess.run([*prefix,str(code)],env=env,cwd=root,capture_output=True,text=True,timeout=15,check=True)
 assert len(result.stdout)<8192 and not result.stderr
 parsed=json.loads(result.stdout)
 assert parsed['model_calls']==0
 assert all(row['parsed']['output_tokens']==0 for row in parsed['parser_fixtures'])
 record={'source_revision':manifest()['evaluator']['source_revision'],'wheel_sha256':manifest()['evaluator']['wheel_sha256'],'runtime_inventory':facts,'program_sha256':hashlib.sha256(program.encode()).hexdigest(),'evidence_kind':'synthetic interface probe','observations':parsed,'elapsed_seconds':time.monotonic()-started,'finding':'Missing primary usage is parsed as zero; default Codex command uses a workspace sandbox and inherits the caller environment. This native harness alone does not meet AEEP paired-worker and unknown-accounting requirements.','scope':'No model, credential, image, network, or installation operation; command was built but not executed.'}
 OUTPUT.write_text(json.dumps(record,indent=2)+'\n')
 print(record['finding'])
