"""Synthetic archive controls for the read-only layer checker; no Docker."""
import copy
import hashlib
import importlib.util
import io
import json
import tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('image_layer_checker',HERE/'image-audit.py')
audit=importlib.util.module_from_spec(spec);spec.loader.exec_module(audit)
files={'/opt/dependencies/stack-check/SKILL.md':b'fixture skill',
       '/opt/dependencies/stack-check/LICENSE':b'fixture notice'}
manifest={'Layers':['base']+['layer'+str(i) for i in range(5)]}
entries=[
 [('opt/dependencies/stack-check','directory',0o444,None),('opt/dependencies/stack-check/SKILL.md','file',0o444,files['/opt/dependencies/stack-check/SKILL.md'])],
 [('opt/dependencies/stack-check/LICENSE','file',0o444,files['/opt/dependencies/stack-check/LICENSE'])],
 [('etc/codex/skills','directory',0o755,None)],
 [('opt/dependencies/stack-check','directory',0o555,None),('etc/codex/skills','directory',0o555,None)],
 [('etc/codex/skills/stack-check','symlink',0o777,'/opt/dependencies/stack-check')],
]
def archive(rows):
 out=io.BytesIO()
 with tarfile.open(fileobj=out,mode='w') as container:
  values=[('manifest.json',json.dumps([manifest]).encode()),('base',b'base contents deliberately not interpreted')]
  for index,layer in enumerate(rows):
   data=io.BytesIO()
   with tarfile.open(fileobj=data,mode='w') as stream:
    for name,kind,mode,payload in layer:
     item=tarfile.TarInfo(name);item.mode=mode
     if kind=='directory':item.type=tarfile.DIRTYPE
     elif kind=='symlink':item.type=tarfile.SYMTYPE;item.linkname=payload
     else:item.size=len(payload)
     stream.addfile(item,io.BytesIO(payload) if kind=='file' else None)
   values.append(('layer'+str(index),data.getvalue()))
  for name,payload in values:
   item=tarfile.TarInfo(name);item.size=len(payload);container.addfile(item,io.BytesIO(payload))
 return out.getvalue()
def check(rows):
 raw=archive(rows)
 def substitute(_docker,_image,consume):
  with tarfile.open(fileobj=io.BytesIO(raw),mode='r|*') as stream:return consume(stream)
 audit.stream=substitute
 return audit.audit([], 'synthetic-image-not-a-real-digest', {p:hashlib.sha256(v).hexdigest() for p,v in files.items()})
assert check(entries)['passed']
controls=['five new layers and exact directory/file/alias metadata accepted']
for name,location,replacement in [
 ('unreadable-directory',(3,0),('opt/dependencies/stack-check','directory',0o444,None)),
 ('wrong-alias',(4,0),('etc/codex/skills/stack-check','symlink',0o777,'/wrong')),
 ('modified-file',(0,1),('opt/dependencies/stack-check/SKILL.md','file',0o444,b'changed')),
 ('unexpected-new-path',(2,0),('unexpected','directory',0o755,None)),
]:
 rows=copy.deepcopy(entries);rows[location[0]][location[1]]=replacement
 try:check(rows)
 except AssertionError:controls.append(name+' rejected')
 else:raise AssertionError(name)
(HERE/'image-audit-controls.json').write_text(json.dumps({'passed':True,'controls':controls,'synthetic_archives_only':True,'actual_images_examined':0},indent=2)+'\n')
print(json.dumps({'passed':True,'controls':len(controls),'Docker_calls':0}))
