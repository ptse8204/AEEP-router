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
    assert not (HERE/'runtime-review.json').exists()
    parent_path=HERE/'observer-envelope.json';parent=json.loads(parent_path.read_text())
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    stability_path=HERE/'validation/source-stability.json'
    stability=json.loads(stability_path.read_text())
    assert stability['all_passed'] and stability['source_unchanged']
    assert verification_source_digest(ROOT)==stability['source_digest']==parent['source_digest']
    assert runtime_dependencies()==before.runtime_dependencies
    metadata=json.loads((HERE/'execution-cases.json').read_text());assert metadata['prepared_cases']==8 and not metadata['errors']
    cases_path,variants_path=ROOT/metadata['cases_file'],ROOT/metadata['variants_file']
    assert sha(cases_path)==metadata['cases_file_sha256']
    cases=[RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants=json.loads(variants_path.read_text());assert len(cases)==8 and len(variants)==20
    assert len({c.source_repository.casefold() for c in cases})==4
    assert len({(c.source_repository.casefold(),c.source_revision) for c in cases})==8
    assert len({c.input.source_sha256 for c in cases})==8
    development={'delgan/loguru','pallets/click','marshmallow-code/marshmallow','pgmpy/pgmpy'}
    assert not {c.source_repository.casefold().removeprefix('https://github.com/') for c in cases}&development
    closure=json.loads((HERE/'runtime-support-review.json').read_text());assert closure['complete_static_dependency_closure'] and len(closure['pins'])==12
    context=ROOT/'.aeep/repository-test-root-image-20261027';context.mkdir(exist_ok=False)
    expanded=0
    for pin in closure['pins']:
        path=ROOT/pin['private_cache'];assert sha(path)==pin['sha256']
        with zipfile.ZipFile(path) as archive:expanded+=sum(x.file_size for x in archive.infolist())
        shutil.copyfile(path,context/pin['filename'])
    requirements=''.join('/opt/aeep-runtime/'+p['filename']+' --hash=sha256:'+p['sha256']+'\n' for p in closure['pins'])
    (context/'requirements.txt').write_text(requirements)
    reference='aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027'
    dockerfile='FROM '+reference+'\nUSER 0:0\nCOPY '+' '.join(p['filename'] for p in closure['pins'])+' requirements.txt /opt/aeep-runtime/\nRUN ["python3", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\nUSER 65534:65534\n'
    source_review=json.loads((HERE/'jsonpath-source-review.json').read_text())
    copy_root=ROOT/source_review['copy_tree']/'jsonpath_rw'
    assert sorted(str(p.relative_to(copy_root)) for p in copy_root.rglob('*') if p.is_file())==sorted([p['file'].removeprefix('jsonpath_rw/') for p in source_review['library_files_identical_to_license_commit']]+['LICENSE.source'])
    for item in source_review['library_files_identical_to_license_commit']:
        assert sha(copy_root/item['file'].removeprefix('jsonpath_rw/'))==item['sha256']
    assert sha(copy_root/'LICENSE.source')==source_review['license_sha256']
    shutil.copytree(copy_root,context/'jsonpath_rw')
    dockerfile=dockerfile.replace('USER 65534:65534\n','COPY --chmod=0555 jsonpath_rw/ /usr/local/lib/python3.13/site-packages/jsonpath_rw/\nUSER 65534:65534\n')
    (context/'Dockerfile').write_text(dockerfile)
    for path in context.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    maximum_growth=192*1024**2;assert expanded+closure['downloaded_wheel_bytes']<maximum_growth
    free=shutil.disk_usage(ROOT).free;assert free>50*1024**3+maximum_growth
    inspection=subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',reference],timeout=20)
    image=json.loads(inspection)[0];assert image['Id']==parent['image'] and image['Config'].get('OnBuild') in (None,[])
    assert image['Architecture']=='arm64' and image['Os']=='linux'
    (HERE/'parent-image-inspection.json').write_bytes(inspection)
    (HERE/'docker-usage-pre-review.txt').write_bytes(subprocess.check_output([parent['docker'],'--host',parent['socket'],'system','df'],timeout=20))
    assets={str(p.resolve()):sha(p) for p in [cases_path,variants_path,parent_path,stability_path,*(p for p in context.rglob('*') if p.is_file()),*(HERE/n for n in ('execution-cases.json','runtime-support-review.json','jsonpath-source-review.json','operator-observer.py','operator-observer-review.json','operator-observer-check.json','runtime-execution/operator_output.py','review-budget.py','parent-image-inspection.json','run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py'))]}
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
        if case.origin_kind=='authored_control':
            extra=set(required)-set(negative);assert len(extra)==1;negative.update({n:'FAILED' for n in extra})
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
    subject=AssessmentSubject(kind='command',location=str(context),dependency_digests=assets,description='One12-wheel offline grader image with unchanged JSONPath library copy and eight cached v4 repository tasks,with three mandatory fresh runtime/containment probes. No models or adopted stages.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id='onboarding',seed=82,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    documents={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]:documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    max_calls=3+len(variants);max_operations=max_calls+3;max_seconds=180+30+120+max_calls*35
    assert (max_calls,max_operations,max_seconds)==(23,26,1135)
    review={'purpose':'One private offline22-wheel optional grader image,three fresh probes and17 exact reference/counterexample/partial variants across six snapshots of five repositories. No models or stage adoption.',
        'source_digest':parent['source_digest'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),'authorization_digest':parent['authorization_digest'],
        'assets':assets,'cases_file':metadata['cases_file'],'variants_file':metadata['variants_file'],'active_case_ids':[c.input.task_id for c in cases],
        'case_summary':metadata['cases'],'variant_labels':labels,'expectations':expectations,
        'parent_reference':reference,'parent_image':parent['image'],'target_tag':'aeep-toolkit-v2/repository-grader:py313-test-roots-20261027',
        'build_context':str(context.relative_to(ROOT)),'context_files':sorted(str(p.relative_to(context)) for p in context.rglob('*') if p.is_file()),'build_request':request.model_dump(mode='json'),
        'build_documents':documents,'build_amendment':amendment.model_dump(mode='json'),'host_canary':parent['host_canary'],
        'maximum_builds':1,'maximum_build_growth_bytes':maximum_growth,'maximum_contained_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,
        'maximum_model_turns':0,'cash_usd':0,'automatic_retry':False,'runtime_dependencies_review':closure,
        'maximum_model_turns':0,
        'permissions':['One local offline image build from existing pinned parentb0eb4add; exactly22 cached hashed support wheels, no resolver/source build/pull/build network/host installation. Retain the output image and all prior images.',
            'Bind actual output image digest before source tests. Verify inherited configuration, parent layer prefix, exactly two new filesystem layers and at most192MiB growth; keep50GiB host free. These operation caps are not product SLOs.',
            'At most20 offline contained calls:three fresh boundary/state/version probes and17 fixed reference/counterexample/per-file-partial variants across six snapshots/five repositories. At most23 existing-grant operations and1030 reserved seconds, including180 build +30 setup +120 analysis +20 times35 per call. The existing hard budget guard applies before each reservation across both phases.',
            'Explicitly load only the declared pytest plugins from the reviewed runtime before exposing project paths. Keep all170 original/declared test identities and every upstream assertion; new audits add private byte-preservation guards. Goodconf uses only its reviewed published capture flag, with all coverage flags retained; unrelated CI/ignored-lockfile edits remain omitted and recorded.',
            'Upstream tests may create their bounded child processes and local fixtures inside the offline container; no host service, published port, host configuration or external connection is authorized. Preserve raw bounded replies, canonical receipts/attempts and all charges. Remove only new attempt-owned containers and the unchanged owned nonsecret canary.',
            'Isolated source incompatibility may exclude a case after canonical completion and verified cleanup; common authority/accounting/binding/cleanup uncertainty stops dispatch. No automatic retry or reuse of unstarted slots.',
            'No models/cash, downloads during execution, image pulls/deletion, OS packages, project installers, credentials, new external destinations/services, package/docs reruns, activation, publication or release.'],
        'limitations':['These22 optional grader supports are not toolkit core requirements. Static closure/tags are not runtime compatibility, model qualification or useful selection evidence.',
            'MCP384, Goodconf51 and Prometheus1134 are explicitly authored corrected-snapshot audits. MCP222 and Twyn317 are multi-file repairs; Dishka512 is a single-file repair. Same-repository snapshots stay in one stage. No case is adopted or stage frozen.',
            'Goodconf retains its original source and all test assertions; the published -s capture flag is applied equally as an authored runtime profile. The CI runner/matrix and ignored uv.lock metadata edits are not executed. The original row and every omitted section hash remain retained.',
            'Dishka and Prometheus earlier reference failures remain failed. New exact plugin/runtime checks cannot rewrite them or claim the old exception cause. CanvasAPI stays excluded after its terminal collection error, and no retry is included here.',
            'PyGLS remains deferred for its decorated collection hook/fixture-scope review. No cattrs/lsprotocol/websockets support is selected for installation. MCP1864 still needs a bounded serial profile; it is not included.',
            'All20 allowed calls are offline grader observations. No model task, formal campaign, benefit, native selection, resource acceptance or release gate follows from reproduction.'],
        'approval_reason':'The actual user approved terminalbe8b0e5f only. Their continuation reserves new untrusted installation/execution, and CONTINUATION.md requires applicable provisioning authority. This review binds22 different packages and six subjects/variants. Routine finite definitions remain delegated; actual exact execution approval is required. No architecture decision is needed.'}
    review.update(purpose='One offline private12-wheel grader image plus unchanged six-file JSONPath source/library license COPY; three fresh probes and20 exact variants for eight v4 tasks. Operator-only public failure tails up to8192bytes. No models or stage adoption.',
        jsonpath_source_review=source_review, maximum_new_filesystem_layers=3,
        permissions=[
            'One local offline image build from retainedf603 through its checked existing tag. Exactly12 cached hashed wheels, no resolver/source build/pull/network/host installation. COPY six unchanged publisher JSONPath modules plus its same-commit Apache2 license at0555; no setup.py or console entry point. Retain every image.',
            'Bind output digest before testing. Require inherited execution configuration, parent layers, exactly three new filesystem layers and at most192MiB growth; maintain50GiB host reserve. These finite operation caps are not product acceptance budgets.',
            'At most23 contained offline calls:three fresh boundary/state/runtime probes and20 fixed reference/counterexample/per-file-partial variants across eight snapshots/four repositories. At most26 existing-grant operations and1135 reserved seconds including180 build,30 setup,120 analysis and23 times35 per call. Preserve counters and check the existing grant before every reservation.',
            'Explicit operator opt-in: retain at most8192bytes of each failed public test log as base64 in the bounded raw reply. Successful tests have empty tails. Only the unchanged five-field evaluation reaches the protected grader. Logs remain untrusted operator data, never model instructions or benchmark answers; default product retention remains unchanged.',
            'Keep1033 declared test identities, every upstream assertion and exact published paths. Use only reviewed explicit plugins. Public tests may create bounded children/fixtures inside offline containers; no host service, port or external network.',
            'Retain raw replies, canonical receipts, terminal attempts and every charge. Remove only new attempt-owned containers and the unchanged owned nonsecret canary. Isolated source incompatibility may exclude a case only after canonical completion/cleanup; common binding, authority, accounting or cleanup uncertainty stops dispatch.',
            'One terminal attempt; no automatic retry or reuse of unused slots. No models, cash, downloads, pulls, OS/project/host installation, credentials, new services/destinations, package/docs reruns in this component, image deletion, activation, publication or release.'],
        limitations=[
            'This operator observer/profile and optional grader runtime require their own applicable reproduction evidence. Historical44-case pool bindings stay unchanged; default-observer campaigns inherit no conformance automatically.',
            'Eight tasks include3single-file repairs,2multi-file repairs and3authored audits. The915 identities in one task are not915 independent cases. No case or stage is adopted/frozen; no usefulness, qualification, selection, resource or release gate closes.',
            'Sopel remains excluded for incompatible SQLAlchemy1.4 and project metadata/plugin requirements. Raygun, Skelebot and Towncrier scope failures stay recorded. No hidden project installer or relaxed test assertion is authorized.',
            'JSONPath distribution1.4.0 embeds module version1.3.0; unchanged file hashes, license provenance and actual module version are checked separately. Static dependency closure is not runtime compatibility.'],
        approval_reason='The completedf0261e6d approval binds different subjects and older source. The user continuation reserves new untrusted installation/execution and CONTINUATION.md requires applicable provisioning authority. This exact build/runtime review needs approval; routine finite definitions remain delegated. No architecture or budget decision is needed.')
    (HERE/'runtime-review.json').write_text(json.dumps(review,indent=2)+'\n')
    resource={'compressed_wheel_bytes':closure['downloaded_wheel_bytes'],'unpacked_wheel_member_bytes':expanded,'maximum_image_growth_bytes':maximum_growth,'host_reserve_bytes':50*1024**3,'free_bytes':free,'operational_cap_is_not_product_acceptance':True,'builds':0}
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps(resource,indent=2)+'\n')
    audit={'passed':True,'source_unchanged':True,'cases':8,'repositories':4,'distinct_snapshots':8,'payloads':20,'first_party_grader_guards':guard_checks,'classifier_checks':classifier.self_check(),'assets':len(assets),'driver_syntax':True,'root_bindings_checked':True,'image_parent_present':True,'new_wheels':12,'maximum_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'review_sha256':sha(HERE/'runtime-review.json'),'builds':0,'external_code_executed':False,'models':0,'cases_adopted':0}
    (HERE/'preparation-checks.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':asyncio.run(main())
