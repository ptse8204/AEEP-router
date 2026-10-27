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
    assert not any((HERE/n).exists() for n in ('operator-approval.json','execution-started.json','build-result.json'))
    if (HERE/'runtime-review.json').exists():
        prior=HERE/'superseded-unapproved-runtime-review-ef1e792b.json'
        assert sha(HERE/'runtime-review.json').startswith('ef1e792b')
        assert not prior.exists(); (HERE/'runtime-review.json').rename(prior)
    parent_path=HERE/'observer-envelope.json';parent=json.loads(parent_path.read_text())
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    stability_path=HERE/'validation/source-stability.json'
    stability=json.loads(stability_path.read_text())
    assert stability['all_passed'] and stability['source_unchanged']
    assert verification_source_digest(ROOT)==stability['source_digest']==parent['source_digest']
    assert runtime_dependencies()==before.runtime_dependencies
    metadata=json.loads((HERE/'execution-cases.json').read_text());assert metadata['prepared_cases']==6 and not metadata['errors']
    cases_path,variants_path=ROOT/metadata['cases_file'],ROOT/metadata['variants_file']
    assert sha(cases_path)==metadata['cases_file_sha256']
    cases=[RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants=json.loads(variants_path.read_text());assert len(cases)==6 and len(variants)==12
    assert len({c.source_repository.casefold() for c in cases})==3
    assert len({(c.source_repository.casefold(),c.source_revision) for c in cases})==6
    assert len({c.input.source_sha256 for c in cases})==6
    development={'delgan/loguru','pallets/click','marshmallow-code/marshmallow','pgmpy/pgmpy'}
    assert not {c.source_repository.casefold().removeprefix('https://github.com/') for c in cases}&development
    closure=json.loads((HERE/'runtime-support-review.json').read_text());assert closure['selected_added_requirements_closed'] and len(closure['pins'])==6
    context=ROOT/'.aeep/repository-large-runtime-image-20261027';context.mkdir(exist_ok=True)
    pending=json.loads((HERE/'pending-wheel-fetch.json').read_text())
    assert pending['size_bytes']==35174018 and not pending['downloaded']
    assert pending['metadata_sha256']==sha(HERE/'scipy-publisher-metadata.json')
    assert pending['publisher_license_sha256']==sha(ROOT/pending['publisher_license_path'])
    all_pins=[*closure['pins'],pending]
    allowed={p['filename'] for p in closure['pins']}|{'Dockerfile','requirements.txt'}
    assert all(p.is_file() and not p.is_symlink() and p.name in allowed for p in context.iterdir())
    expanded=0
    for pin in closure['pins']:
        path=ROOT/pin['private_cache'];assert sha(path)==pin['sha256']
        with zipfile.ZipFile(path) as archive:expanded+=sum(x.file_size for x in archive.infolist())
        shutil.copyfile(path,context/pin['filename'])
    requirements=''.join('/opt/aeep-runtime/'+p['filename']+' --hash=sha256:'+p['sha256']+'\n' for p in all_pins)
    (context/'requirements.txt').write_text(requirements)
    reference='aeep-toolkit-v2/repository-grader:py313-effective-runtime-20261027'
    dockerfile='FROM '+reference+'\nUSER 0:0\nCOPY '+' '.join(p['filename'] for p in all_pins)+' requirements.txt /opt/aeep-runtime/\nRUN ["python3", "-m", "pip", "--isolated", "install", "--no-index", "--no-deps", "--no-compile", "--no-cache-dir", "--disable-pip-version-check", "--require-hashes", "-r", "/opt/aeep-runtime/requirements.txt"]\nUSER 65534:65534\n'
    (context/'Dockerfile').write_text(dockerfile)
    for path in context.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)
    maximum_growth=256*1024**2;assert expanded+closure['downloaded_wheel_bytes']+pending['size_bytes']<maximum_growth
    free=shutil.disk_usage(ROOT).free;assert free>50*1024**3+maximum_growth
    inspection=subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',reference],timeout=20)
    image=json.loads(inspection)[0];assert image['Id']==parent['image'] and image['Config'].get('OnBuild') in (None,[])
    assert image['Architecture']=='arm64' and image['Os']=='linux'
    (HERE/'parent-image-inspection.json').write_bytes(inspection)
    (HERE/'docker-usage-pre-review.txt').write_bytes(subprocess.check_output([parent['docker'],'--host',parent['socket'],'system','df'],timeout=20))
    assets={str(p.resolve()):sha(p) for p in [cases_path,variants_path,parent_path,stability_path,*(p for p in context.rglob('*') if p.is_file()),*(HERE/n for n in ('execution-cases.json','runtime-support-review.json','operator-observer.py','operator-observer-review.json','operator-observer-check.json','runtime-execution/operator_output.py','review-budget.py','parent-image-inspection.json','run-bundle.py','derive-execution.py','fetch-reviewed-wheel.py','pending-wheel-fetch.json','scipy-publisher-metadata.json','scipy-publisher-license.txt','runtime-fit-review.json','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py'))]}
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
    for name in ('run-bundle.py','derive-execution.py','fetch-reviewed-wheel.py','runtime-execution/run.py','runtime-execution/audit-execution.py'):ast.parse((HERE/name).read_text())
    for name in ('run.py','audit-execution.py'):
        assert 'ROOT = HERE.parents[4]' in (HERE/'runtime-execution'/name).read_text()
        assert (HERE/'runtime-execution').resolve().parents[4]==ROOT
    subject=AssessmentSubject(kind='command',location=str(context),dependency_digests=assets,description='One7-wheel private larger repository runtime,six exact subjects,four fresh probes and bounded same-software control diagnostics. One pinned SciPy artifact fetched as data before offline build;no models or adopted stages.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id='onboarding',seed=82,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    documents={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]:documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    initial_calls=4+len(variants);max_calls=initial_calls+4;max_operations=max_calls+7;max_seconds=2*120+180+2*(30+120)+max_calls*35
    assert (max_calls,max_operations,max_seconds)==(20,27,1420)
    review={'purpose':'One private larger-repository runtime and six source-bound subjects. Fetch one exact35MB SciPy wheel as data,then build offline. Four fresh probes include a2.7MB input;12 variants plus at most4 same-software diagnostic calls. No model task or scientific verdict.',
        'source_digest':parent['source_digest'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),'authorization_digest':parent['authorization_digest'],
        'assets':assets,'cases_file':metadata['cases_file'],'variants_file':metadata['variants_file'],'active_case_ids':[c.input.task_id for c in cases],
        'case_summary':metadata['cases'],'variant_labels':labels,'expectations':expectations,
        'parent_reference':reference,'parent_image':parent['image'],'target_tag':'aeep-toolkit-v2/repository-grader:py313-large-repositories-20261027',
        'build_context':str(context.relative_to(ROOT)),'context_files':sorted([*(str(p.relative_to(context)) for p in context.rglob('*') if p.is_file()),pending['filename']]),'pending_wheel_fetch':pending,'fetch_cache':str(ROOT/'.aeep/repository-large-scipy-fetch-20261027'),'maximum_fetch_attempts':2,'maximum_network_download_bytes':2*pending['size_bytes'],'build_request':request.model_dump(mode='json'),
        'build_documents':documents,'build_amendment':amendment.model_dump(mode='json'),'host_canary':parent['host_canary'],
        'maximum_builds':1,'maximum_build_growth_bytes':maximum_growth,'maximum_new_filesystem_layers':2,
        'initial_contained_calls':initial_calls,'maximum_contained_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'maximum_model_turns':0,'cash_usd':0,
        'automatic_retry_of_unknown_attempts':False,'routine_control_repairs_authority':'Standing operator delegation,within this exact external software/subject and finite execution envelope;see bounded_control_repairs.',
        'runtime_dependencies_review':closure,
        'bounded_control_repairs':{'maximum_extra_calls':4,'maximum_additional_setup_analysis_operations':2,
            'allowed':'After known canonical completion and cleanup,record exact first-party report-driver/collector repairs under the standing definition/method delegation. Preserve initial code,review,results and costs;bind changed control code and demonstrate unchanged grading/guardrail semantics before any continuation. Remaining initial calls plus at most4fresh diagnostic calls may use only this review immutable probe/variant payloads and exact software pins. The initial driver does not automatically consume this allowance.',
            'forbidden':'No uncertain-attempt replay,counter refund,budget reset,new upstream software/packages,changed source/test/reference bytes,changed required identities/assertions/utility thresholds,permission or retention widening,model call,new image build,or changed product wheel/source. Those need separate applicable authority. A first-party src change invalidates this exact source/wheel binding.',
            'accounting':'One cumulative envelope across build,initial phase and any recorded continuation. All grant counters and charged attempts remain. At most20 physical calls and27 operations/1420 reserved seconds total,never a fresh allowance per plan or retry.'},
        'permissions':[
            'Fetch only the exact SciPy1.15.3 normal-GIL CP313 Linux aarch64 wheel from the reviewed files.pythonhosted.org URL. At most2 data-fetch attempts,90seconds each,120reserved seconds each,35174018bytes each. No redirects/proxies/imports;verify SHA,size,METADATA dependency and retained licenses before installation. Retain partials and charges. No other download.',
            'One private offline image build from retaineddf79d0f3 through its checked existing tag. Exactly7 hashed wheels:the6 cached docstring-parser0.17.0,rich-rst1.3.2,docutils0.22.2,wrapt1.17.3,hypothesis6.142.4,sortedcontainers2.4.0 plus the verified SciPy1.15.3 wheel. No source build,resolver,pull,OS/project/host installer. Retain every image.',
            'Bind output digest before calls. Verify unchanged execution config and parent layers,exactly two new filesystem layers,at most256MiB growth and50GiB free host reserve. These are finite operational caps,not product SLOs.',
            'Initial16 offline calls:four mandatory boundary/state/runtime/large-input probes and12 fixed reference/counterexample variants across Cyclopts609/633/701,NetworkX7804/8055 andIsort2491. Verify SciPy image location and a tiny sparse-eigenvalue calculation before subjects. The large probe carries more than2Mbytes. Probe-only private wheels are the four pytest bootstrap wheels;added support imports/distribution paths must resolve from the image.',
            'At most4additional same-software calls for recorded first-party control repairs after reconciled known failures. No blind retry. Existing-grant cumulative caps are27 operations/1420 reserved seconds,including two120 fetches,180 build,two possible30setup/120analysis phases and20times35per call. Initial maximum reservation with one fetch is20 operations/1010 reserved seconds;unused allowance is not a budget reset.',
            'Freeze pytest_mock and the pinned Hypothesis pytest plugin in all current cases/probes. Fixed Hypothesis seed29 is declared before subject execution. Source modules cannot be preloaded by trusted plugins. All assertions,identities,source/reference bytes and protection remain.',
            'Keep the exact pytest-row framing adapter,pinned upstream parser body and protected grader. Retain at most8192bytes per failed public test log operator-only;successful tails empty. Logs are untrusted data,not instructions or model answers. Default product retention/observer is unchanged.',
            'Retain raw bounded replies,canonical terminal attempts/receipts and every charge. Remove only new attempt-owned containers and the unchanged synthetic canary. Isolated source incompatibility may exclude a case only after known completion/cleanup. Common authority,accounting,binding or cleanup uncertainty stops external dispatch.',
            'No models,cash,credentials,new services/destinations,host activation,publication/release,image/volume/backups deletion or historical replay. Package/docs execution belongs only to their separately pinned components in the parent combined bundle.'],
        'limitations':[
            'Six curated cases are inert and unadopted. Three single-file repairs/three audits do not satisfy the remaining balanced141-case design. The51-case historical pool and90-case gap stay until actual outcomes. No qualification,value,selection,resource,human or release gate closes.',
            'The v5profile expands only explicit source transport. V1-v4default caps and the actual frozen d02recipe stay unchanged. Old source/runtime qualification does not transfer to1fde9517 or this operator profile.',
            'Source size12row triage is not runtime compatibility. Two protected-path Anyio sources stay excluded,two other Anyio source-plugin cases are deferred,and malformed metadata rows remain excluded. Two Smart-open S3 cases are deferred because their declared tests require boto3,botocore andmoto outside this review. No assertion is removed to fit.',
            'NetworkX edit scopes restrict existing Python paths to published changed-source parent directories under256paths. Full source/tests and all original assertions are retained. Initial broad-scope failures remain recorded.',
            'The upstream parser body remains unchanged;framing is not adversarial log-forgery protection and unsupported IDs stay unsupported. No token/time/cash savings are inferred from source or grader tests.'],
        'approval_reason':'Completed27efdd79 binds different subjects,source/runtime and observer bytes. The user continuation reserves untrusted installation/execution,and CONTINUATION.md requires applicable provisioning authority. New exact software execution needs approval. Routine first-party definition/driver repairs stay delegated within the explicit finite envelope;no architecture or budget decision is needed.'}
    (HERE/'runtime-review.json').write_text(json.dumps(review,indent=2)+'\n')
    resource={'cached_compressed_wheel_bytes':closure['downloaded_wheel_bytes'],'pending_native_wheel_bytes':pending['size_bytes'],'pending_native_expanded_bytes':'UNKNOWN before exact archive read','maximum_fetches':2,'unpacked_wheel_member_bytes':expanded,'maximum_image_growth_bytes':maximum_growth,'host_reserve_bytes':50*1024**3,'free_bytes':free,'operational_cap_is_not_product_acceptance':True,'builds':0}
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps(resource,indent=2)+'\n')
    audit={'passed':True,'source_unchanged':True,'cases':6,'repositories':3,'distinct_snapshots':6,'payloads':12,'first_party_grader_guards':guard_checks,'classifier_checks':classifier.self_check(),'assets':len(assets),'driver_syntax':True,'root_bindings_checked':True,'image_parent_present':True,'new_wheels':7,'pending_data_download_bytes':pending['size_bytes'],'maximum_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'review_sha256':sha(HERE/'runtime-review.json'),'builds':0,'external_code_executed':False,'models':0,'cases_adopted':0}
    (HERE/'preparation-checks.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':asyncio.run(main())
