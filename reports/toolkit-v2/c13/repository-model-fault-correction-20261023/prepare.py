"""Prepare one corrected recipe and exact execution review, without external execution."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

from aeep.assessment.models import RecipeDefinition,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,compressed_patch_artifact,decode_patch,grade_suite_output,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest
from aeep.qualification import behavior_fingerprint
from aeep.assessment.service import AssessmentService
from aeep.router import Router

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'repository-model-journey-20261022'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(name,value):(HERE/name).write_text(json.dumps(value,indent=2)+'\n')


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


async def main():
    assert not (HERE/'operation-review.json').exists()
    parent=json.loads((PRIOR/'operation-review.json').read_text());terminal=json.loads((PRIOR/'terminal-audit.json').read_text());assert terminal['passed'] and terminal['model_turns']==0 and terminal['last_call_is_old_marshmallow_import_fault']
    assert verification_source_digest(ROOT)==parent['source_digest']
    proposal=json.loads((PRIOR/'collector-definitions.json').read_text());old=RecipeDefinition.model_validate(proposal['definitions'][proposal['requests'][0]['recipe_digest']])
    cases=[RepositorySuiteCase.model_validate(c) for c in old.generator_config['cases']]
    certified_path=ROOT/'.aeep/repository-suite-semantic-fault-20261022/cases.json';certified=[RepositorySuiteCase.model_validate(c) for c in json.loads(certified_path.read_text())]
    case=next(c for c in cases if c.input.task_id=='marshmallow-code__marshmallow-2800');accepted=next(c for c in certified if c.input.task_id==case.input.task_id)
    assert case.input==accepted.input
    for key,value in accepted.truth.model_dump(mode='json').items():assert case.truth.model_dump(mode='json')[key]==value
    fault=compressed_patch_artifact(decode_patch(accepted.fault_outputs[0]));case.fault_outputs=[fault]
    recipe=repository_suite_recipe(cases);assert recipe.extension.grader==old.extension.grader and recipe.input_schema==old.input_schema and recipe.output_schema==old.output_schema
    assert all(a.input==b.input and a.truth==b.truth and a.reference==b.reference for a,b in zip(cases,[RepositorySuiteCase.model_validate(c) for c in old.generator_config['cases']],strict=True))
    old_observation=json.loads((HERE.parent/'repository-suite-semantic-fault-20261022/raw-observation.json').read_text())['output'];captured={}
    async def replay(payload):
        captured.update(payload);assert payload['archive_sha256']==old_observation['archive_sha256']
        return old_observation
    grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),fault,replay)
    assert grade.valid is False and grade.detail=='test_failure'
    assert set(case.truth.fail_to_pass+case.truth.pass_to_pass)<=old_observation['statuses'].keys()
    assert all(old_observation['statuses'][name]=='PASSED' for name in case.truth.fail_to_pass)
    assert any(old_observation['statuses'][name]=='FAILED' for name in case.truth.pass_to_pass)
    write('corrected-recipe.json',recipe.model_dump(mode='json'))
    router=Router.from_manifest(Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.json'))
    try:
        before=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        repo=AssessmentService(router,Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')).repository
        repo.put('recipe',recipe.recipe_id,recipe)
        assert content_digest(repo.get('recipe',content_digest(recipe)))==content_digest(recipe)
        assert before==tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    finally:await router.close()
    for name in ['collector-definitions.json','collector-result.json','boundary-result.json','run-collector.py','review-budget.py']:shutil.copyfile(PRIOR/name,HERE/name)
    boundary=json.loads((HERE/'boundary-result.json').read_text());runner=load('corrected_development_runner',HERE/'run-corrected.py').load_runner();pair,new_recipe,mapping,environment,plan,definitions=runner.construct(proposal,boundary)
    old_runner=load('original_development_runner',PRIOR/'run-model-journey.py');old_pair,_,_,old_env,_,_=old_runner.construct(proposal,boundary)
    assert pair==old_pair and environment==old_env and new_recipe==recipe and plan.recipe_digest==content_digest(recipe)
    assert len(plan.suite.cases)==3 and len(plan.suite.routes)==2 and plan.comparison is None and plan.pilot is None
    assert all(item.split.value=='training' for item in plan.suite.cases) and pair.treatment.config['invocation']['exposure']=='optional'
    checks=load('copied_budget_guard',HERE/'review-budget.py').self_check()
    observation=load('observation_filter',HERE/'run-corrected.py').bounded_observation({'unknown_field':'omitted','statuses':{'tests/public.py::check':'ODD'},'exit_code':1,'python':'3.13','pytest':'8.3.5','archive_sha256':'a'*64})
    assert 'unknown_field' not in observation and observation['statuses']['tests/public.py::check']=='ODD'
    assert 'statuses' not in load('observation_filter_bound',HERE/'run-corrected.py').bounded_observation({'statuses':{str(i)+'x'*1000:'FAILED' for i in range(1000)}})
    for path in HERE.glob('*.py'):ast.parse(path.read_text())
    delta={'only_recipe_change':'Replace the old Marshmallow import-time counterexample with the already certified URL-validation bypass,encoded through the existing gzip patch contract.','original_recipe_digest':content_digest(old),'corrected_recipe_digest':content_digest(recipe),'old_fault_digest':content_digest(old.generator_config['cases'][2]['fault_outputs'][0]),'new_fault_digest':content_digest(fault),'same_public_inputs_protected_tests_references':True,'same_worker_profiles_and_fingerprints':{role:behavior_fingerprint(getattr(pair,role)) for role in ['control','treatment']},'same_actual_boundaries_reused':boundary['boundaries'],'prior_certified_fault_path':str(certified_path),'prior_certified_fault_file_sha256':sha(certified_path),'patched_archive_matches_prior_certified_observation':True,'patched_archive_sha256':captured['archive_sha256'],'prior_statuses_replay_grade':grade.model_dump(mode='json'),'replay_is_not_new_runtime_conformance':True,'models_or_containers_started':0,'typed_recipe_record_stored_with_counters_unchanged':True}
    write('correction-checks.json',delta)
    assets={**parent['assets'],**{str((HERE/name).resolve()):sha(HERE/name) for name in ['run-corrected.py','corrected-recipe.json','collector-definitions.json','collector-result.json','boundary-result.json','run-collector.py','review-budget.py','correction-checks.json']},str((PRIOR/'run-model-journey.py').resolve()):sha(PRIOR/'run-model-journey.py'),str((PRIOR/'terminal-audit.json').resolve()):sha(PRIOR/'terminal-audit.json'),str(certified_path):sha(certified_path),str((HERE.parent/'repository-suite-semantic-fault-20261022/raw-observation.json').resolve()):sha(HERE.parent/'repository-suite-semantic-fault-20261022/raw-observation.json')}
    assert all(sha(Path(path))==digest for path,digest in assets.items());free=shutil.disk_usage(ROOT).free;assert free>=parent['minimum_free_bytes']
    review={key:parent[key] for key in ['source_digest','proxy_name','proxy_id','proxy_image','proxy_memory_bytes','network_id','proxy_inspect_format','images','pair_definition_digest','candidate_skill_sha256','public_tasks','maximum_model_turns','maximum_operations','maximum_reserved_seconds','cash_usd','minimum_free_bytes','maximum_task_seconds','maximum_fresh_model_workers_including_inspection','maximum_concurrent_model_workers','public_data_disclosure_scope','budget_enforcement']}
    review.update(purpose='One corrected development attempt:reuse fresh exact worker conformance;validate the corrected protected recipe normally;then at most six optional-skill public repository task turns.',parent_terminal_review_sha256=sha(PRIOR/'operation-review.json'),parent_terminal_operations=15,parent_terminal_charged_seconds=terminal['charged_operation_seconds'],parent_terminal_model_turns=0,assets=assets,corrected_recipe_sha256=sha(HERE/'corrected-recipe.json'),automatic_retry=False,fresh_worker_inspection_repeated=False,worker_profile_and_actual_conformance_unchanged=True,maximum_grader_calls_including_validation_and_task_grading=93,
        changes=['Only the Marshmallow development fault data changes;use the previously certified URL-validator bypass instead of the original import-time raise. Public tasks,tests,source/reference files,observer program,worker settings,images,collector and thresholds are unchanged.','Reuse the prior11-group-per-worker current-source observations and actual collector denial because both worker definitions/fingerprints are identical. Normal runtime identity,boundary and authority checks still apply before each task.','Retain bounded declared public grader-observer reply fields,field names/types,digests and status maps before protocol validation. Never retain raw model output,task artifacts,source contents,authentication or arbitrary undeclared field values.'],
        gates=['No actual execution until this exact review is approved. Verify all assets,source,space,existing grant,proxy identity and terminal predecessor before dispatch.','Normal independent grader validation must pass before models. Preserve every charge,failed observation and incomplete metric. Stop on authority,accounting,environment,identity,cleanup or common evidence uncertainty.','Require six canonical receipts,independent grades,verified token capture chains and confirmed worker cleanup for a completed development journey;skill loading remains optional and missing events remain unknown. Restore the existing proxy stopped;remove only newly owned transient containers.'],
        exclusions=['No installs,downloads,builds,pulls,new images,old-image deletion,new service/destination,credentials,cash,package/docs reruns or release.','No historical-result rewrite,automatic retry,formal qualification,holdout assignment,benefit/selection verdict,admission or activation. The prior attempt stays terminal with all15 operations and65.09651541616768 seconds charged.'],
        approval_reason='The approved9f0bf880 bundle was one-attempt/no-retry and ended at grader validation. Its unused model slots do not authorize replay or these changed fault bytes. The pasted continuation withholds untrusted execution;CONTINUATION.md requires applicable authority. Routine finite definitions remain delegated;no architecture decision is needed.')
    write('operation-review.json',review)
    write('preparation-checks.json',{'passed':True,'source_unchanged':True,'assets_verified':len(assets),'budget_guard_cases':checks,'observer_filter_checks':2,'actual_models_or_workers_started':0,'actual_boundary_reused_only_for_identical_worker_fingerprints':True,'replay_fixture_not_current_runtime_evidence':True,'new_review_sha256':sha(HERE/'operation-review.json'),'free_bytes':free})
    print((HERE/'preparation-checks.json').read_text())


if __name__=='__main__':asyncio.run(main())
