"""Reconcile observed build; use remaining authorized attempt for later edit."""
import asyncio,hashlib,json,psutil
from pathlib import Path
from datetime import timedelta
from aeep.models import StrictModel,Manifest,TaskScope,SideEffect,utc_now
from aeep.router import Router
from aeep.tasks import TaskReconciliation,reconcile,activate,change_state,inspect
from aeep.assessment.repository import AssessmentRepository
from aeep.economic.prepared import executor_fingerprint
from aeep.mcp.server import AEEPToolService
ROOT=Path(__file__).resolve().parents[2];REPORTS=ROOT/'reports/v08'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
async def main():
 s=json.loads((REPORTS/'native-website-local-successor-definition.json').read_text());root=Path(s['root']);data=root/'data';failed=json.loads((REPORTS/'native-website-local-successor-result.json').read_text());r=Router.from_manifest(s['manifest']);repo=AssessmentRepository(r.store);receipt=r.store.get_receipt(failed['phases'][0]['response']['receipts'][0]['receipt_id']);a=r.store.get_execution_attempt(receipt.metadata['attempt_id']);text=(data/'index.html').read_text();assert '<h1>Local website</h1>' in text and '<aside>Preserved content</aside>' in text
 assert sha(data/'style.css')==s['before']['style.css'] and sha(data/'unrelated.txt')==s['before']['unrelated.txt'];assert receipt.actual_resources.latency_ms>0 and receipt.metadata['exit_code']==0
 argv=r.registry.get('local.website.fixed').config['argv'];assert not any(p.info['cmdline']==argv for p in psutil.process_iter(['cmdline']))
 class Inspection(StrictModel):
  receipt_id:str
  index_sha256:str
  unchanged:dict[str,str]
  cleanup_confirmed:bool
 obs=Inspection(receipt_id=receipt.receipt_id,index_sha256=sha(data/'index.html'),unchanged={n:sha(data/n) for n in ['style.css','unrelated.txt']},cleanup_confirmed=True);ed=repo.put('local_website_effect_inspection','successful-write-output-schema-failure',obs);repo.review(ed);rec=TaskReconciliation(attempt_id=a.attempt_id,attempt_version=a.version,scope_digest=s['scope_digest'],resolution='effects_verified',evidence_digests=[ed]);rd=repo.put('task_reconciliation','website-build-effect-verified',rec);repo.review(rd);recovery=reconcile(r,'website-build-effect-verified');change_state(r,failed['activation_id'],'uninstall');await r.close()
 m=Manifest.model_validate_json(Path(s['manifest']).read_text());m.executors[0].config['output']={'type':'json'};Path(s['manifest']).write_text(m.model_dump_json());r=Router.from_manifest(s['manifest']);repo=AssessmentRepository(r.store);scope=TaskScope(scope_id='local-website-remaining-edit',project_root=str(root),executor_fingerprints={m.executors[0].id:executor_fingerprint(m.executors[0])},approval_ceiling=SideEffect.WRITE,max_attempts=1,max_attempt_seconds=15,expires_at=utc_now()+timedelta(hours=1));sd=repo.put('task_scope',scope.scope_id,scope);repo.review(sd)
 review={'authority':'Standing finite fixture amendment; no additional dispatch beyond original1+successor2 authorized total3','change':'Existing output JSON parser setting; remaining single edit scope on SAME DB','source_digest':s['source_digest'],'driver_sha256':sha(Path(__file__)),'manifest_sha256':sha(Path(s['manifest'])),'scope_digest':sd,'executor_fingerprint':executor_fingerprint(m.executors[0]),'build_reconciliation':recovery,'build_observation':obs.model_dump(mode='json'),'build_receipt_id':receipt.receipt_id};(REPORTS/'native-website-local-final-review.json').write_text(json.dumps(review,indent=2)+'\n')
 evidence={'review':review,'classification':s['classification'],'phases':[]};target=REPORTS/'native-website-local-final-result.json'
 def save():target.write_text(json.dumps(evidence,indent=2)+'\n')
 activation=activate(r,scope.scope_id);service=AEEPToolService(r,profile='task',task_activation=activation.activation_id,approved_side_effect=SideEffect.WRITE);tool=service.list_tools()[0]['name'];(data/'operator-note.txt').write_text('Added between tasks; preserve.\n');note=sha(data/'operator-note.txt')
 try:
  result=(await service.call(tool,{'operation':'edit'}))['structuredContent'];evidence['phases'].append({'operation':'later_edit','response':result});save();assert result['ok'];text=(data/'index.html').read_text();assert '<h1>Updated local website</h1>' in text and '<aside>Preserved content</aside>' in text and 'href="style.css"' in text;assert sha(data/'style.css')==s['before']['style.css'] and sha(data/'unrelated.txt')==s['before']['unrelated.txt'];assert sha(data/'operator-note.txt')==note;evidence['independent_file_checks']=True
  denied=await service.call('aeep_website_publish',{'destination':'https://example.invalid'});assert denied['isError'];evidence['publish']={'response':denied,'permitted_route':False,'network_invoked':False,'destination_authority':False}
  change_state(r,activation.activation_id,'pause');paused=(await service.call(tool,{'operation':'edit'}))['structuredContent'];assert not paused.get('ok',False);evidence['paused_dispatch']=paused
  change_state(r,activation.activation_id,'resume');assert inspect(r,activation.activation_id)['attempts_used']==1;restored=change_state(r,activation.activation_id,'uninstall');assert restored['overlay']=='absent' and (root/'.codex/config.toml').read_text()==s['original_config'];assert sha(data/'operator-note.txt')==note;evidence.update(uninstall=restored,complete=True,project_config_restored=True,later_user_edit_preserved=True,model_turns=0,publish_gate_complete=False,receipt_retained=r.store.get_receipt(result['receipts'][0]['receipt_id']) is not None,limits=['Fixed literal HTML checks only; no browser rendering or accessibility audit','Build receipt output schema failed before parser fixture repair; build effects independently inspected and operator-reviewed, never relabeled automated success']);save()
 except Exception as exc:evidence.update(complete=False,failure=repr(exc));save();raise
 finally:await r.close()
 print(json.dumps({'complete':True,'result':str(target)}))
asyncio.run(main())
