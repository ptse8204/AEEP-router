import hashlib,json,tempfile,shutil,time
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentPlan,AssessmentAuthorization,AssessmentScopeAmendment,content_digest
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
p=json.loads((OUT/'pilot-workflow-46803-preparation.json').read_text());plan=AssessmentPlan.model_validate(p['plan']);assert not plan.blocked_reasons and verification_source_digest(ROOT)==p['source_digest']
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository
try:
 roots={content_digest(plan),plan.subject_digest,plan.recipe_digest,plan.mapping_digest,plan.environment_digest,*plan.definition_digests,plan.recipe_case_set_digest};defs={}
 for digest in roots:
  row=r.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(digest,)).fetchone();assert row;defs[digest]=json.loads(row[0])
 grant=AssessmentAuthorization.model_validate(q.get('authorization','onboarding'));am=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],reviewed_digests=list(defs))
 before=r.store._connection.execute('SELECT kind,count(*),sum(length(payload_json)) FROM assessment_records GROUP BY kind ORDER BY kind').fetchall();before=[list(x) for x in before]
 owned=Path(tempfile.mkdtemp(prefix='aeep-actual-pilot-snapshot-'));target=owned/'pilot.sqlite3';began=time.monotonic();snap=r.store.campaign_snapshot(target,bound_digests=roots)
 tables=('assessment_reviews','assessment_grants','assessment_admissions','host_correlation_keys','route_candidates','qualification_reports','rate_card_snapshots','provider_signing_keys','provider_packages','provider_package_signatures','content_artifacts','provider_package_artifacts','evidence_records','evidence_acceptances','smoke_test_reports','candidate_verification_snapshots')
 exact={t:[tuple(x) for x in r.store._connection.execute('SELECT * FROM '+t)]==[tuple(x) for x in snap._connection.execute('SELECT * FROM '+t)] for t in tables};assert all(exact.values())
 rows=[list(x) for x in snap._connection.execute('SELECT kind,count(*),sum(length(payload_json)) FROM assessment_records GROUP BY kind ORDER BY kind')];snap.close();size=target.stat().st_size;sha=hashlib.sha256(target.read_bytes()).hexdigest();after=[list(x) for x in r.store._connection.execute('SELECT kind,count(*),sum(length(payload_json)) FROM assessment_records GROUP BY kind ORDER BY kind')];assert before==after
 allowance=p['budget_preview']['campaign_allowance']['upper_allowance'];ops=allowance['operations'];storage={'actual_materialized_plan_digest':content_digest(plan),'snapshot_bytes':size,'snapshot_sha256':sha,'elapsed_seconds':time.monotonic()-began,'rows':rows,'authority_tables_exact':exact,'canonical_record_counts_and_bytes_unchanged':True,'owned_path_removed':str(owned),'snapshot_copies_conservative_upper':ops,'copy_bytes_upper':size*ops,'finite_disk_allowance_bytes':size*ops+256*1024*1024,'purpose':'Exact current pilot closure times all finite operations conservatively; additional256MiB covers owned attempt/log growth, not whole-system memory or storage acceptance.'};shutil.rmtree(owned)
 review={'authority':'Standing finite amendment; parent authorized existing workflow timing structure for two independently conformed workers. No controlled causal, qualification, admission, benefit or production acceptance claim. Inert controlled-agent plan and failed preparation records retained.','source_digest':p['source_digest'],'plan_id':plan.plan_id,'plan_digest':content_digest(plan),'definitions':defs,'amendment':am.model_dump(mode='json'),'budget_preview':p['budget_preview'],'storage':storage,'exposure':'Forced Spreadsheets candidate workflow timing only','automatic_retries':0,'maximum_operations':ops,'maximum_model_turns':16,'maximum_reserved_seconds':allowance['elapsed_seconds'],'maximum_cash_usd':0,'not_enqueued':True}
 (OUT/'pilot-workflow-46803-review.json').write_text(json.dumps(review,indent=2)+'\n');print(json.dumps({'plan_id':plan.plan_id,'review_sha256':hashlib.sha256((OUT/'pilot-workflow-46803-review.json').read_bytes()).hexdigest(),'storage':storage,'maximum_operations':ops,'maximum_seconds':allowance['elapsed_seconds']}))
finally:r.store.close()
