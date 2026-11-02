"""Two trusted stdlib boundary probes; no optional runtime execution."""
import asyncio,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
spec=importlib.util.spec_from_file_location('boundary_driver',HERE/'run-review.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
review=json.loads((HERE/'review-draft.json').read_bytes());review['identity']='d'*64
stage=ROOT/'.aeep/workflow-lifecycle-preparation-20261102'
async def main():
 results=[]
 for name in ('framework','package'):
  work=stage/('boundary-'+name);work.mkdir()
  for directory in ('home','tmp'):(work/directory).mkdir()
  worker=work/'boundary-check.py';worker.write_bytes((HERE/'boundary-check.py').read_bytes())
  original=HERE/'execution/owned-work'/name
  profile=(HERE/(name+'.sb')).read_text().replace(str(original),str(work))
  profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in work.parents if p.is_relative_to(Path.home()))+')\n'
  boundary=work/'profile.sb';boundary.write_text(profile)
  model,context=module.make_spec(review,name,[str(worker)],20)
  model.config['argv'][2]=str(boundary)
  model.config['argv'][3]=str(Path(sys.executable).resolve())
  model.config['argv'].insert(model.config['argv'].index('-I')+1,'-S')
  model.config['cwd']=str(work)
  model.config['env']['HOME']=str(work/'home');model.config['env']['TMPDIR']=str(work/'tmp')
  executor=module.CommandExecutor()
  try:raw=await(await executor.start(context)).task
  finally:await executor.close()
  assert raw.status.value=='success' and raw.output['passed'] is True,(raw.error_type,raw.stderr)
  results.append({'component':name,'passed':True,'checks':raw.output['checks'],
   'profile_adaptation':'Same rules, prospective working path replaced with owned preparation path; ancestor metadata only.',
   'retained_work':str(work),'upstream_executed':False})
 return results
result={'passed':True,'upstream_executed':False,'trusted_stdlib_only':True,'results':asyncio.run(main())}
(HERE/'first-party-boundary.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
