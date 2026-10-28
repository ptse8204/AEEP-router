"""Check canonical v6 review, immutable payloads and finite limits without dispatch."""
import asyncio
import hashlib
import json
from pathlib import Path
import shutil

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

async def main():
    review=json.loads((HERE/'operation-review.json').read_text());parent=json.loads((ROOT/review['parent_review']).read_text())
    assert source_matches(review) and not any((HERE/n).exists() for n in ('operator-approval.json','execution-started.json','review-budget-anchor.json'))
    models={'subject':AssessmentSubject,'environment':AssessmentEnvironment,'recipe':RecipeDefinition,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    documents={**parent['documents'],**review['new_documents']}
    for key,item in documents.items():assert content_digest(models[item['kind']].model_validate(item['document']))==key
    request=RecipeMaterializationRequest.model_validate(review['request']);amendment=AssessmentScopeAmendment.model_validate(review['amendment'])
    assert set(documents)==set(review['reviewed_document_digests'])==set(amendment.reviewed_digests)
    assert request.runtime_dependencies==runtime_dependencies()
    env=next(AssessmentEnvironment.model_validate(x['document']) for x in documents.values() if x['kind']=='environment')
    assert env.identity['source_digest']==review['source_digest'] and env.network is False
    assert env.container_image==review['parent_image']==parent['image']
    assert (review['initial_contained_calls'],review['maximum_contained_calls'],review['maximum_operations'],review['maximum_reserved_seconds'])==(15,17,21,895)
    assert 17*35+2*(30+120)==review['maximum_reserved_seconds'] and 17+2*2==review['maximum_operations']
    assert len(review['probes'])==4 and len(review['native_fixtures'])==2
    for item in [*review['probes'],*review['native_fixtures']]:assert hashlib.sha256(json.dumps(item['payload'],separators=(',',':')).encode()).hexdigest()==item['payload_sha256']
    gate=review['collection'];assert sha(ROOT/gate['payload'])==gate['payload_sha256']
    assert len(gate['expected_native_required'])==len(set(gate['expected_native_required']))==915
    assert len(gate['expected_selected_ids'])==899 and set(gate['expected_selected_ids'])<set(gate['expected_native_required'])
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())]
    native=cases[-1];assert native.truth.fail_to_pass+native.truth.pass_to_pass==gate['expected_native_required']
    identity_map=json.loads((HERE/'identity-map.json').read_text());assert identity_map['frozen_before_native_collection'] and not identity_map['actual_native_collection_executed']
    original=RepositorySuiteCase.model_validate(identity_map['original_case'])
    assert native.input.source_sha256==original.input.source_sha256 and native.input.task==original.input.task
    for role in ('fail_to_pass','pass_to_pass'):
        assert [identity_map['mapping'][n] for n in getattr(original.truth,role)]==getattr(native.truth,role)
    program=parent['recipe']['extension']['grader']['config']['argv'][-1]
    assert hashlib.sha256(program.encode()).hexdigest()==env.identity['observer_program_sha256']
    default=repository_suite_recipe([c.model_copy(update={'split':'development','used_for_development':True}) for c in cases])
    assert program.replace('OPERATOR_REVIEW = True','OPERATOR_REVIEW = False')==default.extension.grader.config['argv'][-1]
    variants=json.loads((ROOT/review['variants_file']).read_text());derivations=0
    for item in variants:
        case=next(c for c in cases if c.input.task_id==item['case']);captured=[]
        class Captured(Exception):pass
        async def probe(payload):captured.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest());raise Captured()
        try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),item['artifact'],probe)
        except Captured:pass
        else:raise AssertionError('Inert preparation returned a test grade')
        assert captured==[item['sha256']] and sha(ROOT/item['payload'])==item['sha256'];derivations+=1
    assert derivations==8 and source_matches(review)
    value={'passed':True,'assets_reopened':len(review['assets']),'canonical_documents_verified':len(documents),'immutable_payload_derivations':derivations,'all915_roles_preserved':True,'native_observer_differs_only_by_review_constant':True,'collection_gate_not_test_grade':True,'no_execution':True,'review_sha256':sha(HERE/'operation-review.json')}
    with(HERE/'static-bundle-audit.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    with(HERE/'runtime-operation-resource-bound.json').open('x') as f:json.dump({'free_bytes':shutil.disk_usage(ROOT).free,'host_reserve_bytes':50*1024**3,'builds_downloads_models':0,'whole_host_resource_gate':'OPEN','finite_execution_limits_are_not_product_resource_acceptance':True},f,indent=2);f.write('\n')
    print(json.dumps(value))

def source_matches(review):
    assert verification_source_digest(ROOT)==review['source_digest']
    for p,h in review['assets'].items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    return True

if __name__=='__main__':asyncio.run(main())
