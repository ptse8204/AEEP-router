"""Reopen canonical definitions, budget and inherited boundary bindings; no dispatch."""
import hashlib
import json
from pathlib import Path
import shutil

from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    review=json.loads((HERE/'operation-review.json').read_text())
    assert verification_source_digest(ROOT)==review['source_digest']
    assert not any((HERE/n).exists() for n in ('operator-approval.json','execution-started.json','review-budget-anchor.json'))
    for p,h in review['assets'].items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h
    parent=json.loads((ROOT/review['parent_review']).read_text())
    assert sha(ROOT/review['parent_review'])==review['parent_review_sha256']
    models={'subject':AssessmentSubject,'environment':AssessmentEnvironment,'recipe':RecipeDefinition,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    docs={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')};docs.update(review['new_documents'])
    request=RecipeMaterializationRequest.model_validate(review['request']);amendment=AssessmentScopeAmendment.model_validate(review['amendment'])
    assert set(docs)==set(review['reviewed_document_digests'])==set(amendment.reviewed_digests)
    for h,item in docs.items():assert content_digest(models[item['kind']].model_validate(item['document']))==h
    env=next(AssessmentEnvironment.model_validate(v['document']) for v in docs.values() if v['kind']=='environment')
    assert content_digest(env)==request.environment_digest and env.container_image==review['parent_image']==parent['image']
    assert env.identity['source_digest']==review['source_digest'] and env.network is False
    assert (review['initial_contained_calls'],review['maximum_contained_calls'],review['maximum_operations'],review['maximum_reserved_seconds'])==(13,17,21,895)
    assert 17*35+2*(30+120)==review['maximum_reserved_seconds']
    assert len(review['probes'])==1 and review['probes'][0]['name']=='markup_runtime'
    p=review['probes'][0];assert hashlib.sha256(json.dumps(p['payload'],separators=(',',':')).encode()).hexdigest()==p['payload_sha256']
    reuse=review['current_containment_reuse'];assert sha(ROOT/reuse['manifest'])==reuse['manifest_sha256']
    audit=json.loads((ROOT/reuse['manifest']).read_text());assert audit['physical_receipt_integrity_passed'] and audit['all_owned_containers_absent']
    assert reuse['completed_probe_receipts']==audit['reopened'][:4] and reuse['image']==env.container_image
    assert reuse['source_digest']==review['source_digest'] and reuse['observer_program_sha256']==parent['recipe']['dependencies']['program']
    for n in ('scope-check.json','execution-control-check.json','terminal-control-check.json'):assert json.loads((HERE/n).read_text())['passed']
    value={'passed':True,'assets_reopened':len(review['assets']),'all_definitions_canonical':True,'current_completed_probe_receipts_reused':4,'new_markup_probe':1,'same_source_image_observer_permissions':True,'cumulative_control_budget_checked':True,'actual_execution_or_models':0,'review_sha256':sha(HERE/'operation-review.json')}
    (HERE/'static-bundle-audit.json').write_text(json.dumps(value,indent=2)+'\n')
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps({'free_bytes':shutil.disk_usage(ROOT).free,'host_reserve_bytes':50*1024**3,'new_image_growth':0,'builds_installs_downloads_models':0,'retained_image':env.container_image,'finite_review_limits_are_not_product_resource_acceptance':True,'whole_host_resource_gate':'OPEN'},indent=2)+'\n')
    print(json.dumps(value))

if __name__=='__main__':main()
