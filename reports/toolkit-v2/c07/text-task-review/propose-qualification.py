"""Freeze the existing text qualification campaign; no enqueue or worker execution."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.boundary import require_differential, require_managed_boundaries
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSetupCost, IncrementalExperiment, UtilityPolicy, content_digest
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent
CANONICAL=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
    assert not (OUT/'qualification-review.json').exists()
    pair=json.loads((OUT/'pair-review.json').read_text());boundary=json.loads((OUT/'boundary-result.json').read_text())
    source=verification_source_digest(ROOT);assert source==pair['source_digest']==boundary['source_digest']
    definition=pair['definitions'][pair['pair_definition_digest']]
    router=Router.from_manifest(CANONICAL/'aeep.json');service=AssessmentService(router,CANONICAL/'.aeep/assessments');repo=service.repository
    try:
        specs=[ExecutorSpec.model_validate(definition[r]) for r in ('control','treatment')]
        for spec in specs:router.register(spec)
        assert router.registry.get('reference.text') == reference_spec('text')
        subject=pair['requests'][0]['subject_digest']
        capture=json.loads((OUT.parent/'worker-readiness/candidate-capture.json').read_text())
        cost=AssessmentSetupCost(cost_id='toolkit-ponytail-source-capture-20261009',subject_digest=subject,
            stage='source_capture',elapsed_seconds=capture['elapsed_seconds'],cpu_ms=capture['coordinator_cpu_seconds']*1000)
        repo.put('setup_cost',cost.cost_id,cost)
        env=AssessmentEnvironment(environment_id='toolkit-text-qualification-'+source[:12],kind='codex_sandbox',
            identity={'source_digest':source,'purpose':'Text qualification only, current exact capable profiles'},
            conformance_digests={spec.id:boundary['boundaries'][role]['conformance_digest'] for role,spec in zip(('control','treatment'),specs,strict=True)},
            differential_conformance_digest=boundary['differential_conformance_digest'])
        utility=UtilityPolicy(benefit_dimensions=['task_success','wall_time_ms','input_tokens','output_tokens'],
            guardrail_dimensions=['wall_time_ms','input_tokens','output_tokens'])
        experiment=IncrementalExperiment(stage='qualification',exposure='required',environment=definition['differential'],utility=utility)
        plan=service.propose(subject_id=subject,family='text',candidate_id=specs[1].id,baseline_id=specs[0].id,
            authorization_id='onboarding',environment=env,seed=2026100901,structure='controlled_agent',experiment=experiment)
        require_managed_boundaries(repo,env,specs,{spec.id:boundary['boundaries'][role]['identity_digest'] for role,spec in zip(('control','treatment'),specs,strict=True)})
        require_differential(repo,env,plan)
        router.managed_hosts.configure(specs,principal_salt=router.store.host_principal_key,manifest_directory=router.manifest_path.parent)
        budget=service.budget_preview(plan.plan_id)
        ds=set(plan.definition_digests)|{content_digest(plan),plan.subject_digest}
        documents={d:json.loads(router.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in ds}
        grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),
            subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],reviewed_digests=sorted(ds))
        review={'authority':'Standing September25/27 routine finite scope and test definition delegation',
            'source_digest':source,'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'plan_id':plan.plan_id,'plan_digest':content_digest(plan),'definitions':documents,
            'amendment':amendment.model_dump(mode='json'),'budget_preview':budget,'blocked_reasons':plan.blocked_reasons,
            'qualification':False,'admission':False,'not_enqueued':True,'utility':utility.model_dump(mode='json'),
            'scope':'Qualification uses required candidate exposure. It cannot demonstrate optional selection or comparative benefit.',
            'stop_rules':'Existing assessment execution, correctness, budget and conformance gates unchanged; no automatic retry or threshold adjustment.',
            'new_families':'This is the existing text extraction qualification only. Complex coding and adjacent/no-benefit value families still require applicable task mappings and separate preregistration; text correctness cannot substitute for them.'}
        (OUT/'qualification-review.json').write_text(json.dumps(review,indent=2)+'\n')
        print(json.dumps({k:review[k] for k in ('plan_id','plan_digest','blocked_reasons','not_enqueued')}));print(json.dumps(budget['campaign_allowance']['upper_allowance']));print(json.dumps(budget['campaign_allowance']['gaps']))
    finally:await router.close()
asyncio.run(main())
