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
    stability_path=HERE.parent/'repository-worker-input-20261027/validation/source-stability.json'
    stability=json.loads(stability_path.read_text())
    assert stability['all_passed'] and stability['source_unchanged']
    assert verification_source_digest(ROOT)==stability['source_digest']==parent['source_digest']
    assert runtime_dependencies()==before.runtime_dependencies
    metadata=json.loads((HERE/'execution-cases.json').read_text());assert metadata['prepared_cases']==4 and not metadata['errors']
    cases_path,variants_path=ROOT/metadata['cases_file'],ROOT/metadata['variants_file']
    assert sha(cases_path)==metadata['cases_file_sha256']
    cases=[RepositorySuiteCase.model_validate(x) for x in json.loads(cases_path.read_text())]
    variants=json.loads(variants_path.read_text());assert len(cases)==4 and len(variants)==16
    assert len({c.source_repository.casefold() for c in cases})==3
    assert len({(c.source_repository.casefold(),c.source_revision) for c in cases})==4
    assert len({c.input.source_sha256 for c in cases})==4
    development={'delgan/loguru','pallets/click','marshmallow-code/marshmallow','pgmpy/pgmpy'}
    assert not {c.source_repository.casefold().removeprefix('https://github.com/') for c in cases}&development
    closure=json.loads((HERE/'runtime-support-review.json').read_text());assert closure['selected_added_requirements_closed'] and len(closure['pins'])==8
    context=ROOT/'.aeep/repository-multifile-image-20261027';assert context.is_dir()
    expanded=closure['unpacked_wheel_member_bytes']
    for pin in closure['pins']:assert sha(context/pin['filename'])==pin['sha256']
    support=closure['source_support']
    assert sha(context/'untokenize-support/untokenize.py')==support['module_sha256']
    assert sha(context/'untokenize-support/untokenize-0.1.1.dist-info/METADATA')==support['publisher_metadata_sha256']
    reference='aeep-toolkit-v2/repository-grader:py313-large-repositories-20261027'
    maximum_growth=96*1024**2;assert expanded+closure['compressed_wheel_bytes']+closure['upstream_source_copy_bytes']<maximum_growth
    free=shutil.disk_usage(ROOT).free;assert free>50*1024**3+maximum_growth
    inspection=subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',reference],timeout=20)
    image=json.loads(inspection)[0];assert image['Id']==parent['image'] and image['Config'].get('OnBuild') in (None,[])
    assert image['Architecture']=='arm64' and image['Os']=='linux'
    (HERE/'parent-image-inspection.json').write_bytes(inspection)
    (HERE/'docker-usage-pre-review.txt').write_bytes(subprocess.check_output([parent['docker'],'--host',parent['socket'],'system','df'],timeout=20))
    assets={str(p.resolve()):sha(p) for p in [cases_path,variants_path,parent_path,stability_path,*(p for p in context.rglob('*') if p.is_file()),*(HERE/n for n in ('execution-cases.json','runtime-support-review.json','curation-dispositions.json','pyserde-exclusion-detail.json','source-size-review.json','untokenize-source-review.json','runtime-execution/operator_output.py','review-budget.py','parent-image-inspection.json','run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py'))]}
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
    for path in (ROOT/support['module_cache'],ROOT/support['publisher_metadata_path'],ROOT/support['sdist_cache'],*(ROOT/v['path'] for v in support['licenses'])):assets[str(path.resolve())]=sha(path)
    for pin in closure['pins']:
        for license in pin['licenses']:
            path=ROOT/license['retained'];assert sha(path)==license['sha256'];assets[str(path.resolve())]=license['sha256']
        path=ROOT/pin['private_cache'];assets[str(path.resolve())]=pin['sha256']
    for name in ('run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py'):ast.parse((HERE/name).read_text())
    for name in ('run.py','audit-execution.py'):
        assert 'ROOT = HERE.parents[4]' in (HERE/'runtime-execution'/name).read_text()
        assert (HERE/'runtime-execution').resolve().parents[4]==ROOT
    subject=AssessmentSubject(kind='command',location=str(context),dependency_digests=assets,description='One8-wheel private offline image plus unchanged untokenize module/publisher metadata and four semantic multi-file subjects with four mandatory fresh probes. No models or adopted stages.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id='onboarding',seed=82,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    documents={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')}
    for kind,identity,value in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]:documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=parent['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(documents))
    initial_calls=4+len(variants);max_calls=initial_calls+4;max_operations=max_calls+5;max_seconds=180+2*(30+120)+max_calls*35
    assert (max_calls,max_operations,max_seconds)==(24,29,1320)
    previous=json.loads((HERE.parent/'repository-worker-input-20261027/operation-review.json').read_text())
    review={'purpose':'Four genuine multi-file repository repairs on one privately expanded grader image. Four fresh probes and16 fixed variants,plus at most4 bounded same-software report diagnostics. No model task or scientific verdict.',
        'source_digest':parent['source_digest'],'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),
        'parent_review':str(parent_path.relative_to(ROOT)),'parent_review_sha256':sha(parent_path),'authorization_digest':parent['authorization_digest'],
        'assets':assets,'cases_file':metadata['cases_file'],'variants_file':metadata['variants_file'],'active_case_ids':[c.input.task_id for c in cases],'case_summary':metadata['cases'],'variant_labels':labels,'expectations':expectations,
        'parent_reference':reference,'parent_image':parent['image'],'target_tag':'aeep-toolkit-v2/repository-grader:py313-multifile-20261027',
        'build_context':str(context.relative_to(ROOT)),'context_files':sorted(str(p.relative_to(context)) for p in context.rglob('*') if p.is_file()),'build_request':request.model_dump(mode='json'),'build_documents':documents,'build_amendment':amendment.model_dump(mode='json'),'host_canary':parent['host_canary'],
        'maximum_builds':1,'maximum_build_growth_bytes':maximum_growth,'maximum_new_filesystem_layers':3,'initial_contained_calls':initial_calls,'maximum_contained_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'maximum_model_turns':0,'cash_usd':0,'automatic_retry':False,'runtime_dependencies_review':closure,
        'bounded_control_repairs':{**previous['bounded_control_repairs'],'accounting':'One cumulative24call/29operation/1320reserved-second envelope across build,initial phase and any explicitly recorded first-party report continuation. All prior attempts/counters/charges remain;no fresh per-plan allowance.'},
        'permissions':[
            'One private offline image build from retained2386ef22 through its checked local tag. Exactly8 cached hashed wheels:python-can4.6.1,canmatrix1.2,asn1crypto1.5.1,cbor2 5.6.5,pyOpenSSL25.3.0,lxml6.0.2,docformatter1.7.5,toposort1.10. No resolver,downloads,pulls,source build,setup.py,OS/project/host install. Keep all images.',
            'COPY unchanged untokenize0.1.1 module,in-file permission notice and exact upstream sdist PKG-INFO as dist-info METADATA. No invented version,no setup.py or source build;this is an explicitly identified upstream source copy,not a wheel installation. Paths/modes are frozen0644files/0755directories.',
            'Bind output digest before calls. Verify inherited configuration and parent layers,exactly3new filesystem layers,at most96MiB growth and50GiB free host reserve. Finite execution caps are not product resource SLOs.',
            'Initial20offline calls:four mandatory boundary/state/large-frame probes with image-resolved support imports,then16 unchanged reference/counterexample/partial-repair variants for Canopen613,WebAuthn241,Xsdata1126/1132. Retain all125 required identities/assertions and strict missing/error/skip/exit/preservation rejection.',
            'At most4additional same-software diagnostic calls and one additional30setup/120analysis phase for recorded first-party report controls after known terminal completion/cleanup. Maximum29existing-grant operations and1320reserved seconds total:180build,two possible150setup/analysis phases and24times35per call. Initial maximum23operations/1030reserved seconds. No unknown-attempt replay or budget refund.',
            'Reuse the explicit pytest-row framing adapter and unchanged pinned upstream parser. Hypothesis seed29 and common pytest_mock/Hypothesis plugins stay fixed. Retain at most8192bytes per failed public log operator-only;successful tails empty. No model sees or executes these logs.',
            'Keep bounded raw replies,canonical receipts/terminal attempts and every charge. Remove only new owned containers and unchanged synthetic canary. Known isolated source incompatibility may exclude a case;common authority,binding,accounting or cleanup uncertainty stops dispatch.',
            'No models,cash,credentials,new services/destinations,activation,release,publication,image/volume/backups removal or historical replay. No unchanged package/source test rerun. Cached offline docs belongs only to its separately pinned component.'],
        'limitations':[
            'These4cases are inert/unadopted. The initial7-case preparation includes2Pymdown version-bookkeeping false multi-file hints and deferred Pyinfra;those are not counted. Original curation failures/prohibited paths/partial source reads stay recorded.',
            'Local Python3.13 profile differs from published3.9-3.12 benchmark setup. This checks these declared tests under the reviewed local runtime;it is not an official benchmark score or whole-project support claim.',
            'Only actually observed inherited distribution versions close added requirements;no whole inherited inventory claim. No source package is installed from its project tree. Project metadata/entrypoint-dependent sources such as Isort/Pyinfra remain separately excluded.',
            'Ruff CLI and unrelated project extras are not added:the selected Xsdata handler/filter/config tests do not invoke the generator Ruff subprocess. All required upstream assertions remain. Actual compatibility is unknown until executed.',
            'The56-case historical pool retains original bindings and85cases remain. No stage freeze,model qualification,comparative usefulness,selection quality,resource acceptance,human-control or release gate closes. No savings are inferred.'],
        'approval_reason':'Completed4661ce49 covers different subjects and image bytes and permits no new dependencies. The user continuation reserves untrusted execution/installation,and CONTINUATION.md requires applicable image/container provisioning authority. This exact new runtime/software/subject review needs approval. Routine finite definition/budget work remains delegated;no architecture or budget decision is needed.'}
    (HERE/'runtime-review.json').write_text(json.dumps(review,indent=2)+'\n')
    resource={'compressed_wheel_bytes':closure['compressed_wheel_bytes'],'upstream_source_copy_bytes':closure['upstream_source_copy_bytes'],'unpacked_wheel_member_bytes':expanded,'maximum_image_growth_bytes':maximum_growth,'host_reserve_bytes':50*1024**3,'free_bytes':free,'operational_cap_is_not_product_acceptance':True,'builds':0}
    (HERE/'runtime-operation-resource-bound.json').write_text(json.dumps(resource,indent=2)+'\n')
    audit={'passed':True,'source_unchanged':True,'cases':4,'repositories':3,'distinct_snapshots':4,'payloads':16,'first_party_grader_guards':guard_checks,'classifier_checks':classifier.self_check(),'assets':len(assets),'driver_syntax':True,'root_bindings_checked':True,'image_parent_present':True,'new_wheels':8,'unchanged_upstream_source_modules':1,'maximum_calls':max_calls,'maximum_operations':max_operations,'maximum_reserved_seconds':max_seconds,'review_sha256':sha(HERE/'runtime-review.json'),'builds':0,'external_code_executed':False,'models':0,'cases_adopted':0}
    (HERE/'preparation-checks.json').write_text(json.dumps(audit,indent=2)+'\n');print(json.dumps(audit))


if __name__=='__main__':asyncio.run(main())
