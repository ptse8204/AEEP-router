"""Prepare only the six unstarted observations; do not execute repository software."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentSubject, RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from aeep.assessment.verification import verification_source_digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent/'repository-suite-integration-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'operation-review.json').exists()
    parent_path = OLD/'grader-operation-review.json'
    parent = json.loads(parent_path.read_text())
    prior = json.loads((OLD/'grader-execution-result.json').read_text())
    audit = json.loads((HERE/'prior-observations-audit.json').read_text())
    assert audit['completed_observations_acceptable'] and not prior['passed']
    assert prior['contained_calls_started']==6 and prior['containers_removed'] and prior['canary_removed']
    assert verification_source_digest(ROOT)==parent['source_digest']==audit['source_digest']
    assert runtime_dependencies()==parent['request']['runtime_dependencies']
    assert shutil.disk_usage(ROOT).free>50*1024**3
    image = subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',parent['image'],'--format','{{.Id}}'],timeout=20).decode().strip()
    assert image==parent['image']
    for name,expected in parent['assets'].items():
        assert Path(name).is_file() and not Path(name).is_symlink() and sha(Path(name))==expected
    active = ['pallets__click-3239','marshmallow-code__marshmallow-2800']
    variants = [item for item in parent['variants'] if item['case'] in active]
    assert len(variants)==6
    subject = AssessmentSubject(kind='command',location=str((ROOT/parent['cases_file']).parent),
        dependency_digests=parent['assets'],description='Finish only six unstarted Click/Marshmallow development observations; prior Loguru/probe receipts are retained, not replayed.')
    before = RecipeMaterializationRequest.model_validate(parent['request'])
    request = RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),
        recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,
        authorization_id=before.authorization_id,seed=37,definition_digests=before.definition_digests,
        runtime_dependencies=before.runtime_dependencies)
    documents = {key:item for key,item in parent['documents'].items() if item['kind'] in ('recipe','environment','recipe_runtime')}
    new_documents = {}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]:
        new_documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    documents.update(new_documents)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],
        environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    review = {'purpose':'Complete the six unstarted real v5 development observations after correcting only the review-script handling of rejected fault exit codes.',
        'source_digest':parent['source_digest'],'runner_sha256':sha(HERE/'run.py'),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),
        'prior_observation_audit':str((HERE/'prior-observations-audit.json').relative_to(ROOT)),
        'prior_observation_audit_sha256':sha(HERE/'prior-observations-audit.json'),
        'fault_audit_regression_sha256':sha(HERE/'fault-audit-regression.json'),
        'new_documents':new_documents,'reviewed_document_digests':list(documents),
        'request':request.model_dump(mode='json'),'amendment':amendment.model_dump(mode='json'),
        'active_case_ids':active,'variants':variants,'maximum_contained_calls':6,
        'maximum_operations':8,'maximum_reserved_seconds':360,'maximum_model_turns':0,'cash_usd':0,
        'automatic_retry':False,'probes':[],
        'inherited_containment':{'source_digest':parent['source_digest'],'environment_digest':before.environment_digest,
            'image':image,'receipts':prior['receipts'][:3],'basis':'Same source, observer bytes, immutable image, environment and containment profile; three fresh probes passed in the immediately preceding terminal attempt.'},
        'previous_terminal_bundle_sha256':'a2787cd8828ebbad3a06169c3df5793e0f43238ad4af57b026cac432a28fc739',
        'previous_error':'My review script allowed only fault exit1/2. Pytest returned4 when the intentional broken import failed while loading conftest; AEEP correctly graded it invalid with missing_test. Preserve that terminal failed script result and all8 operation charges.',
        'correction':'The report driver accepts only already-invalid scoped faults with nonzero documented pytest exit1..5. Positive reference and unchanged-source requirements are unchanged. No product source, test, dependency, image, wheel, runtime, payload, oracle or threshold changes.',
        'permissions':['One fresh invocation for each of the six unchanged reviewed Click/Marshmallow reference, original and scoped-fault payloads, in fresh offline containers on the existing image.',
            'Record a new finite canonical plan/scope amendment under existing delegation; preserve counters and prior evidence. Maximum8 operations and360 reserved seconds on the same grant.',
            'Reuse completed containment/Loguru observations without replay. No installer, wheel check, docs-checker execution, model call, download, image build/pull, credentials, new destination, cash, activation, release or retained-resource deletion.',
            'Remove only new attempt-owned containers. No new host canary, image, volume, backup or unrelated cleanup.'],
        'evidence_limits':parent['limitations'],
        'approval_reason':'The previous exact review permits one attempt per component and binds its runner hash. That grader component is terminal; its unused ceiling is not a retry authorization. This new review covers only six previously unstarted calls with a corrected report driver.',
        'approval_rule':'One exact human approval, one new execution attempt. No automatic retry or replay of completed observations.',
        'execution_started':False}
    with (HERE/'operation-review.json').open('x') as output:json.dump(review,output,indent=2);output.write('\n')
    print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'calls':6,'operations':8,'maximum_reserved_seconds':360,'source_unchanged':True,'no_new_execution':True}))


if __name__=='__main__':
    main()
