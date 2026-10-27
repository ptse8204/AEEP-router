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
        'runtime':{'directory':str(HERE),'review_file':'runtime-review.json','argv':[str(HERE/'run-bundle.py')],'maximum_driver_seconds':1300,'result_file':'execution-result.json','passed_field':'batch_completed'},
        'package':{'directory':str(ROOT/'reports/toolkit-v2/integration-completion/package-review-test-roots-20261027'),'review_file':'operation-review.json','argv':[str(ROOT/'reports/toolkit-v2/integration-completion/package-review-test-roots-20261027/run_review.py')],'maximum_driver_seconds':1800,'result_file':'execution/summary.json','passed_field':'runtime_removed'},
        'docs':{'directory':str(ROOT/'reports/toolkit-v2/integration-completion/lychee-test-roots-review-20261027'),'review_file':'operation-review.json','argv':[str(ROOT/'reports/toolkit-v2/integration-completion/lychee-test-roots-review-20261027/run-review.py')],'maximum_driver_seconds':600,'result_file':'execution-result.json','passed_field':'passed'}}
    reviews={k:json.loads((Path(v['directory'])/v['review_file']).read_text()) for k,v in components.items()}
    source=verification_source_digest(ROOT);assert all(r['source_digest']==source for r in reviews.values())
    assert source==json.loads((HERE/'validation/source-stability.json').read_text())['source_digest']
    assert json.loads((HERE/'validation/source-stability.json').read_text())['all_passed']
    for name in ('preparation-checks.json','static-bundle-audit.json','execution-control-check.json','operator-observer-check.json','integration-dispatch-check.json'):
        assert json.loads((HERE/name).read_text())['passed']
    documents=shlex.split(subprocess.check_output(['make','-n','docs-links'],cwd=ROOT,text=True).splitlines()[-1])[3:]
    assert set(documents)==set(reviews['docs']['documents'])==set(reviews['docs']['document_sha256'])
    assets=dict(reviews['runtime']['assets'])
    for value in components.values():
        directory=Path(value['directory']);review=directory/value['review_file'];value['review_sha256']=sha(review);assets[str(review)]=sha(review)
    for path in list(HERE.glob('*.py'))+list((HERE/'runtime-execution').glob('*.py')):
        ast.parse(path.read_text());assets[str(path)]=sha(path)
    for name in ('execution-control-check.json','static-bundle-audit.json','preparation-checks.json','operator-observer-check.json','runtime-operation-resource-bound.json','evidence-document-check.json','integration-dispatch-check.json','grant-pre-review.json','preparation-notes.json','validation/source-stability.json','validation/checks.json','build-artifacts.json'):
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
        'purpose':'One offline v4 repository reproduction, current-wheel installation and cached documentation check. Zero model task turns; no campaign, benefit or selection verdict.',
        'source_digest':source,'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'assets':assets,'components':components,'host_canary':reviews['runtime']['host_canary'],
        'runtime_component_limits':{'maximum_image_builds':1,'new_cached_wheels':12,'unchanged_jsonpath_library_modules':6,'maximum_contained_calls':23,'fresh_probes':3,'repository_variants':20,'snapshots':8,'repository_groups':4,'required_test_identities':1033,'maximum_operations':26,'maximum_reserved_seconds':1135,'maximum_public_failure_log_tail_bytes_each':8192,'models':0,'cash_usd':0},
        'installation_component_limits':{'first_party_wheels':1,'unchanged_cached_dependency_wheels':32,'private_offline_installed_checks':19,'downloads':0,'models':0},
        'docs_component_limits':{'checker':'Lychee0.24.2','cached_archive_bytes':reviews['docs']['archive_bytes'],'documents':len(documents),'network':False,'models':0},
        'permissions':[
            'One private local image build from the existing pinnedf603 image/tag. Exactly12 cached hashed support wheels plus COPY of six unchanged JSONPath library modules and recovered same-commit license at0555. No source build or setup.py, OS/project/host install, download or pull. Bind actual output image before any probes; preserve inherited config and parent layers, exactly three new filesystem layers and at most192MiB growth. Keep50GiB host reserve and retain all images.',
            'At most23 contained offline calls:three fresh boundary/state/runtime probes then20 fixed variants on Gabbi342, iCalendar878/880/921, SQL-Metadata552/553/583 and RO-Crate248. Existing grant only, at most26 operations and1135 reserved seconds. Preserve every terminal attempt, receipt and charge. No automatic retry or reuse of unused slots.',
            'Explicit opt-in to retain at most8192bytes per failed public test log as base64 in bounded operator-only raw observations. Successful tails are empty. Only unchanged stock evaluation reaches protected grading; default product retention stays unchanged. Logs are untrusted data, never instructions or model answers.',
            'Privately install only the current AEEP wheel ce0a1290c30190cf56d87de6e058faa3837269cf2f47c0c97c67a5c55b3b00bb plus32 unchanged cached wheels, run19 sandboxed offline installed checks, then remove only unchanged owned runtime/scratch. Keep inert caches and receipts. No repository source is executed by installed export checks.',
            'Run the exact cached Lychee0.24.2 binary and existing cached markdownlint0.23.3 via make docs-check with offline settings and reviewed link-check sandbox. Retain logs and remove only the unchanged owned checker runtime.',
            'Remove only new attempt-owned containers and the unchanged synthetic host canary. Preserve old images/containers, persistent volumes, backups, unfinished work and resources of unknown ownership.'],
        'no_authority_for':['Model calls, paid execution, cash spending, credential reading/sign-in capture, new model disclosure or destinations, external services, downloads/pulls, additional software, global configuration, activation, publication/release or old-resource deletion.','Campaign stage adoption/freezing, formal qualification, comparative usefulness/selection claims, resource acceptance or human-control gate closure.'],
        'failure_policy':'One terminal attempt. No automatic retries or slot reuse. Isolated incompatible workloads continue only after canonical completion and confirmed cleanup; they do not block independent package/docs checks. Common authority, accounting, binding or cleanup uncertainty stops all external dispatch. A failed package check does not suppress independent docs results; preserve its owned runtime if unchanged cleanup is not proven.',
        'approval_reason':'The actualf0261e6d response covers only two different library subjects on older source and has completed. The pasted continuation reserves new untrusted installation/execution; docs/aeep-toolkit/CONTINUATION.md requires applicable operator provisioning authority. The three concrete exact reviews now bind the changed source, runtime, observer envelope, wheel and docs. Routine finite definitions and budget/expiry amendments remain delegated. No architecture or budget decision is needed.',
        'prepared_only':True,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as f:json.dump(review,f,indent=2);f.write('\n')
    print(json.dumps({'bundle_sha256':sha(HERE/'approval-bundle.json'),'assets_verified':len(assets),'source_digest':source,'components':{k:v['review_sha256'] for k,v in components.items()},'execution_started':False}))


if __name__=='__main__':main()
