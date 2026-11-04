"""Actual old plan, corrected first-party constructor, zero executor dispatch."""
import asyncio,json,shutil,sys,tempfile,traceback
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.router import Router
from aeep.assessment.models import AssessmentPlan,RecipeDefinition,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
OLD=HERE.parent/'worker-readiness-correction-20261103'

async def main():
 assert shutil.disk_usage(ROOT).free>=50*1024**3+100*1024**2
 plan=AssessmentPlan.model_validate_json((OLD/'plan-agent-skill-eval.json').read_bytes())
 router=Router.from_manifest(ROOT/'.aeep/worker-readiness-correction-20261103/selected-manifest.json')
 result={'inert_campaign_constructor_only':True,'upstream_execution':False,'models':0,'passed':False,
  'source':verification_source_digest(ROOT),'stored_original_plan_source_scope':'Historical c48e931b; this check grants no fresh worker/model qualification'}
 try:
  repo=AssessmentRepository(router.store);recipe=RecipeDefinition.model_validate(repo.get('recipe',plan.recipe_digest))
  before=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
  with tempfile.TemporaryDirectory(prefix='aeep-integration-snapshot-constructor-') as temporary:
   child=None
   try:
    child=router._campaign_router([recipe.extension.grader],plan_digest=content_digest(plan),database=Path(temporary)/'fixture.sqlite3',snapshot_bound_digests={content_digest(plan),plan.subject_digest,plan.recipe_digest,plan.mapping_digest,plan.environment_digest,*plan.definition_digests})
    rows=child.store._connection.execute("SELECT digest FROM assessment_records WHERE kind='integration_case_set'").fetchall()
    assert {row[0] for row in rows}=={plan.integration_case_set_digest}
    result.update(passed=True,retained_integration_set=plan.integration_case_set_digest,
     selected_grader_id=recipe.extension.grader.id,upstream_executor_started=False)
   except Exception as error:result.update(error_type=type(error).__name__,message=str(error),traceback=traceback.format_exc())
   finally:
    if child:await child.close()
  after=tuple(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
  assert before==after
  result.update(grant_unchanged=True,new_owned_temporary_database_removed=True)
  with (HERE/'constructor-result.json').open('x') as f:json.dump(result,f,indent=2);f.write('\n')
  print(json.dumps(result))
  if not result['passed']:raise SystemExit(1)
 finally:await router.close()

if __name__=='__main__':asyncio.run(main())
