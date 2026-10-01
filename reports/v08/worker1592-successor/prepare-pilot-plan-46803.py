"""Existing service proposal only; no enqueue, model trial, or qualification."""
import json, hashlib
from pathlib import Path
from aeep.router import Router
from aeep.assessment.service import AssessmentService
from aeep.assessment.models import AssessmentEnvironment, PilotPolicy, content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
ROOT=Path(__file__).resolve().parents[3]; OUT=Path(__file__).parent
r=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json'); s=AssessmentService(r,ROOT/'.aeep/live-review-v3/.aeep/assessments'); q=s.repository
try:
 source=verification_source_digest(ROOT); material=json.loads((OUT/'materialization-corrected-46803-result.json').read_text()); assert material['materialization_passed'] and material['source_digest']==source
 prep=json.loads((OUT/'pilot-materialization-corrected-46803-review.json').read_text()); pair=q.get('worker_pair_definition','a62371cc67388021616af291ec55e8c4c6e4952ec5003d558e84c0f1fe04b729')
 for role in ('control','treatment'): r.registry.replace(ExecutorSpec.model_validate(pair[role]))
 env=AssessmentEnvironment.model_validate(prep['environment'])
 plan=s.propose(subject_id=prep['request']['subject_digest'],family=prep['request']['recipe_digest'],candidate_id=pair['treatment']['id'],baseline_id=pair['control']['id'],authorization_id='onboarding',environment=env,seed=109,case_set_id=material['case_set_digest'],pilot=PilotPolicy())
 preview=s.budget_preview(plan.plan_id)
 assert len(plan.suite.cases)==8 and len({c.case_id for c in plan.suite.cases})==8 and all(c.split.value=='qualification' for c in plan.suite.cases)
 assert preview['minimum_trial_model_turns']==16
 record={'source_digest':source,'plan':plan.model_dump(mode='json'),'plan_digest':content_digest(plan),'budget_preview':preview,'materialization_result_sha256':hashlib.sha256((OUT/'materialization-corrected-46803-result.json').read_bytes()).hexdigest(),'not_enqueued':True,'no_qualification_or_admission_or_benefit':True,'exposure':'Existing treatment requires the Spreadsheets candidate: forced invocation timing pilot only; not optional-use value.'}
 (OUT/'pilot-plan-46803-preparation.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps({'plan_id':plan.plan_id,'plan_digest':content_digest(plan),'blocked_reasons':plan.blocked_reasons,'preview':preview}))
finally:r.store.close()
