"""Bind two supported cached sources and offline docs; never dispatch."""
import ast
import hashlib
import json
from pathlib import Path
import shlex
import subprocess

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    docs=ROOT/'reports/toolkit-v2/integration-completion/lychee-native-batch-ready-review-20261028'
    components={'runtime':{'directory':str(HERE),'review_file':'operation-review.json','argv':[str(HERE/'run-runtime.py')],'maximum_driver_seconds':1100,'result_file':'completion-audit.json','passed_field':'batch_completed'},
        'docs':{'directory':str(docs),'review_file':'operation-review.json','argv':[str(docs/'run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(c['directory'])/c['review_file']).read_text()) for k,c in components.items()}
    source=verification_source_digest(ROOT);assert all(v['source_digest']==source for v in reviews.values())
    checks=('preparation-checks.json','static-bundle-audit.json','execution-control-check.json','native-scope-check.json','seed-provenance-check.json','terminal-control-check-profile-routing.json','integration-dispatch-check.json')
    for n in checks:assert json.loads((HERE/n).read_text())['passed']
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['document_sha256']) and len(documents)==69
    assets=dict(reviews['runtime']['assets'])
    for c in components.values():
        p=Path(c['directory'])/c['review_file'];c['review_sha256']=sha(p);assets[str(p)]=sha(p)
    for p in [*HERE.glob('*.py'),*(docs/n for n in ('prepare-review.py','run-review.py','sandbox-preflight.py'))]:ast.parse(p.read_text());assets[str(p)]=sha(p)
    for p in [*(HERE/n for n in (*checks,'README.md','grant-pre-review.json')),*(docs/n for n in ('sandbox-template.sb','sandbox-preflight.json')),HERE.parent/'repository-native-batch-20261028/withdrawn-review.json']:
        assets[str(p)]=sha(p)
    assets[reviews['docs']['archive_path']]=reviews['docs']['archive_sha256']
    for p,h in reviews['docs']['document_sha256'].items():assets[str(ROOT/p)]=h
    for p,h in assets.items():assert Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p))==h,p
    review={'purpose':'Test two exact cached repository snapshots using exhaustive native-name scopes,verify the existing default observer,and check current docs. Sopel was withdrawn before execution for known runtime/version metadata blockers.',
        'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'retained_image':reviews['runtime']['parent_image'],'fresh_default_boundary_probes':4,'fresh_default_event_fixtures':2,'support_probe':1,'collection_calls':2,'body_calls':4,'default_reference_calls':1,'initial_calls':14,'extra_control_calls':2,'maximum_calls':16,'maximum_operations':20,'maximum_reserved_seconds':860,'seed_aliases':195,'maximum_expanded_required_ids_per_case':5000,'maximum_required_id_metadata_chars_per_case':300000,'models':0,'cash_usd':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':69,'network':False},
        'bounded_control_repairs':reviews['runtime']['bounded_control_repairs'],'permissions':[*reviews['runtime']['permissions'],'Run the exact cached Lychee0.24.2/markdownlint0.23.3 offline over69documents;retain results and remove only the unchanged owned checker runtime.'],
        'no_authority_for':['Models,cash,credentials,new destinations/services,downloads,image builds/pulls/deletion,host/project/private package installation,activation,publication/release,volumes/backups deletion or uncertain replay.','No changed derivation rule,observer bytes,source/assertions,repair bytes,permissions or scientific thresholds after collection/body outcomes. All matched tests required;old metadata/results stay.','No Sopel execution or compatibility claims;no default-observer proof before its fresh checks;no model usefulness,selection,resource,human or release gate closure.'],
        'failure_policy':'Initial components execute once. Known completed/cleaned-up case-specific support/collection/grader failures remain exclusions and do not stop independent cases/docs. Common authority,identity,accounting or cleanup uncertainty stops dispatch. Extra immutable-payload calls require an exact recorded first-party report-control correction;no automatic retry/refund.',
        'evidence_reuse':'Current source dbf9be31 passed13gates and wheel3791d8f7 passed20installed checks. Those unchanged checks and exact diagnostic-operator conformance are reused;no package or full source rerun. New default profile and new subjects still require actual execution.',
        'approval_reason':'The user continuation explicitly excludes untrusted software execution,and CONTINUATION.md requires applicable container authority. Completed d9352568 covers iCalendar and different source/payload scope;it cannot authorize Dead204,Python-json-logger39 or private Identify2.6.15. No architecture,budget,image or installation decision is needed.',
        'prepared_only':True,'execution_started':False}
    with(HERE/'approval-bundle.json').open('x') as stream:json.dump(review,stream,indent=2);stream.write('\n')
    result={'passed':True,'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'subjects':2,'docs':69,'source13_and_package20checks_reused':True,'actual_external_execution_models_downloads_or_installs':0,'components':{k:v['review_sha256'] for k,v in components.items()}}
    with(HERE/'final-preparation-audit.json').open('x') as stream:json.dump(result,stream,indent=2);stream.write('\n')
    print(json.dumps(result))

if __name__=='__main__':main()
