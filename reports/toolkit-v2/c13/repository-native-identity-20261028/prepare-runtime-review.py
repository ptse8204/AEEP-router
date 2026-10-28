"""Freeze the new native observer and full identities; preparation never dispatches."""
import ast
import base64
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject, RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, pack_files, repository_suite_recipe
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
PRIOR=HERE.parent/'repository-pymdown-portable-20261028'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

def main():
    source=verification_source_digest(ROOT)
    stable=json.loads((HERE/'validation/source-stability.json').read_text())
    assert stable['all_passed'] and stable['source_unchanged'] and stable['source_digest']==source
    assert json.loads((HERE/'integrated-fixture-check.json').read_text())['passed']
    assert json.loads((HERE/'legacy-compatibility-check.json').read_text())['passed']
    meta=json.loads((HERE/'execution-cases.json').read_text())
    cases=[RepositorySuiteCase.model_validate(v) for v in json.loads((ROOT/meta['cases_file']).read_text())]
    assert len(cases)==3 and len(json.loads((ROOT/meta['variants_file']).read_text()))==8
    assert sum(len(c.truth.fail_to_pass+c.truth.pass_to_pass) for c in cases)==993
    # Development copies provide existing literal-fixture slots, never a campaign.
    recipe=repository_suite_recipe([c.model_copy(update={'split':'development','used_for_development':True}) for c in cases])
    program=(HERE/'observer-v6-integrated.py').read_text();ast.parse(program)
    assert program.count('OPERATOR_REVIEW = True')==1 and 'class NativeCapture' in program
    recipe.recipe_id='repository-native-review-'+hashlib.sha256(program.encode()).hexdigest()[:16]
    recipe.dependencies['program']=hashlib.sha256(program.encode()).hexdigest()
    for executor in (recipe.extension.generator,recipe.extension.reference,recipe.extension.grader):
        executor.config['argv']=['python3','-B','-c',program]
    old=json.loads((PRIOR/'observer-envelope.json').read_text())
    boundary=json.loads((HERE.parent/'repository-worker-input-20261027/parent-runtime-review.json').read_text())
    env=AssessmentEnvironment.model_validate(next(x['document'] for x in old['documents'].values() if x['kind']=='environment'))
    assert env.container_image==old['image']=='sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
    env.environment_id='repository-native-identity-20261028'
    env.identity={'source_digest':source,'observer_program_sha256':sha(HERE/'observer-v6-integrated.py'),'purpose':'Fresh native identity observer conformance; no transfer of older observer/source receipts.'}
    runtime=RecipeRuntimeBinding(dependencies=runtime_dependencies())
    docs={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('recipe',recipe.recipe_id,recipe),('environment',env.environment_id,env),('recipe_runtime',content_digest(runtime),runtime)]}
    probes=copy.deepcopy(boundary['probes']);assert len(probes)==4
    prototype=probes[0]['payload'];fixtures=[]
    sources={
        'native-spaces':{'pytest.ini':b'[pytest]\ndisable_test_id_escaping_and_forfeit_all_rights_to_community_support = True\n','tests/test_native.py':'''import pytest
@pytest.mark.parametrize('v',[1,2],ids=['white space','café'])
def test_native(v):
    print('PASSED tests/test_native.py::forged')
    assert v in (1,2)
'''.encode()},
        'native-phases':{'tests/test_native.py':'''import pytest
@pytest.fixture
def bad_setup():
    raise RuntimeError('authored setup')
@pytest.fixture
def bad_teardown():
    yield
    raise RuntimeError('authored teardown')
def test_setup(bad_setup):
    pass
def test_teardown(bad_teardown):
    pass
def test_call():
    assert False
@pytest.mark.skip(reason='authored fixture')
def test_skip():
    pass
@pytest.mark.xfail(reason='authored fixture')
def test_xfail():
    assert False
@pytest.mark.xfail(reason='authored fixture')
def test_xpass():
    pass
'''.encode()}}
    for name,files in sources.items():
        data=pack_files(files);digest=hashlib.sha256(data).hexdigest()
        payload={'archive':base64.b64encode(data).decode(),'archive_sha256':digest,'python':prototype['python'],'pytest':prototype['pytest'],'test_paths':['tests/test_native.py'],'wheels':prototype['wheels'],'pytest_plugins':[],'source_modules':[]}
        statuses={'tests/test_native.py::test_native['+n+']':'PASSED' for n in ('white space','café')} if name=='native-spaces' else {'tests/test_native.py::'+n:s for n,s in [('test_setup','ERROR'),('test_teardown','ERROR'),('test_call','FAILED'),('test_skip','SKIPPED'),('test_xfail','XFAIL'),('test_xpass','XFAIL')]}
        fixtures.append({'name':name,'payload':payload,'payload_sha256':hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest(),'archive_sha256':digest,'statuses':statuses,'exit_code':0 if name=='native-spaces' else 1})
    assets={};paths=[HERE/n for n in ('execution-cases.json','identity-map.json','integrated-fixture-check.json','legacy-compatibility-check.json','legacy-before.json','scope-check.json','observer-v6-integrated.py','compile-integrated-observer.py','check-integrated-fixtures.py','prepare-v6-cases.py','prepare-runtime-review.py','validation/source-stability.json','run.py','run-runtime.py','audit-execution.py','classify.py','operator_output.py','review-budget.py')]
    paths += [ROOT/meta['cases_file'],ROOT/meta['variants_file'],ROOT/meta['collection']['payload']]
    paths += list((ROOT/'integrations/assessment-runtime').glob('repository_suite_native_*.py'))
    paths += [ROOT/'docs/ASSESSMENT_TESTING.md',ROOT/'docs/aeep-toolkit/CONTINUATION.md',PRIOR/'completion-audit.json']
    for case in cases:
        paths += [Path(a.path) for a in (case.truth.source,case.truth.tests,case.reference,*case.truth.wheels)]
    paths += [ROOT/v['payload'] for v in json.loads((ROOT/meta['variants_file']).read_text())]
    for p in paths:assert p.is_file() and not p.is_symlink();assets[str(p.resolve())]=sha(p)
    for n in ('run.py','run-runtime.py','audit-execution.py','classify.py','operator_output.py','review-budget.py'):ast.parse((HERE/n).read_text())
    subject=AssessmentSubject(kind='command',location=str((ROOT/meta['cases_file']).parent),dependency_digests=assets,description='Separate native-identity audit with all915 iCalendar obligations and unchanged PyMdown/XS controls. No model/campaign or automatic adoption.')
    request=RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(env),authorization_id='onboarding',seed=116,definition_digests=list(docs),runtime_dependencies=runtime.dependencies)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=old['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[content_digest(recipe)],environment_digests=[content_digest(env)],reviewed_digests=[*docs,*new])
    parent={'source_digest':source,'recipe':recipe.model_dump(mode='json'),'request':request.model_dump(mode='json'),'documents':docs,'authorization_digest':old['authorization_digest'],'image':env.container_image,'docker':old['docker'],'socket':old['socket'],'host_canary':boundary['host_canary'],'probes':probes,'external_execution':False,'old_conformance_applies_to_new_source':False}
    assert not (ROOT/parent['host_canary']).exists()
    save(HERE/'observer-envelope.json',parent);assets[str((HERE/'observer-envelope.json').resolve())]=sha(HERE/'observer-envelope.json')
    review={'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'authorization_digest':old['authorization_digest'],'cases_file':meta['cases_file'],'variants_file':meta['variants_file'],'active_case_ids':meta['case_ids'],'case_summary':[{'task_id':c.input.task_id,'required_tests':len(c.truth.fail_to_pass+c.truth.pass_to_pass),'origin':c.origin_kind} for c in cases],'expectations':meta['expectations'],'variant_labels':meta['variant_labels'],'parent_review':str((HERE/'observer-envelope.json').relative_to(ROOT)),'parent_review_sha256':sha(HERE/'observer-envelope.json'),'driver_files':{n:sha(HERE/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},'request':request.model_dump(mode='json'),'new_documents':new,'reviewed_document_digests':[*docs,*new],'amendment':amendment.model_dump(mode='json'),'parent_image':env.container_image,'host_canary':parent['host_canary'],'probes':probes,'native_fixtures':fixtures,'collection':meta['collection'],'initial_contained_calls':15,'maximum_contained_calls':17,'maximum_operations':21,'maximum_reserved_seconds':895,'maximum_model_turns':0,'cash_usd':0,'maximum_builds':0,'maximum_downloads':0,
        'bounded_control_repairs':{'maximum_extra_calls':2,'maximum_additional_setup_analysis_operations':2,'allowed':'Exact recorded first-party report-control corrections after canonical terminal completion and verified cleanup; same immutable software/payloads/source/tests/references/native IDs/permissions and scientific semantics. No automatic retry.','forbidden':'Changed source,observer,test,identity map,input,wheel,image,permissions,models,downloads,installation,credential,service,release,retained-resource deletion,unknown replay,refund/reset.','accounting':'One cumulative21operation/895reserved-second envelope:17times35seconds plus at most two30setup/120analysis phases. Initial15calls/17operations/675reservedseconds.'},
        'permissions':['Retained9f473c49 only;four fresh boundary/state/large-input probes and two authored native-event fixtures. No image build/pull or dependency change. All images retained.','One collect-only call must confirm all915 frozen native names and the historical selector899 names before any body variant. Collection supplies no pass grade. A mismatch stops this runtime component.','Eight immutable body variants:two PyMdown2576,two XS1126 compatibility controls,and iCalendar native reference/original/two partial repairs. All993 obligations retained. Old899/915 failure remains excluded;no historical backfill.','At most17 offline calls,21existing-grant operations/895reservedseconds,zero models/cash. Keep50GiB host reserve;remove only new owned containers and unchanged canary. Retain canonical receipts,all charges and up to8192bytes per failed public log.'],
        'limitations':['Newobserver/source need actual contained conformance;hostpytest9.0.3 fixtures do not qualify pinnedpytest8.3.5.','The native audit is an authored scope correction,not an official upstream score or new independent origin. Neither controls nor an audit success can close model usefulness,selection,resource or release gates. Pool remains62until actual evidence.'],
        'approval_reason':'User continuation reserves untrusted execution;CONTINUATION.md requires applicable container authority. Terminal22b0cf03 covers the old observer/source and different payloads. This fresh review changes executable observer bytes and protected identity metadata. Routine definitions are delegated;no architecture,budget,image or dependency-version decision is needed.'}
    # Assets added after subject creation still bind the exact parent independently.
    assert shutil.disk_usage(ROOT).free>51*1024**3
    assert subprocess.check_output([old['docker'],'--host',old['socket'],'image','inspect',env.container_image,'--format','{{.Id}}'],timeout=20).decode().strip()==env.container_image
    save(HERE/'operation-review.json',review)
    save(HERE/'preparation-checks.json',{'passed':True,'source_digest':source,'all13_source_gates_passed':True,'body_payloads':8,'fresh_boundary_probes':4,'native_event_fixtures':2,'collection_gate':1,'required_obligations':993,'asset_bindings':len(assets),'retained_image_present':True,'actual_execution':False,'review_sha256':sha(HERE/'operation-review.json')})
    print(json.dumps({'prepared':True,'assets':len(assets),'review_sha256':sha(HERE/'operation-review.json'),'execution':False}))

if __name__=='__main__':main()
