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
    docs=ROOT/'reports/toolkit-v2/integration-completion/lychee-contract-scope-review-20261028'
    components={'runtime':{'directory':str(HERE),'review_file':'operation-review.json','argv':[str(HERE/'run-runtime.py')],'maximum_driver_seconds':1000,'result_file':'completion-audit.json','passed_field':'batch_completed'},'docs':{'directory':str(docs),'review_file':'operation-review.json','argv':[str(docs/'run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(v['source_digest']==source for v in reviews.values())
    static_files=('preparation-checks.json','scope-check.json','static-bundle-audit.json','execution-control-check.json','terminal-control-check.json','integration-dispatch-check.json')
    for name in static_files:assert json.loads((HERE/name).read_text())['passed']
    spec=importlib.util.spec_from_file_location('classification_contract_fixture',HERE/'classify.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);assert module.self_check()==22
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['document_sha256']) and len(documents)==69
    assets=dict(reviews['runtime']['assets'])
    for value in components.values():
        p=Path(value['directory'])/value['review_file'];value['review_sha256']=sha(p);assets[str(p)]=sha(p)
    for p in [*HERE.glob('*.py'),*(docs/n for n in ('run-review.py','prepare-review.py','sandbox-preflight.py'))]:ast.parse(p.read_text());assets[str(p)]=sha(p)
    for name in (*static_files,'runtime-operation-resource-bound.json','grant-pre-review.json','README.md'):assets[str(HERE/name)]=sha(HERE/name)
    for n in ('sandbox-preflight.json','sandbox-template.sb'):assets[str(docs/n)]=sha(docs/n)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for p,h in reviews['docs']['document_sha256'].items():assets[str(ROOT/p)]=h
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    review={'purpose':'Verify issue-scoped SafetyNet and explicit existing Xsdata pytest plugin on the retained image,then current offline docs. No image build,install,download,package rerun or models.','source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'retained_image':reviews['runtime']['parent_image'],'new_builds_installs_downloads':0,'completed_current_image_probes_reused':4,'fresh_plugin_probes':1,'initial_variants':11,'initial_calls':12,'extra_same_software_control_calls':4,'maximum_calls':16,'maximum_operations':20,'maximum_reserved_seconds':860,'snapshots':3,'repository_groups':2,'required_identities':117,'models':0,'cash_usd':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False,'models':0},
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],'permissions':[*reviews['runtime']['permissions'],'Run the pinned cached Lychee0.24.2 and cached markdownlint0.23.3 through make docs-check in the reviewed offline boundary;retain logs and remove only the unchanged owned checker runtime.'],
        'no_authority_for':['Models,paid calls,cash,credentials,new destinations/services,downloads,pulls,builds,installations,activation,publication/release,retained-image/volume/backups deletion or uncertain replay.','No task-source/test/reference/plugin change within the control allowance;no unchanged product-source suite or package rerun;no campaign adoption,qualification,usefulness,selection,resource,human or release gate closure.'],
        'failure_policy':'Initial drivers run once. Retain every terminal failure,receipt and charge. Isolated case rejection after known completion/cleanup does not block independent cases/docs. Common authority,identity,accounting or cleanup uncertainty stops all external dispatch. Extra control calls require an exact recorded first-party control correction with immutable payload/software/scientific semantics;no automatic retry or allowance refund.',
        'approval_reason':'Completedad0adfcf binds the old multi-file oracle and explicit-plugin payloads. This SafetyNet-only task restores protected authentication assertions and changes input/reference scope;Xsdata enables an existing plugin. The user continuation reserves untrusted execution and CONTINUATION.md requires applicable container authority. New exact execution approval is necessary;no architecture,budget,dependency,image or core-source decision is needed.',
        'prepared_only':True,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    value={'passed':True,'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'classifier_guards':22,'documents_bound':len(documents),'current_source_checks_and_package_evidence_reused':True,'actual_execution_or_models':0,'components':{k:v['review_sha256'] for k,v in components.items()}}
    with (HERE/'final-preparation-audit.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))

if __name__=='__main__':main()
