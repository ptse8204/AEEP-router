"""Freeze one scoped validator regression as inert data; execute no external code."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentSubject,RecipeMaterializationRequest,
    AssessmentScopeAmendment,content_digest)
from aeep.assessment.repository_suites import (RepositorySuiteCase,decode_patch,grade_suite_output,
    patch_artifact,repository_suite_recipe)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.assessment.verification import verification_source_digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OLD=HERE.parent/'repository-suite-integration-20261022'
PRIOR=HERE.parent/'repository-suite-continuation-20261022'
PRIVATE=ROOT/'.aeep/repository-suite-semantic-fault-20261022'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not(HERE/'operation-review.json').exists()
    assert shutil.disk_usage(ROOT).free>50*1024**3
    parent_path=OLD/'grader-operation-review.json'
    parent=json.loads(parent_path.read_text())
    assert verification_source_digest(ROOT)==parent['source_digest']
    assert runtime_dependencies()==parent['request']['runtime_dependencies']
    previous=json.loads((PRIOR/'execution-result.json').read_text())
    assert previous['contained_calls_started']==6 and previous['containers_removed'] and not previous['passed']
    assert [item['name'] for item in previous['results']]==['pallets__click-3239-reference','pallets__click-3239-unchanged',
        'pallets__click-3239-semantic_fault','marshmallow-code__marshmallow-2800-reference','marshmallow-code__marshmallow-2800-unchanged']
    assert all(item['passed'] for item in previous['results'])
    audit=json.loads((PRIOR/'completion-audit.json').read_text())
    assert audit['physical_receipt_integrity_passed'] and audit['canonical_receipts_reopened']==6
    PRIVATE.mkdir(exist_ok=False)
    cases=[RepositorySuiteCase.model_validate(value) for value in json.loads((ROOT/parent['cases_file']).read_text())]
    case=next(item for item in cases if item.input.task_id=='marshmallow-code__marshmallow-2800')
    patch=decode_patch(json.loads(case.reference.read()))
    name,source=next(iter(patch.files.items()))
    assert name=='src/marshmallow/validate.py'
    tree=ast.parse(source)
    url=next(item for item in tree.body if isinstance(item,ast.ClassDef) and item.name=='URL')
    call=next(item for item in url.body if isinstance(item,ast.FunctionDef) and item.name=='__call__')
    assert [arg.arg for arg in call.args.args]==['self','value']
    lines=source.splitlines(keepends=True)
    index=call.body[0].lineno-1
    lines.insert(index,'        return value  # AEEP reviewed semantic fault: bypass URL validation.\n')
    faulty=''.join(lines)
    new_tree=ast.parse(faulty)
    assert len(faulty)>len(source) and 'raise RuntimeError("AEEP development semantic fault")' not in faulty
    new_url=next(item for item in new_tree.body if isinstance(item,ast.ClassDef) and item.name=='URL')
    new_call=next(item for item in new_url.body if isinstance(item,ast.FunctionDef) and item.name=='__call__')
    assert isinstance(new_call.body[0],ast.Return) and isinstance(new_call.body[0].value,ast.Name) and new_call.body[0].value.id=='value'
    # Verify the only AST change is the deliberately inserted return; no imports altered.
    new_call.body.pop(0)
    assert ast.dump(tree,include_attributes=False)==ast.dump(new_tree,include_attributes=False)
    artifact=patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input),files={name:faulty}))
    case.fault_outputs=[artifact]
    cases_path=PRIVATE/'cases.json'
    cases_path.write_text(json.dumps([item.model_dump(mode='json') for item in cases],indent=2)+'\n')
    recipe=repository_suite_recipe(cases)
    assert content_digest(recipe.extension.grader)==content_digest(parent['recipe']['extension']['grader'])
    payload_path=PRIVATE/'marshmallow-semantic-fault-payload.json'
    class Captured(Exception):pass
    async def capture(payload):
        payload_path.write_text(json.dumps(payload,separators=(',',':')))
        raise Captured()
    try:
        await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,capture)
    except Captured:pass
    else:raise AssertionError('Preparation returned a grade')
    payload=json.loads(payload_path.read_text())
    assets={**parent['assets'],str(cases_path):sha(cases_path),str(payload_path):sha(payload_path)}
    for path,expected in assets.items():assert Path(path).is_file() and not Path(path).is_symlink() and sha(Path(path))==expected
    subject=AssessmentSubject(kind='command',location=str(PRIVATE),dependency_digests=assets,
        description='One reviewed URL-validator bypass fault; no positive/original, model, wheel or docs replay.')
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),
        recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=before.environment_digest,
        authorization_id=before.authorization_id,seed=41,definition_digests=[content_digest(recipe),before.environment_digest,
            *[key for key,item in parent['documents'].items() if item['kind']=='recipe_runtime']],runtime_dependencies=before.runtime_dependencies)
    docs={key:item for key,item in parent['documents'].items() if item['kind'] in ('environment','recipe_runtime')}
    new_docs={}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe',recipe.recipe_id,recipe),
        ('recipe_materialization_request',request.plan_id,request)]:
        new_docs[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    docs.update(new_docs)
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)],recipe_digests=[content_digest(recipe)],
        environment_digests=[before.environment_digest],reviewed_digests=list(docs))
    prior_summary={'completed_observations_acceptable':True,
        'meaning':'Only previously successful observations are reused. Both terminal script failures and the missing raw reply remain failures/unknown, not rewritten as passed.',
        'accepted_boundary_probes':3,'accepted_loguru_variants':3,'accepted_click_variants':3,'accepted_marshmallow_variants':2,
        'missing_marshmallow_fault_grade':True,'previous_result_sha256':sha(PRIOR/'execution-result.json'),
        'previous_receipt_audit_sha256':sha(PRIOR/'completion-audit.json'),'first_result_sha256':sha(OLD/'grader-execution-result.json'),
        'first_receipt_audit_sha256':sha(OLD/'completion-audit.json'),'source_digest':parent['source_digest']}
    (HERE/'prior-observations-audit.json').write_text(json.dumps(prior_summary,indent=2)+'\n')
    image=subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',parent['image'],'--format','{{.Id}}'],timeout=20).decode().strip()
    assert image==parent['image']
    review={'purpose':'One semantic-fault observation after an import-time fault produced an unretained malformed-protocol reply. No positive-result or completed-cell replay.',
        'source_digest':parent['source_digest'],'runner_sha256':sha(HERE/'run.py'),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),
        'prior_observation_audit':str((HERE/'prior-observations-audit.json').relative_to(ROOT)),
        'prior_observation_audit_sha256':sha(HERE/'prior-observations-audit.json'),
        'new_documents':new_docs,'reviewed_document_digests':list(docs),'recipe':recipe.model_dump(mode='json'),
        'request':request.model_dump(mode='json'),'amendment':amendment.model_dump(mode='json'),
        'cases_file':str(cases_path.relative_to(ROOT)),'cases_file_sha256':sha(cases_path),'assets':assets,
        'active_case_ids':[case.input.task_id],'active_variants':['semantic_fault'],
        'variants':[{'case':case.input.task_id,'variant':'semantic_fault','payload':str(payload_path.relative_to(ROOT)),
            'sha256':sha(payload_path),'bytes':payload_path.stat().st_size}],
        'maximum_contained_calls':1,'maximum_operations':3,'maximum_reserved_seconds':185,'maximum_model_turns':0,'cash_usd':0,
        'automatic_retry':False,'probes':[],
        'change':{'kind':'development fault data and report-driver observation retention only',
            'file':name,'published_repair_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'faulty_source_sha256':hashlib.sha256(faulty.encode()).hexdigest(),
            'mutation':'Insert return value as the first statement in URL.__call__, bypassing validation. AST comparison verifies no other source change from the published repair.',
            'expected':'The same190 required tests must all be observed. Pytest must exit1; at least one preservation test must fail. AEEP must return invalid/test_failure. Missing, malformed, error or skipped required results cannot satisfy this new check.'},
        'inherited_containment':{'environment_digest':before.environment_digest,'image':image,'source_digest':parent['source_digest'],'receipts':parent['inherited_containment']['receipts'] if 'inherited_containment' in parent else json.loads((OLD/'grader-execution-result.json').read_text())['receipts'][:3]},
        'permissions':['Run one fresh offline contained test observation on the same image/source/runtime. Retain its bounded public-test status reply before coordinator validation, receipt and ledger.',
            'No model, install, download, image build/pull, docs execution, credentials, new destination, cash, activation, release, positive/original replay or retained-resource removal.',
            'Charge one setup, one analysis and one contained operation to the existing grant without refund/reset. Remove only the new attempt-owned container.'],
        'limitations':parent['limitations'],
        'approval_reason':'Both preceding exact attempts are terminal. This changes a deliberate untrusted fault artifact and report driver, while leaving product source, positive/reference data, runtime dependencies, observer bytes, required tests and thresholds unchanged.',
        'approval_rule':'One exact approval, one observation. No automatic retry.', 'execution_started':False}
    with (HERE/'operation-review.json').open('x') as output:json.dump(review,output,indent=2);output.write('\n')
    (HERE/'mutation-static-review.json').write_text(json.dumps({'passed':True,'only_ast_change':'One leading return value in URL.__call__','imports_unchanged':True,'source_parse_only':True,'payload_bytes':payload_path.stat().st_size,'payload_sha256':sha(payload_path),'candidate_grades_returned':0,'new_containers':0,'model_turns':0},indent=2)+'\n')
    print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'calls':1,'operations':3,'reserved_seconds':185,'product_source_unchanged':True,'external_code_executed':False}))


if __name__=='__main__':
    import asyncio
    asyncio.run(main())
