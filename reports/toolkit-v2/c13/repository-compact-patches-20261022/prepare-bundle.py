"""Freeze three concrete offline components; no installation or execution."""
import ast,hashlib,json,sys
from pathlib import Path
from aeep_toolkit.install_runtime import digest
from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'approval-bundle.json').exists()
    (HERE/'run-bundle.py').write_bytes((HERE.parent/'repository-plugin-support-20261022/run-bundle.py').read_bytes())
    runtime=HERE/'operation-review.json'
    package=ROOT/'reports/toolkit-v2/integration-completion/package-review-compact-patches-20261022/operation-review.json'
    docs=ROOT/'reports/toolkit-v2/integration-completion/lychee-compact-patches-review-20261022/operation-review.json'
    checks=json.loads((HERE/'validation/source-stability.json').read_text())
    assert checks['all_passed'] and checks['source_digest']==verification_source_digest(ROOT)
    actions=[]
    configurations=[
      ('runtime',runtime,HERE/'run-reviewed-runtime.py',[sha(runtime)],'completion-audit.json',1100,{'batch_completed':True,'physical_receipt_integrity_passed':True,'all_owned_containers_absent':True,'source_unchanged':True,'eligible_cases':json.loads(runtime.read_text())['active_case_ids']}),
      ('package',package,package.parent/'run_review.py',['--execute-reviewed-digest',digest(json.loads(package.read_text()))],'execution/summary.json',1500,{'installed_cli_checks':18,'installed_capture_checks':1,'dependency_downloaded_bytes':0,'runtime_removed':True,'private_scratch_removed':True,'model_calls':0}),
      ('docs',docs,docs.parent/'run-review.py',[sha(docs)],'execution-result.json',240,{'passed':True,'immutable_runtime_unchanged':True,'runtime_removed':True})]
    for name,path,runner,args,terminal,maximum,conditions in configurations:
        assert not (path.parent/'execution-started.json').exists() and not (path.parent/'operator-approval.json').exists()
        ast.parse(runner.read_text())
        actions.append({'name':name,'review':str(path.relative_to(ROOT)),'review_sha256':sha(path),'runner':str(runner.relative_to(ROOT)),'runner_sha256':sha(runner),'argv':[sys.executable,str(runner),*args],
          'approval_record':str((path.parent/'operator-approval.json').relative_to(ROOT)),'started_marker':str((path.parent/'execution-started.json').relative_to(ROOT)),'terminal_result':str((path.parent/terminal).relative_to(ROOT)),'maximum_seconds':maximum,'pass_conditions':conditions})
    value={'schema_version':'aeep.operator-review-bundle.v1','source_commit':'2e64701b5cf4680fee52f66aaa8d851e140e2c67','source_digest':verification_source_digest(ROOT),'runner_sha256':sha(HERE/'run-bundle.py'),'actions':actions,
      'purpose':'Verify compact repository patch transport on real source, then the changed installed wheel and offline docs. No model or capability-value claim.',
      'permissions':'At most22 offline calls on the existing pinned image:3 fresh boundary/state/runtime probes,4 SQL reference/original pairs,9 per-file regressions,and1 Circuitbreaker reference/original pair with explicit existing mocker/asyncio plugins. At most24 existing-grant operations/920 reserved grader seconds. Separately install the new exact AEEP wheel with32 unchanged cached dependencies in a private runtime for19 installed checks,including compact-output CLI export and a large first-party codec fixture. Run cached Lychee0.24.2 offline docs verification. No downloads,image changes/builds/pulls,new dependencies,models,credentials,cash,activation or release.',
      'cleanup':'Remove only new attempt-owned containers and unchanged new installed/runtime/scratch resources. Preserve caches,failures,receipts,grant counters,all images/volumes,backups and unrelated work.',
      'approval_rule':'One exact human approval covers these three raw component digests,one attempt each. No replay of a started component. Independent package/docs actions continue after an isolated grader failure,with all source/artifact checks intact.',
      'approval_reason':'The user continuation excludes untrusted software execution and CONTINUATION.md requires applicable container-provisioning authority. Terminalab120327 and038b2af9 bind older software/artifacts,so they do not cover this changed source/wheel. Definition and scope preparation use standing finite delegation. No architecture decision is needed.',
      'evidence_limits':['All13 configured Python checks pass on source59b9d61c:1676 tests per full run,21 skips,82% coverage,both gates.53 focused tests,exact legacy definition proofs,current offline CI proof and69-document lint pass.',
        'The optional DSH Node runtime check remains blocked by missing @deepseek-ai/dsh-llm;12 independent Node tests passed. This bundle installs no npm packages and does not qualify that runtime.',
        'The earlier15-case pool retains sourcef694024c evidence. Five prepared v3 tasks do not freeze8/28/105 or prove model qualification,usefulness,selection quality,resource acceptance or release.',
        'Standard-library gzip is already used for source archives. Artifact bytes do not establish token,time,memory or cash savings. No scientific threshold changes.'], 'approved':False,'execution_started':False}
    with (HERE/'approval-bundle.json').open('x') as output:json.dump(value,output,indent=2);output.write('\n')
    print(json.dumps({'bundle_sha256':sha(HERE/'approval-bundle.json'),'actions':[(x['name'],x['review_sha256']) for x in actions],'execution_started':False}))


if __name__=='__main__':main()
