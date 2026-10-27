"""Freeze the corrected source with unchanged tasks/tests/image; never dispatch."""
import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import AssessmentEnvironment,AssessmentScopeAmendment,AssessmentSubject,RecipeMaterializationRequest,RecipeRuntimeBinding,content_digest
from aeep.assessment.repository_suites import RepositorySuiteCase,grade_suite_output
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-large-archives-20261027'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def save(path,value):
    with path.open('x') as f:json.dump(value,f,indent=2);f.write('\n')

async def main():
    assert not (HERE/'operation-review.json').exists()
    stable=json.loads((HERE/'validation/source-stability.json').read_text());assert stable['all_passed'] and stable['source_unchanged']
    source=verification_source_digest(ROOT);assert source==stable['source_digest']
    prior=json.loads((OLD/'runtime-review.json').read_text());old_parent=json.loads((OLD/'runtime-execution/parent-runtime-review.json').read_text());parent=copy.deepcopy(old_parent)
    assert json.loads((OLD/'initial-failure-reconciliation.json').read_text())['uncertain_attempts']==0
    assert json.loads((OLD/'independent-execution-result.json').read_text())['all_components_passed']
    before=RecipeMaterializationRequest.model_validate(parent['request']);current_runtime=runtime_dependencies()
    changed={p for p in set(current_runtime)|set(before.runtime_dependencies) if current_runtime.get(p)!=before.runtime_dependencies.get(p)}
    assert changed=={str(ROOT/'src/aeep/assessment/container_worker.py'),str(ROOT/'src/aeep/assessment/containment.py')}
    old_runtime_digest=next(k for k,v in parent['documents'].items() if v['kind']=='recipe_runtime')
    runtime=RecipeRuntimeBinding(dependencies=current_runtime);runtime_digest=content_digest(runtime)
    env=AssessmentEnvironment.model_validate(next(x['document'] for x in parent['documents'].values() if x['kind']=='environment'))
    assert env.container_image=='sha256:2386ef223e39b5dc12e6d8cdbaa6ac9779753f13ee74dc51e8d207279edae91f'
    env.environment_id='repository-worker-input-20261027';env.identity={'source_digest':source,'purpose':'Fresh inner-worker input-limit correction;earlier3 probes do not qualify this source.'}
    digest=content_digest(env);parent['documents']={k:v for k,v in parent['documents'].items() if v['kind']=='recipe'}
    parent['documents'][runtime_digest]={'kind':'recipe_runtime','id':runtime_digest,'document':runtime.model_dump(mode='json')}
    parent['documents'][digest]={'kind':'environment','id':env.environment_id,'document':env.model_dump(mode='json')}
    parent['request']['environment_digest']=digest
    parent['request']['definition_digests']=[digest if d==before.environment_digest else runtime_digest if d==old_runtime_digest else d for d in before.definition_digests]
    parent['source_digest']=source;parent['external_execution']=False;parent['request']['runtime_dependencies']=current_runtime
    # Same immutable probe payloads,including the formerly failed2.7MB fixture.
    # Their old canary location is reused only after verified removal.
    assert len(parent['probes'])==4
    save(HERE/'parent-runtime-review.json',parent)
    assets=dict(prior['assets'])
    for path in [HERE/'parent-runtime-review.json',HERE/'validation/source-stability.json',OLD/'initial-failure-reconciliation.json',OLD/'independent-execution-result.json',OLD/'build-result.json',OLD/'wheel-fetch-result.json',OLD/'licenses/scipy/LICENSE.txt',*(HERE/n for n in ('run-runtime.py','run.py','audit-execution.py','classify.py','operator_output.py','review-budget.py'))]:assets[str(path.resolve())]=sha(path)
    cases=[RepositorySuiteCase.model_validate(c) for c in json.loads((ROOT/prior['cases_file']).read_text())];variants=json.loads((ROOT/prior['variants_file']).read_text())
    assert len(cases)==6 and len(variants)==12 and [c.input.task_id for c in cases]==prior['active_case_ids']
    checks=0
    for c in cases:
        for variant in [v for v in variants if v['case']==c.input.task_id]:
            captured=[]
            class Captured(Exception):pass
            async def capture(payload):captured.append(hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest());raise Captured()
            try:await grade_suite_output(c.input.model_dump(mode='json'),c.truth.model_dump(mode='json'),variant['artifact'],capture)
            except Captured:pass
            else:raise AssertionError('Inert transport check returned a grade')
            assert captured==[variant['sha256']];checks+=1
    for path,expected in assets.items():assert Path(path).is_file() and not Path(path).is_symlink() and sha(Path(path))==expected
    for name in ('run-runtime.py','run.py','audit-execution.py','classify.py','operator_output.py','review-budget.py'):ast.parse((HERE/name).read_text())
    subject=AssessmentSubject(kind='command',location=str((ROOT/prior['cases_file']).parent),dependency_digests=assets,description='Six unchanged repository subjects on corrected worker framing;four fresh exact probes. No build,install,download or model.')
    request=RecipeMaterializationRequest(schema_version=before.schema_version,subject_digest=content_digest(subject),recipe_digest=before.recipe_digest,mapping_digest=before.mapping_digest,environment_digest=digest,authorization_id='onboarding',seed=94,definition_digests=parent['request']['definition_digests'],runtime_dependencies=current_runtime)
    new={content_digest(v):{'kind':kind,'id':identity,'document':v.model_dump(mode='json')} for kind,identity,v in [('subject',subject.subject_id,subject),('recipe_materialization_request',request.plan_id,request)]}
    documents={**parent['documents'],**new}
    amendment=AssessmentScopeAmendment(authorization_id='onboarding',authorization_digest=prior['authorization_digest'],subject_digests=[content_digest(subject)],recipe_digests=[before.recipe_digest],environment_digests=[digest],reviewed_digests=list(documents))
    review={k:prior[k] for k in ('cases_file','variants_file','active_case_ids','case_summary','expectations','variant_labels','authorization_digest','host_canary')}
    review.update(source_digest=source,source_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),assets=assets,parent_review=str((HERE/'parent-runtime-review.json').relative_to(ROOT)),parent_review_sha256=sha(HERE/'parent-runtime-review.json'),driver_files={n:sha(HERE/n) for n in ('run.py','audit-execution.py','classify.py','operator_output.py')},request=request.model_dump(mode='json'),new_documents=new,reviewed_document_digests=list(documents),amendment=amendment.model_dump(mode='json'),probes=parent['probes'],maximum_operations=24,maximum_reserved_seconds=1000,maximum_contained_calls=20,maximum_model_turns=0,cash_usd=0,initial_contained_calls=16,maximum_builds=0,maximum_downloads=0,parent_image=env.container_image,
        bounded_control_repairs={**prior['bounded_control_repairs'],'accounting':'One cumulative24operation/1000reserved-second/20call envelope across this fresh initial phase and any recorded control continuation. Prior8operations and failed probe remain charged;no refund/replay authority transfers.'},
        permissions=['Use only the retained2386ef22 image. No runtime install,download,build,pull or image deletion. Four fresh unchanged probes and12 unchanged reference/counterexample payloads;up to4 additional same-software diagnostic calls for recorded first-party controls after known canonical completion/cleanup.',
            'Cumulative maximum24 existing-grant operations and1000reserved seconds:two possible30setup/120analysis phases plus20times35per contained call. No models/cash/credentials/services/activation/release. Keep50GiB host reserve and all images.',
            'The worker receives an explicit operator-owned input-limit argv. Default2MB launches retain their old argv. Candidate/task data cannot set it. Missing IDs,errors,skips,nonzero reference exits and preservation failures still reject tasks.',
            'Canonical FAILED attempts with complete terminal evidence and absent containers remain failed observations;their known completion is not called uncertain or accepted as task success. Common unresolved accounting/identity/cleanup stops dispatch. Retain8192byte failed public log tails,raw replies,all receipts and every charge.'],
        limitations=['Same6case bytes and scientific contracts;new source is not qualified by old probes. No subject ran in the terminal preceding bundle.','This is engineering grader reproduction,not model qualification,usefulness,selection or resource acceptance. The51-case pool and90-case gap remain.'],
        approval_reason='The prior explicit control-repair allowance excludes product-source/wheel changes. Correcting the inner worker changes source374579f1 and the executable wheel. A fresh exact approval is required;no architecture,budget,dependency or image decision is needed.')
    assert shutil.disk_usage(ROOT).free>51*1024**3
    image=json.loads(subprocess.check_output(['/usr/local/bin/docker','--host','unix:///Users/edwintse/.docker/run/docker.sock','image','inspect',env.container_image],timeout=20))[0];assert image['Id']==env.container_image
    save(HERE/'operation-review.json',review);save(HERE/'preparation-checks.json',{'passed':True,'source_digest':source,'all13_source_gates_passed':True,'unchanged_payload_derivations':checks,'unchanged_required_tests_and_references':True,'fresh_probes':4,'retained_image_present':True,'asset_bindings':len(assets),'driver_syntax':True,'no_execution_or_models':True,'review_sha256':sha(HERE/'operation-review.json')})
    print(json.dumps({'prepared':True,'review_sha256':sha(HERE/'operation-review.json'),'assets':len(assets),'payloads':checks,'executed':False}))

if __name__=='__main__':asyncio.run(main())
