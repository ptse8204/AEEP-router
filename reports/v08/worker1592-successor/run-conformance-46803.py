import asyncio,hashlib,json,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import execute_pair
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
SOURCE='46803ee2814c77977c4408b60768c6581fc0189f0c8fb9a8ccd7dd77ccc4b236'
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 review=json.loads((OUT/'conformance-46803-review.json').read_text());assert hashlib.sha256((OUT/'conformance-46803-review.json').read_bytes()).hexdigest()=='77c6d4e357ea6c933de2a1b14758915c48fd30fe8111127b60c11189bd11eac8'
 assert not(OUT/'conformance-46803-result.json').exists()
 r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');service=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');repo=service.repository
 result={'source_digest':SOURCE,'request_ids':review['request_ids'],'model_turns':0,'images':review['images'],'started':True,'replay_allowed':False,'no_admission':True};began=time.monotonic()
 try:
  repo.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
  async with asyncio.timeout(500):pair=await execute_pair(service,*review['request_ids'])
  result['pair']=pair;workers={}
  for role in ['control','treatment']:
   record=repo.get('worker_pair_inspection',pair['workers'][role]['record_digest']);inspection=record['observations']['inspection'];models=inspection.get('models',[]);sol=[m for m in models if m['id']=='gpt-6.1-sol']
   workers[role]={'cleanup_confirmed':record['observations'].get('cleanup_confirmed'),'identity_digest':inspection.get('identity_digest'),'model_present':len(sol)==1,'medium_present':len(sol)==1 and 'medium' in sol[0]['reasoning_efforts'],'models':models,'failed_stage':inspection.get('failed_stage'),'error_type':inspection.get('error_type')}
  result['workers']=workers;result['conformance_passed']=bool(pair.get('probes_match')) and all(v['cleanup_confirmed'] and v['identity_digest'] and v['model_present'] and v['medium_present'] for v in workers.values())
 except BaseException as exc:result.update(conformance_passed=False,error_type=type(exc).__name__)
 finally:
  result['elapsed_seconds']=time.monotonic()-began;result['source_unchanged']=verification_source_digest(ROOT)==SOURCE
  row=r.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',('onboarding',)).fetchone();result['grant_after']=dict(zip(('operations','model_turns','elapsed_seconds','cash_usd'),row))
  (OUT/'conformance-46803-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));await r.close()
asyncio.run(main())
