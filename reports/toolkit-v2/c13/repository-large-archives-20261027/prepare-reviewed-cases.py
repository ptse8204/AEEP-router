"""Merge inert cases, bind the fixed property-test seed and retain old failures."""
import asyncio
from collections import Counter
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


async def main():
    reports=[json.loads((HERE/n).read_text()) for n in ('prepared-cases.json','networkx-scoped-cases.json')]
    cases=[];descriptions=[];variants=[]
    out=ROOT/'.aeep/repository-large-reviewed-cases-20261027';out.mkdir(exist_ok=False)
    for report in reports:
        old_variants=json.loads((ROOT/report['variants_file']).read_text())
        for raw,description in zip(json.loads((ROOT/report['cases_file']).read_text()),report['cases'],strict=True):
            # The fixed upstream Hypothesis pytest plugin is common to the grader
            # profile. It does not become a candidate capability or model tool.
            raw['truth']['pytest_plugins']=['_hypothesis_pytestplugin']
            case=RepositorySuiteCase.model_validate(raw);cases.append(raw)
            descriptions.append({**description,'explicit_plugins':['_hypothesis_pytestplugin'],'property_test_seed':29})
            for old in [v for v in old_variants if v['case']==case.input.task_id]:
                class Captured(Exception):pass
                async def capture(payload):
                    target=out/(case.input.task_id+'-'+old['variant']+'.json')
                    target.write_text(json.dumps(payload,separators=(',',':')))
                    variants.append({**old,'payload':str(target.relative_to(ROOT)),'sha256':sha(target),'bytes':target.stat().st_size})
                    raise Captured()
                try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),old['artifact'],capture)
                except Captured:pass
                else:raise AssertionError('Inert capture returned a grade')
    assert len(cases)==8 and len(variants)==16
    save(out/'cases.json',cases);save(out/'variants.json',variants)
    save(HERE/'execution-cases.json',{'prepared_cases':8,'cases_file':str((out/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha(out/'cases.json'),'variants_file':str((out/'variants.json').relative_to(ROOT)),'cases':descriptions,'errors':[],'payloads':16,'external_code_executed':False,'models':0,'cases_adopted':0,'stages_frozen':False})
    old=HERE.parent/'repository-supported-suites-20261027/observer-envelope.json'
    frozen=json.loads(old.read_text())['recipe']['generator_config']['cases']
    legacy=repository_suite_recipe([RepositorySuiteCase.model_validate(c) for c in frozen])
    expected='d02cb9538fe9a42470612f799912b7907c3b72ffd6a8ab0c42661b22e3ab4b0f'
    assert content_digest(legacy)==expected
    save(HERE/'legacy-compatibility.json',{'passed':True,'retained_recipe_digest':expected,'rebuilt_recipe_digest':content_digest(legacy),'actual_legacy_recipe_digest_unchanged':True,'old_mapping_and_stdin_limits_preserved_by_focused_tests':True,'historical_qualification_transferred':False,'source_digest':verification_source_digest(ROOT)})
    save(HERE/'curation-findings.json',{'initial_local_syntax_error':'An overly broad import-string replacement also changed an embedded guard literal; corrected before the script parsed or any case was prepared. Initial failure log retained.','initial_networkx_static_failures':reports[0]['errors'],'networkx_scope_resolution':'Keep full source/tests and assertions; limit editable files to changed-source parent directories,within existing256path cap. Separate scoped materialization retained;initial failures unchanged.','deferred':['Two Anyio sources contain protected paths and stay excluded. Two other Anyio cases need source-plugin/target-namespace review;not executed or included.','Pdoc806 and NetworkX8369 metadata fail conservative identity/test-root checks;IDs not repaired.'],'external_subject_execution':False})
    print(json.dumps({'cases':len(cases),'payloads':len(variants),'largest_payload_bytes':max(v['bytes'] for v in variants),'families':dict(Counter(c['input']['family'] for c in cases)),'source_digest':verification_source_digest(ROOT),'legacy_recipe_unchanged':True,'subject_execution':False}))


if __name__=='__main__':asyncio.run(main())
