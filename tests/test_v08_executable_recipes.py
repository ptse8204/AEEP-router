"""Recipe lifecycle fixtures; mocked containment is never host conformance evidence."""

from __future__ import annotations

import os
from collections import Counter
from datetime import timedelta

import pytest

from aeep.assessment.extensions import materialize, prepare, structural_features
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    ExecutableRecipeExtension,
    RecipeDefinition,
    RecipeFeatureRule,
    RecipeLiteralFixture,
)
from aeep.assessment.onboarding import reference_spec
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.executors.command import CommandExecutor
from aeep.models import ExecutorSpec, Manifest, utc_now
from aeep.router import Router

pytestmark = pytest.mark.assessment_lifecycle

GENERATOR = '''import json,random,sys
p=json.load(sys.stdin); rng=random.Random(p['seed']); cases=[]
for stage in p['stages']:
 for i in range(stage['count']):
  n=i%3+1; value={'items':[str(rng.getrandbits(128)) for _ in range(n)]}
  cases.append({'input':value,'output':{'count':n},'variation':str(n),'template_family':'list-count'})
print(json.dumps({'cases':cases}))
'''
GRADER = "import json,sys; p=json.load(sys.stdin); print(json.dumps({'valid':[e['output']==e['expected'] for e in p['examples']]}))"
REFERENCE = "import json,sys; p=json.load(sys.stdin); print(json.dumps({'outputs':[{'count':len(v['items'])} for v in p['inputs']]}))"
CANDIDATE = "import json,sys,time; p=json.load(sys.stdin); print(json.dumps({'count':len(p['items'])}))"


def program(name, code):
    return ExecutorSpec(id=name, capability="example.count@1", kind="command", description="Controlled extension fixture",
        estimate=reference_spec("csv").estimate,
        config={"argv": ["python3", "-c", code], "stdin_json": True,
                "timeout_seconds": 5, "max_output_bytes": 1000000, "output": {"type": "json"}})


def definition(generator=GENERATOR, grader=GRADER):
    return RecipeDefinition(schema_version="assessment.recipe.v2", recipe_id="contained-list-count",
        capability="example.count@1", description="Reviewed executable count fixture",
        input_schema={"type":"object", "properties":{"items":{"type":"array","items":{"type":"string"},"maxItems":3}}, "required":["items"], "additionalProperties":False},
        output_schema={"type":"object", "properties":{"count":{"type":"integer"}}, "required":["count"], "additionalProperties":False},
        generator="contained_json:1", grader="contained_json:1", extractor="structural_json:1",
        variations=["1", "2", "3"], extension=ExecutableRecipeExtension(
            generator=program("generator", generator), grader=program("grader", grader), reference=program("reference", REFERENCE),
            independent_fixtures=[RecipeLiteralFixture(input={"items":["a"]}, output={"count":1}), RecipeLiteralFixture(input={"items":["a","b"]}, output={"count":2})],
            transformed_fixtures=[RecipeLiteralFixture(input={"items":["b","a"]}, output={"count":2})],
            fault_outputs=[{"count":-1}], feature_rules={"length":RecipeFeatureRule(path="/items", operation="length")},
            variation_features={str(n):{"length":n} for n in (1,2,3)}, template_families=["list-count"]))


class LocalContainmentFixture(CommandExecutor):
    def __init__(self, *_args, **_kwargs):
        super().__init__()


def setup(tmp_path, monkeypatch, *, recipe=None, real=False):
    if not real:
        # Recovery keeps a module-level adapter import; initialize it before the
        # local lifecycle replacement so other boundary tests retain real cleanup.
        __import__("aeep.assessment.recovery")
        monkeypatch.setattr("aeep.assessment.containment.ContainerExecutor", LocalContainmentFixture)
    recipe = recipe or definition()
    candidate = program("candidate", CANDIDATE)
    baseline = program("baseline", CANDIDATE.replace("p=json.load(sys.stdin);", "p=json.load(sys.stdin); time.sleep(.01);"))
    router = Router(Manifest(database=":memory:", executors=[candidate, baseline]))
    service = AssessmentService(router, tmp_path / "assessment")
    selected = tmp_path / "plugin.txt"
    selected.write_text("Controlled fixture; not a real plugin benefit claim")
    subject = service.inspect_local(selected)
    service.repository.put("recipe", recipe.recipe_id, recipe)
    environment = AssessmentEnvironment(environment_id="recipe-container", kind="container", identity={},
        container_image=os.environ.get("AEEP_CONTAINER_IMAGE", "sha256:" + "1" * 64),
        container_runtime=os.environ.get("AEEP_CONTAINER_RUNTIME", os.path.abspath("/fixture/docker")),
        container_socket=os.environ.get("AEEP_CONTAINER_SOCKET", os.path.abspath("/fixture/docker.sock")))
    request = prepare(service, subject_id=subject.subject_id, recipe_id=recipe.recipe_id,
        authorization_id="fixture-grant", environment=environment, seed=19)
    service.repository.grant(AssessmentAuthorization(authorization_id="fixture-grant",
        subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest], environment_digests=[request.environment_digest],
        limits=AssessmentLimits(max_operations=5000, max_elapsed_seconds=6000), expires_at=utc_now()+timedelta(hours=2)))
    return router, service, recipe, request, environment


