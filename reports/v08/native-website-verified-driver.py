"""Two fixed SDK task writes with operator-registered independent callback; no CLI support claim."""
import asyncio,hashlib,json,sys
from datetime import timedelta
from pathlib import Path
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.models import Manifest,SideEffect,TaskScope,ValidationKind,ValidationSpec,utc_now
from aeep.router import Router
from aeep.tasks import activate,change_state,inspect
from aeep.mcp.server import AEEPToolService
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08';REVIEW=REPORTS/'native-website-verified-review.json';RESULT=REPORTS/'native-website-verified-result.json'
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 s=json.loads((REPORTS/'native-website-local-successor-definition.json').read_text());root=Path(s['root']);data=root/'data';manifest=Path(s['manifest']);oracle=REPORTS/'native-website-verified-oracle.json'
 if sys.argv[1]=='prepare':
  assert not REVIEW.exists();index='<!doctype html><html lang="en"><head><title>Verified fixture</title><link rel="stylesheet" href="verified.css"></head><body><h1>Draft</h1><aside>Preserve literal content</aside></body></html>';style='body { color: #222; background: #fff; }\n';note='Keep this unrelated operator note.\n'
  files={'verified.html':index,'verified.css':style,'verified-note.txt':note}
  for name,value in files.items():assert not (data/name).exists();(data/name).write_text(value)
  expected={op:{**files,'verified.html':index.replace('<h1>Draft</h1>','<h1>'+heading+'</h1>')} for op,heading in [('build','Verified local website'),('edit','Verified updated website')]}
  oracle.write_text(json.dumps({'expected':expected,'output':{op:{'operation':op,'updated':'verified.html'} for op in expected}},indent=2)+'\n')
  spec=Manifest.model_validate_json(manifest.read_text()).executors[0];spec=spec.model_copy(deep=True);spec.id='local.website.fixed.verified';spec.capability='local.website.fixed@1';program="import json,sys;from pathlib import Path;x=json.load(sys.stdin);p=Path("+repr(str(data/'verified.html'))+");text=p.read_text();old,new={'build':('<h1>Draft</h1>','<h1>Verified local website</h1>'),'edit':('<h1>Verified local website</h1>','<h1>Verified updated website</h1>')}[x['operation']];assert text.count(old)==1;p.write_text(text.replace(old,new));print(json.dumps({'operation':x['operation'],'updated':'verified.html'}))";spec.config['argv']=[s['python'],'-I','-c',program];spec.config.update(stdin_json=True,argv_literal=True,output={'type':'json'});spec.output_schema['properties']['updated']={'const':'verified.html'};spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'operator.local.website.fixed.v1','driver_sha256':sha(Path(__file__)),'oracle_sha256':sha(oracle)})]
  m=Manifest.model_validate_json(manifest.read_text());m.executors=[spec];manifest.write_text(m.model_dump_json());r=Router.from_manifest(manifest);repo=AssessmentRepository(r.store);scope=TaskScope(scope_id='local-website-verified-build-edit',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.WRITE,max_attempts=2,max_attempt_seconds=15,expires_at=utc_now()+timedelta(hours=3));sd=repo.put('task_scope',scope.scope_id,scope);repo.review(sd)
  review={'authority':'Parent exact bounded successor instruction and standing finite test-definition delegation','source_digest':SOURCE,'driver_sha256':sha(Path(__file__)),'oracle_sha256':sha(oracle),'manifest_sha256':sha(manifest),'scope_id':scope.scope_id,'scope_digest':sd,'executor_fingerprint':executor_fingerprint(spec),'attempts':2,'seconds_per_attempt':15,'same_database':str(root/'.aeep/state.db'),'root':str(root),'inputs':{op:{'operation':op} for op in expected},'input_hashes':{op:digest({'operation':op}) for op in expected},'output_hashes':{op:digest({'operation':op,'updated':'verified.html'}) for op in expected},'fixture_before_sha256':{n:sha(data/n) for n in files},'original_config':(root/'.codex/config.toml').read_text(),'validator':'Operator-registered trusted SDK CallbackValidator; exact driver/oracle reviewed, oracle outside native data roots','limits':['SDK-only: no automatic website validator in fresh CLI','Fixed literal local artifact checks only; no arbitrary website, browser rendering, live model or publication claims']};REVIEW.write_text(json.dumps(review,indent=2)+'\n');await r.close();print(json.dumps(review));return
 review=json.loads(REVIEW.read_text());assert sha(Path(__file__))==review['driver_sha256'] and sha(oracle)==review['oracle_sha256'] and sha(manifest)==review['manifest_sha256'];truth=json.loads(oracle.read_text());r=Router.from_manifest(manifest)
 def verify(context):
  op=context.input.get('operation')
  if op not in truth['expected'] or digest(context.input)!=review['input_hashes'][op] or digest(context.output)!=review['output_hashes'][op]:return False
  if sha(oracle)!=review['oracle_sha256'] or sha(Path(__file__))!=review['driver_sha256']:return False
  if any((data/name).read_text()!=content for name,content in truth['expected'][op].items()):return False
  if op=='edit' and (data/'verified-later-note.txt').read_text()!='Added after build; keep.\n':return False
  return True
 # Small negative calibration: success-shaped output cannot hide missing or corrupted artifact.
 for op in ('build','edit'):
  from aeep.validators import ValidationContext
  assert verify(ValidationContext({'operation':op},truth['output'][op])) is False
 r.validator_callbacks['operator.local.website.fixed.v1']=verify
 evidence={'review_sha256':sha(REVIEW),'source_digest':SOURCE,'classification':'Fixed offline SDK local website build/edit lifecycle; no live model or deployment evidence','phases':[],'limits':review['limits']}
 def save():RESULT.write_text(json.dumps(evidence,indent=2)+'\n')
 assert not RESULT.exists();activation=activate(r,review['scope_id']);evidence['activation_id']=activation.activation_id;service=AEEPToolService(r,profile='task',task_activation=activation.activation_id,approved_side_effect=SideEffect.WRITE);tool=service.list_tools()[0]['name']
 try:
  for op in ('build','edit'):
   if op=='edit':(data/'verified-later-note.txt').write_text('Added after build; keep.\n')
   result=(await service.call(tool,review['inputs'][op]))['structuredContent'];evidence['phases'].append({'operation':op,'response':result});save();assert result['ok'];receipt=result['receipts'][0];assert receipt['task_valid'] is True and any(c['kind']=='callback' and c['valid'] is True and c['trust']=='verified' for c in receipt['checks']);assert 'non-schema task checks passed' in result['summary'];assert verify(ValidationContext(review['inputs'][op],result['output']))
  denied=await service.call('aeep_website_publish',{'destination':'https://example.invalid'});assert denied['isError'];evidence['publish']={'denied':True,'response':denied,'network_invoked':False}
  change_state(r,activation.activation_id,'pause');paused=(await service.call(tool,{'operation':'edit'}))['structuredContent'];assert not paused.get('ok',False);evidence['paused_dispatch']=paused;change_state(r,activation.activation_id,'resume');assert inspect(r,activation.activation_id)['attempts_used']==2
  evidence['undo']=change_state(r,activation.activation_id,'rollback');assert evidence['undo']['overlay']=='absent' and (root/'.codex/config.toml').read_text()==review['original_config'];assert verify(ValidationContext({'operation':'edit'},truth['output']['edit']));evidence['receipts_durable']=all(r.store.get_receipt(p['response']['receipts'][0]['receipt_id']) is not None for p in evidence['phases']);evidence.update(complete=True,source_unchanged=verification_source_digest(ROOT)==SOURCE,negative_callback_calibration=True,task_files_preserved_after_undo=True,scope_allowance_reset=False,model_turns=0);save()
 except Exception as exc:evidence.update(complete=False,failure=repr(exc));save();raise
 finally:await r.close()
 print(json.dumps({'complete':True,'result':str(RESULT)}))
asyncio.run(main())
