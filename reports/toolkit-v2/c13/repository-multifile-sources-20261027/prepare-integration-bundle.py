"""Bind exact private-runtime and cached-docs components;do not execute either."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    assert not (HERE/'approval-bundle.json').exists()
    docs=ROOT/'reports/toolkit-v2/integration-completion/lychee-multifile-sources-review-20261027'
    components={'runtime':{'directory':str(HERE),'review_file':'runtime-review.json','argv':[str(HERE/'run-bundle.py')],'maximum_driver_seconds':1450,'result_file':'execution-result.json','passed_field':'batch_completed'},'docs':{'directory':str(docs),'review_file':'operation-review.json','argv':[str(docs/'run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(r['source_digest']==source for r in reviews.values())
    stable=HERE.parent/'repository-worker-input-20261027/validation/source-stability.json';assert json.loads(stable.read_text())['all_passed'] and json.loads(stable.read_text())['source_digest']==source
    for name in ('preparation-checks.json','static-bundle-audit.json','execution-control-check.json','integration-dispatch-check.json'):assert json.loads((HERE/name).read_text())['passed']
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:];assert set(documents)==set(reviews['docs']['document_sha256'])
    assets=dict(reviews['runtime']['assets'])
    for value in components.values():
        p=Path(value['directory'])/value['review_file'];value['review_sha256']=sha(p);assets[str(p)]=sha(p)
    for p in [*HERE.glob('*.py'),*(HERE/'runtime-execution').glob('*.py')]:ast.parse(p.read_text());assets[str(p)]=sha(p)
    for name in ('preparation-checks.json','static-bundle-audit.json','execution-control-check.json','integration-dispatch-check.json','curation-dispositions.json','runtime-operation-resource-bound.json','grant-pre-review.json','preparation-notes.json'):assets[str(HERE/name)]=sha(HERE/name)
    assets[str(stable)]=sha(stable)
    for name in ('run-review.py','prepare-review.py','sandbox-preflight.py','sandbox-preflight.json','sandbox-template.sb'):assets[str(docs/name)]=sha(docs/name)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for name,expected in reviews['docs']['document_sha256'].items():assets[str(ROOT/name)]=expected
    for name,expected in assets.items():assert Path(name).is_file() and not Path(name).is_symlink() and sha(Path(name))==expected,name
    review={'purpose':'Reproduce four real multi-file repository repairs with exact private grader supports and check the current offline docs. No source/package rebuild or model task.','source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'maximum_image_builds':1,'cached_wheels':8,'unchanged_upstream_source_modules':1,'publisher_metadata_and_license_copy':True,'fresh_probes':4,'initial_variants':16,'initial_calls':20,'extra_same_software_control_calls':4,'maximum_calls':24,'maximum_operations':29,'maximum_reserved_seconds':1320,'snapshots':4,'repository_groups':3,'required_identities':125,'maximum_image_growth_bytes':96*1024**2,'maximum_new_filesystem_layers':3,'models':0,'cash_usd':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False,'models':0},
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],'permissions':[*reviews['runtime']['permissions'],'Run the exact cached Lychee0.24.2 and cached markdownlint0.23.3 via make docs-check,with the reviewed offline sandbox. Retain evidence;remove only the unchanged owned checker runtime.'],
        'no_authority_for':['Models,paid calls,cash,credentials,downloads,pulls,new services or model destinations,OS/project/host installation,activation,publication/release,retained-image/volume/backups deletion or unknown-attempt replay.','Unchanged package installation/source suites are not repeated. No campaign adoption,qualification,usefulness,selection,resource or human gate closure.'],
        'failure_policy':'Initial drivers do not retry. Keep all canonical receipts,terminal failures and charges. After known completion/cleanup,isolated case incompatibility does not block independent cases or docs. Common authority,binding,accounting or cleanup uncertainty stops external dispatch. The finite same-software report-control allowance requires exact recorded repairs and unchanged source/test/reference/permission/scientific semantics;it permits no new build,source change or uncertain replay.',
        'approval_reason':'Completed4661ce49 covered six different subjects on2386 and no new dependencies. The user continuation reserves untrusted execution/installation,and CONTINUATION.md requires applicable image/container provisioning authority. This exact build/source-support/subject review needs approval;routine finite definitions/budget amendments are delegated. No architecture or budget decision is needed.','prepared_only':True,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    print(json.dumps({'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'components':{k:v['review_sha256'] for k,v in components.items()},'executed':False}))

if __name__=='__main__':main()
