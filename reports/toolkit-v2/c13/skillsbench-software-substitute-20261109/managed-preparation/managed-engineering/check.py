"""Exercise the ordinary CLI against an isolated database without workers."""

import asyncio
import json
import runpy
import subprocess
import sys
import tempfile
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentLimits, AssessmentPlan, AssessmentSetupRequest,
    IncrementalExperiment, UtilityPolicy, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.models import Manifest, utc_now
from aeep.router import Router

RUN = runpy.run_path(str(Path(__file__).with_name('run.py')))
engine, read, save = (RUN[k] for k in ('engine','read','save'))


def check(work):
    rights, _, recipe, pair, _, env, cases, _, _ = RUN['definitions']()
    defs = RUN['DEFS']
    manifest = Manifest.model_validate(read(engine.BASE)).model_copy(update={
        'database':str(work/'fixture.sqlite3'), 'executors':[pair.control,pair.treatment],
    })
    manifest_path = work/'aeep.json'
    save(manifest_path,manifest.model_dump(mode='json'))
    registered = engine.cli('define-rights','--manifest',manifest_path,'--file',defs/'rights.json')
    rights_ref = content_digest(rights)
    assert registered == {'rights_review_ref':rights_ref,'reviewed':False,'execution_authorized':False}
    router = Router.from_manifest(manifest_path)
    try:
        service = AssessmentService(router,work/'campaigns')
        repo = service.repository
        subject = service.inspect_local(engine.prepared.SKILL,kind='skill')
        recipe_ref = repo.put('recipe',recipe.recipe_id,recipe)
        env_ref = repo.put('environment',env.environment_id,env)
        case_ref = repo.put('integration_case_set',content_digest(cases),cases)
        experiment = IncrementalExperiment(stage='qualification',exposure='required',environment=pair.differential,
            utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'],guardrail_dimensions=['wall_time_ms']))
        exp_ref = repo.put('experiment',content_digest(experiment),experiment)
        subject_ref = content_digest(subject)
        grant = AssessmentAuthorization(authorization_id='isolated-cli-fixture',subject_digests=[subject_ref],
            recipe_digests=[recipe_ref],environment_digests=[env_ref],allowed_destinations=['local'],remote_disclosure=False,
            limits=AssessmentLimits(max_operations=64,max_elapsed_seconds=3900,max_model_turns=1),
            expires_at=utc_now()+timedelta(minutes=5))
        repo.grant(grant)
        for ref in (subject_ref,recipe_ref,env_ref,case_ref,exp_ref):
            repo.review(ref)
        request = AssessmentSetupRequest(schema_version='assessment.setup.v2',authorization_id=grant.authorization_id,
            subject_id=subject.subject_id,recipe_id=recipe.recipe_id,environment_id=env.environment_id,
            candidate_id=pair.treatment.id,baseline_id=pair.control.id,structure='controlled_agent',
            integration_case_set_id=case_ref,experiment_id=exp_ref)
        request_path = work/'setup.json'
        save(request_path,request.model_dump(mode='json'))
        workflow = read(defs/'workflow.json')
        workflow['configurations'][RUN['CONFIGURATION']]['preparation'] = {
            'source':engine.binding(engine.PREVIOUS/'source.json'),'manifest':engine.binding(manifest_path),
            'request':engine.binding(request_path),
        }
        config = work/'workflow.json'
        save(config,workflow)
        common = ('--workflow',config,*RUN['CONFIG'])
        preview = engine.cli('plan',*common)
        assert preview['blockers'] == ['canonical plan preparation is selected but has not been performed']
        output = work/'prepared'
        args = (*common,'--write-plan',output,'--directory',service.directory,'--reviewed-digest',preview['review_sha256'])
        rejection = subprocess.run([sys.executable,'-B','-m','aeep_toolkit','workflow','prepare',*map(str,args)],
                                   env=engine.PATH_ENV,cwd=RUN['ROOT'],capture_output=True,text=True,timeout=20)
        assert rejection.returncode == 2 and not output.exists(), rejection.stderr
        repo.review(rights_ref)
        ready = engine.cli('prepare',*args)
        plan = AssessmentPlan.model_validate_json((output/'plan.json').read_bytes())
        assert ready['plan_digest'] == content_digest(plan) and ready['execution_authorized'] is False
        assert plan.schema_version == 'assessment.plan.v7' and plan.environment_digest == env_ref
        assert plan.recipe_digest == recipe_ref and plan.integration_case_set_digest == case_ref
        assert plan.suite.cases == cases.cases and [route.executor_id for route in plan.suite.routes] == [pair.treatment.id]
        assert plan.suite.conditions == ['fresh-worker'] and plan.suite.repetitions == 1
        assert plan.comparison.experiment.stage == 'qualification' and plan.comparison.experiment.exposure == 'required'
        assert not plan.blocked_reasons
        assert not repo.operation_ledger(plan.plan_id).operations
        assert repo.store._connection.execute('SELECT count(*) FROM assessment_jobs').fetchone()[0] == 0
        budget = service.budget_preview(plan.plan_id)
        return {'fixture':'Isolated local CLI draft using the exact public files and protected grader binding',
                'unreviewed_rights_rejected':True,'readiness': 'PENDING_FRESH_WORKER_CHECKS',
                'cli_plan_schema':plan.schema_version,'one_required_use_route':True,
                'recipe_digest':recipe_ref,'environment_digest':env_ref,'case_set_digest':case_ref,
                'campaign_upper_allowance':budget['campaign_allowance']['upper_allowance'],
                'workers_started':0,'jobs_created':0,'model_turns':0,'provider_transfer':False}
    finally:
        asyncio.run(router.close())


if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='aeep-prefix-cli-inert-') as tmp:
        print(json.dumps(check(Path(tmp).resolve()),indent=2))
