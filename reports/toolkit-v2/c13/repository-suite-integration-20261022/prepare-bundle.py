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
    checks = json.loads((HERE / 'validation-v2/source-stability.json').read_text())
    assert checks['all_passed'] and checks['source_unchanged'] and checks['source_digest'] == verification_source_digest(ROOT)
    assert json.loads((HERE / 'supplemental/summary.json').read_text())['all_passed']
    assert json.loads((HERE / 'grader-preparation-checks.json').read_text())['passed']
    package = ROOT / 'reports/toolkit-v2/integration-completion/package-review-repository-suites-20261022'
    docs = ROOT / 'reports/toolkit-v2/integration-completion/lychee-repository-suites-review-20261022'
    assert json.loads((docs / 'sandbox-preflight.json').read_text())['passed']
    actions = []
    for name, directory, review_name, runner_name, approval_name, marker, terminal, seconds, conditions in [
        ('grader', HERE, 'grader-operation-review.json', 'run-grader-review.py', 'grader-operator-approval.json',
         'grader-execution-started.json', 'grader-execution-result.json', 1200,
         {'passed': True, 'contained_calls_started': 12, 'source_unchanged': True,
          'canary_removed': True, 'containers_removed': True, 'ledger_operations': 14, 'elapsed_complete': True}),
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
        'purpose': 'Validate the reusable v5 repository pack against three real development issues, then check its actual wheel and public documentation. This enables corpus adoption; it is not a model comparison or release.',
        'permissions': '12 fresh offline containers through14 existing-grant operations, at most630 reserved seconds; current AEEP wheel plus32 unchanged cached dependencies and19 sandboxed installed checks; pinned cached Lychee0.24.2 offline docs check. Zero models, downloads, image builds/pulls, credentials, new destinations, cash, activation or release.',
        'cleanup': 'Remove only new attempt-owned containers, unchanged synthetic canary, private installed runtime/scratch and unchanged Lychee runtime. Retain inert caches, historical evidence, current/rollback images, volumes, backups, unrelated work and all accounting.',
        'approval_reason': 'The pasted continuation excludes untrusted software execution, and CONTINUATION.md requires applicable container-provisioning authority. Completed56ca1751 is terminal and binds the older one-case prototype; earlier wheel/docs approvals also bind older artifacts. Routine finite definitions and scope amendments remain delegated.',
        'approval_rule': 'One explicit human approval covers these three raw component digests, one attempt each. No replay of a started component. Independent unstarted package/docs components may continue if grader execution fails, after all source/artifact checks.',
        'evidence_limits': ['Three source-only single-file repairs are development calibration, not representative holdouts or capability qualification.',
            'Published non-source edits are excluded by explicit task scope. Marshmallow Python3.11 is adapted to3.13; no official upstream runtime equivalence.',
            'No comparative usefulness, token saving, monetary saving, automatic admission, production resource acceptance or selection improvement is inferred from these checks.'],
        'approved': False, 'execution_started': False}
    with (HERE / 'approval-bundle.json').open('x') as output:
        json.dump(bundle, output, indent=2);output.write('\n')
    print(json.dumps({'bundle_sha256': sha(HERE / 'approval-bundle.json'), 'source_digest': bundle['source_digest'], 'execution_started': False}))


if __name__ == '__main__':
    main()
