"""Prepare first-party execution drivers and inert v4/probe data; no subjects run."""
import base64
import copy
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-supported-suites-20261027'


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')
def change(text,old,new):
    assert old in text, old[:100]
    return text.replace(old,new)
def pack(files):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w:gz',format=tarfile.USTAR_FORMAT) as t:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name);info.size=len(data);info.mode=0o444;t.addfile(info,io.BytesIO(data))
    return out.getvalue()


def main():
    out=HERE/'runtime-execution';out.mkdir(exist_ok=False)
    for name in ('review-budget.py','runtime-execution/classify.py'):
        shutil.copyfile(OLD/name,HERE/name)
    text=(OLD/'run-bundle.py').read_text().replace('approval-bundle.json','runtime-review.json')
    text=change(text,"{path.name for path in context.iterdir()}","{str(path.relative_to(context)) for path in context.rglob('*') if path.is_file()}")
    text=change(text,"len(parent['RootFS']['Layers']) + 2","len(parent['RootFS']['Layers']) + 3")
    (HERE/'run-bundle.py').write_text(text)
    text=(OLD/'derive-execution.py').read_text().replace('approval-bundle.json','runtime-review.json').replace('repository-supported-runtime-20261027','repository-rooted-runtime-20261027').replace('Six provisional tasks','Eight provisional tasks').replace('twenty offline calls','twenty-three offline calls')
    (HERE/'derive-execution.py').write_text(text)
    text=(OLD/'runtime-execution/run.py').read_text().replace("HERE.parent / 'approval-bundle.json'","HERE.parent / 'runtime-review.json'")
    text=change(text,'from classify import discrepancies','from classify import discrepancies\nfrom operator_output import evaluation')
    text=change(text,'            return output\n','            return evaluation(output)\n')
    (out/'run.py').write_text(text)
    text=(OLD/'runtime-execution/audit-execution.py').read_text()
    text=change(text,'from classify import discrepancies','from classify import discrepancies\nfrom operator_output import evaluation')
    text=change(text,"raw_by_name[item['name']] = raw['output']","raw_by_name[item['name']] = evaluation(raw['output']) if raw['output'] is not None else None")
    (out/'audit-execution.py').write_text(text)
    # One shared fail-closed wrapper is used by the live driver and independent audit.
    (out/'operator_output.py').write_text('''"""Unwrap exactly the approved public-test envelope, preserving stock evaluation."""
import base64

def evaluation(output):
    if not isinstance(output,dict) or set(output)!={'evaluation','failure_log_tail_b64'}:
        raise ValueError('Operator observer envelope mismatch')
    value=output['evaluation']
    if not isinstance(value,dict) or set(value)!={'exit_code','statuses','archive_sha256','python','pytest'}:
        raise ValueError('Stock evaluation mismatch')
    tail=base64.b64decode(output['failure_log_tail_b64'],validate=True)
    if len(tail)>8192 or (value['exit_code']==0 and tail):
        raise ValueError('Public failure tail exceeds retention authority')
    return value
''')
    # Both child files are pinned along with every other execution driver.
    text=(HERE/'derive-execution.py').read_text().replace("('run.py', 'classify.py', 'audit-execution.py')","('run.py', 'classify.py', 'audit-execution.py', 'operator_output.py')")
    (HERE/'derive-execution.py').write_text(text)
    original=json.loads((OLD/'observer-envelope.json').read_text())
    cases=json.loads((ROOT/'.aeep/repository-compact-patches-20261022-envelope/cases.json').read_text())
    for case in cases:
        case['schema_version']='assessment.repository-suite-case.v4';case['truth']['test_roots']=['tests']
    data=ROOT/'.aeep/repository-test-roots-envelope-20261027';data.mkdir(exist_ok=False)
    save(data/'cases.json',cases)
    recipe=repository_suite_recipe([RepositorySuiteCase.model_validate(c) for c in cases])
    program=(HERE/'operator-observer.py').read_text()
    for spec in (recipe.extension.generator,recipe.extension.reference,recipe.extension.grader):
        spec.config['argv']=['python3','-B','-c',program]
    recipe.dependencies['program']=hashlib.sha256(program.encode()).hexdigest()
    recipe.recipe_id='repository-operator-curation-'+content_digest(recipe)[:16]
    deps=runtime_dependencies();binding=RecipeRuntimeBinding(dependencies=deps)
    previous_environment=next(x['document'] for x in original['documents'].values() if x['kind']=='environment')
    environment=AssessmentEnvironment.model_validate({**previous_environment,'environment_id':'repository-rooted-parent-20261027','identity':{'source_digest':verification_source_digest(ROOT),'purpose':'Operator-only source reproduction; no campaign/model authority'},'container_image':'sha256:f60342e9c6a50933353ebea047b89935c75579541cf628f4fe4d15a1c0515e93'})
    documents={}
    for kind,identity,value in [('recipe',recipe.recipe_id,recipe),('environment',environment.environment_id,environment),('recipe_runtime',content_digest(binding),binding)]:
        documents[content_digest(value)]={'kind':kind,'id':identity,'document':value.model_dump(mode='json')}
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=original['request']['subject_digest'],recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(environment),authorization_id='onboarding',seed=88,definition_digests=list(documents),runtime_dependencies=deps)
    canary='.aeep/repository-test-roots-envelope-20261027/host-canary'
    support=json.loads((HERE/'runtime-support-review.json').read_text());jsonpath=json.loads((HERE/'jsonpath-source-review.json').read_text())
    probe_append='\n\ndef test_rooted_runtime_supports():\n    import importlib.metadata,hashlib,jsonpath_rw\n    from pathlib import Path\n    expected='+repr({p['project']:p['version'] for p in support['pins']})+'\n    for name,version in expected.items():\n        assert importlib.metadata.version(name)==version\n    assert jsonpath_rw.__version__=="1.3.0"\n    base=Path(jsonpath_rw.__file__).parent\n'
    for p in jsonpath['library_files_identical_to_license_commit']:
        probe_append+='    assert hashlib.sha256((base/'+repr(p['file'].removeprefix('jsonpath_rw/'))+').read_bytes()).hexdigest()=='+repr(p['sha256'])+'\n'
    probe_append+='    assert hashlib.sha256((base/"LICENSE.source").read_bytes()).hexdigest()=='+repr(jsonpath['license_sha256'])+'\n'
    probes=copy.deepcopy(original['probes'])
    for probe in probes:
        payload=probe['payload']
        with tarfile.open(fileobj=io.BytesIO(base64.b64decode(payload['archive'])),mode='r:gz') as t:
            files={m.name:t.extractfile(m).read() for m in t if m.isfile()}
        for name in files:
            files[name]=files[name].replace(original['host_canary'].encode(),canary.encode())
        if probe['name']=='boundary':files['tests/test_boundary.py']+=probe_append.encode()
        archive=pack(files);payload['archive']=base64.b64encode(archive).decode();payload['archive_sha256']=hashlib.sha256(archive).hexdigest()
        probe['archive_sha256']=payload['archive_sha256'];probe['payload_sha256']=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
    save(HERE/'observer-envelope.json',{'source_digest':verification_source_digest(ROOT),'recipe':recipe.model_dump(mode='json'),'request':request.model_dump(mode='json'),'documents':documents,'authorization_digest':original['authorization_digest'],'image':environment.container_image,'docker':original['docker'],'socket':original['socket'],'host_canary':canary,'probes':probes,'external_execution':False,'old_conformance_applies_to_new_source':False,'profile':'Operator-only bounded public failure context; stock default observer is unchanged','fresh_boundary_state_runtime_probes_required':True})
    meta=json.loads((HERE/'prepared-cases.json').read_text())
    selected=[c for c in json.loads((ROOT/meta['cases_file']).read_text()) if 'sopel' not in c['source_repository'].lower()]
    ids={c['input']['task_id'] for c in selected};variants=[v for v in json.loads((ROOT/meta['variants_file']).read_text()) if v['case'] in ids]
    save(data/'active-cases.json',selected);save(data/'active-variants.json',variants)
    selected_meta={**meta,'prepared_cases':len(selected),'payloads':len(variants),'cases_file':str((data/'active-cases.json').relative_to(ROOT)),'cases_file_sha256':sha(data/'active-cases.json'),'variants_file':str((data/'active-variants.json').relative_to(ROOT)),'cases':[c for c in meta['cases'] if c['id'] in ids],'errors':[],'excluded_inert_case':'Sopel2653 needs incompatible SQLAlchemy1.4 and installed project metadata/plugin; no downgrade/installer requested.'}
    save(HERE/'execution-cases.json',selected_meta)
    print(json.dumps({'active_cases':len(selected),'payloads':len(variants),'source':verification_source_digest(ROOT),'external_code_executed':False}))


if __name__=='__main__':main()
