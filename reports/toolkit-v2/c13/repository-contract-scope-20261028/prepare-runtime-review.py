"""Freeze issue-scoped definitions on the retained runtime; no subject execution."""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase, grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-multifile-sources-20261027'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

async def main():
    assert not (HERE/'operation-review.json').exists()
    source=verification_source_digest(ROOT)
    stable=HERE.parent/'repository-worker-input-20261027/validation/source-stability.json'
    assert json.loads(stable.read_text())['all_passed'] and json.loads(stable.read_text())['source_digest']==source
    prior=json.loads((OLD/'runtime-review.json').read_text())
    parent=json.loads((HERE/'observer-envelope.json').read_text())
    before=RecipeMaterializationRequest.model_validate(parent['request'])
    assert source==parent['source_digest']==prior['source_digest']
    assert before.runtime_dependencies==runtime_dependencies()
    env=AssessmentEnvironment.model_validate(next(v['document'] for v in parent['documents'].values() if v['kind']=='environment'))
    assert env.container_image==parent['image']=='sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
    reuse=parent['current_containment_reuse'];audit=ROOT/reuse['manifest']
    assert sha(audit)==reuse['manifest_sha256'] and json.loads(audit.read_text())['physical_receipt_integrity_passed']
    assert len(reuse['completed_probe_receipts'])==4
    prepared=json.loads((HERE/'execution-cases.json').read_text())
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/prepared['cases_file']).read_text())]
    variants=json.loads((ROOT/prepared['variants_file']).read_text())
    assert len(cases)==3 and len(variants)==11 and sum(x['required_tests'] for x in prepared['cases'])==117
    assets=dict(prior['assets'])
    paths=[HERE/'observer-envelope.json',HERE/'scope-review.json',HERE/'execution-cases.json',HERE/'prepare-cases.py',HERE/'preparation-correction.json',stable,audit,OLD/'final-accounting-audit.json',OLD/'build-result.json',ROOT/reuse['manifest'],ROOT/prepared['cases_file'],ROOT/prepared['variants_file']]
    checks=0;expectations={};labels={}
    for case in cases:
        paths.extend(Path(x.path) for x in (case.truth.source,case.truth.tests,case.reference,*case.truth.wheels))
        required=list(case.truth.fail_to_pass)+list(case.truth.pass_to_pass)
        expectations[case.input.task_id]={};labels[case.input.task_id]=[]
        for variant in [v for v in variants if v['case']==case.input.task_id]:
            paths.append(ROOT/variant['payload']);captured=[]
            class Captured(Exception):pass
            async def capture(payload):captured.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest());raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),variant['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Inert transport check returned a grade')
            assert captured==[variant['sha256']];checks+=1
            label=variant['variant'];labels[case.input.task_id].append(label)
            if case.input.task_id.startswith('tefra'):
                expected=prior['expectations'][case.input.task_id][label]
            elif label in ('reference','counterexample'):
                expected=prior['expectations']['duo-labs__py_webauthn-241-declared-tests'][label]
            else:
                assert label=='preservation-fault'
                expected={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{n:'PASSED' for n in case.truth.fail_to_pass},'at_least_one_failed':list(case.truth.pass_to_pass)}
            expectations[case.input.task_id][label]={**expected,'required_identities':required}
    for n in ('run-runtime.py','run.py','audit-execution.py','classify.py','operator_output.py','review-budget.py'):
        ast.parse((HERE/n).read_text());paths.append(HERE/n)
    for p in paths:assets[str(p.resolve())]=sha(p)
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    subject=AssessmentSubject(kind='command',location=str((ROOT/prepared['cases_file']).parent),dependency_digests=assets,description='SafetyNet-only contract and explicit existing Xsdata benchmark plugin;one fresh plugin probe plus eleven fixed variants. No install,build,download or model.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=before.environment_digest,authorization_id='onboarding',seed=113,definition_digests=before.definition_digests,runtime_dependencies=before.runtime_dependencies)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    docs={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')};docs.update(new)
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=prior['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[before.environment_digest],reviewed_digests=list(docs))
    review={'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'authorization_digest':prior['authorization_digest'],'assets':assets,'cases_file':prepared['cases_file'],'variants_file':prepared['variants_file'],'active_case_ids':[c.input.task_id for c in cases],'case_summary':prepared['cases'],'expectations':expectations,'variant_labels':labels,'host_canary':parent['host_canary'],'parent_review':str((HERE/'observer-envelope.json').relative_to(ROOT)),'parent_review_sha256':sha(HERE/'observer-envelope.json'),'driver_files':{n:sha(HERE/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},'request':request.model_dump(mode='json'),'new_documents':new,'reviewed_document_digests':list(docs),'amendment':amendment.model_dump(mode='json'),'probes':parent['probes'],'current_containment_reuse':reuse,'parent_image':env.container_image,'initial_contained_calls':12,'maximum_contained_calls':16,'maximum_operations':20,'maximum_reserved_seconds':860,'maximum_model_turns':0,'cash_usd':0,'maximum_builds':0,'maximum_downloads':0,
        'bounded_control_repairs':{**prior['bounded_control_repairs'],'accounting':'One cumulative20operation/860reserved-second/16call envelope:16times35seconds plus at most two30setup/120analysis phases. Initial12calls/14operations/570reservedseconds. All earlier charges remain;no allowance refund or uncertain replay.'},
        'permissions':['Use only retained9f473c49 with identical source374579f1,observer,bootstrap wheels and permissions. Reuse the four completed current-image boundary/state/runtime probes bound by receipt;one fresh explicit benchmark-plugin/config probe and eleven fixed variants are mandatory. No image build,pull,install or download.',
            'SafetyNet-only input restricts edits to the issue target. Restore both original authentication assertions;all11 required identities remain. Both Xsdata cases keep exact source/reference/tests and28/78identities;enable only installed pytest_benchmark.plugin. Old failures and legitimate partial outcomes remain unchanged.',
            'Maximum16offline calls,20existing-grant operations and860reservedseconds,zero models/cash. Keep50GiB host reserve and all images. Remove only new owned containers and unchanged canary. Retain up to8192bytes of failed public logs,raw replies,canonical receipts,terminal failures and all charges.',
            'Up to4extra calls and one additional setup/analysis phase cover only recorded first-party report-control corrections using these immutable payloads/software after known completion/cleanup. No uncertain replay,source/test/reference/plugin/identity change,threshold relaxation,permission widening or allowance reset. Common authority,identity,accounting or cleanup uncertainty stops dispatch.'],
        'limitations':['Engineering grader checks,not model qualification,comparative usefulness,selection or resource acceptance. Pool57 and84case gap remain until actual evidence.','No source/package regression or installation rerun. Existing13source gates and19installed checks retain their current bindings.'],
        'approval_reason':'Terminalad0adfcf binds the old multi-file oracle and explicit plugin payloads. New issue scope/protected test overlay and plugin launch bytes need exact execution authority under the user continuation and CONTINUATION.md. No architecture,budget,dependency,image or core-source decision is needed.'}
    assert shutil.disk_usage(ROOT).free>50*1024**3
    assert subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',env.container_image,'--format','{{.Id}}'],timeout=20).decode().strip()==env.container_image
    save(HERE/'operation-review.json',review)
    save(HERE/'preparation-checks.json',{'passed':True,'source_digest':source,'all13_source_gates_reused':True,'payload_derivations':checks,'fresh_plugin_probes':1,'completed_probes_reused':4,'retained_image_present':True,'asset_bindings':len(assets),'driver_syntax':True,'no_external_execution_or_models':True,'review_sha256':sha(HERE/'operation-review.json')})
    print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'payloads':checks,'executed':False}))

if __name__=='__main__':asyncio.run(main())
