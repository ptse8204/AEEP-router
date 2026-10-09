import hashlib,json,urllib.request
from datetime import datetime,timezone
from pathlib import Path
from aeep_toolkit.models import DeveloperIdentity,SourcePin
from aeep.assessment.models import content_digest
root=Path('/Users/edwintse/Documents/aeep-toolkit-v2')
out=root/'reports/toolkit-v2/c12/developer-source'
def fetch(url):
 req=urllib.request.Request(url,headers={'User-Agent':'AEEP-source-review'})
 with urllib.request.urlopen(req,timeout=30) as response:return response.read()
ref=json.loads(fetch('https://api.github.com/repos/DietrichGebert/ponytail/git/ref/tags/v4.10.0'))
obj=ref['object']
if obj['type']=='tag':obj=json.loads(fetch(obj['url']))['object']
assert obj['type']=='commit'
commit=obj['sha']; sources=[]; contents={}
assert commit=='1d95ff7d39de12d87014ea40d4e22201bddc501b'
for path in ['package.json','LICENSE','.github/FUNDING.yml','skills/ponytail/SKILL.md']:
 url=f'https://raw.githubusercontent.com/DietrichGebert/ponytail/{commit}/{path}'
 try:
  data=fetch(url);contents[path]=data
  sources.append({'path':path,'url':url,'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'status':200})
 except urllib.error.HTTPError as e:
  sources.append({'path':path,'url':url,'status':e.code})
package=json.loads(contents['package.json'])
assert package['version']=='4.10.0'
skill_sha=hashlib.sha256(contents['skills/ponytail/SKILL.md']).hexdigest()
assert skill_sha=='1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2'
funding=contents.get('.github/FUNDING.yml',b'').decode().strip()
assert funding=='github: [DietrichGebert]'
evidence={'recorded_at':datetime.now(timezone.utc).isoformat(),'commit':commit,'tag':'v4.10.0','sources':sources,'declared_author':package['author'],'funding_declaration':funding,'subject_skill_sha256':skill_sha,'scope':'Matches the historical selected skill bytes. GitHub source declaration only; no legal identity, ownership or payment attestation.','candidate_executed':False,'installation_performed':False}
assertion=content_digest(evidence)
source=SourcePin(repository='https://github.com/DietrichGebert/ponytail',revision=commit,artifact_sha256=content_digest({'SKILL.md':skill_sha}),license_expression='MIT',data_rights='Source-declared MIT for pinned repository code; no task dataset redistribution claim.')
developer=DeveloperIdentity(source=source,identity='DietrichGebert',assertion_ref=assertion,support_url='https://github.com/sponsors/DietrichGebert',support_kind='donation')
(out/'source-review.json').write_text(json.dumps(evidence,indent=2)+'\n')
(out/'developer.json').write_text(developer.model_dump_json(indent=2)+'\n')
(out/'source.json').write_text(source.model_dump_json(indent=2)+'\n')
print(json.dumps({'commit':commit,'skill_sha256':skill_sha,'assertion_ref':assertion,'support':'source-declared donation link','executed':False}))
