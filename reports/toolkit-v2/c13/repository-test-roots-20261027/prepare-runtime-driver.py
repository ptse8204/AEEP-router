"""Adapt the completed finite driver to pinned v4 cases, without executing it."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
OLD=HERE.parent/'repository-supported-suites-20261027'
s=(OLD/'prepare-review.py').read_text()
def replace(a,b):
    global s
    assert a in s,a[:90]
    s=s.replace(a,b)
replace('approval-bundle.json','runtime-review.json')
replace("HERE.parent/'repository-task-delivery-20261023/validation-final/source-stability.json'","HERE/'validation/source-stability.json'")
replace("HERE/'prepared-cases.json'","HERE/'execution-cases.json'")
replace("metadata['prepared_cases']==6","metadata['prepared_cases']==8")
replace('len(cases)==6 and len(variants)==17','len(cases)==8 and len(variants)==20')
replace('for c in cases})==5','for c in cases})==4')
replace('for c in cases})==6','for c in cases})==8')
replace("HERE/'runtime-install-review.json'","HERE/'runtime-support-review.json'")
replace("len(closure['pins'])==22","len(closure['pins'])==12")
replace("ROOT/'.aeep/repository-supported-suite-image-20261027'","ROOT/'.aeep/repository-test-root-image-20261027'")
replace("'aeep-toolkit-v2/repository-grader:py313-repository-supports-20261024'","'aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027'")
replace("    (context/'Dockerfile').write_text(dockerfile)","""    source_review=json.loads((HERE/'jsonpath-source-review.json').read_text())
    copy_root=ROOT/source_review['copy_tree']/'jsonpath_rw'
    assert sorted(str(p.relative_to(copy_root)) for p in copy_root.rglob('*') if p.is_file())==sorted([p['file'].removeprefix('jsonpath_rw/') for p in source_review['library_files_identical_to_license_commit']]+['LICENSE.source'])
    for item in source_review['library_files_identical_to_license_commit']:
        assert sha(copy_root/item['file'].removeprefix('jsonpath_rw/'))==item['sha256']
    assert sha(copy_root/'LICENSE.source')==source_review['license_sha256']
    shutil.copytree(copy_root,context/'jsonpath_rw')
    dockerfile=dockerfile.replace('USER 65534:65534\\n','COPY --chmod=0555 jsonpath_rw/ /usr/local/lib/python3.13/site-packages/jsonpath_rw/\\nUSER 65534:65534\\n')
    (context/'Dockerfile').write_text(dockerfile)""")
replace('for path in context.iterdir():path.chmod(0o644)',"for path in context.rglob('*'):path.chmod(0o755 if path.is_dir() else 0o644)")
replace('*context.iterdir()','*(p for p in context.rglob(\'*\') if p.is_file())')
replace("'prepared-cases.json','runtime-install-review.json','source-review.json','git-tree-source-scopes.json','source-scope-review.json'","'execution-cases.json','runtime-support-review.json','jsonpath-source-review.json','operator-observer.py','operator-observer-review.json','operator-observer-check.json','runtime-execution/operator_output.py'")
replace("if case.origin_kind=='authored_control':negative['tests/test_aeep_preservation.py::test_snapshot_preserved']='FAILED'","if case.origin_kind=='authored_control':\n            extra=set(required)-set(negative);assert len(extra)==1;negative.update({n:'FAILED' for n in extra})")
replace('One22-wheel offline grader image and six cached provisional repository tasks','One12-wheel offline grader image with unchanged JSONPath library copy and eight cached v4 repository tasks')
replace('(20,23,1030)','(23,26,1135)')
replace("'target_tag':'aeep-toolkit-v2/repository-grader:py313-cached-suites-20261027'","'target_tag':'aeep-toolkit-v2/repository-grader:py313-test-roots-20261027'")
replace("'context_files':sorted(p.name for p in context.iterdir())","'context_files':sorted(str(p.relative_to(context)) for p in context.rglob('*') if p.is_file())")
replace("    (HERE/'runtime-review.json').write_text", """    review.update(purpose='One offline private12-wheel grader image plus unchanged six-file JSONPath source/library license COPY; three fresh probes and20 exact variants for eight v4 tasks. Operator-only public failure tails up to8192bytes. No models or stage adoption.',
        jsonpath_source_review=source_review, maximum_new_filesystem_layers=3,
        permissions=[
            'One local offline image build from retainedf603 through its checked existing tag. Exactly12 cached hashed wheels, no resolver/source build/pull/network/host installation. COPY six unchanged publisher JSONPath modules plus its same-commit Apache2 license at0555; no setup.py or console entry point. Retain every image.',
            'Bind output digest before testing. Require inherited execution configuration, parent layers, exactly three new filesystem layers and at most192MiB growth; maintain50GiB host reserve. These finite operation caps are not product acceptance budgets.',
            'At most23 contained offline calls:three fresh boundary/state/runtime probes and20 fixed reference/counterexample/per-file-partial variants across eight snapshots/four repositories. At most26 existing-grant operations and1135 reserved seconds including180 build,30 setup,120 analysis and23 times35 per call. Preserve counters and check the existing grant before every reservation.',
            'Explicit operator opt-in: retain at most8192bytes of each failed public test log as base64 in the bounded raw reply. Successful tests have empty tails. Only the unchanged five-field evaluation reaches the protected grader. Logs remain untrusted operator data, never model instructions or benchmark answers; default product retention remains unchanged.',
            'Keep1033 declared test identities, every upstream assertion and exact published paths. Use only reviewed explicit plugins. Public tests may create bounded children/fixtures inside offline containers; no host service, port or external network.',
            'Retain raw replies, canonical receipts, terminal attempts and every charge. Remove only new attempt-owned containers and the unchanged owned nonsecret canary. Isolated source incompatibility may exclude a case only after canonical completion/cleanup; common binding, authority, accounting or cleanup uncertainty stops dispatch.',
            'One terminal attempt; no automatic retry or reuse of unused slots. No models, cash, downloads, pulls, OS/project/host installation, credentials, new services/destinations, package/docs reruns in this component, image deletion, activation, publication or release.'],
        limitations=[
            'This operator observer/profile and optional grader runtime require their own applicable reproduction evidence. Historical44-case pool bindings stay unchanged; default-observer campaigns inherit no conformance automatically.',
            'Eight tasks include3single-file repairs,2multi-file repairs and3authored audits. The915 identities in one task are not915 independent cases. No case or stage is adopted/frozen; no usefulness, qualification, selection, resource or release gate closes.',
            'Sopel remains excluded for incompatible SQLAlchemy1.4 and project metadata/plugin requirements. Raygun, Skelebot and Towncrier scope failures stay recorded. No hidden project installer or relaxed test assertion is authorized.',
            'JSONPath distribution1.4.0 embeds module version1.3.0; unchanged file hashes, license provenance and actual module version are checked separately. Static dependency closure is not runtime compatibility.'],
        approval_reason='The completedf0261e6d approval binds different subjects and older source. The user continuation reserves new untrusted installation/execution and CONTINUATION.md requires applicable provisioning authority. This exact build/runtime review needs approval; routine finite definitions remain delegated. No architecture or budget decision is needed.')
    (HERE/'runtime-review.json').write_text""")
replace("'cases':6,'repositories':5,'distinct_snapshots':6,'payloads':17","'cases':8,'repositories':4,'distinct_snapshots':8,'payloads':20")
replace("'new_wheels':22","'new_wheels':12")
(HERE/'prepare-runtime-review.py').write_text(s)
