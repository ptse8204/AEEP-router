"""Check new preparation and routing on an isolated in-memory authority fixture."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, AssessmentSubject, content_digest
from aeep.models import ActionConstraints, ActionRequest, Manifest, utc_now

import run as driver

HERE = Path(__file__).resolve().parent


async def main():
    _prior, _request, prompt, schema, _wire = driver.payload()
    pair, shared = driver.pair_for(schema)
    runtime = Manifest.model_validate(driver.read(driver.SOURCE_MANIFEST))
    runtime = runtime.model_copy(update={'database':':memory:','executors':[pair.control,pair.treatment],
                                         'registries':[]})
    for policy in runtime.policies.values():
        policy.fallback.enabled = False
    helpers = driver.load_module('evoagentx_preparation_test_helpers',driver.SKILLSBENCH/'run-engineering.py')
    prepared = {}
    helpers.prepared.write = lambda name,value: prepared.setdefault(str(name),value)
    router = driver.Router(runtime)
    service = driver.AssessmentService(router,driver.WORK.parent)
    repo = service.repository
    try:
        subject = AssessmentSubject(subject_id='evoagentx-in-memory-preparation',kind='command',
            location=str(driver.HANDOFF/'planner-bridge.py'),dependency_digests={},
            description='First-party preparation fixture')
        recipe = driver.shipped_recipe('text')
        subject_ref = repo.put('subject',subject.subject_id,subject)
        recipe_ref = repo.put('recipe',recipe.recipe_id,recipe)
        env_ref = repo.put('shared_environment_definition',content_digest(shared),helpers.previous.Document(value=shared))
        repo.grant(AssessmentAuthorization(authorization_id='onboarding',
            subject_digests=[subject_ref],recipe_digests=[recipe_ref],environment_digests=[env_ref],
            limits=AssessmentLimits(max_operations=5,max_model_turns=1,max_elapsed_seconds=880),
            expires_at=utc_now()+timedelta(hours=1)))
        ids = helpers.worker_requests(service,'evoagentx',pair,recipe,subject,
                                      driver.verification_source_digest(driver.ROOT))
        definition, requests, workers, probes = helpers.inspection.authorize_pair(service,*ids)
        assert definition == pair and len(requests) == len(workers) == len(probes) == 2
        for key in ids:
            assert not repo.operation_ledger(key).operations
        assert helpers.budget.self_check() == 7
        campaign = router._campaign_router([pair.control],plan_digest='e'*64)
        try:
            request = ActionRequest(capability=driver.CAPABILITY,input={'prompt':prompt},
                constraints=ActionConstraints(allowed_executor_ids=[pair.control.id],allow_network=False))
            decision = campaign.route(request)
            assert decision.selected_executor_id == pair.control.id
            assert {item.executor_id for item in decision.candidates if item.feasible} == {pair.control.id}
        finally:
            await campaign.close()
        result = {'kind':'first_party_in_memory_authority_fixture','passed':True,'authorized_inspection_definitions':2,
                  'canonical_preparation_passed':True,'route_selected_only_control':True,
                  'budget_controls':7,'workers_started':0,'models':0}
        driver.write(HERE/'preparation-controls.json',result)
        print(driver.encode(result))
    finally:
        await router.close()


if __name__ == '__main__':
    asyncio.run(main())
