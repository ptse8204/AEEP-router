"""Check exact issue/oracle/plugin changes and grader guards without execution."""
import asyncio
import copy
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, archive_files, _decode_suite_patch, grade_suite_output

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-multifile-sources-20261027'

async def main():
    review=json.loads((HERE/'operation-review.json').read_text())
    prior=json.loads((OLD/'runtime-review.json').read_text())
    old={c['input']['task_id']:c for c in json.loads((ROOT/prior['cases_file']).read_text())}
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/review['cases_file']).read_text())]
    checks=0;case_records=[]
    for case in cases:
        original=RepositorySuiteCase.model_validate(old[case.input.task_id if case.input.task_id.startswith('tefra') else 'duo-labs__py_webauthn-241-declared-tests'])
        assert case.truth.source==original.truth.source
        assert case.truth.fail_to_pass==original.truth.fail_to_pass and case.truth.pass_to_pass==original.truth.pass_to_pass
        if case.input.task_id.startswith('tefra'):
            assert case.input==original.input and case.reference==original.reference and case.truth.tests==original.truth.tests
            before=original.truth.model_dump(mode='json');after=case.truth.model_dump(mode='json')
            assert {k for k in before if before[k]!=after[k]}=={'pytest_plugins'}
            assert after['pytest_plugins']==[*before['pytest_plugins'],'pytest_benchmark.plugin']
            source=archive_files(case.truth.source.read(),large=True)
            assert b'--benchmark-skip' in source['pyproject.toml']
        else:
            assert case.input.family=='single-file-repair' and case.input.editable_paths==['webauthn/registration/formats/android_safetynet.py']
            source=archive_files(case.truth.source.read(),large=True)
            before=archive_files(original.truth.tests.read(),large=True);after=archive_files(case.truth.tests.read(),large=True)
            name='tests/test_verify_authentication_response.py'
            assert set(before)==set(after) and {n for n in before if before[n]!=after[n]}=={name}
            assert after[name]==source[name]
            assert after[name].count(b'assert not verification.user_verified')==1 and after[name].count(b'assert verification.user_verified')==1
            gold=_decode_suite_patch(original.truth,json.loads(original.reference.read()))
            scoped=_decode_suite_patch(case.truth,json.loads(case.reference.read()))
            assert scoped.base_sha256==content_digest(case.input) and scoped.files=={case.input.editable_paths[0]:gold.files[case.input.editable_paths[0]]}
        required=case.truth.fail_to_pass+case.truth.pass_to_pass
        assert len(required)==len(set(required))
        artifact=json.loads(case.reference.read())
        # Exercise the actual grader with synthetic replies, never upstream code.
        for mode in ('pass','nonzero','missing','error','skip','preservation_failed'):
            async def fake(payload):
                statuses={n:'PASSED' for n in required};exit_code=0
                if mode=='nonzero':exit_code=1
                elif mode=='missing':statuses.pop(required[0])
                elif mode=='error':statuses[required[0]]='ERROR'
                elif mode=='skip':statuses[required[0]]='SKIPPED'
                elif mode=='preservation_failed':statuses[case.truth.pass_to_pass[0]]='FAILED'
                return {'exit_code':exit_code,'statuses':statuses,'archive_sha256':payload['archive_sha256'],'python':case.truth.python,'pytest':case.truth.pytest}
            grade=await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),artifact,fake)
            assert grade.valid==(mode=='pass');checks+=1
        case_records.append({'case':case.input.task_id,'required_identities':len(required),'unchanged_source_and_required_identities':True,'scope_and_overlay_checked':True})
    result={'passed':True,'cases':case_records,'actual_grader_guards':checks,'xsdata_option_and_all_assertions_preserved':True,'webauthn_issue_scope_preserves_original_auth_assertions':True,'subject_execution_or_models':0,'synthetic_grades_are_not_benchmark_evidence':True}
    (HERE/'scope-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))

if __name__=='__main__':asyncio.run(main())
