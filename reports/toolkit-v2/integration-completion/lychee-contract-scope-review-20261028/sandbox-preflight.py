import json,pathlib,socket,sys,uuid
root,scratch=map(pathlib.Path,sys.argv[1:])
checks={'public_project_readable':bool((root/'README.md').read_text())}
for name,path in [('private_assessment_denied',root/'.aeep'),('other_home_project_denied',pathlib.Path('/Users/edwintse/Documents/aeep-agent-router'))]:
 try:
  list(path.iterdir());checks[name]=False
 except PermissionError:checks[name]=True
s=socket.socket();s.settimeout(.2)
try:
 s.connect(('127.0.0.1',9));checks['network_denied']=False
except PermissionError:checks['network_denied']=True
finally:s.close()
p=scratch/'home'/'canary.txt';p.write_text('fixture');checks['scratch_write']=p.read_text()=='fixture'
p=root/('aeep-docs-canary-'+uuid.uuid4().hex+'.txt')
try:
 with p.open('x') as f:f.write('fixture')
 checks['project_write_denied']=False
 if p.read_text()=='fixture':p.unlink()
except PermissionError:checks['project_write_denied']=True
print(json.dumps(checks));assert all(checks.values())
