"""Version the inert replacement metadata; keep the earlier v1 draft untouched."""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, SuiteTruthV2, archive_files, decode_patch, grade_suite_output, patch_artifact, repository_suite_recipe
from aeep.assessment.repository_tasks import RepositoryPatch

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]
OUT=ROOT/'.aeep/repository-replacement-runtime-20261022-v5'


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    prior=json.loads((HERE/'prepared-cases.json').read_text())
    original=ROOT/prior['cases_file']
    assert sha(original)==prior['cases_file_sha256']
    OUT.mkdir(exist_ok=False)
    cases=[RepositorySuiteCase.model_validate(item) for item in json.loads(original.read_text())]
    variants=json.loads((ROOT/prior['variants_file']).read_text())
    assert len(cases)==2 and len(variants)==4
    completed=HERE.parent/'repository-screening-curation-20261022'
    eligible=json.loads((completed/'completion-audit.json').read_text())['eligible_cases']
    eligible=[name for name in eligible if name not in ('fox-it__dissect.cstruct-120','kaste__mockito-python-93')]
    prior_screen=json.loads((completed/'prepared-cases.json').read_text())
    screen_cases=[RepositorySuiteCase.model_validate(item) for item in json.loads((ROOT/prior_screen['cases_file']).read_text()) if item['input']['task_id'] in eligible]
    assert len(screen_cases)==4
    additional=json.loads((HERE/'prepared-additional-cases.json').read_text())
    added_cases=[RepositorySuiteCase.model_validate(item) for item in json.loads((ROOT/additional['cases_file']).read_text())]
    cases=[*screen_cases,*cases,*added_cases]
    previous_variants=json.loads((ROOT/prior_screen['variants_file']).read_text())
    variants=[*[item for item in previous_variants if item['case'] in eligible],*variants,*json.loads((ROOT/additional['variants_file']).read_text())]
    summaries=[*[item for item in prior_screen['cases'] if item['id'] in eligible],*prior['cases'],*additional['cases']]
    for case in cases:
        if case.input.task_id=='AbsaOSS__generate-release-notes-207':
            value=case.model_dump(mode='json')
            value['schema_version']='assessment.repository-suite-case.v2'
            value['truth']=SuiteTruthV2(**case.truth.model_dump(),pytest_plugins=['pytest_mock']).model_dump(mode='json')
            value['provenance']+=' Version2 explicitly loads pytest_mock3.15.0 from the separately reviewed image; autoload remains disabled. Exact SDK/runtime closure is private, frozen and offline. Original v1 draft remains unexecuted.'
            case=RepositorySuiteCase.model_validate(value)
            cases[cases.index(next(item for item in cases if item.input.task_id==case.input.task_id))]=case
        if case.input.task_id=='oOo0oOo__leanclient-24':
            value=case.model_dump(mode='json')
            value['provenance']+=' Source-only scope retains the full leanclient and tests trees and root license/packaging/README, excluding unrelated docs/examples/CI. Full upstream archive and every omitted file are retained in diagnostic-source-scope-review.json. This is not the full upstream checkout or official runtime.'
            case=RepositorySuiteCase.model_validate(value)
            cases[cases.index(next(item for item in cases if item.input.task_id==case.input.task_id))]=case
        if case.input.family=='multi-file-repair':
            files=archive_files(case.truth.source.read())
            reference=decode_patch(json.loads(case.reference.read()))
            assert len(reference.files)==2
            for index,name in enumerate(sorted(reference.files),1):
                altered={**reference.files,name:files[name].decode()}
                artifact=patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input),files=altered))
                variants.append({'case':case.input.task_id,'variant':'partial-'+str(index),'artifact':artifact,
                    'regressed_file':name,'expectation':'invalid/test_failure; all required identities observed, preservation passed and at least one bug test failed'})
        for staged in (item for item in variants if item['case']==case.input.task_id):
            class Captured(Exception): pass
            async def capture(payload):
                path=OUT/(case.input.task_id+'-'+staged['variant']+'-payload.json')
                path.write_text(json.dumps(payload,separators=(',',':')))
                staged.update(payload=str(path.relative_to(ROOT)),sha256=sha(path),bytes=path.stat().st_size)
                raise Captured()
            try:
                await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),staged['artifact'],capture)
            except Captured: pass
            else: raise AssertionError('Inert preparation returned a grade')
    cases_file=OUT/'cases.json';cases_file.write_text(json.dumps([case.model_dump(mode='json') for case in cases],indent=2)+'\n')
    (OUT/'variants.json').write_text(json.dumps(variants,indent=2)+'\n')
    development=[RepositorySuiteCase.model_validate(item) for item in json.loads((ROOT/'.aeep/repository-suite-integration-20261022-v2/protected/cases.json').read_text())]
    # The ordinary development recipe refuses campaign cases. Preserve that rule:
    # this is a v2 observer envelope, not adoption/materialization of the new cases.
    first=development[0].model_dump(mode='json')
    first['schema_version']='assessment.repository-suite-case.v2'
    first['truth']=SuiteTruthV2(**development[0].truth.model_dump(),pytest_plugins=['pytest_mock']).model_dump(mode='json')
    first['provenance']+=' New explicit-plugin development envelope only. This changed runtime has not executed this development case; previous conformance is not transferred.'
    development[0]=RepositorySuiteCase.model_validate(first)
    recipe=repository_suite_recipe(development)
    (OUT/'recipe.json').write_text(recipe.model_dump_json(indent=2)+'\n')
    combined=OUT/'observer-development-cases.json';combined.write_text(json.dumps([case.model_dump(mode='json') for case in development],indent=2)+'\n')
    result={**prior,'prepared_cases':len(cases),'cases':summaries,'previous_unexecuted_v1_cases_file':prior['cases_file'],
        'cases_file':str(cases_file.relative_to(ROOT)),'cases_file_sha256':sha(cases_file),
        'variants_file':str((OUT/'variants.json').relative_to(ROOT)),
        'recipe_file':str((OUT/'recipe.json').relative_to(ROOT)),
        'observer_development_cases_file':str(combined.relative_to(ROOT)),
        'recipe_scope':'Three development cases bind the v2 observer envelope only. Eight qualification-labelled candidates are separate pre-adoption inputs; no split is relabelled and no campaign cases are materialized.',
        'runtime_recheck':'Four cases retain prior reproduction evidence only for the old image/observer. Recheck them alongside four replacements on one current runtime. Dissect.cstruct and Mockito test outcomes remain historical, but their nominal multi-file classifications are rejected.',
        'independence':'Eight distinct screening-candidate repositories, excluding Loguru, Click, Marshmallow and pgmpy development origins. Four are current-runtime rechecks and four are new replacements. No final stage freeze or model outcome selection.',
        'recipe_sha256':sha(OUT/'recipe.json'),
        'explicit_plugins':{'AbsaOSS__generate-release-notes-207':['pytest_mock']},
        'payloads':[{key:value for key,value in item.items() if key!='artifact'} for item in variants]}
    (HERE/'prepared-plugin-cases.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'cases':len(cases),'payloads':len(variants),'external_execution':False,'recipe_id':recipe.recipe_id}))


if __name__=='__main__': asyncio.run(main())
