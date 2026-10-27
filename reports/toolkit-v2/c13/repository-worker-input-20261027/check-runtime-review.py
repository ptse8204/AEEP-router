"""Reopen exact definitions and assets;do not grant,provision or dispatch."""
import hashlib
import json
from pathlib import Path
import shutil

from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    review=json.loads((HERE/'operation-review.json').read_text());assert verification_source_digest(ROOT)==review['source_digest']
    assert not any((HERE/n).exists() for n in ('operator-approval.json','execution-started.json','review-budget-anchor.json'))
    for path,expected in review['assets'].items():assert Path(path).is_file() and not Path(path).is_symlink() and sha(Path(path))==expected
    parent=json.loads((ROOT/review['parent_review']).read_text());assert sha(ROOT/review['parent_review'])==review['parent_review_sha256']
    request=RecipeMaterializationRequest.model_validate(review['request']);amendment=AssessmentScopeAmendment.model_validate(review['amendment'])
    models={'subject':AssessmentSubject,'environment':AssessmentEnvironment,'recipe':RecipeDefinition,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    docs={**parent['documents'],**review['new_documents']};assert set(docs)==set(review['reviewed_document_digests'])==set(amendment.reviewed_digests)
    for digest,item in docs.items():assert content_digest(models[item['kind']].model_validate(item['document']))==digest
    env=next(AssessmentEnvironment.model_validate(v['document']) for v in docs.values() if v['kind']=='environment')
    assert content_digest(env)==request.environment_digest and env.container_image==review['parent_image']
    assert env.identity['source_digest']==review['source_digest']
    assert env.network is False and env.kind=='container'
    assert (review['initial_contained_calls'],review['maximum_contained_calls'],review['maximum_operations'],review['maximum_reserved_seconds'])==(16,20,24,1000)
    assert review['maximum_operations']==20+4 and review['maximum_reserved_seconds']==20*35+2*(30+120)
    assert len(review['probes'])==4 and [p['name'] for p in review['probes']]==['boundary','state_write','state_read','large_transport']
    large=review['probes'][-1]['payload'];assert len(json.dumps(large,separators=(',',':')).encode())>2_000_000
    for probe in review['probes']:assert hashlib.sha256(json.dumps(probe['payload'],separators=(',',':')).encode()).hexdigest()==probe['payload_sha256']
    assert json.loads((HERE/'terminal-control-check.json').read_text())['passed']
    result={'passed':True,'assets_reopened':len(review['assets']),'all_definitions_canonical':True,'new_source_image_bound':True,'same_four_probes':True,'extra_call_budget_cumulative':True,'new_builds_downloads_installs_models_or_authority':0,'review_sha256':sha(HERE/'operation-review.json')}
    (HERE/'static-bundle-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    resources={'free_bytes':shutil.disk_usage(ROOT).free,'host_reserve_bytes':50*1024**3,'runtime_image_growth_planned':0,'downloads':0,'builds':0,'retained_image':env.container_image,'worker_memory_mb':env.memory_mb,'worker_cpu_count':env.cpu_count,'worker_process_limit':env.process_limit,'finite_execution_bounds_are_not_product_resource_acceptance':True,'whole_host_resource_gate':'OPEN'}
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps(resources,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':main()
