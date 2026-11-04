"""New first-party metadata fixtures, not a repeat of the service pipeline."""
import hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('corrected_service_identity',HERE/'run-service.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
reference='registry.invalid/reviewed@sha256:'+'a'*64
review={'images':{'web':reference},'image_ids':{'web':'sha256:'+'a'*64},'image_layer_diff_ids':{'web':['sha256:'+'b'*64]}}
row=['sha256:'+'a'*64,[reference],['sha256:'+'b'*64]]
encode=lambda xs:' '.join(json.dumps(x) for x in xs)
m.validate_image_record('web',encode(row),review)
for index,value in [(0,'sha256:wrong'),(1,['registry.invalid/other@sha256:wrong']),(2,['sha256:wrong'])]:
    wrong=list(row);wrong[index]=value
    try:m.validate_image_record('web',encode(wrong),review)
    except AssertionError:pass
    else:raise AssertionError('wrong OCI identity accepted')
obj=object.__new__(m.Journey);obj.owned={}
obj.review={'service_image_allowed_ids':{'web':[row[0],'sha256:'+'c'*64]},'service_image_allowed_references':{'web':[reference]}}
values=['sha256:owned','/'+m.PROJECT+'-web',row[0],{m.LABEL:m.PROJECT,'com.docker.compose.service':'web','com.docker.compose.project':m.PROJECT},'running',0,reference]
obj.command=lambda *_a,**_k:encode(values)+'\n'
obj.docker=lambda *args:['FIRST_PARTY_NOT_EXECUTED',*args]
assert obj.inspect([m.PROJECT+'-web'])[0]['id']=='sha256:owned'
values[2]='sha256:'+'c'*64;assert obj.inspect([m.PROJECT+'-web'])[0]['id']=='sha256:owned'
values[-1]='registry.invalid/not-reviewed@sha256:'+'a'*64
try:obj.inspect([m.PROJECT+'-web'])
except AssertionError:pass
else:raise AssertionError('wrong declared reference accepted')
result={'passed':True,'evidence_kind':'NEW_FIRST_PARTY_OCI_IDENTITY_FIXTURES_NOT_DOCKER_OR_SERVICE_EXECUTION','checks':['exact reported image ID, reference and ordered layer diffIDs','wrong ID/reference/layer list rejected','same pinned artifact can report manifest or config container identity','unreviewed container image reference rejected'],'upstream_execution':False,'services':0,'models':0}
result['fixture_source_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
(HERE/'identity-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
