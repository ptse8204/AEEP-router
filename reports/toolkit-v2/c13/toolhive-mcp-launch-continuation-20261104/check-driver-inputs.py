"""Development regression for relocated inputs; no external executables."""
import copy,hashlib,importlib.util,json,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('bound_inputs',HERE/'input_binding.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
review=json.loads((HERE/'operation-review.json').read_bytes());checks=[]
assert not (HERE/'server.py').exists()
facts=m.verify_inputs(review);assert facts['server_source']==review['assets'][review['server_source']];checks.append('relocated report folder needs no local server copy')
with tempfile.TemporaryDirectory(prefix='aeep-bound-inputs-') as temp:
    source=Path(temp)/'server.py';source.write_bytes(Path(review['server_source']).read_bytes())
    altered=copy.deepcopy(review);altered['server_source']=str(source);altered['assets'][str(source)]=review['assets'][review['server_source']]
    m.verify_inputs(altered);source.write_bytes(source.read_bytes()+b'\n# synthetic drift\n')
    try:m.verify_inputs(altered)
    except AssertionError:checks.append('source drift rejected before dispatch')
    else:raise AssertionError('source drift accepted')
    source.unlink()
    try:m.verify_inputs(altered)
    except AssertionError:checks.append('missing source rejected before dispatch')
    else:raise AssertionError('missing input accepted')
image={'Id':review['retained_image_id'],'RootFS':{'Layers':review['retained_image_layers']},'Config':{'User':'65534:65534','Entrypoint':['/usr/local/bin/python3','-I','-B','/opt/aeep-reviewed-mcp.py']}}
m.verify_image(review,image);image['Id']='sha256:'+'0'*64
try:m.verify_image(review,image)
except AssertionError:checks.append('changed retained image rejected')
else:raise AssertionError('changed image accepted')
text=(HERE/'run.py').read_text();assert "sha(HERE/'server.py')" not in text and 'self.review[\'controller_profile\']' in text
checks.append('driver reads reviewed source/profile bindings, not output-folder inputs')
result={'passed':True,'evidence_kind':'FIRST_PARTY_DRIVER_PREPARATION_ONLY','checks':checks,'fixture_source_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'actual_ToolHive_Docker_MCP_model_execution':False,'runtime_functional_gate':'OPEN'}
(HERE/'driver-input-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
