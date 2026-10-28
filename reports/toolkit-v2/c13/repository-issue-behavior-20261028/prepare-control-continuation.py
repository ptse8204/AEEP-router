"""Apply the approved bounded first-party dispatch repair; do not execute subjects."""
import ast
import copy
import hashlib
import json
from pathlib import Path
import shutil

from aeep.assessment.models import AssessmentSubject,AssessmentScopeAmendment,RecipeMaterializationRequest,content_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OUT=HERE/'control-continuation'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def main():
    bundle=json.loads((HERE/'approval-bundle.json').read_text());approval=json.loads((HERE/'bundle-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sha(HERE/'approval-bundle.json')=='f18daa4a2923557e3326ba42977126c9d1938378a3def8d2eab14caa12bffd97'
    reconciled=json.loads((HERE/'initial-failure-reconciliation.json').read_text());assert reconciled['passed'] and reconciled['uncertain_attempts']==0 and reconciled['subjects_started']==0
    original=json.loads((HERE/'operation-review.json').read_text());parent=json.loads((ROOT/original['parent_review']).read_text())
    assert original['bounded_control_repairs']['maximum_additional_setup_analysis_operations']==2
    OUT.mkdir(exist_ok=False)
    cases=[c for c in json.loads((ROOT/original['cases_file']).read_text()) if c['input']['task_id'].startswith('tefra')]
    ids=[c['input']['task_id'] for c in cases];assert len(cases)==2
    variants=[v for v in json.loads((ROOT/original['variants_file']).read_text()) if v['case'] in ids];assert len(variants)==8
    cache=ROOT/'.aeep/repository-issue-behavior-control-20261028';cache.mkdir(exist_ok=False)
    save(cache/'cases.json',cases);save(cache/'variants.json',variants)
    # A repair of the shared report driver narrows dispatch to unaffected subjects.
    # The failed markup dependency probe is kept; no probe is repeated or changed.
    for n in ('run.py','audit-execution.py','classify.py','operator_output.py'):
        text=(HERE/n).read_text().replace('ROOT = HERE.parents[3]','ROOT = HERE.parents[4]')
        if n=='run.py':
            text=text.replace("HERE / 'review-budget.py'","HERE.parent / 'review-budget.py'").replace('envelope = review',"envelope = json.loads((HERE.parent / 'operation-review.json').read_text())").replace("HERE / 'review-budget-anchor.json'","HERE.parent / 'review-budget-anchor.json'")
        (OUT/n).write_text(text);ast.parse(text)
    assets={**original['assets'],str((HERE/'initial-failure-reconciliation.json').resolve()):sha(HERE/'initial-failure-reconciliation.json'),str((HERE/'prepare-control-continuation.py').resolve()):sha(HERE/'prepare-control-continuation.py')}
    for p in [cache/'cases.json',cache/'variants.json',*(OUT/n for n in ('run.py','audit-execution.py','classify.py','operator_output.py'))]:assets[str(p.resolve())]=sha(p)
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h
    before=RecipeMaterializationRequest.model_validate(original['request'])
    subject=AssessmentSubject(kind='command',location=str(cache),dependency_digests=assets,description='Approved report-control continuation:only eight unstarted immutable XS variants. Optional Markdown metadata probe failure is reconciled;PyMdown remains unstarted. No test/source/reference/software/permission changes or retries.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id=before.authorization_id,seed=before.seed,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    docs={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')};docs.update(new)
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=original['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(docs))
    review={k:copy.deepcopy(original[k]) for k in ('source_digest','authorization_digest','host_canary','parent_review','parent_review_sha256')}
    review.update(assets=assets,cases_file=str((cache/'cases.json').relative_to(ROOT)),variants_file=str((cache/'variants.json').relative_to(ROOT)),active_case_ids=ids,case_summary=[d for d in original['case_summary'] if d['id'] in ids],expectations={k:v for k,v in original['expectations'].items() if k in ids},variant_labels={k:v for k,v in original['variant_labels'].items() if k in ids},driver_files={n:sha(OUT/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},request=request.model_dump(mode='json'),new_documents=new,reviewed_document_digests=list(docs),amendment=amendment.model_dump(mode='json'),probes=[],maximum_operations=10,maximum_reserved_seconds=430,maximum_contained_calls=8,
        cumulative_parent_review_sha256=sha(HERE/'operation-review.json'),cumulative_parent_grant_anchor=json.loads((HERE/'review-budget-anchor.json').read_text())['grant_before'],actual_parent_approval=approval['review_sha256'],
        authority='Actual f18daa4a approval explicitly permits recorded first-party report-control corrections after known completion/cleanup,using only immutable payloads/software and one additional setup/analysis phase. This continuation narrows dispatch to unaffected XS subjects;no new third-party byte or repeated attempt. Routine definitions are covered by the recorded September25/27 delegation.',
        accounting='Initial3operations and3.6952117918990552seconds remain charged. Additional at most8calls+2setup/analysis operations and430reservedseconds;the actual reserve wrapper enforces the original cumulative21operation/895second/zero-model/zero-cash ceiling.',
        failure_policy='One explicit continuation,not an automatic retry. All guards,grading thresholds,upstream/authored assertions,source/reference bytes,required identities,images,programs,wheels,retention and permissions remain identical. Isolated subject rejection remains a rejection;uncertain identity/accounting/cleanup stops dispatch. PyMdown remains blocked and no Markdown payload is added.')
    save(OUT/'operation-review.json',review)
    save(OUT/'operator-approval.json',{**approval,'review_sha256':sha(OUT/'operation-review.json'),'parent_review_sha256':approval['review_sha256'],'authority':'Mechanical application of the explicitly approved finite first-party report-control allowance;not a new human response or general execution authority.'})
    save(HERE/'control-correction-review.json',{'prepared':True,'approved_parent':approval['review_sha256'],'child_review_sha256':sha(OUT/'operation-review.json'),'initial_failure_retained':True,'uncertain_attempts':0,'changed_first_party_controls':['Select only the two unaffected XS cases;do not apply a markup-only dependency probe to them.','Bind both phases to the original cumulative grant anchor/envelope.'],'unchanged_payloads':8,'new_probes_or_extra_diagnostic_calls':0,'remaining_initial_calls_only':True,'additional_setup_analysis_operations':2,'maximum_cumulative_calls_for_this_continuation':9,'maximum_cumulative_operations_for_this_continuation':13,'maximum_original_operations':21,'new_upstream_software_test_or_reference_bytes':0,'execution_started':False})
    print(json.dumps({'prepared':True,'cases':2,'unchanged_payloads':8,'review_sha256':sha(OUT/'operation-review.json'),'actual_execution':False}))

if __name__=='__main__':main()
