import json,hashlib
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentScopeAmendment
from aeep.assessment.boundary import BoundaryConformance,require_conformance
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[3];OUT=Path(__file__).parent
review=json.loads((OUT/'boundary-review.json').read_text());assert hashlib.sha256((OUT/'boundary-review.json').read_bytes()).hexdigest()=='de97143fd1a922021af3514002af3fff08a264e4a7c9bb1fbf1ecbe4e91ea5f4';assert verification_source_digest(ROOT)==review['source_digest'];assert json.loads((OUT/'connectivity-typed-result.json').read_text())['connectivity_passed'];assert not(OUT/'boundary-verifier-result.json').exists()
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments');q=s.repository;result={'source_digest':review['source_digest'],'verifier':'existing aeep.assessment.boundary.require_conformance','connectivity_result_sha256':hashlib.sha256((OUT/'connectivity-typed-result.json').read_bytes()).hexdigest(),'no_workbook_execution':True,'no_admission':True,'records':{}}
try:
 q.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']),review['definitions'])
 for role,digest in review['conformance_records'].items():
  expected=BoundaryConformance.model_validate(q.get('boundary_conformance',digest));actual=require_conformance(q,digest,source_digest=review['source_digest'],worker_digest=expected.worker_digest,identity_digest=expected.identity_digest);assert actual==expected
  result['records'][role]={'digest':digest,'existing_verifier_accepted':True,'worker_digest':actual.worker_digest,'identity_digest':actual.identity_digest,'probe_count':len(actual.probe_digests)}
 result['full_boundary_verifier_accepted']=len(result['records'])==2
except Exception as exc:result.update(full_boundary_verifier_accepted=False,error_type=type(exc).__name__,safe_verifier_message=str(exc) if str(exc).startswith('environment verification unavailable:') else 'review or verifier rejected')
finally:(OUT/'boundary-verifier-result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result));r.store.close()
