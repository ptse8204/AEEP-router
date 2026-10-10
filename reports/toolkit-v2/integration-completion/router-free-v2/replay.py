import hashlib,json,os,subprocess,time
from pathlib import Path
root=Path('/Users/edwintse/Documents/aeep-toolkit-v2');os.chdir(root)
r=root/'reports/toolkit-v2/integration-completion/router-free-v2';output=r/'result'
python='/Library/Frameworks/Python.framework/Versions/3.13/bin/python3'
env={**os.environ,'PYTHONPATH':str(root/'src')}
wrapper=r/'no_router.py'
base=[python,'-B',str(wrapper)]
args=['--candidate',str(root/'examples/toolkit_offline/format-json'),'--suite',str(r/'private-suite.json'),'--source',str(root/'examples/toolkit_offline/source.json'),'--runtime','/private/tmp/aeep-ase-c04-tt14mj6r/rebuild','--output',str(output),'--image','sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7','--docker','/usr/local/bin/docker','--socket','/Users/edwintse/.docker/run/docker.sock']
review={'authority':'September 25/27 standing finite test delegation; current continuous V2 instruction','purpose':'Current-source upstream adapter journey with Router construction prohibited','source':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'worker_limit':6,'model_turn_limit':0,'cash_limit':0,'pull_limit':0,'credentials':False,'network':'none in workers; existing coordinator sandbox','timeout_seconds':240,'entrypoint_sha256':hashlib.sha256(wrapper.read_bytes()).hexdigest(),'free_disk_bytes':__import__('shutil').disk_usage(root).free,'image':args[args.index('--image')+1]}
(r/'review.json').write_text(json.dumps(review,indent=2)+'\n')
checks=[]
def run(argv,name):
 start=time.monotonic()
 with (r/name).open('w') as log:
  rc=subprocess.run(argv,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=240).returncode
 checks.append({'argv':argv,'returncode':rc,'seconds':time.monotonic()-start,'log':name})
 (r/'checks.json').write_text(json.dumps(checks,indent=2)+'\n');print(name,rc,flush=True)
 if rc:raise SystemExit(rc)
run(base+['plan']+args,'plan.json')
review['reviewed_digest']=json.loads((r/'plan.json').read_text())['review_sha256']
(r/'review.json').write_text(json.dumps(review,indent=2)+'\n')
run(base+['run']+args+['--reviewed-digest',review['reviewed_digest']],'run.log')
run(base+['report','--output',str(output)],'verification.json')
names=set(subprocess.check_output(['/usr/local/bin/docker','-H','unix:///Users/edwintse/.docker/run/docker.sock','ps','-a','--format','{{.Names}}'],text=True).splitlines())
workers={trial['worker_name'] for trial in json.loads((output/'result.json').read_text())['trials']}
(r/'cleanup-audit.json').write_text(json.dumps({'worker_names':sorted(workers),'remaining':sorted(workers & names),'cleanup_confirmed':not(workers & names)},indent=2)+'\n')
assert len(workers)==6 and not(workers & names)
print('exact worker cleanup confirmed',flush=True)