@pytest.mark.parametrize("real", [False, pytest.param(True, marks=[pytest.mark.assessment_boundary, pytest.mark.real_container, pytest.mark.skipif(not os.environ.get("AEEP_CONTAINER_IMAGE"), reason="requires reviewed local container runtime")])])
async def test_reviewed_executable_recipe_enters_the_same_campaign(tmp_path, monkeypatch, real):
    router, service, recipe, request, environment = setup(tmp_path, monkeypatch, real=real)
    try:
        with pytest.raises(ConfigurationError, match="review"):
            await materialize(service, request.plan_id)
        for digest in request.definition_digests:
            service.repository.review(digest)
        cases = await materialize(service, request.plan_id)
        assert await materialize(service, request.plan_id) == cases
        assert Counter(case.variation for case in cases.cases if case.split.value == "holdout") == {"1":35,"2":35,"3":35}
        assert structural_features(recipe, {"items":["unseen content"]}) == {"length":1}
        assert structural_features(recipe, {"wrong":[]}) is None
        options = dict(subject_id=request.subject_digest, family=recipe.recipe_id, candidate_id="candidate", baseline_id="baseline",
                       authorization_id=request.authorization_id, environment=environment, seed=request.seed, case_set_id=request.plan_id)
        plan = service.propose(**options)
        assert plan.schema_version == "assessment.plan.v3"
        with pytest.raises(ConfigurationError, match="fresh cases"):
            service.propose(**options)
        for digest in plan.definition_digests:
            service.repository.review(digest)
        preview = service.budget_preview(plan.plan_id)['campaign_allowance']
        report = await service.run(service.enqueue(plan.plan_id))
        current_operations = service.repository.operation_ledger(plan.plan_id).operations
        assert sum(item.reserved.max_operations for item in current_operations) == preview['upper_allowance']['operations']
        assert sum(item.reserved.max_elapsed_seconds for item in current_operations) == pytest.approx(preview['upper_allowance']['elapsed_seconds'])
        assert any(item['stage'] == 'recipe_generation' for item in preview['prior_operations'])
        assert report.qualification_passed, report.explanations
        assert report.distinct_holdout_cases == 105
        assert report.grader_validation_digest
        ledger = service.repository.operation_ledger(plan.plan_id, source_plan_ids=[request.plan_id])
        assert {"recipe_generation", "recipe_grading", "grader_reference", "grader_probe"}.issubset({item.stage for item in ledger.operations})
        assert not router.store.list_receipts()
        changed = plan.model_copy(deep=True)
        changed.suite.cases[0].action.input = {"items":[]}
        with pytest.raises(ConfigurationError, match="changed after materialization"):
            service._verify_dependencies(changed)
    finally:
        await router.close()


