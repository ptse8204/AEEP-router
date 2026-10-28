"""Check exact v4 definitions, failure-tail controls and accounting without dispatch."""
import base64
import copy
from datetime import timedelta
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from aeep.assessment.models import AssessmentAuthorization, AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment, AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def main():
    review=json.loads((HERE/'operation-review.json').read_text())
    request=RecipeMaterializationRequest.model_validate(review['request'])
    models={'subject':AssessmentSubject,'recipe':RecipeDefinition,'environment':AssessmentEnvironment,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    budget=load('review_budget_fixture',HERE/'review-budget.py');checks=budget.self_check()
    with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-authority-only-',dir=ROOT/'.aeep') as temp:
        store=ReceiptStore(Path(temp)/'fixture-only.sqlite3')
        try:
            repo=AssessmentRepository(store)
            grant=AssessmentAuthorization(authorization_id='onboarding',subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],limits=AssessmentLimits(max_operations=100,max_elapsed_seconds=2000),expires_at=utc_now()+timedelta(minutes=5))
            repo.grant(grant)
            documents={**json.loads((ROOT/review['parent_review']).read_text())['documents'],**review['new_documents']}
            for key,item in documents.items():assert repo.put(item['kind'],item['id'],models[item['kind']].model_validate(item['document']))==key
            amendment=copy.deepcopy(review['amendment']);amendment['authorization_digest']=content_digest(grant)
            repo.approve_bundle(AssessmentScopeAmendment.model_validate(amendment),{k:v['document'] for k,v in documents.items()})
            repo.authorize(request)
            budget.install(repo,store._connection,[0,0,0.,'0'],review)
            for index in range(21):
                name='SYNTHETIC-no-dispatch-'+str(index)
                repo.reserve(request,name,AssessmentLimits(max_operations=1,max_elapsed_seconds=1),stage='synthetic_no_dispatch')
                repo.finish_operation(name,elapsed_seconds=.001)
            try:repo.reserve(request,'SYNTHETIC-operation22',AssessmentLimits(max_operations=1,max_elapsed_seconds=1),stage='synthetic_no_dispatch')
            except RuntimeError:pass
            else:raise AssertionError('Actual bound guard allowed operation22')
        finally:store.close()
    assert not Path(temp).exists()
    unwrap=load('operator_output_fixture',HERE/'operator_output.py').evaluation
    evaluation={'exit_code':1,'statuses':{'test::id':'FAILED'},'archive_sha256':'a'*64,'python':'3.13','pytest':'8.3.5'}
    good={'evaluation':evaluation,'failure_log_tail_b64':base64.b64encode(b'public failure').decode()}
    assert unwrap(good) is evaluation
    bad=[evaluation,{**good,'extra':False},{'evaluation':{},'failure_log_tail_b64':''},{**good,'failure_log_tail_b64':'$'},{**good,'failure_log_tail_b64':base64.b64encode(b'x'*8193).decode()},{**good,'evaluation':{**evaluation,'exit_code':0}}]
    for value in bad:
        try:unwrap(value)
        except (ValueError,TypeError):pass
        else:raise AssertionError('Unreviewed envelope/tail accepted')
    value={'passed':True,'build_definitions_stored_and_authorized_in_synthetic_database':True,'actual_budget_guard_rejects_operation22':True,'budget_guards':checks,'operator_envelope_guards':1+len(bad),'synthetic_database_removed':True,'fixture_is_not_authority_or_benchmark':True,'new_containers_installs_or_external_execution':0,'model_turns':0,'runtime_review_sha256':hashlib.sha256((HERE/'operation-review.json').read_bytes()).hexdigest()}
    (HERE/'execution-control-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))


if __name__=='__main__':main()
