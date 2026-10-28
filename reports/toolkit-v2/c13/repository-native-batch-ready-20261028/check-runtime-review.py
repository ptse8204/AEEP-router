"""Reopen exact assets/definitions and seed payloads without executing subjects."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

async def main():
    review=json.loads((HERE/'operation-review.json').read_text());parent=json.loads((ROOT/review['parent_review']).read_text())
    assert verification_source_digest(ROOT)==review['source_digest']
    for p,h in review['assets'].items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    types={'subject':AssessmentSubject,'recipe':RecipeDefinition,'environment':AssessmentEnvironment,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    docs={**parent['documents'],**review['new_documents']}
    for h,item in docs.items():assert content_digest(types[item['kind']].model_validate(item['document']))==h
    request=RecipeMaterializationRequest.model_validate(review['request']);amendment=AssessmentScopeAmendment.model_validate(review['amendment'])
    assert set(docs)==set(review['reviewed_document_digests'])==set(amendment.reviewed_digests)
    assert request.runtime_dependencies==runtime_dependencies()
    assert (review['initial_contained_calls'],review['maximum_contained_calls'],review['maximum_operations'],review['maximum_reserved_seconds'])==(14,16,20,860)
    assert 16+2*2==20 and 16*35+2*(30+120)==860
    assert len(review['probes'])==4 and len(review['native_fixtures'])==2 and len(review['collections'])==2
    for item in [*review['probes'],*review['native_fixtures'],review['support_probe']]:assert hashlib.sha256(json.dumps(item['payload'],separators=(',',':')).encode()).hexdigest()==item['payload_sha256']
    recipe=RecipeDefinition.model_validate(parent['recipe']);assert recipe.extension.reference.id!=recipe.extension.grader.id
    operator=recipe.extension.grader.config['argv'][-1];default=recipe.extension.reference.config['argv'][-1]
    assert operator.replace('OPERATOR_REVIEW = True','OPERATOR_REVIEW = False')==default
    assert sha(HERE/'native_scope.py')==review['method_sha256']==recipe.dependencies['native_scope_derivation']
    seeds=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())]
    records=json.loads((ROOT/review['records_file']).read_text());assert len(seeds)==len(records)==2
    count=0
    for seed in seeds:
        item=next(c for c in review['collections'] if c['case_id']==seed.input.task_id)
        record=next(c for c in records if c['case_id']==seed.input.task_id);captured=[]
        class Captured(Exception):pass
        async def probe(v):captured.append(v);raise Captured()
        try:await grade_suite_output(seed.input.model_dump(mode='json'),seed.truth.model_dump(mode='json'),record['reference'],probe)
        except Captured:pass
        else:raise AssertionError('Preparation returned a grade')
        assert len(captured)==1;captured[0]['collect_only']=True
        assert hashlib.sha256(json.dumps(captured[0],separators=(',',':')).encode()).hexdigest()==item['sha256']==sha(ROOT/item['payload']);count+=1
    reuse=review['operator_conformance_reused'];assert sha(ROOT/reuse['evidence'])==reuse['sha256']
    actual=json.loads((ROOT/reuse['evidence']).read_text());assert actual['physical_receipt_integrity_passed'] and actual['all_owned_containers_absent'] and actual['canonical_receipts_reopened']==15
    value={'passed':True,'assets_reopened':len(review['assets']),'canonical_documents':len(docs),'collection_payload_derivations':count,'frozen_scope_method_and_both_profiles_bound':True,'current_operator_conformance_reused':True,'new_default_profile_requires_fresh_checks':True,'all_source_and_installed_evidence_reused_without_execution':True,'actual_external_execution':False,'review_sha256':sha(HERE/'operation-review.json')}
    with(HERE/'static-bundle-audit.json').open('x') as stream:json.dump(value,stream,indent=2);stream.write('\n')
    print(json.dumps(value))

if __name__=='__main__':asyncio.run(main())
