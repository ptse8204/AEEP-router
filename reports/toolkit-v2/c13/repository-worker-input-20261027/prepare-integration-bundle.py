"""Freeze three exact offline component reviews; do not execute them."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'approval-bundle.json').exists()
    components={
        'runtime':{'directory':str(HERE),'review_file':'operation-review.json','argv':[str(HERE/'run-runtime.py')],'maximum_driver_seconds':1150,'result_file':'completion-audit.json','passed_field':'batch_completed'},
        'package':{'directory':str(ROOT/'reports/toolkit-v2/integration-completion/package-review-worker-input-20261027'),'review_file':'operation-review.json','argv':[str(ROOT/'reports/toolkit-v2/integration-completion/package-review-worker-input-20261027/run_review.py')],'maximum_driver_seconds':1800,'result_file':'execution/summary.json','passed_field':'runtime_removed'},
        'docs':{'directory':str(ROOT/'reports/toolkit-v2/integration-completion/lychee-worker-input-review-20261027'),'review_file':'operation-review.json','argv':[str(ROOT/'reports/toolkit-v2/integration-completion/lychee-worker-input-review-20261027/run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(r['source_digest']==source for r in reviews.values())
    assert source==json.loads((HERE/'validation/source-stability.json').read_text())['source_digest']
    assert json.loads((HERE/'validation/source-stability.json').read_text())['all_passed']
    for name in ('preparation-checks.json','static-bundle-audit.json','execution-control-check.json','integration-dispatch-check.json'):
        assert json.loads((HERE/name).read_text())['passed']
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['documents'])==set(reviews['docs']['document_sha256'])
    assets=dict(reviews['runtime']['assets'])
    for value in components.values():
        directory=Path(value['directory']);review=directory/value['review_file'];value['review_sha256']=sha(review);assets[str(review)]=sha(review)
    for path in list(HERE.glob('*.py'))+list((HERE/'runtime-execution').glob('*.py')):
        ast.parse(path.read_text());assets[str(path)]=sha(path)
    for name in ('execution-control-check.json','static-bundle-audit.json','terminal-control-check.json','driver-syntax-check.json','legacy-compatibility.json','old-reader-reproduction.json','preparation-checks.json','runtime-operation-resource-bound.json','integration-dispatch-check.json','grant-pre-review.json','preparation-notes.json','validation/source-stability.json','validation/checks.json','build-artifacts.json'):
        assets[str(HERE/name)]=sha(HERE/name)
    pkg=Path(components['package']['directory']);docs=Path(components['docs']['directory'])
    for name in ('installation.json','registry.json','policy.json','review.json','dependency-cache.json','capture-fixture.json','run_review.py','prepare-review.py'):assets[str(pkg/name)]=sha(pkg/name)
    for name,value in reviews['package']['inputs'].items():assets[str(ROOT/name)]=value
    installation=json.loads((pkg/'installation.json').read_text())
    for wheel in installation['wheels']:assets[str(Path(installation['wheelhouse'])/wheel['filename'])]=wheel['sha256']
    for name in ('run-review.py','prepare-review.py','sandbox-preflight.py','sandbox-preflight.json','sandbox-template.sb'):assets[str(docs/name)]=sha(docs/name)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for name,value in reviews['docs']['document_sha256'].items():assets[str(ROOT/name)]=value
    for name,expected in assets.items():
        path=Path(name);assert path.is_file() and not path.is_symlink() and sha(path)==expected
    review={
        'purpose':'Check the corrected inner-worker input framing and six unchanged public repository tasks on retained image2386,verify the corrected installed wheel and check offline docs. No downloads,image builds or models.',
        'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'maximum_image_builds':0,'downloads':0,'new_dependencies':0,'retained_image':'sha256:2386ef223e39b5dc12e6d8cdbaa6ac9779753f13ee74dc51e8d207279edae91f','maximum_contained_calls':20,'initial_calls':16,'fresh_probes':4,'initial_repository_variants':12,'extra_same_software_diagnostic_calls':4,'snapshots':6,'repository_groups':3,'required_test_identities':sum(c['required_tests'] for c in reviews['runtime']['case_summary']),'maximum_operations':24,'maximum_reserved_seconds':1000,'maximum_public_failure_log_tail_bytes_each':8192,'models':0,'cash_usd':0},
        'installation_component_limits':{'first_party_wheels':1,'unchanged_cached_dependency_wheels':32,'private_offline_installed_checks':19,'downloads':0,'models':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False,'models':0},
        'permissions':[
            *reviews['runtime']['permissions'],
            'Privately install only the exact corrected AEEP wheel pinned in the package component plus32 unchanged cached dependencies. Run19 sandboxed offline installed checks,including the installed worker positive/default-denial framing fixture,then remove only the unchanged owned runtime/scratch. Keep caches and receipts. No repository subject code is run by export checks.',
            'Run the exact cached Lychee0.24.2 binary and cached markdownlint0.23.3 via make docs-check with offline settings and the reviewed sandbox. Retain logs and remove only the unchanged owned checker runtime.'],
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],
        'no_authority_for':['Model calls, paid execution, cash spending, credential reading/sign-in capture, new model disclosure or destinations, external services, downloads, pulls, additional software, global configuration, activation, publication/release or old-resource deletion.','Campaign stage adoption/freezing, formal qualification, comparative usefulness/selection claims, resource acceptance or human-control gate closure.'],
        'failure_policy':'The initial drivers do not retry. Preserve all results,partial fetches,charged operations and uncertain attempts. Isolated incompatible workloads continue only after canonical completion/confirmed cleanup;independent package/docs components continue after a reconciled runtime. Common authority,accounting,binding or cleanup uncertainty stops external dispatch. The explicit finite bounded_control_repairs permits recorded first-party runtime report controls only with unchanged external software/tasks/source/permissions and known completed attempts;it grants no new build or uncertain replay. No fresh per-plan allowance. Package/docs remain single exact checks;failed owned-resource cleanup retains that resource.',
        'approval_reason':'The prior e6b1fb2c review explicitly excludes changed product-source/wheel from its bounded control-repair room. The real probe exposed an unchanged inner2MB reader;correcting it changes source374579f1 and the wheel. The pasted continuation reserves untrusted execution/installation,and CONTINUATION.md requires applicable provisioning authority. This review binds the actual corrected source,wheel and fresh four probes plus twelve unchanged variants. Reuse retained2386;no new image,download,dependency,architecture or budget decision. The old8operations/15.73691733321175seconds remain charged.',
        'prepared_only':True,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    print(json.dumps({'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'components':{k:v['review_sha256'] for k,v in components.items()},'execution_started':False}))


if __name__=='__main__':main()