async def test_generator_failure_keeps_its_charge_and_never_runs_a_candidate(tmp_path, monkeypatch):
    router, service, _recipe, request, _environment = setup(tmp_path, monkeypatch, recipe=definition(generator="print('{}')"))
    try:
        for digest in request.definition_digests:
            service.repository.review(digest)
        with pytest.raises(ConfigurationError, match="141"):
            await materialize(service, request.plan_id)
        with pytest.raises(ConfigurationError, match="already reserved"):
            await materialize(service, request.plan_id)
        ledger = service.repository.operation_ledger(request.plan_id)
        assert len(ledger.operations) == 1 and ledger.operations[0].elapsed_seconds is not None
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_generator_runtime_drift_blocks_before_spending(tmp_path, monkeypatch):
    from aeep.assessment.identity import file_digest

    runtime = tmp_path / 'reviewed-runtime.py'
    runtime.write_text('reviewed')
    monkeypatch.setattr('aeep.assessment.identity.runtime_dependencies', lambda: {str(runtime):file_digest(runtime)})
    router, service, _recipe, request, _environment = setup(tmp_path, monkeypatch)
    try:
        for digest in request.definition_digests:
            service.repository.review(digest)
        runtime.write_text('changed after review')
        with pytest.raises(ConfigurationError, match='changed'):
            await materialize(service, request.plan_id)
        assert not service.repository.operation_ledger(request.plan_id).operations
    finally:
        await router.close()


@pytest.mark.parametrize('fault', ['generator_truth', 'grader_accepts_all', 'grader_protocol'])
async def test_recipe_faults_block_before_candidate_execution(tmp_path, monkeypatch, fault):
    recipe = definition(
        generator=GENERATOR.replace("'count':n", "'count':n+1") if fault == 'generator_truth' else GENERATOR,
        grader=GRADER.replace("e['output']==e['expected']", 'True') if fault == 'grader_accepts_all'
        else "print('{}')" if fault == 'grader_protocol' else GRADER)
    router, service, _recipe, request, environment = setup(tmp_path, monkeypatch, recipe=recipe)
    try:
        for digest in request.definition_digests:
            service.repository.review(digest)
        await materialize(service, request.plan_id)
        plan = service.propose(subject_id=request.subject_digest, family=recipe.recipe_id, candidate_id='candidate', baseline_id='baseline',
            authorization_id=request.authorization_id, environment=environment, seed=request.seed, case_set_id=request.plan_id)
        for digest in plan.definition_digests:
            service.repository.review(digest)
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.outcome == 'insufficient_evidence'
        assert not report.qualification_passed and not report.grader_validation_digest
        ledger = service.repository.operation_ledger(plan.plan_id, source_plan_ids=[request.plan_id])
        assert all(item.stage != 'trial' for item in ledger.operations)
        assert all(item.elapsed_seconds is not None for item in ledger.operations)
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_reviewed_diagnostics_survive_the_contained_campaign(tmp_path, monkeypatch):
    recipe = definition()
    assert recipe.extension is not None
    raw = recipe.extension.model_dump()
    for key in ('generator', 'grader', 'reference'):
        raw[key]['config']['argv_literal'] = True
    raw['grader']['config']['argv'][2] = (
        "import json,sys; p=json.load(sys.stdin); "
        "v=[e['output']==e['expected'] for e in p['examples']]; "
        "print(json.dumps({'valid':v,'failure_codes':[None if ok else 'wrong_count' for ok in v]}))"
    )
    recipe.extension = ExecutableRecipeExtension.model_validate({**raw,
        'schema_version': 'assessment.recipe-extension.v3',
        'truth_schema': recipe.output_schema, 'failure_codes': ['wrong_count']})
    router, service, recipe, request, environment = setup(tmp_path, monkeypatch, recipe=recipe)
    try:
        spec = router.registry.get('candidate').model_copy(deep=True)
        spec.config['argv'][2] = "print('{\"count\":-1}')"
        router.registry.replace(spec)
        for digest in request.definition_digests:
            service.repository.review(digest)
        cases = await materialize(service, request.plan_id)
        assert all(case.validators[0].config['failure_codes'] == ['wrong_count'] for case in cases.cases)
        plan = service.propose(subject_id=request.subject_digest, family=recipe.recipe_id,
            candidate_id='candidate', baseline_id='baseline', authorization_id=request.authorization_id,
            environment=environment, seed=request.seed, case_set_id=request.plan_id)
        for digest in plan.definition_digests:
            service.repository.review(digest)
        report = await service.run(service.enqueue(plan.plan_id))
        assert not report.qualification_passed and report.grader_validation_digest
        import json
        import sqlite3
        with sqlite3.connect(service.directory / plan.plan_id / 'campaign.sqlite3') as db:
            trials = [json.loads(row[0]) for row in db.execute('SELECT payload_json FROM trials')]
        assert any(t['case_validation'][0]['detail'] == 'wrong_count' for t in trials if t['correctness_failed'])
        assert not router.store.list_receipts()
    finally:
        await router.close()
