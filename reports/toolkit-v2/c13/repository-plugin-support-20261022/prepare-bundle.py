"""Freeze three concrete component reviews after configured source verification."""
import hashlib
import json
import sys
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import digest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE / 'approval-bundle.json').exists()
    checks = json.loads((HERE / 'validation/source-stability.json').read_text())
    assert checks['all_passed'] and checks['source_unchanged'] and checks['source_digest'] == verification_source_digest(ROOT)
    assert json.loads((HERE.parent / 'repository-replacement-runtime-20261022/static-bundle-audit.json').read_text())['passed']
    assert json.loads((HERE.parent / 'repository-replacement-runtime-20261022/current-case-family-audit.json').read_text())['passed']
    package = ROOT / 'reports/toolkit-v2/integration-completion/package-review-repository-plugins-20261022'
    docs = ROOT / 'reports/toolkit-v2/integration-completion/lychee-repository-plugins-review-20261022'
    assert json.loads((docs / 'sandbox-preflight.json').read_text())['passed']
    actions = []
    for name, directory, review_name, runner_name, approval_name, marker, terminal, seconds, conditions in [
        ('runtime', HERE.parent / 'repository-replacement-runtime-20261022', 'approval-bundle.json', 'run-bundle.py', 'operator-approval.json',
         'execution-started.json', 'execution-result.json', 1500,
         {'batch_completed': True, 'build_passed': True, 'receipt_integrity_passed': True, 'source_unchanged': True,
          'eligible_cases': json.loads((HERE.parent / 'repository-replacement-runtime-20261022/approval-bundle.json').read_text())['active_case_ids']}),
        ('package', package, 'operation-review.json', 'run_review.py', 'operator-approval.json',
         'execution-started.json', 'execution/summary.json', 1800,
         {'installed_cli_checks': 18, 'installed_capture_checks': 1, 'runtime_removed': True, 'private_scratch_removed': True}),
        ('documentation', docs, 'operation-review.json', 'run-review.py', 'operator-approval.json',
         'execution-started.json', 'execution-result.json', 240,
         {'passed': True, 'immutable_runtime_unchanged': True, 'runtime_removed': True})]:
        review = directory / review_name
        document = json.loads(review.read_text())
        assert document['source_digest'] == checks['source_digest']
        argument = digest(document) if name == 'package' else sha(review)
        argv = [sys.executable, str(directory / runner_name)]
        argv += ['--execute-reviewed-digest', argument] if name == 'package' else [argument]
        actions.append({'name': name, 'review': str(review.relative_to(ROOT)), 'review_sha256': sha(review),
            'runner': str((directory / runner_name).relative_to(ROOT)), 'runner_sha256': sha(directory / runner_name),
            'argv': argv, 'approval_record': str((directory / approval_name).relative_to(ROOT)),
            'started_marker': str((directory / marker).relative_to(ROOT)),
            'terminal_result': str((directory / terminal).relative_to(ROOT)), 'maximum_seconds': seconds,
            'pass_conditions': conditions})
    bundle = {'schema_version': 'aeep.operator-review-bundle.v1', 'source_digest': checks['source_digest'],
        'runner_sha256': sha(HERE / 'run-bundle.py'), 'actions': actions,
        'purpose': 'Verify the explicit-plugin grader and25 pinned runtime dependencies on8 provisional real repository tasks, including6 partial-repair rejections, then check the current installed wheel and offline docs. No model comparison or release.',
        'permissions': 'One local offline image build from the existing pinned image, installing exactly25 cached pinned wheels. Bind its actual image digest, then at most25 fresh contained calls (3 runtime/containment/state probes,16 reference/counterexample calls and6 partial repairs); maximum28 existing-grant operations and1205 reserved seconds total. Current AEEP wheel plus32 unchanged cached dependencies and19 sandboxed installed checks; cached Lychee0.24.2 offline docs check. Zero models, downloads, pulls, credentials, new destinations, cash, activation or release. Keep the new image for remaining work; no old-image deletion or host installation.',
        'cleanup': 'Remove only new attempt-owned containers, unchanged synthetic canary, private installed runtime/scratch and unchanged Lychee runtime. Retain the new runtime image for remaining work. Retain inert caches, historical evidence, current/rollback images, volumes, backups, unrelated work and all accounting.',
        'approval_reason': 'The pasted continuation excludes untrusted software execution, and CONTINUATION.md requires applicable container-provisioning authority. Approved48fa60c0 remains unused because it was withdrawn for an invalid multi-file premise and binds superseded source/dependencies; completed4cfc412d binds the prior observer/image and different sources. Earlier wheel/docs approvals also bind older artifacts. Routine finite definitions and scope amendments remain delegated.',
        'approval_rule': 'One explicit human approval covers these three raw component digests, one attempt each. No replay of a started component. Independent unstarted package/docs components may continue if grader execution fails, after all source/artifact checks.',
        'evidence_limits': ['Eight provisional tasks have a verified static3/3/2 family mix and234 required reference test identities, but no current-runtime result or model qualification. Full independent8/28/105 stages remain incomplete.',
            'Original upstream assertions remain, with two explicitly authored behavior checks. Leanclient is a documented source-only snapshot omitting unrelated docs/examples/CI; adapted Python3.13/pytest8.3.5 is not official benchmark-runtime equivalence. Source and wheel licenses remain private and retained.',
            'No comparative usefulness, token saving, monetary saving, automatic admission, production resource acceptance or selection improvement is inferred from these checks.'],
        'approved': False, 'execution_started': False}
    with (HERE / 'approval-bundle.json').open('x') as output:
        json.dump(bundle, output, indent=2);output.write('\n')
    print(json.dumps({'bundle_sha256': sha(HERE / 'approval-bundle.json'), 'source_digest': bundle['source_digest'], 'execution_started': False}))


if __name__ == '__main__':
    main()
