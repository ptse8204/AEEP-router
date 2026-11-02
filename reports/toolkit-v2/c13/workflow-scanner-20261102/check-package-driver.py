"""First-party installation/child substitutes; no package installation or SDK."""
import importlib.util,json,shutil,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('grouped_review_driver',HERE/'run-review.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
checks=[]
for failure in (None,'install','boundary','source-cli'):
 with tempfile.TemporaryDirectory(prefix='aeep-package-driver-fixture-') as directory:
  work=Path(directory).resolve()
  for name in ('package-check.py','package-boundary.py'):shutil.copyfile(HERE/name,work/name)
  calls=[]
  def apply(*args):
   calls.append('apply')
   if failure=='install':raise ValueError('explicit first-party installation failure')
   return {'status':'installed'}
  async def command(review,name,argv,payload,seconds):
   calls.append(name)
   assert seconds<=60 and len(argv)==1 and Path(argv[0]).is_file()
   if name==failure:raise ValueError('explicit first-party child failure')
   return {'passed':True,'fixture':True}
  with patch.object(module,'HERE',work),patch.object(module,'apply',apply),patch.object(module,'digest',lambda p:'a'*64),patch.object(module,'snapshot',lambda p:{}),patch.object(module,'package_command',command):
   result=module.package({'package':{'runtime':str(work/'runtime'),'installed_source':'b'*64},'identity':'first-party-fixture','minimum_headroom_bytes':0},SimpleNamespace(destination=str(work/'runtime')))
  assert result['passed']==(failure is None),result
  if failure=='install':assert calls==['apply']
  if failure=='boundary':assert calls==['apply','apply','boundary']
  assert result['runtime_retained'] is True
  checks.append({'fault':failure,'passed':True,'substitute_calls':calls})
(HERE/'first-party-package-driver.json').write_text(json.dumps({'passed':True,'evidence_kind':'first_party_substitutes',
 'upstream_executed':False,'installed':False,'checks':checks},indent=2)+'\n')
print(json.dumps(checks))
