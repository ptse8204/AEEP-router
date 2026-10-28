"""Bind one finite native-runtime, changed-wheel and offline-docs review; no execution."""
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
    base=ROOT/'reports/toolkit-v2/integration-completion'
    package=base/'package-review-native-identity-20261028';docs=base/'lychee-native-identity-review-20261028'
    components={
        'runtime':{'directory':str(HERE),'review_file':'operation-review.json','argv':[str(HERE/'run-runtime.py')],'maximum_driver_seconds':1000,'result_file':'completion-audit.json','passed_field':'batch_completed'},
        'package':{'directory':str(package),'review_file':'operation-review.json','argv':[str(package/'run_review.py')],'maximum_driver_seconds':1800,'result_file':'execution/summary.json','passed_field':'runtime_removed'},
        'docs':{'directory':str(docs),'review_file':'operation-review.json','argv':[str(docs/'run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(r['source_digest']==source for r in reviews.values())
    static=('preparation-checks.json','scope-check.json','static-bundle-audit.json','execution-control-check.json','terminal-control-check.json','integration-dispatch-check.json','legacy-compatibility-check.json')
    for n in static:assert json.loads((HERE/n).read_text())['passed']
    spec=importlib.util.spec_from_file_location('classification_fixture',HERE/'classify.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);assert mod.self_check()==22
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['document_sha256']) and len(documents)==69
    assets=dict(reviews['runtime']['assets'])
    for value in components.values():
        p=Path(value['directory'])/value['review_file'];value['review_sha256']=sha(p);assets[str(p)]=sha(p)
    for p in [*HERE.glob('*.py'),*(package/n for n in ('prepare-review.py','run_review.py')),*(docs/n for n in ('prepare-review.py','run-review.py','sandbox-preflight.py'))]:ast.parse(p.read_text());assets[str(p)]=sha(p)
    for n in (*static,'runtime-operation-resource-bound.json','grant-pre-review.json','README.md'):assets[str(HERE/n)]=sha(HERE/n)
    for folder,names in [(docs,('sandbox-preflight.json','sandbox-template.sb')),(package,('installation.json','registry.json','policy.json','review.json','dependency-cache.json','capture-fixture.json'))]:
        for n in names:assets[str(folder/n)]=sha(folder/n)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for p,h in reviews['docs']['document_sha256'].items():assets[str(ROOT/p)]=h
    installation=json.loads((package/'installation.json').read_text())
    for w in installation['wheels']:
        p=Path(installation['wheelhouse'])/w['filename'];assert sha(p)==w['sha256'];assets[str(p)]=w['sha256']
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    review={'purpose':'Validate optional native pytest identities without changing old contracts:confirm frozen915-name crosswalk before body grading,check compatibility controls,the changed installed wheel and offline docs. Engineering evidence remains separate from comparative value/selection/resource gates.',
        'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'retained_image':reviews['runtime']['parent_image'],'new_builds_pulls_installs_downloads':0,'fresh_boundary_state_transport_probes':4,'first_party_native_fixtures':2,'collection_only_gate':1,'immutable_body_variants':8,'initial_calls':15,'extra_same_software_control_calls':2,'maximum_calls':17,'maximum_operations':21,'maximum_reserved_seconds':895,'required_obligations':993,'new_authored_native_audit_obligations':915,'models':0,'cash_usd':0},
        'package_component_limits':{'changed_wheel_sha256':reviews['package']['wheel_sha256'],'dependency_wheels':32,'new_cli_identity_checks':19,'retained_capture_checks':1,'private_install_only':True,'network':False},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False},
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],'permissions':[*reviews['runtime']['permissions'],'Install the exact changed AEEP wheel and32unchanged cached dependency wheels privately with no resolver/download;run20sandboxed offline installed checks,then remove only the unchanged owned runtime/scratch. Keep cached wheels.','Run pinned cached Lychee0.24.2 and cached markdownlint0.23.3 via make docs-check in the reviewed offline boundary;retain logs and remove only the unchanged owned checker runtime.'],
        'no_authority_for':['Models,cash,credentials,new destinations/services,downloads,pulls,image builds/deletion,host/project installation,activation,publication/release or backups/volumes deletion.','No changed source,observer,protected tests,identity map or software payload within the control allowance;no unknown-attempt replay/refund or silent scientific change.','No qualification,usefulness,selection,resource,human or release gate closure from these engineering checks;pool62 remains until actual evidence.'],
        'failure_policy':'Each initial component executes once. Retain every terminal result,receipt and charge. After reconciled runtime completion and absent owned containers,isolated rejected workloads do not prevent package/docs checks. Common authority,identity,accounting or cleanup uncertainty stops external dispatch. Up to2extra calls require exact recorded first-party controls with immutable payloads/software;no automatic retry.',
        'approval_reason':'The user continuation reserves untrusted execution/installation,and CONTINUATION.md requires applicable container authority. Terminal22b0cf03 binds older observer/core/wheel bytes and cannot cover this correction. Routine finite definition work remains delegated. No architecture,budget,image or dependency-version decision is needed.',
        'prepared_only':True,'execution_started':False}
    with(HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    value={'passed':True,'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'classifier_guards':22,'documents_bound':69,'new_wheel_checks':20,'actual_execution_or_models':0,'components':{k:v['review_sha256'] for k,v in components.items()}}
    with(HERE/'final-preparation-audit.json').open('x') as f:json.dump(value,f,indent=2);f.write('\n')
    print(json.dumps(value))

if __name__=='__main__':main()
