"""Prepare one finite offline image and repository batch, without executing it."""
import ast
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentScopeAmendment, AssessmentSubject, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    assert not (HERE/'approval-bundle.json').exists()
    parent_path=HERE/'observer-envelope.json';parent=json.loads(parent_path.read_text())
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    stability_path=HERE.parent/'repository-compact-patches-20261022/validation/source-stability.json'
    stability=json.loads(stability_path.read_text())
    assert stability['all_passed'] and stability['source_unchanged']
    assert verification_source_digest(ROOT)==stability['source_digest']==parent['source_digest']
    assert runtime_dependencies()==before.runtime_dependencies
    metadata=json.loads((HERE/'prepared-cases.json').read_text());assert metadata['prepared_cases']==22 and not metadata['errors']
    cases_path,variants_path=ROOT/metadata['cases_file'],ROOT/metadata['variants_file']
    assert sha(cases_path)==metadata['cases_file_sha256']
    cases=[RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants=json.loads(variants_path.read_text());assert len(cases)==22 and len(variants)==94
    assert len({c.source_repository.casefold() for c in cases})==6
    assert len({(c.source_repository.casefold(),c.source_revision) for c in cases})==22
    assert len({c.input.source_sha256 for c in cases})==22
    development={'delgan/loguru','pallets/click','marshmallow-code/marshmallow','pgmpy/pgmpy'}
    assert not {c.source_repository.casefold().removeprefix('https://github.com/') for c in cases}&development
    closure=json.loads((HERE/'runtime-install-review.json').read_text());assert closure['complete_static_dependency_closure'] and len(closure['pins'])==14
    context=ROOT/'.aeep/repository-workload-batch-20261022-image-context-v2';context.mkdir(exist_ok=False)
    expanded=0
    for pin in closure['pins']:
        path=ROOT/pin['private_cache'];assert sha(path)==pin['sha256']
        with zipfile.ZipFile(path) as archive:expanded+=sum(x.file_size for x in archive.infolist())
        shutil.copyfile(path,context/pin['filename'])
    requirements=''.join('/opt/aeep-runtime/'+p['filename']+' --hash=sha256:'+p['sha256']+'\n' for p in closure['pins'])
    (context/'requirements.txt').write_text(requirements)
    reference='aeep-toolkit-v2/repository-grader:py313-explicit-plugins-20261022'
    dockerfile='FROM '+reference+'\nUSER 0:0\nCOPY '+' '.join(p['filename'] for p in closure['pins'])+' requirements.txt /opt/aeep-runtime/\nRUN ["python3", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\nUSER 65534:65534\n'
    (context/'Dockerfile').write_text(dockerfile)
    for path in context.iterdir():path.chmod(0o644)
    maximum_growth=192*1024**2;assert expanded+closure['downloaded_wheel_bytes']<maximum_growth
    free=shutil.disk_usage(ROOT).free;assert free>50*1024**3+maximum_growth
    inspection=subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',reference],timeout=20)
    image=json.loads(inspection)[0];assert image['Id']==parent['image'] and image['Config'].get('OnBuild') in (None,[])
    assert image['Architecture']=='arm64' and image['Os']=='linux'
    (HERE/'parent-image-inspection.json').write_bytes(inspection)
    (HERE/'docker-usage-pre-review.txt').write_bytes(subprocess.check_output([parent['docker'],'--host',parent['socket'],'system','df'],timeout=20))
    assets={str(p.resolve()):sha(p) for p in [cases_path,variants_path,parent_path,stability_path,*context.iterdir(),*(HERE/n for n in ('prepared-cases.json','runtime-install-review.json','combined-source-review.json','combined-git-tree-scopes.json','source-scope-review-v3.json','parent-image-inspection.json','run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py'))]}
    spec=importlib.util.spec_from_file_location('reviewed_case_classifier',HERE/'runtime-execution/classify.py');classifier=importlib.util.module_from_spec(spec);spec.loader.exec_module(classifier)
    expectations,labels,guard_checks={},{},0
    for case,description in zip(cases,metadata['cases'],strict=True):
        assert case.input.task_id==description['id']
        for item in (case.truth.source,case.truth.tests,case.reference,*case.truth.wheels):item.read();assets[item.path]=item.sha256
        row_path=ROOT/description['source_record']/'row.json';row=json.loads(row_path.read_text());assets[str(row_path.resolve())]=sha(row_path)
        for record in description['license_records']:
            path=ROOT/record['path'];assert sha(path)==record['sha256'];assets[str(path.resolve())]=record['sha256']
        required=case.truth.fail_to_pass+case.truth.pass_to_pass
        negative={n:'FAILED' for n in row['FAIL_TO_PASS']};negative.update({n:'PASSED' for n in row['PASS_TO_PASS']})
        if case.origin_kind=='authored_control':negative['tests/test_aeep_preservation.py::test_snapshot_preserved']='FAILED'
        assert set(negative)==set(required)
        positive={'exit_code':0,'valid':True,'detail':'','statuses':{n:'PASSED' for n in required},'required_identities':required}
        counter={'exit_code':1,'valid':False,'detail':'test_failure','statuses':negative,'required_identities':required}
        partial={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{},'at_least_one_failed':required,'required_identities':required}
        own=[v for v in variants if v['case']==case.input.task_id];labels[case.input.task_id]=[v['variant'] for v in own]
        expectations[case.input.task_id]={v['variant']:positive if v['variant']=='reference' else counter if v['variant']=='counterexample' else partial for v in own}
        for variant in own:
            path=ROOT/variant['payload'];assert sha(path)==variant['sha256'] and path.stat().st_size==variant['bytes'];assets[str(path.resolve())]=variant['sha256']
            class Captured(Exception):pass
            captured=[]
            async def capture(payload):
                captured.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest());raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),variant['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Inert payload verification returned a grade')
            assert captured==[variant['sha256']]
        for kind in ('pass','exit','missing','error','skip'):
            async def fake(payload):
                statuses={n:'PASSED' for n in required}
                if kind=='missing':statuses.pop(required[0])
                if kind in ('error','skip'):statuses[required[0]]='ERROR' if kind=='error' else 'SKIPPED'
                return {'exit_code':1 if kind=='exit' else 0,'statuses':statuses,'archive_sha256':payload['archive_sha256'],'python':payload['python'],'pytest':payload['pytest']}
            grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),own[0]['artifact'],fake)
            assert grade.valid==(kind=='pass');guard_checks+=1
    for pin in closure['pins']:
        for license in pin['licenses']:
            path=ROOT/license['retained'];assert sha(path)==license['sha256'];assets[str(path.resolve())]=license['sha256']
        path=ROOT/pin['private_cache'];assets[str(path.resolve())]=pin['sha256']
    for name in ('run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py'):ast.parse((HERE/name).read_text())
    for name in ('run.py','audit-execution.py'):
        assert 'ROOT = HERE.parents[4]' in (HERE/'runtime-execution'/name).read_text()
        assert (HERE/'runtime-execution').resolve().parents[4]==ROOT
    subject=AssessmentSubject(kind='command',location=str(context),dependency_digests=assets,description='One14-wheel offline grader image and22 provisional repository tasks,with three mandatory fresh runtime/containment probes. No models or adopted stages.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id='onboarding',seed=66,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    documents={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]:documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    max_calls=3+len(variants);max_operations=max_calls+3;max_seconds=180+30+120+max_calls*30
    assert (max_calls,max_operations,max_seconds)==(97,100,3240)
    review={'purpose':'One private offline14-wheel grader image,three fresh probes and94 exact repository variants across22 distinct snapshots/six repositories. No models or stage adoption.',
        'source_digest':parent['source_digest'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),'authorization_digest':parent['authorization_digest'],
        'assets':assets,'cases_file':metadata['cases_file'],'variants_file':metadata['variants_file'],'active_case_ids':[c.input.task_id for c in cases],
        'case_summary':metadata['cases'],'variant_labels':labels,'expectations':expectations,
        'parent_reference':reference,'parent_image':parent['image'],'target_tag':'aeep-toolkit-v2/repository-grader:py313-pydantic-django-20261022',
        'build_context':str(context.relative_to(ROOT)),'context_files':sorted(p.name for p in context.iterdir()),'build_request':request.model_dump(mode='json'),
        'build_documents':documents,'build_amendment':amendment.model_dump(mode='json'),'host_canary':parent['host_canary'],
        'maximum_builds':1,'maximum_build_growth_bytes':maximum_growth,'maximum_contained_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,
        'maximum_model_turns':0,'cash_usd':0,'automatic_retry':False,'runtime_dependencies_review':closure,
        'permissions':['Build once from the verified existing local image/tag,with pulls and build network disabled. Install only14 exact hashed wheels privately,without dependency resolution,source builds or host installation. Retain the output image for remaining work; no old-image deletion.',
            'Verify parent ID before/after build,inherited configuration,parent layer prefix,exactly two new filesystem layers,and no more than192MiB growth. This operation cap is not a product resource SLO.',
            'Bind the actual output image ID in a deterministic new environment/request/review before any source call. Parent approval covers only that derivation. Three fresh containment/state/runtime probes must pass,including metadata versions for all14 supports and basic compiled-Pydantic/Django checks.',
            'At most97 contained calls:three probes and94 exact reference/counterexample/per-file-regression variants. Maximum100 existing-grant operations and3240 reserved seconds including build/setup/analysis. No resets,refunds,model turns or cash.',
            'Retain raw bounded replies before protocol validation,canonical attempts/receipts/ledgers,and all failures. Remove only attempt-owned containers and the unchanged named nonsecret canary. Independent cases may continue only after verified accounting/completion/cleanup; common uncertainty stops dispatch.',
            'No downloads,pulls,OS packages,project installers,new destinations,credentials,services,package/docs reruns,models,cash,activation,publication or release. No automatic replay of a terminal attempt.'],
        'limitations':['Static closure/tags are not runtime compatibility or qualification. The selected image is a private optional grader support,not a new AEEP core dependency or normal task requirement.',
            'Most new multi-file cases are SQLglot issues from distinct revisions. They remain one repository group across stage assignment and uncertainty; no same-repository case may cross stages. No full8/28/105 cohort is frozen.',
            'DjangoBird retains all Python source/assertions and all declared pytest options except automatic xdist concurrency. A reviewed pytest.ini selects serial execution. The original pyproject remains; this is an authored runtime adaptation,not official benchmark equivalence.',
            'SVCS and Prometheus audits are explicitly authored corrected snapshots with private preservation guards; they are not official upstream benchmark repair results. All original required assertions remain.',
            'The old SQL7479 failure is retained. Its selected module imports missing pytz; that is a static explanation to test,not the recovered past exception. This changed-runtime check cannot rewrite the old result.',
            'No candidate benefit,correct selection,token/time/cash savings,human-control success,resource acceptance or release follows from reference reproduction.'],
        'approval_reason':'The user continuation reserves untrusted software execution/installation and CONTINUATION.md requires applicable container-provisioning authority. Completed31c5138d covers a different runtime and sources. Routine finite definitions are delegated; this new exact installation/execution needs actual user approval.'}
    (HERE/'approval-bundle.json').write_text(json.dumps(review,indent=2)+'\n')
    resource={'compressed_wheel_bytes':closure['downloaded_wheel_bytes'],'unpacked_wheel_member_bytes':expanded,'maximum_image_growth_bytes':maximum_growth,'host_reserve_bytes':50*1024**3,'free_bytes':free,'operational_cap_is_not_product_acceptance':True,'builds':0}
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps(resource,indent=2)+'\n')
    audit={'passed':True,'source_unchanged':True,'cases':22,'repositories':6,'distinct_snapshots':22,'payloads':94,'first_party_grader_guards':guard_checks,'classifier_checks':classifier.self_check(),'assets':len(assets),'driver_syntax':True,'root_bindings_checked':True,'image_parent_present':True,'new_wheels':14,'maximum_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'review_sha256':sha(HERE/'approval-bundle.json'),'builds':0,'external_code_executed':False,'models':0,'cases_adopted':0}
    (HERE/'preparation-checks.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':asyncio.run(main())
