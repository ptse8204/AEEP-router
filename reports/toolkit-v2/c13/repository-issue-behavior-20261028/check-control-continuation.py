"""Verify the finite approved dispatch correction without any execution."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.assessment.models import AssessmentEnvironment,AssessmentLimits,AssessmentScopeAmendment,AssessmentSubject,RecipeDefinition,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OUT=HERE/'control-continuation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    original=json.loads((HERE/'operation-review.json').read_text());child=json.loads((OUT/'operation-review.json').read_text());parent=json.loads((ROOT/child['parent_review']).read_text())
    assert child['source_digest']==verification_source_digest(ROOT)==original['source_digest']
    assert child['parent_review']==original['parent_review'] and child['parent_review_sha256']==original['parent_review_sha256']
    assert child['probes']==[] and child['maximum_contained_calls']==8 and child['maximum_operations']==10 and child['maximum_reserved_seconds']==430
    before_cases=json.loads((ROOT/original['cases_file']).read_text());after_cases=json.loads((ROOT/child['cases_file']).read_text())
    assert after_cases==[c for c in before_cases if c['input']['task_id'].startswith('tefra')]
    before_variants=json.loads((ROOT/original['variants_file']).read_text());after_variants=json.loads((ROOT/child['variants_file']).read_text())
    assert after_variants==[v for v in before_variants if v['case'].startswith('tefra')] and len(after_variants)==8
    for item in after_variants:assert sha(ROOT/item['payload'])==item['sha256']
    for name in ('expectations','variant_labels'):assert child[name]=={k:v for k,v in original[name].items() if k.startswith('tefra')}
    for p,h in child['assets'].items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h
    models={'subject':AssessmentSubject,'environment':AssessmentEnvironment,'recipe':RecipeDefinition,'recipe_runtime':RecipeRuntimeBinding,'recipe_materialization_request':RecipeMaterializationRequest}
    docs={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')};docs.update(child['new_documents'])
    for key,value in docs.items():assert content_digest(models[value['kind']].model_validate(value['document']))==key
    request=RecipeMaterializationRequest.model_validate(child['request']);prior=RecipeMaterializationRequest.model_validate(original['request']);amendment=AssessmentScopeAmendment.model_validate(child['amendment'])
    assert set(docs)==set(child['reviewed_document_digests'])==set(amendment.reviewed_digests)
    assert request.recipe_digest==prior.recipe_digest and request.environment_digest==prior.environment_digest and request.runtime_dependencies==prior.runtime_dependencies
    source=(OUT/'run.py').read_text();ast.parse(source)
    assert "envelope = json.loads((HERE.parent / 'operation-review.json').read_text())" in source
    assert "HERE.parent / 'review-budget-anchor.json'" in source
    expected=(HERE/'run.py').read_text().replace('ROOT = HERE.parents[3]','ROOT = HERE.parents[4]').replace("HERE / 'review-budget.py'","HERE.parent / 'review-budget.py'").replace('envelope = review',"envelope = json.loads((HERE.parent / 'operation-review.json').read_text())").replace("HERE / 'review-budget-anchor.json'","HERE.parent / 'review-budget-anchor.json'")
    assert source==expected
    spec=importlib.util.spec_from_file_location('cumulative_control_budget',HERE/'review-budget.py');budget=importlib.util.module_from_spec(spec);spec.loader.exec_module(budget)
    initial=json.loads((HERE/'review-budget-anchor.json').read_text())['grant_before'];current=json.loads((HERE/'initial-failure-reconciliation.json').read_text())['grant_after']
    budget.require_room(current,initial,AssessmentLimits(max_operations=10,max_elapsed_seconds=430),original)
    try:budget.require_room([initial[0]+21,initial[1],initial[2]+10,initial[3]],initial,AssessmentLimits(max_operations=1,max_elapsed_seconds=1),original)
    except RuntimeError:pass
    else:raise AssertionError('Cumulative operation ceiling bypassed')
    value={'passed':True,'identical_unstarted_payloads':8,'unchanged_case_truth_reference_software_permissions':True,'all_definitions_canonical':True,'same_source_recipe_environment':True,'cumulative_parent_anchor_preserved':True,'actual_budget_guard_rejects_operation22':True,'no_initial_attempt_replay_or_refund':True,'new_model_install_build_download_or_execution':0,'child_review_sha256':sha(OUT/'operation-review.json')}
    with(HERE/'control-correction-check.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))

if __name__=='__main__':main()
