"""Freeze the existing text qualification campaign; no enqueue or worker execution."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.boundary import require_differential, require_managed_boundaries
from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentScopeAmendment, RecipeDefinition, IncrementalExperiment, UtilityPolicy, content_digest
from aeep.assessment.extensions import prepare, materialize
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];OUT=Path(__file__).parent;PRIOR=OUT.parent/'edit-study-preparation'
CANONICAL=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
async def main():
    assert not (OUT/'qualification-review.json').exists()
    with (OUT/'preparation-v2-started.json').open('x') as marker:json.dump({'source_digest_expected':'d05541e90d2e200ba1ea61b4169a8ebcdf62fd96217fdbe35a81e42accd4d1b0'},marker)
    pair=json.loads((OUT/'pair-review.json').read_text());boundary=json.loads((OUT/'boundary-result.json').read_text())
    pair_result=json.loads((OUT/'pair-result.json').read_text());assert pair_result['paired_checks_passed'] and pair_result['source_unchanged'] and pair_result['proxy_restored_stopped']
    source=verification_source_digest(ROOT);assert source==pair['source_digest']==boundary['source_digest']
    definition=pair['definitions'][pair['pair_definition_digest']]
    router=Router.from_manifest(CANONICAL/'aeep.json');service=AssessmentService(router,CANONICAL/'.aeep/assessments');repo=service.repository
    try:
        specs=[ExecutorSpec.model_validate(definition[r]) for r in ('control','treatment')]
        for spec in specs:router.register(spec)
        from aeep.assessment.models import AssessmentSubject
        from aeep.assessment.identity import verify_subject
        subject_record=AssessmentSubject.model_validate(repo.get('subject','subject_7d5c4d6ed2c955adf5883ea254748758fb7dbe3b9d02453582794208de20644b'));verify_subject(subject_record);assert subject_record.dependency_digests=={'SKILL.md':'1316a2f3f95741d2300b116fe0c2d81ce4a9568656ed0a62643f54aaf09957f2'};subject=content_digest(subject_record)
        recipe=RecipeDefinition.model_validate_json((PRIOR/'recipe.json').read_text())
        env=AssessmentEnvironment(environment_id='toolkit-edit-prompt-20261019-'+source[:12],kind='container',
            identity={'source_digest':source,'purpose':'Three-family editing successor after proxy OOM repair; unchanged workers and thresholds','proxy_memory_bytes':'536870912','proxy_repair_review_sha256':'3f6f9d94c29c6b7473f5dc3b550d2b553c41270fd1e181da833fdeeaa77e1912'},
            container_image='sha256:b40522e4be1a398b9366333096d80066097f2784f04f3a0838256b057e9b6228',container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock',memory_mb=512,
            conformance_digests={spec.id:boundary['boundaries'][role]['conformance_digest'] for role,spec in zip(('control','treatment'),specs,strict=True)},
            differential_conformance_digest=boundary['differential_conformance_digest'])
        assert __import__('shutil').disk_usage(ROOT).free>51*1024**3
        request=prepare(service,subject_id=subject,recipe_id=content_digest(recipe),authorization_id='onboarding',environment=env,seed=2026101903)
        scope_ds=set(request.definition_digests)|{subject,content_digest(request)}
        scope_docs={d:json.loads(router.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(d,)).fetchone()[0]) for d in scope_ds}
        grant=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'))
        scope_amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=content_digest(grant),subject_digests=[subject],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=sorted(scope_ds))
        case_review={'authority':'Standing September25/27 first-party fixture definition and finite scope delegation','preregistration_sha256':hashlib.sha256((OUT/'preregistration.json').read_bytes()).hexdigest(),'worker_pair_digest':pair['pair_definition_digest'],'request':request.model_dump(mode='json'),'amendment':scope_amendment.model_dump(mode='json'),'definitions':scope_docs,'maximum_operations':1,'maximum_reserved_seconds':20,'model_turns':0,'cash_usd':0}
        with (OUT/'case-materialization-review.json').open('x') as f:json.dump(case_review,f,indent=2)
        repo.approve_bundle(scope_amendment,scope_docs)
        cases=await materialize(service,request.plan_id)
        from aeep.assessment.models import AssessmentPlan
        previous=AssessmentPlan.model_validate(repo.get('plan','plan_0a8359a155184098ad3ba790f8a77f55'))
        old_inputs={content_digest(case.action.input) for case in previous.suite.cases}
        second=AssessmentPlan.model_validate(repo.get('plan','plan_16fb057af234452e91214c6829348d29'));old_inputs.update(content_digest(case.action.input) for case in second.suite.cases)
        assert len(cases.cases)==141 and not old_inputs.intersection(content_digest(case.action.input) for case in cases.cases)
        (OUT/'case-materialization-result.json').write_text(json.dumps({'request_id':request.plan_id,'case_set_digest':content_digest(cases),'cases':len(cases.cases),'seed':cases.seed,'model_calls':0},indent=2)+'\n')
        utility=UtilityPolicy(benefit_dimensions=['task_success','wall_time_ms','input_tokens','output_tokens'],
            guardrail_dimensions=['wall_time_ms','input_tokens','output_tokens'])
        experiment=IncrementalExperiment(stage='qualification',exposure='required',environment=definition['differential'],utility=utility)
        plan=service.propose(subject_id=subject,family=content_digest(recipe),candidate_id=specs[1].id,baseline_id=specs[0].id,
            authorization_id='onboarding',environment=env,seed=2026101903,case_set_id=request.plan_id,structure='controlled_agent',experiment=experiment)
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
            'scope':'Three-family qualification uses required candidate exposure. It cannot demonstrate optional selection or comparative benefit.',
            'stop_rules':'Existing assessment execution, correctness, budget and conformance gates unchanged; no automatic retry or threshold adjustment.',
            'new_families':'Easy literal edit, bounded three-file rename, adjacent unchanged-file counting. No arbitrary-code execution or broad programming competence claim.',
            'predecessor_plan_id':'plan_0a8359a155184098ad3ba790f8a77f55','predecessor_inputs_disjoint':True,'qualification_seed':2026101903,'durable_subject_location':subject_record.location}
        (OUT/'qualification-review.json').write_text(json.dumps(review,indent=2)+'\n')
        print(json.dumps({k:review[k] for k in ('plan_id','plan_digest','blocked_reasons','not_enqueued')}));print(json.dumps(budget['campaign_allowance']['upper_allowance']));print(json.dumps(budget['campaign_allowance']['gaps']))
    finally:await router.close()
asyncio.run(main())
