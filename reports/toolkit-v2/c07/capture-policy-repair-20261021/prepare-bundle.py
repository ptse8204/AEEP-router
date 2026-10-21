"""Freeze actual verified artifacts into one review; no third-party or worker execution."""
import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import digest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
COMMIT = '77077562e1a63d45791c478066affba35dd8d10d'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    assert not (OUT / 'approval-bundle.json').exists()
    stability = json.loads((OUT / 'validation/source-stability.json').read_text())
    source = verification_source_digest(ROOT)
    assert stability['all_passed'] and stability['source_unchanged'] and stability['source_digest'] == source
    metadata = json.loads((OUT / 'image-metadata-result.json').read_text())
    assert metadata['source_digest'] == source and metadata['passed']
    original = OUT.parent / 'capture-repair-20261019'
    ancestor = json.loads((original / 'collector-operation-review.json').read_text())
    collector = sha(ROOT / 'src/aeep/hosts/codex_metrics.py')
    builds = {}
    for role, item in metadata['images'].items():
        context = OUT / ('image-' + role)
        assert sha(context / 'codex_metrics.py') == collector
        assert (context / 'Dockerfile').read_text() == (
            'FROM ' + item['parent_reference'] + '\nCOPY --chown=0:0 --chmod=0444 codex_metrics.py /opt/aeep/codex_metrics.py\n')
        builds[role] = {**item, 'tag': 'aeep-toolkit-v2/capture-policy-20261021:' + role,
                        'dockerfile_sha256': sha(context / 'Dockerfile'), 'collector_sha256': collector}
    inputs = {str(path.relative_to(ROOT)): sha(path)
              for path in [*OUT.glob('*.py'), OUT / 'diagnostic-tasks.json', OUT / 'diagnostic-input-preflight.json',
                           OUT / 'image-metadata-result.json', OUT / 'regression-before.log', OUT / 'focused.log',
                           OUT / 'validation/checks.json', OUT / 'validation/source-stability.json',
                           ROOT / 'src/aeep/hosts/codex_metrics.py',
                           *OUT.glob('image-*/*'), *OUT.glob('validation/*.log')] if path.is_file()}
    review = {
        'purpose': 'One prospective test of the same-scope policy/telemetry launch correction, then up to four gated public capture tasks; no historical replay.',
        'source_commit': COMMIT, 'source_digest': source, 'collector_sha256': collector,
        'candidate_skill_sha256': ancestor['candidate_skill_sha256'],
        'grader_runtime_image': ancestor['additional_runtime_image'],
        'existing_proxy': {key: ancestor[key] for key in (
            'proxy_name', 'proxy_id', 'proxy_image', 'proxy_memory_bytes', 'network_id')},
        'model_and_effort': {'model_id': 'gpt-6-astra', 'reasoning_effort': 'medium'},
        'builds': builds, 'maximum_build_growth_bytes': 1024**3,
        'minimum_host_reserve_bytes': 50 * 1024**3, 'inputs': inputs,
        'prior_source_review': 'capture-local-parent-20261021: approved builds/collector denial passed; effective-policy and treatment inventory conformance failed. All failures/costs retained.',
        'source_change': 'Move only telemetry -c options before app-server, after the existing global policy options. Synthetic regressions verify this launch contract; actual installed Codex behavior is unverified until this review runs.',
        'actions': [
            'Build two COPY-only derivatives of the two exact already-local parent images. Validate name@digest and absent ONBUILD instructions first. No RUN, pull, dependency install or new destination. Each fresh worker starts only its reviewed private loopback collector.',
            'Resolve output image IDs and freeze exact current-source definitions under September25/27 authority. Tighten the inherited task timeout to the reviewed102-second cap in both arms.',
            'Run one fresh two-worker inspection: the unchanged11 probe groups plus denial against each actual collector endpoint. Both must pass before any model turn.',
            'Run the exact explicit-read-request pair first; complete token captures plus bound positive instruction loading gate the optional pair. Maximum4 task turns, no holdouts, new value study, admission or automatic retry.',
            'Restore the existing proxy stopped and remove only new transient workers/private security scratch. Retain output tags/IDs, parents, old records, volumes, backups and unrelated work.'
        ],
        'limits': {**ancestor['limits'], 'maximum_build_operations': 1, 'maximum_build_seconds': 360,
                   'maximum_builds': 2},
        'forbidden': ['Credential reading/copying/login', 'New hosted/persistent services, model destinations, paid calls or hosted telemetry',
                      'Changing source or dependencies during execution', 'More than4 task turns or automatic retries',
                      'Historical evidence/threshold changes', 'Image/volume/backup removal, activation, release, publication or pushing'],
        'approval_record': 'operator-approval.json; exact raw review hash, with explicit human wording and bundle lineage',
        'execution_started': False,
    }
    save(OUT / 'operation-review.json', review)
    package = ROOT / 'reports/toolkit-v2/integration-completion/package-review-policy-20261021'
    if not (package / 'operation-review.json').exists():
        subprocess.run([sys.executable, str(package / 'prepare-review.py')], cwd=ROOT, check=True)
    package_review = json.loads((package / 'operation-review.json').read_text())
    assert package_review['source_digest'] == source and package_review['source_commit'] == COMMIT
    preview = subprocess.run([sys.executable, str(package / 'run_review.py')], cwd=ROOT,
                             capture_output=True, text=True, check=True)
    save(package / 'execution-preflight.json', json.loads(preview.stdout))
    lychee = ROOT / 'reports/toolkit-v2/integration-completion/lychee-policy-review-20261021'
    actions = [
        {'name': 'collector', 'review': OUT / 'operation-review.json', 'runner': OUT / 'run-repair.py',
         'maximum_seconds': 3600, 'terminal_result': OUT / 'execution-result.json',
         'pass_conditions': {'build_passed': True, 'collector_passed': True, 'diagnostics_passed': True,
                             'diagnostic_records': 4, 'proxy_restored_stopped': True}},
        {'name': 'package', 'review': package / 'operation-review.json', 'runner': package / 'run_review.py',
         'maximum_seconds': 1800, 'terminal_result': package / 'execution/summary.json',
         'pass_conditions': {'installed_cli_checks': 15, 'installed_capture_checks': 1,
                             'runtime_removed': True, 'private_scratch_removed': True}},
        {'name': 'documentation', 'review': lychee / 'operation-review.json', 'runner': lychee / 'run-review.py',
         'maximum_seconds': 240, 'terminal_result': lychee / 'execution-result.json',
         'pass_conditions': {'passed': True, 'immutable_runtime_unchanged': True, 'runtime_removed': True}},
    ]
    for action in actions:
        action['review_sha256'] = sha(action['review'])
        action['started_marker'] = 'execution-started.json'
        for field in ('review', 'runner', 'terminal_result'):
            action[field] = str(action[field].relative_to(ROOT))
    bundle = {'schema_version': 'aeep.operator-review-bundle.v1', 'source_commit': COMMIT,
              'source_digest': source, 'runner_sha256': sha(OUT / 'execute-bundle.py'), 'actions': actions,
              'purpose': 'Complete this source-bound correction with one exact execution review. The package and docs checks continue independently after collector failure.',
              'permissions': 'Collector:2 COPY-only images, fresh no-model conformance, at most4 existing-grant task turns. Package:33 exact cached wheels, no downloads,16 offline checks, owned removal. Docs:same pinned cached Lychee0.24.2,67 files,network/home denied,owned removal.',
              'outside_scope': ['Authentication intervention','New paid/model/telemetry destinations','Historical study replay or evidence-policy changes','Release, activation, publication or retained-resource cleanup'],
              'why_approval_required': 'The preceding exact reviews bind the earlier collector bytes and wheel. The user continuation excludes unreviewed software execution, and CONTINUATION.md requires applicable image/service authority. This bundle binds the changed collector and installed artifact; routine finite definitions/budget amendments remain delegated. No architecture, dependency or new spending decision is requested.',
              'approval_rule': 'Explicit approval of this raw bundle digest covers precisely the three listed raw component digests. Preserve actual human wording in bundle-operator-approval.json before executing.',
              'approved': False, 'execution_started': False}
    save(OUT / 'approval-bundle.json', bundle)
    for path in [*OUT.glob('*.py'), *package.glob('*.py'), *lychee.glob('*.py')]:
        ast.parse(path.read_text())
    save(OUT / 'bundle-preflight.json', {'bundle_sha256': sha(OUT / 'approval-bundle.json'),
         'collector_inputs_verified': len(inputs), 'source_unchanged': verification_source_digest(ROOT) == source,
         'installed_wheel_execution': False, 'package_policy_argument_digest': digest(package_review),
         'workers_or_models_started': False})
    print(json.dumps({'bundle_sha256': sha(OUT / 'approval-bundle.json'), 'actions': len(actions)}))


if __name__ == '__main__':
    main()
