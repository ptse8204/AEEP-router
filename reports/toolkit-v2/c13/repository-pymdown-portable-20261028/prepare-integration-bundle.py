"""Bind retained-image scope checks and cached docs; do not execute components."""
import ast
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import subprocess

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    assert not (HERE/'approval-bundle.json').exists()
    docs=ROOT/'reports/toolkit-v2/integration-completion/lychee-pymdown-portable-review-20261028'
    components={'runtime':{'directory':str(HERE),'review_file':'operation-review.json','argv':[str(HERE/'run-runtime.py')],'maximum_driver_seconds':700,'result_file':'completion-audit.json','passed_field':'batch_completed'},'docs':{'directory':str(docs),'review_file':'operation-review.json','argv':[str(docs/'run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(v['source_digest']==source for v in reviews.values())
    static_files=('preparation-checks.json','scope-check.json','static-bundle-audit.json','execution-control-check.json','terminal-control-check.json','integration-dispatch-check.json')
    for name in static_files:assert json.loads((HERE/name).read_text())['passed']
    spec=importlib.util.spec_from_file_location('classification_contract_fixture',HERE/'classify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);assert module.self_check()==22
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['document_sha256']) and len(documents)==69
    assets=dict(reviews['runtime']['assets'])
    reuse=json.loads((HERE/'terminal-control-check.json').read_text());proof=Path(reuse['evidence_manifest']);assert sha(proof)==reuse['evidence_sha256'];assets[str(proof.resolve())]=sha(proof)
    for value in components.values():
        p=Path(value['directory'])/value['review_file'];value['review_sha256']=sha(p);assets[str(p)]=sha(p)
    for p in [*HERE.glob('*.py'),*(docs/n for n in ('run-review.py','prepare-review.py','sandbox-preflight.py'))]:ast.parse(p.read_text());assets[str(p)]=sha(p)
    for name in (*static_files,'runtime-operation-resource-bound.json','grant-pre-review.json','README.md'):assets[str(HERE/name)]=sha(HERE/name)
    for n in ('sandbox-preflight.json','sandbox-template.sb'):assets[str(docs/n)]=sha(docs/n)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for p,h in reviews['docs']['document_sha256'].items():assets[str(ROOT/p)]=h
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    review={'purpose':'Verify exact cached pure Markdown3.9 through the existing private ZIP-wheel loader for two pending unchanged PyMdown tasks,then current offline docs. No image build,install,download,package rerun or models.','source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'retained_image':reviews['runtime']['parent_image'],'new_builds_installs_downloads':0,'completed_current_image_probes_reused':4,'fresh_portable_runtime_probes':1,'initial_variants':4,'initial_calls':5,'extra_same_software_control_calls':2,'maximum_calls':7,'maximum_operations':11,'maximum_reserved_seconds':545,'snapshots':2,'repository_groups':1,'required_identities':765,'additional_cached_pure_wheels':1,'additional_wheel_bytes':107441,'models':0,'cash_usd':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False,'models':0},
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],'permissions':[*reviews['runtime']['permissions'],'Run the pinned cached Lychee0.24.2 and cached markdownlint0.23.3 through make docs-check in the reviewed offline boundary;retain logs and remove only the unchanged owned checker runtime.'],
        'no_authority_for':['Models,paid calls,cash,credentials,new destinations/services,downloads,pulls,builds,installations,activation,publication/release,retained-image/volume/backups deletion or uncertain replay.','No task-source/test/reference/plugin change within the control allowance;no unchanged product-source suite or package rerun;no campaign adoption,qualification,usefulness,selection,resource,human or release gate closure.'],
        'failure_policy':'Initial drivers run once. Retain every terminal failure,receipt and charge. Isolated case rejection after known completion/cleanup does not block independent cases/docs. Common authority,identity,accounting or cleanup uncertainty stops all external dispatch. Extra control calls require an exact recorded first-party control correction with immutable payload/software/scientific semantics;no automatic retry or allowance refund.',
        'approval_reason':'Terminalf18daa4a and its approved report-control continuation bind payloads without Markdown. This review adds the exact cached pure Markdown3.9 software bytes to the existing private ZIP-loader,while preserving all765PyMdown identities/assertions,input/source/test/reference/fault bytes and plugins. New software payload execution requires exact approval. The user continuation reserves untrusted execution and CONTINUATION.md requires applicable container authority. New exact execution approval is necessary;no architecture,budget,dependency,image or core-source decision is needed.',
        'prepared_only':True,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    value={'passed':True,'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'classifier_guards':22,'documents_bound':len(documents),'current_source_checks_and_package_evidence_reused':True,'actual_execution_or_models':0,'components':{k:v['review_sha256'] for k,v in components.items()}}
    with (HERE/'final-preparation-audit.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))

if __name__=='__main__':main()
