"""Freeze actual prepared component artifacts; do not execute them."""
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
    assert json.loads((HERE / 'validation-v2/source-stability.json').read_text())['all_passed']
    package = ROOT / 'reports/toolkit-v2/integration-completion/package-review-repository-audit-20261021'
    docs = ROOT / 'reports/toolkit-v2/integration-completion/lychee-repository-audit-review-20261021'
    assert json.loads((docs / 'sandbox-preflight.json').read_text())['passed']
    actions = []
    for name, directory, review_name, runner_name, approval_name, marker, terminal, seconds, conditions in [
        ('grader', HERE, 'grader-operation-review.json', 'run-grader-review.py', 'grader-operator-approval.json',
         'grader-execution-started.json', 'grader-execution-result.json', 1800,
         {'passed': True, 'contained_calls_started': 23, 'source_unchanged': True,
          'host_canary_removed': True, 'containers_removed': True, 'ledger_operations': 25, 'elapsed_complete': True}),
        ('package', package, 'operation-review.json', 'run_review.py', 'operator-approval.json',
         'execution-started.json', 'execution/summary.json', 1800,
         {'installed_cli_checks': 17, 'installed_capture_checks': 1, 'runtime_removed': True, 'private_scratch_removed': True}),
        ('documentation', docs, 'operation-review.json', 'run-review.py', 'operator-approval.json',
         'execution-started.json', 'execution-result.json', 240,
         {'passed': True, 'immutable_runtime_unchanged': True, 'runtime_removed': True})]:
        review = directory / review_name
        argument = digest(json.loads(review.read_text())) if name == 'package' else sha(review)
        argv = [sys.executable, str(directory / runner_name)]
        argv += ['--execute-reviewed-digest', argument] if name == 'package' else [argument]
        actions.append({'name': name, 'review': str(review.relative_to(ROOT)), 'review_sha256': sha(review),
            'runner': str((directory / runner_name).relative_to(ROOT)), 'runner_sha256': sha(directory / runner_name),
            'argv': argv, 'approval_record': str((directory / approval_name).relative_to(ROOT)),
            'started_marker': str((directory / marker).relative_to(ROOT)),
            'terminal_result': str((directory / terminal).relative_to(ROOT)), 'maximum_seconds': seconds,
            'pass_conditions': conditions})
    bundle = {'schema_version': 'aeep.operator-review-bundle.v1', 'source_digest': verification_source_digest(ROOT),
        'runner_sha256': sha(HERE / 'run-bundle.py'), 'actions': actions,
        'purpose': 'Complete protected grader conformance after correcting the receipt audit, and validate the adapter-boundary fix from the changed wheel; no model campaign or release.',
        'permissions': '23 offline contained observations through 25 existing-grant operations, at most 1240 reserved seconds; 33 cached wheels and 18 sandboxed offline installed checks; pinned cached Lychee 0.24.2 offline documentation scan. No downloads, builds/pulls of images, model proxy, model turns, credentials, external services, cash, activation, publication or retained-resource deletion.',
        'approval_reason': 'The pasted continuation excludes untrusted software execution; CONTINUATION.md requires applicable container-provisioning authority. Earlier exact bundles are terminal and bind older artifacts. Routine definition review and finite grant scope amendments remain delegated; counters are preserved.',
        'approval_rule': 'One explicit human approval covers these three raw component digests, one execution attempt each. Do not replay a started component. A dispatcher failure does not revoke an unstarted independent component; it may run under this same approval after source/artifact checks.',
        'previous_failed_attempt': 'Bundle 0d992ca9 grader review stopped after 1 observation because its audit expected omitted receipt metadata. The canonical attempt is COMPLETED and its derived owned container is absent. Preserve that failure and its 3 charges; this is one fresh source-bound correction attempt, never a replay of the previous plan ID.',
        'audit_regression': 'receipt-audit-regression.json passes six checks against the actual minimized receipt, including five rejected misbindings. check_assessment_policy.py now passes with provider validation owned by the host registry.',
        'approved': False, 'execution_started': False}
    (HERE / 'approval-bundle.json').write_text(json.dumps(bundle, indent=2) + '\n')
    print(json.dumps({'bundle_sha256': sha(HERE / 'approval-bundle.json'), 'source_digest': bundle['source_digest'], 'execution_started': False}))


if __name__ == '__main__':
    main()
