"""Scope the protected oracle to its existing declared tests; never execute upstream code."""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentScopeAmendment,AssessmentSubject,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository_suites import (RepositorySuiteCase,SuiteAsset,archive_files,decode_patch,
    grade_suite_output,pack_files,patch_artifact)
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep.assessment.verification import verification_source_digest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
PRIOR=HERE.parent/'repository-replacement-runtime-20261022'
PRIVATE=ROOT/'.aeep/repository-declared-tests-20261022-v3'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def asset(path): return SuiteAsset(path=str(path.resolve()),size_bytes=path.stat().st_size,sha256=sha(path))


async def main():
    assert not (HERE/'operation-review.json').exists()
    parent_path=PRIOR/'runtime-execution/parent-runtime-review.json'
    parent=json.loads(parent_path.read_text())
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    assert runtime_dependencies()==before.runtime_dependencies
    assert verification_source_digest(ROOT)==parent['source_digest']
    audit=json.loads((PRIOR/'runtime-execution/completion-audit.json').read_text())
    assert audit['all_owned_containers_absent'] and audit['physical_receipt_integrity_passed']
    old_review=json.loads((PRIOR/'runtime-execution/operation-review.json').read_text())
    original=next(item for item in json.loads((ROOT/old_review['cases_file']).read_text()) if item['input']['task_id']=='oOo0oOo__leanclient-24')
    case=RepositorySuiteCase.model_validate(original)
    required=[*case.truth.fail_to_pass,*case.truth.pass_to_pass]
    assert len(required)==14 and len(set(required))==14
    observed=json.loads((PRIOR/'runtime-execution/raw-observation-22.json').read_text())['output']
    assert observed['exit_code']==1 and all(observed['statuses'][name]=='PASSED' for name in required)
    unexpected={name:status for name,status in observed['statuses'].items() if name not in required}
    assert len(unexpected)==3 and set(unexpected.values())=={'ERROR'}
    source=archive_files(case.truth.source.read());overlay=archive_files(case.truth.tests.read())
    original_config=source['tests/conftest.py'].decode()
    assert 'tests/conftest.py' not in overlay
    assert not any(isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name=='pytest_collection_modifyitems' for node in ast.parse(original_config).body)
    hook=('\n\n# AEEP protected task scope: all14 frozen required identities, without unrelated Lean-runtime tests.\n'
        +'_AEEP_REQUIRED_NODES=frozenset('+repr(required)+')\n'
        +'def pytest_collection_modifyitems(config, items):\n'
        +'    selected=[item for item in items if item.nodeid in _AEEP_REQUIRED_NODES]\n'
        +'    deselected=[item for item in items if item.nodeid not in _AEEP_REQUIRED_NODES]\n'
        +'    items[:]=selected\n'
        +'    if deselected:\n        config.hook.pytest_deselected(items=deselected)\n')
    # Only our own appended hook executes here, against first-party fake pytest items.
    namespace={};exec(compile(hook,'first-party-node-selector','exec'),namespace)
    deselected=[]
    config=SimpleNamespace(hook=SimpleNamespace(pytest_deselected=lambda **kw:deselected.extend(kw['items'])))
    items=[SimpleNamespace(nodeid=name) for name in [*required,*unexpected]]
    namespace['pytest_collection_modifyitems'](config,items)
    assert [item.nodeid for item in items]==required and {item.nodeid for item in deselected}==set(unexpected)
    assert namespace['_AEEP_REQUIRED_NODES']==set(required)
    overlay['tests/conftest.py']=(original_config+hook).encode();ast.parse(overlay['tests/conftest.py'])
    PRIVATE.mkdir(exist_ok=False)
    tests=PRIVATE/'tests.tar.gz';tests.write_bytes(pack_files(overlay))
    value=case.model_dump(mode='json')
    value['input']['task_id']+='-declared-tests'
    value['input']['task']+='\n\nEvaluation scope: the declared diagnostic-range/parser contract and preservation checks. Real Lean-server elaboration, symbol/folding requests and edit persistence are outside this bounded task. The existing14 required assertions remain; the protected oracle selects them by exact test identity.'
    value['truth'].update(tests=asset(tests).model_dump(mode='json'),input_sha256=content_digest(value['input']))
    value['independent_case_id']=value['input']['task_id']
    reference=decode_patch(json.loads(case.reference.read()))
    reference.base_sha256=content_digest(value['input'])
    ref=PRIVATE/'reference.json';ref.write_text(json.dumps(patch_artifact(reference),separators=(',',':')))
    value['reference']=asset(ref).model_dump(mode='json')
    value['provenance']+=' New explicit declared-node task scope. All14 original required identities/assertions are retained; a protected appended collection hook deselects only other identities. Earlier whole-module observation remains FAILED at exit1 (14 declared PASSED,3 unrelated ERROR). No frozen campaign/holdout, success threshold or global exit guard changes. No claim about the three Lean-server tests or their unretained traceback.'
    original_name=sorted(reference.files)[0]
    value['fault_outputs']=[patch_artifact(RepositoryPatch(base_sha256=content_digest(value['input']),files={original_name:source[original_name].decode()}))]
    case=RepositorySuiteCase.model_validate(value)
    cases_file=PRIVATE/'cases.json';cases_file.write_text(json.dumps([case.model_dump(mode='json')],indent=2)+'\n')
    variants=[]
    outputs={'reference':patch_artifact(reference),
        'counterexample':patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input),files={}))}
    for index,name in enumerate(sorted(reference.files),1):
        outputs['partial-'+str(index)]=patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input),files={**reference.files,name:source[name].decode()}))
    for label,output in outputs.items():
        class Captured(Exception):pass
        async def capture(payload):
            path=PRIVATE/(label+'-payload.json');path.write_text(json.dumps(payload,separators=(',',':')))
            variants.append({'case':case.input.task_id,'variant':label,'artifact':output,'payload':str(path.relative_to(ROOT)),
                'sha256':sha(path),'bytes':path.stat().st_size})
            raise Captured()
        try: await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),output,capture)
        except Captured:pass
        else:raise AssertionError('Inert preparation returned a grade')
    variants_file=PRIVATE/'variants.json';variants_file.write_text(json.dumps(variants,indent=2)+'\n')
    assets={str(path.resolve()):sha(path) for path in [cases_file,variants_file,HERE/'run.py',HERE/'classify.py',HERE/'audit-execution.py',
        PRIOR/'runtime-execution/completion-audit.json',PRIOR/'runtime-execution/raw-observation-22.json']}
    for item in [case.truth.source,case.truth.tests,case.reference,*case.truth.wheels]:item.read();assets[item.path]=item.sha256
    for item in variants:assets[str(ROOT/item['payload'])]=item['sha256']
    subject=AssessmentSubject(kind='command',location=str(PRIVATE),dependency_digests=assets,
        description='One new explicitly scoped14-node Leanclient task, reference/original/two partial repairs; no unrelated Lean execution, models or new runtime.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),
        recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,
        authorization_id='onboarding',seed=49,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    documents={key:item for key,item in parent['documents'].items() if item['kind'] in ('recipe','environment','recipe_runtime')}
    new={content_digest(val):{'kind':kind,'id':ident,'document':val.model_dump(mode='json')} for kind,ident,val in [
        ('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    documents.update(new)
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],
        subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    positive={'exit_code':0,'valid':True,'detail':'','statuses':{name:'PASSED' for name in required}}
    negative={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{**{name:'FAILED' for name in case.truth.fail_to_pass},**{name:'PASSED' for name in case.truth.pass_to_pass}}}
    partial={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{name:'PASSED' for name in case.truth.pass_to_pass},'at_least_one_failed':case.truth.fail_to_pass}
    expected={'reference':positive,'counterexample':negative,'partial-1':partial,'partial-2':partial}
    review={'source_digest':parent['source_digest'],'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),
        'authorization_digest':parent['authorization_digest'],'assets':assets,'cases_file':str(cases_file.relative_to(ROOT)),
        'variants_file':str(variants_file.relative_to(ROOT)),'active_case_ids':[case.input.task_id],'variant_labels':{case.input.task_id:list(outputs)},
        'expectations':{case.input.task_id:expected},'driver_files':{name:sha(HERE/name) for name in ('run.py','classify.py')},
        'request':request.model_dump(mode='json'),'new_documents':new,'reviewed_document_digests':list(documents),'amendment':amendment.model_dump(mode='json'),
        'maximum_operations':6,'maximum_reserved_seconds':290,'maximum_contained_calls':4,'probes':[],
        'current_containment_reuse':{'source_digest':parent['source_digest'],'image':parent['image'],'observer_program_sha256':parent['recipe']['dependencies']['program'],
            'receipts':audit['reopened'][:3],'reason':'Same exact source, observer, image, runtime and permissions as the completed fresh3 probes. Only the protected oracle/task-scope data change.'},
        'permissions':['One fresh offline reference/original/two-partial-repair batch on the existing pinned image; at most4 calls,6 operations and290 reserved seconds.',
            'Keep all14 required identities and assertions. Protected test collection selects exactly those nodes; preserve the earlier whole-module failure and all charges. Global zero-exit, missing/error and preservation guards stay intact.',
            'No source change, builds, installations, package/docs reruns, downloads, models, credentials, cash, new destinations, activation, release or retained-image deletion.'],
        'failure_handling':'No automatic replay. Preserve raw bounded observations, canonical accounting/receipts and terminal failures. Stop dispatch on common identity/accounting/cleanup uncertainty.',
        'limitations':['This is a new bounded declared-node task adaptation, not a passed whole-module Lean integration suite or a retroactive correction of the failed task.','Existing seven-case reproduction is not model qualification, a frozen141-case corpus, usefulness, selection quality or resource acceptance.'],
        'approval_reason':'The completed038b2af9 bundle is terminal and explicitly forbids replay. This review changes protected test bytes/task scope, so the exact untrusted-execution boundary needs a new approval. No architecture choice is needed.'}
    with (HERE/'operation-review.json').open('x') as stream:json.dump(review,stream,indent=2);stream.write('\n')
    checks={'passed':True,'source_unchanged':True,'old_required_tests':required,'same14_required_identities':True,'original_assertions_unchanged':True,
        'selector_first_party_fixture_passed':True,'unrelated_observed_errors':unexpected,'variants':len(variants),'assets':len(assets),
        'no_new_external_execution':True,'review_sha256':sha(HERE/'operation-review.json')}
    (HERE/'preparation-checks.json').write_text(json.dumps(checks,indent=2)+'\n')
    print(json.dumps({'passed':True,'review_sha256':checks['review_sha256'],'required':len(required),'variants':len(variants),'external_code_executed':False}))


if __name__=='__main__':asyncio.run(main())
