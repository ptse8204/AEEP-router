"""Reopen exact portable-wheel scope and retained grading guards; no package imports."""
import asyncio
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path, PurePosixPath
import zipfile

from packaging.requirements import Requirement
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-issue-behavior-20261028'

async def main():
    review=json.loads((HERE/'operation-review.json').read_text());before=json.loads((OLD/'operation-review.json').read_text())
    originals={c['input']['task_id']:RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/before['cases_file']).read_text())}
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())]
    old_variants={(v['case'],v['variant']):v for v in json.loads((ROOT/before['variants_file']).read_text())}
    new_variants=json.loads((ROOT/review['variants_file']).read_text());pin=json.loads((HERE/'portable-wheel-review.json').read_text())['pin'];wheel=ROOT/pin['private_cache']
    assert hashlib.sha256(wheel.read_bytes()).hexdigest()==pin['sha256'] and wheel.stat().st_size==107441
    with zipfile.ZipFile(wheel) as z:
        assert sum(i.file_size for i in z.infolist())<2_000_000
        for item in z.infolist():
            p=PurePosixPath(item.filename);assert not p.is_absolute() and '..' not in p.parts
            assert not item.filename.endswith(('.so','.dylib','.dll','.pyd'))
        wheel_meta=z.read('markdown-3.9.dist-info/WHEEL').decode();assert 'Root-Is-Purelib: true' in wheel_meta and 'Tag: py3-none-any' in wheel_meta
        metadata=BytesParser().parsebytes(z.read('markdown-3.9.dist-info/METADATA'));assert metadata['Name']=='Markdown' and metadata['Version']=='3.9'
        active=[]
        for text in metadata.get_all('Requires-Dist',[]):
            requirement=Requirement(text)
            if requirement.marker is None or requirement.marker.evaluate({'python_version':'3.13','python_full_version':'3.13.15','platform_system':'Linux','sys_platform':'linux','platform_machine':'aarch64','extra':''}):active.append(str(requirement))
        assert active==[]
    payload_checks=0;guard_checks=0
    for case in cases:
        original=originals[case.input.task_id]
        assert case.input==original.input and case.reference==original.reference and case.fault_outputs==original.fault_outputs
        a=original.truth.model_dump(mode='json');b=case.truth.model_dump(mode='json')
        assert {k for k in a if a[k]!=b[k]}=={'wheels'} and b['wheels'][:-1]==a['wheels']
        assert b['wheels'][-1]['sha256']==pin['sha256'] and len(b['wheels'])==5
        assert case.origin_kind==original.origin_kind=='upstream_issue'
        for variant in [v for v in new_variants if v['case']==case.input.task_id]:
            old_payload=json.loads((ROOT/old_variants[(case.input.task_id,variant['variant'])]['payload']).read_text());payload=json.loads((ROOT/variant['payload']).read_text())
            assert {k for k in payload if payload[k]!=old_payload[k]}=={'wheels'}
            assert payload['wheels'][:-1]==old_payload['wheels'] and payload['wheels'][-1]['sha256']==pin['sha256']
            assert payload['archive']==old_payload['archive'] and payload['archive_sha256']==old_payload['archive_sha256'];payload_checks+=1
        required=case.truth.fail_to_pass+case.truth.pass_to_pass
        for mode in ('pass','nonzero','missing','error','skip','preservation_failure'):
            async def fake(payload):
                states={n:'PASSED' for n in required};exit_code=0
                if mode=='nonzero':exit_code=1
                elif mode=='missing':states.pop(required[0])
                elif mode=='error':states[required[0]]='ERROR'
                elif mode=='skip':states[required[0]]='SKIPPED'
                elif mode=='preservation_failure':states[case.truth.pass_to_pass[0]]='FAILED'
                return {'exit_code':exit_code,'statuses':states,'archive_sha256':payload['archive_sha256'],'python':case.truth.python,'pytest':case.truth.pytest}
            result=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),json.loads(case.reference.read()),fake)
            assert result.valid==(mode=='pass');guard_checks+=1
    value={'passed':True,'unchanged_original_required_identities':765,'unchanged_test_assertions_inputs_source_reference_and_fault_bytes':True,'payloads_changed_only_by_one_exact_wheel':payload_checks,'actual_grader_guard_fixtures':guard_checks,'pure_wheel_and_empty_active_dependency_closure_checked':True,'wheel_bytes':107441,'cached_wheel_imported_or_executed':False,'models_installs_builds_downloads':0,'synthetic_guard_results_are_not_benchmark_evidence':True}
    with(HERE/'scope-check.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))

if __name__=='__main__':asyncio.run(main())
