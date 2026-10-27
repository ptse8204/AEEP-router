"""Prepare an explicit larger-input execution profile; no build or subject runs."""
import asyncio
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import random
import shutil
import tarfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output,pack_files,repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-effective-runtime-20261027'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')


async def main():
    stable=json.loads((HERE/'validation/source-stability.json').read_text());assert stable['all_passed'] and stable['source_digest']==verification_source_digest(ROOT)
    out=HERE/'runtime-execution';out.mkdir(exist_ok=False)
    for name in ('run-bundle.py','derive-execution.py','review-budget.py','runtime-execution/run.py','runtime-execution/audit-execution.py','runtime-execution/classify.py','runtime-execution/operator_output.py'):
        shutil.copyfile(OLD/name,HERE/name)
    p=HERE/'derive-execution.py';p.write_text(p.read_text().replace('repository-effective-runtime-20261027','repository-large-runtime-20261027').replace('Six provisional tasks','Eight provisional tasks').replace('nineteen offline calls','twenty offline calls'))
    # Mocker is part of the existing image. Freeze both explicit common plugins
    # before subject execution; retain the earlier inert metadata separately.
    meta=json.loads((HERE/'execution-cases.json').read_text());save(HERE/'hypothesis-only-inert-cases.json',meta)
    cases=json.loads((ROOT/meta['cases_file']).read_text());old_variants=json.loads((ROOT/meta['variants_file']).read_text())
    directory=ROOT/'.aeep/repository-large-execution-cases-20261027';directory.mkdir(exist_ok=False);variants=[]
    for data in cases:
        data['truth']['pytest_plugins']=['pytest_mock','_hypothesis_pytestplugin'];case=RepositorySuiteCase.model_validate(data)
        for old in [v for v in old_variants if v['case']==case.input.task_id]:
            class Captured(Exception):pass
            async def capture(payload):
                path=directory/(case.input.task_id+'-'+old['variant']+'.json');path.write_text(json.dumps(payload,separators=(',',':')))
                variants.append({**old,'payload':str(path.relative_to(ROOT)),'sha256':sha(path),'bytes':path.stat().st_size});raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),old['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Inert payload capture returned a grade')
    save(directory/'cases.json',cases);save(directory/'variants.json',variants)
    meta.update(cases_file=str((directory/'cases.json').relative_to(ROOT)),cases_file_sha256=sha(directory/'cases.json'),variants_file=str((directory/'variants.json').relative_to(ROOT)))
    for row in meta['cases']:row['explicit_plugins']=['pytest_mock','_hypothesis_pytestplugin']
    (HERE/'execution-cases.json').write_text(json.dumps(meta,indent=2)+'\n')
    previous=json.loads((OLD/'runtime-execution/parent-runtime-review.json').read_text())
    develop=json.loads((ROOT/'.aeep/repository-compact-patches-20261022-envelope/cases.json').read_text())
    for c in develop:c['schema_version']='assessment.repository-suite-case.v5';c['truth'].update(test_roots=['tests'],archive_profile='repository-v1',pytest_plugins=['pytest_mock','_hypothesis_pytestplugin'])
    save(directory/'development-cases.json',develop)
    recipe=repository_suite_recipe([RepositorySuiteCase.model_validate(c) for c in develop]);program=(HERE/'operator-observer.py').read_text()
    for role in (recipe.extension.generator,recipe.extension.reference,recipe.extension.grader):role.config['argv']=['python3','-B','-c',program]
    recipe.dependencies['program']=sha(HERE/'operator-observer.py');recipe.recipe_id='repository-large-profile-'+content_digest(recipe)[:16]
    runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies())
    environment=AssessmentEnvironment.model_validate(next(x['document'] for x in previous['documents'].values() if x['kind']=='environment'))
    environment.environment_id='repository-large-parent-20261027';environment.identity={'source_digest':verification_source_digest(ROOT),'purpose':'New larger-input source and optional runtime profile; no qualification transfer'}
    docs={}
    for kind,identity,value in [('recipe',recipe.recipe_id,recipe),('recipe_runtime',content_digest(runtime),runtime),('environment',environment.environment_id,environment)]:docs[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=previous['request']['subject_digest'],recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(environment),authorization_id='onboarding',seed=90,definition_digests=list(docs),runtime_dependencies=runtime.dependencies)
    canary='.aeep/repository-large-execution-cases-20261027/host-canary';probes=copy.deepcopy(previous['probes'])
    pins=json.loads((HERE/'runtime-support-review.json').read_text())['pins'];versions={p['project']:p['version'] for p in pins}
    imports=['docstring_parser','rich_rst','docutils','wrapt','hypothesis','sortedcontainers']
    append='\n\ndef test_added_runtime_and_seed(pytestconfig):\n    import importlib.metadata\n    from pathlib import Path\n    import '+','.join(imports)+'\n    expected='+repr(versions)+'\n    for name,version in expected.items():\n        dist=importlib.metadata.distribution(name)\n        assert dist.version==version\n        assert str(dist.locate_file(""))=="/usr/local/lib/python3.13/site-packages"\n    for module in ('+','.join(imports)+'):\n        assert Path(module.__file__).is_relative_to("/usr/local/lib/python3.13/site-packages")\n    assert str(pytestconfig.getoption("hypothesis_seed"))=="29"\n'
    for probe in probes:
        payload=probe['payload'];payload['pytest_plugins']=['pytest_mock','_hypothesis_pytestplugin']
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload['archive'])),mode='r:gz') as archive:files={m.name:archive.extractfile(m).read() for m in archive if m.isfile()}
        for name in files:files[name]=files[name].replace(previous['host_canary'].encode(),canary.encode())
        if probe['name']=='boundary':files['tests/test_boundary.py']+=append.encode()
        encoded=pack_files(files,large=True);payload['archive']=base64.b64encode(encoded).decode();payload['archive_sha256']=hashlib.sha256(encoded).hexdigest();probe['archive_sha256']=payload['archive_sha256'];probe['payload_sha256']=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
    blob=random.Random(9027).randbytes(1_600_000);blob_sha=hashlib.sha256(blob).hexdigest()
    test=('from pathlib import Path\nimport hashlib\n\ndef test_large_transport():\n    data=(Path(__file__).resolve().parents[1]/"public-fixture.bin").read_bytes()\n    assert len(data)==1600000\n    assert hashlib.sha256(data).hexdigest()=='+repr(blob_sha)+'\n').encode()
    encoded=pack_files({'public-fixture.bin':blob,'tests/test_large_transport.py':test},large=True)
    payload={**probes[0]['payload'],'archive':base64.b64encode(encoded).decode(),'archive_sha256':hashlib.sha256(encoded).hexdigest(),'test_paths':['tests/test_large_transport.py']}
    size=len(json.dumps(payload,separators=(',',':')).encode());assert 2_000_000<size<6_970_000
    probes.append({'name':'large_transport','payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),'archive_sha256':payload['archive_sha256'],'expected_node':'tests/test_large_transport.py::test_large_transport'})
    save(HERE/'observer-envelope.json',{'source_digest':verification_source_digest(ROOT),'recipe':recipe.model_dump(mode='json'),'request':request.model_dump(mode='json'),'documents':docs,'authorization_digest':previous['authorization_digest'],'image':environment.container_image,'docker':previous['docker'],'socket':previous['socket'],'host_canary':canary,'probes':probes,'external_execution':False,'old_conformance_applies_to_new_source':False,'profile':'Explicit larger source profile,Hypothesis seed29,pytest framing and four mandatory fresh probes'})
    save(HERE/'operator-observer-review.json',{'operator_program_sha256':sha(HERE/'operator-observer.py'),'upstream_parser_body_unchanged':program.startswith((ROOT/'integrations/assessment-runtime/swe_rebench_pytest_parser.py').read_text()+'\n'),'explicit_plugins':['pytest_mock','_hypothesis_pytestplugin'],'property_test_seed':29,'default_product_observer_changed':False,'maximum_failed_public_log_bytes':8192,'large_probe_payload_bytes':size,'actual_subject_or_probe_execution':False,'new_profile_qualification':'NOT_ASSESSED'})
    print(json.dumps({'cases':len(cases),'variants':len(variants),'mandatory_fresh_probes':len(probes),'large_probe_bytes':size,'largest_subject_payload':max(v['bytes'] for v in variants),'new_installs_or_builds':0}))


if __name__=='__main__':asyncio.run(main())
