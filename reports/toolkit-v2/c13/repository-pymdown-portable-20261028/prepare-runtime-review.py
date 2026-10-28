"""Freeze the exact pending portable-wheel execution; do not dispatch or install."""
import ast
import asyncio
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.models import AssessmentEnvironment,AssessmentSubject,AssessmentScopeAmendment,RecipeMaterializationRequest,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-issue-behavior-20261028'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')

async def main():
    assert not (HERE/'operation-review.json').exists()
    source=verification_source_digest(ROOT);stable=HERE.parent/'repository-worker-input-20261027/validation/source-stability.json'
    assert json.loads(stable.read_text())['all_passed'] and json.loads(stable.read_text())['source_digest']==source
    old=json.loads((OLD/'operation-review.json').read_text());parent=json.loads((HERE/'observer-envelope.json').read_text())
    prior=RecipeMaterializationRequest.model_validate(parent['request']);env=AssessmentEnvironment.model_validate(next(v['document'] for v in parent['documents'].values() if v['kind']=='environment'))
    assert source==old['source_digest']==parent['source_digest'] and env.container_image==parent['image']=='sha256:9f473c493b7af1854922807d2acbdcbe3b955313dc57f203e6f73c9c50f9ea85'
    meta=json.loads((HERE/'execution-cases.json').read_text());cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/meta['cases_file']).read_text())];variants=json.loads((ROOT/meta['variants_file']).read_text())
    assert len(cases)==2 and len(variants)==4 and sum(d['required_tests'] for d in meta['cases'])==765
    assets=dict(old['assets']);paths=[HERE/'observer-envelope.json',HERE/'execution-cases.json',HERE/'portable-wheel-review.json',HERE/'prepare-cases.py',stable,OLD/'runtime-location-audit.json',OLD/'final-accounting-audit.json',OLD/'control-continuation/completion-audit.json',ROOT/meta['cases_file'],ROOT/meta['variants_file']]
    pin=json.loads((HERE/'portable-wheel-review.json').read_text())['pin']
    for item in pin['licenses']:
        p=ROOT/item['retained'];assert sha(p)==item['sha256'];paths.append(p)
    checks=0;expectations={};labels={}
    for case in cases:
        required=case.truth.fail_to_pass+case.truth.pass_to_pass;expectations[case.input.task_id]={};labels[case.input.task_id]=[]
        paths.extend(Path(a.path) for a in (case.truth.source,case.truth.tests,case.reference,*case.truth.wheels))
        for variant in [v for v in variants if v['case']==case.input.task_id]:
            paths.append(ROOT/variant['payload']);captured=[]
            class Captured(Exception):pass
            async def capture(payload):captured.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest());raise Captured()
            try:await grade_suite_output(case.input.model_dump(mode='json'),case.truth.model_dump(mode='json'),variant['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Inert preparation returned a grade')
            assert captured==[variant['sha256']];checks+=1;label=variant['variant'];labels[case.input.task_id].append(label)
            if label=='reference':expected={'exit_code':0,'valid':True,'detail':'','statuses':{n:'PASSED' for n in required}}
            else:
                assert label=='counterexample';expected={'exit_code':1,'valid':False,'detail':'test_failure','statuses':{**{n:'PASSED' for n in case.truth.pass_to_pass},**{n:'FAILED' for n in case.truth.fail_to_pass}}}
            expectations[case.input.task_id][label]={**expected,'required_identities':required}
    for n in ('run.py','audit-execution.py','classify.py','operator_output.py','review-budget.py','run-runtime.py'):
        ast.parse((HERE/n).read_text());paths.append(HERE/n)
    for p in paths:assets[str(p.resolve())]=sha(p)
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    subject=AssessmentSubject(kind='command',location=str((ROOT/meta['cases_file']).parent),dependency_digests=assets,description='Two unchanged pending PyMdown single-file subjects with exact cached Markdown3.9 ZIP-wheel added to private payloads;fresh origin/behavior probe and four variants. No install,build,download,models or source/package rerun.')
    request=RecipeMaterializationRequest(schema_version=prior.schema_version,subject_digest=content_digest(subject),recipe_digest=prior.recipe_digest,mapping_digest=prior.mapping_digest,environment_digest=prior.environment_digest,authorization_id='onboarding',seed=115,definition_digests=prior.definition_digests,runtime_dependencies=prior.runtime_dependencies)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    docs={k:v for k,v in parent['documents'].items() if v['kind'] in ('recipe','environment','recipe_runtime')};docs.update(new)
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=old['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[prior.recipe_digest],environment_digests=[prior.environment_digest],reviewed_digests=list(docs))
    review={'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'authorization_digest':old['authorization_digest'],'assets':assets,'cases_file':meta['cases_file'],'variants_file':meta['variants_file'],'active_case_ids':[c.input.task_id for c in cases],'case_summary':meta['cases'],'expectations':expectations,'variant_labels':labels,'host_canary':parent['host_canary'],'parent_review':str((HERE/'observer-envelope.json').relative_to(ROOT)),'parent_review_sha256':sha(HERE/'observer-envelope.json'),'driver_files':{n:sha(HERE/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},'request':request.model_dump(mode='json'),'new_documents':new,'reviewed_document_digests':list(docs),'amendment':amendment.model_dump(mode='json'),'probes':parent['probes'],'current_containment_reuse':parent['current_containment_reuse'],'benchmark_plugin_reuse':parent['benchmark_plugin_reuse'],'parent_image':env.container_image,'initial_contained_calls':5,'maximum_contained_calls':7,'maximum_operations':11,'maximum_reserved_seconds':545,'maximum_model_turns':0,'cash_usd':0,'maximum_builds':0,'maximum_downloads':0,
        'bounded_control_repairs':{'maximum_extra_calls':2,'maximum_additional_setup_analysis_operations':2,'allowed':'After known canonical completion/cleanup,record exact first-party report-control repairs preserving all reviewed software/payload/source/test/reference/identity/permission/scientific semantics. At most two fresh diagnostics may use only these immutable payloads. Initial driver does not automatically retry.','forbidden':'No changed software/test/reference/input/required identity,permission widening,installation,image build,pull,download,model,cash,credential,service,activation,release,retained-resource deletion,unknown-attempt replay,refund or reset.','accounting':'One new exact additional envelope,not a reset:7times35seconds plus at most two30setup/120analysis phases=545seconds;7calls+4phase operations=11. Initial5calls/7operations/325reservedseconds. All prior13operations and24.90588324982673seconds remain charged.'},
        'permissions':['Use only retained9f473c49,current source374579f1,unchanged observer and boundary. ZIP-load one exact107441byte cached pure Markdown3.9 wheel in the private probe and both PyMdown payloads through the existing wheel loader. No installer,image mutation,download or host/project installation.','One fresh version,ZIP-origin,module-hash and behavior probe;four reference/original variants. All765original identities/assertions,source/input/protected tests/reference/fault bytes and existing plugins stay unchanged.','Maximum7offline calls,11existing-grant operations,545reservedseconds,zero models/cash. Keep50GiB host reserve and all images. Remove only new owned containers and unchanged canary;retain all receipts,terminal failures/charges and failed public log tails up to8192bytes.','At most2extra calls and one extra setup/analysis phase cover only exact recorded first-party report controls after known completion/cleanup with immutable payloads/software. Common identity/accounting/cleanup/authority uncertainty stops dispatch;no automatic retry or allowance refund.'],
        'limitations':['Runtime-only correction for two unstarted subjects;no historical failure is rewritten. Markdown cache presence was not installed inventory.','Engineering grader checks,not model qualification,comparative usefulness,selection or resource acceptance. Pool60 and81case gap remain until actual evidence.','All13source gates and19installed checks remain current;no unchanged source/package verification is repeated.'],
        'approval_reason':'Terminalf18daa4a and its explicitly permitted report-control continuation bind payloads without Markdown. Adding exact cached software bytes to the private ZIP-loader payload requires new execution authority under the user continuation and CONTINUATION.md. No architecture,budget,image,dependency-version,installation or core-source decision is needed.'}
    assert shutil.disk_usage(ROOT).free>51*1024**3
    assert subprocess.check_output([parent['docker'],'--host',parent['socket'],'image','inspect',env.container_image,'--format','{{.Id}}'],timeout=20).decode().strip()==env.container_image
    save(HERE/'operation-review.json',review);save(HERE/'preparation-checks.json',{'passed':True,'source_digest':source,'all13_source_gates_reused':True,'payload_derivations':checks,'fresh_portable_probe':1,'asset_bindings':len(assets),'image_present':True,'driver_syntax':True,'no_actual_execution':True,'review_sha256':sha(HERE/'operation-review.json')})
    print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'payloads':checks,'executed':False}))

if __name__=='__main__':asyncio.run(main())
