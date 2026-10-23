"""Exercise deterministic derivation on an explicitly synthetic, removed fixture."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile

from aeep.assessment.models import AssessmentEnvironment,RecipeDefinition,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output
from aeep.assessment.verification import verification_source_digest
import asyncio

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[3]


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


async def main():
    bundle=json.loads((HERE/'approval-bundle.json').read_text())
    assert verification_source_digest(ROOT)==bundle['source_digest']
    for name,expected in bundle['assets'].items(): assert sha(Path(name))==expected
    cases=[RepositorySuiteCase.model_validate(value) for value in json.loads((ROOT/bundle['cases_file']).read_text())]
    variants=json.loads((ROOT/bundle['variants_file']).read_text())
    assert len(cases)==8 and len(variants)==22
    from collections import Counter
    assert Counter(case.input.family for case in cases)=={'single-file-repair':3,'multi-file-repair':3,'contract-audit':2}
    payloads=0
    for case in cases:
        for item in (value for value in variants if value['case']==case.input.task_id):
            class Captured(Exception):pass
            async def capture(payload):
                nonlocal payloads
                assert hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()==item['sha256']
                assert len(json.dumps(payload,separators=(',',':')).encode())<2_000_000
                payloads+=1
                raise Captured()
            try: await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),item['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Static capture returned an external grade')
    spec=importlib.util.spec_from_file_location('reviewed_derivation_fixture',HERE/'derive-execution.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory(prefix='synthetic-derivation-only-',dir=ROOT/'.aeep') as temporary:
        fixture=Path(temporary);out=fixture/'runtime-execution';out.mkdir()
        (fixture/'approval-bundle.json').write_bytes((HERE/'approval-bundle.json').read_bytes())
        fixture_digest=sha(fixture/'approval-bundle.json')
        (fixture/'operator-approval.json').write_text(json.dumps({'approved':True,'review_sha256':fixture_digest,
            'synthetic_fixture_only':True,'authority':'NONE. Fabricated first-party software test fixture; not an actual operator response.'}))
        image='sha256:'+'0'*64
        (fixture/'build-result.json').write_text(json.dumps({'passed':True,'parent_review_sha256':fixture_digest,
            'image_id':image,'synthetic_fixture_only':True}))
        for name in ('run.py','classify.py'):(out/name).write_bytes((HERE/'runtime-execution'/name).read_bytes())
        module.HERE=fixture;module.OUT=out;module.ROOT=ROOT
        module.main()
        derived=json.loads((out/'operation-review.json').read_text())
        parent=json.loads((out/'parent-runtime-review.json').read_text())
        request=RecipeMaterializationRequest.model_validate(derived['request'])
        environment=AssessmentEnvironment.model_validate(next(value['document'] for value in parent['documents'].values() if value['kind']=='environment'))
        assert environment.container_image==image and request.environment_digest==content_digest(environment)
        assert (derived['maximum_contained_calls'],derived['maximum_operations'],derived['maximum_reserved_seconds'])==(25,27,1025)
        assert (bundle['maximum_operations'],bundle['maximum_reserved_seconds'])==(28,1205)
        assert sum(len(value) for value in derived['variant_labels'].values())==22
        assert sum(name.startswith('partial-') for values in derived['variant_labels'].values() for name in values)==6
        recipe=RecipeDefinition.model_validate(parent['recipe'])
        assert request.recipe_digest==content_digest(recipe)
        program='\n'.join([(ROOT/'integrations/assessment-runtime/swe_rebench_pytest_parser.py').read_text(),
            (ROOT/'integrations/assessment-runtime/repository_suite_plugins_program.py').read_text()])
        assert recipe.dependencies['program']==hashlib.sha256(program.encode()).hexdigest()
        assert len(derived['probes'])==3 and all(isinstance(item['payload'],dict) for item in derived['probes'])
        assert all(item['payload']['pytest_plugins']==['pytest_mock'] for item in derived['probes'])
        for item in derived['probes']:
            assert hashlib.sha256(json.dumps(item['payload'],separators=(',',':')).encode()).hexdigest()==item['payload_sha256']
        assert json.loads((out/'operator-approval.json').read_text())['synthetic_fixture_only']
    assert not fixture.exists()
    for name in ('run-bundle.py','derive-execution.py','runtime-execution/run.py','runtime-execution/audit-execution.py'):
        ast.parse((HERE/name).read_text())
    result={'passed':True,'payloads_regenerated_and_verified':payloads,'family_counts':dict(Counter(case.input.family for case in cases)),
        'assets_verified':len(bundle['assets']),'derived_current_program_and_image_binding':True,
        'probe_payloads_are_actual_objects':True,'three_explicit_plugin_probes':True,
        'synthetic_fixture_removed':True,'synthetic_approval_is_not_human_authority':True,
        'external_code_executed':False,'real_image_built':False,'real_container_started':False,'canonical_operations':0,
        'review_sha256':sha(HERE/'approval-bundle.json')}
    (HERE/'static-bundle-audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':asyncio.run(main())
