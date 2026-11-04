"""Freeze a bounded engineering review. Metadata only; no service/model start."""
import ast
import json
import shutil
import sqlite3
from pathlib import Path

import prepare
import run

HERE, ROOT = prepare.HERE, prepare.ROOT
assert not (HERE / 'operation-review.json').exists()
for name in ('preparation-controls.json', 'native-controls.json', 'task-delivery-controls.json', 'controller-controls.json'):
    assert prepare.load(HERE / name)['passed']
context = prepare.load(HERE / 'context.json')
assert run.verification_source_digest(ROOT) == context['source']
checks_path = HERE.parent / 'coverage-completion-20261103/verification/checks.json'
checks = prepare.load(checks_path)
assert checks['source_before'] == checks['source_after'] == context['source']
assert len(checks['checks']) == 13 and all(row['exit_code'] == 0 for row in checks['checks'])
assert prepare.snapshot(prepare.RUNTIME) == context['runtime_tree_sha256']
assert not prepare.SCHEDULER_WORK.exists()
image_format = '{"Id":{{json .Id}},"Layers":{{json .RootFS.Layers}},"Size":{{json .Size}},"User":{{json .Config.User}},"Workdir":{{json .Config.WorkingDir}},"Entrypoint":{{json .Config.Entrypoint}}}'
parent = json.loads(run.docker('image', 'inspect', '--format', image_format, prepare.PARENT_TAG))
assert parent['Id'] == prepare.PARENT_ID
assert not run.docker('images', '-q', prepare.TAG)
assert run.docker('image', 'inspect', '--format', '{{.Id}}', prepare.GRADER) == prepare.GRADER
old = prepare.load(HERE.parent / 'repository-usefulness-pilot-20261029/collector-operation-review.json')
proxy_keys = ('proxy_name', 'proxy_id', 'proxy_image', 'proxy_memory_bytes', 'network_id', 'proxy_inspect_format')
proxy = {key: old[key] for key in proxy_keys}
observed = json.loads(run.docker('inspect', '--format', proxy['proxy_inspect_format'], proxy['proxy_name']))
assert observed['Id'] == proxy['proxy_id'] and observed['Image'] == proxy['proxy_image'] and not observed['Running']
assert observed['Memory'] == observed['MemorySwap'] == proxy['proxy_memory_bytes']
assert proxy['network_id'] in {item['NetworkID'] for item in observed['Networks'].values()}
free = shutil.disk_usage(ROOT).free
assert free >= 50 * 1024**3
assets = {}
for path in HERE.rglob('*'):
    if (path.is_file() and '__pycache__' not in path.parts
            and 'preparation-history' not in path.parts
            and path.name not in {'operation-review.json', 'review-preflight.json'}):
        if path.suffix == '.py':
            ast.parse(path.read_text())
        assets[str(path)] = prepare.sha(path)
for path in [checks_path, run.BASE / 'aeep.json', prepare.WORK / 'tools/git',
        HERE.parent / 'repository-usefulness-pilot-20261029/review-budget.py',
        HERE.parent / 'repository-usefulness-pilot-20261029/run-collector.py',
        HERE.parent / 'repository-usefulness-pilot-20261029/trial-evidence.py',
        *[prepare.WORK / 'build-context' / name for name in ('Dockerfile', 'candidate/SKILL.md', 'candidate/LICENSE')]]:
    assets[str(path)] = prepare.sha(path)
assets.update(prepare.scheduler().executable_dependencies)
for case in prepare.recipe().generator_config['cases']:
    truth = case['truth']
    for record in [truth['source'], truth['tests'], *truth['wheels'], case['reference']]:
        path = Path(record['path'])
        assert path.stat().st_size == record['size_bytes'] and prepare.sha(path) == record['sha256']
        assets[str(path)] = record['sha256']
assert all(prepare.sha(Path(name)) == digest for name, digest in assets.items())
with sqlite3.connect((run.BASE / 'aeep.sqlite3').as_uri() + '?mode=ro', uri=True) as connection:
    grant = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'),
        connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()))
review = {
    **proxy, 'purpose': 'Two frozen evaluator engineering checks through ordinary eval managed CLI; no comparative campaign',
    'source_digest': context['source'], 'source_checks': str(checks_path), 'assets': assets,
    'engines': ['agent-skill-eval', 'managed'], 'image_format': image_format,
    'parent_metadata': parent, 'proxy_metadata': observed,
    'output_image_tag': prepare.TAG, 'build': 'One local --pull=false --network=none build; three COPY-only layers and no RUN. Exact context contains only Dockerfile and neutral SKILL.md/LICENSE. Verify inherited layers/configuration and bind produced ID before workers.',
    'runtime': str(prepare.RUNTIME), 'runtime_tree_sha256': context['runtime_tree_sha256'],
    'ASE_revision': prepare.ASE_REVISION, 'ASE_wheel_sha256': prepare.ASE_ARTIFACT,
    'runtime_scope': 'Installed ASE child/contract match current source; read helper retains its proven equivalence. Other installed AEEP modules retain older scope. No reinstall.',
    'candidate_source': prepare.load(HERE / 'source.json'),
    'public_model_task': {key: prepare.load(HERE / 'task.json')[key]
        for key in ('source_repository', 'source_revision', 'independent_case_id', 'license', 'origin_kind')},
    'public_source_archive': prepare.load(HERE / 'task.json')['truth']['source'],
    'protected_calibration_tasks': [case['independent_case_id'] for case in prepare.recipe().generator_config['cases']],
    'maximum_model_turns': 2, 'maximum_operations': 144, 'maximum_reserved_seconds': 6200,
    'maximum_task_seconds': 300, 'cash_usd': 0, 'minimum_free_bytes': 50 * 1024**3,
    'review_expires_at': '2026-11-05T12:00:00Z', 'grant_baseline_read_only': grant,
    'budget_basis': 'Existing calculator: 68/67 operations and about2585/2525 reserved seconds for ASE/managed, plus one build180, two inspections480 and exclusive proxy overhead120. 135 projected campaign operations plus4 extra gives139; ceiling144 includes five operations of bookkeeping headroom; actual remaining grant and exact preview must pass before each CLI. These are ceilings, not expected times.',
    'accounting': 'Use original onboarding grant, counters and durable operation/attempt records. No reset. SDK and controller wall overhead exclude nested canonical execution; setup intervals are excluded from wrapper timing. Preserve partial charges and two old unresolved reservations. Engineering auxiliary accounting is linked in result, not claimed as complete composed product accounting.',
    'phases': [
        'Verify approval, source gates, files, actual50GiB space, local parent/grader and stopped proxy metadata. Record current original grant baseline; no credential or volume contents are read.',
        'Build one exact COPY-only image, bind its ID and inherited layer/configuration checks. Keep it. Derive the reviewed generic skill profile only by substituting this produced digest.',
        'Start the existing pinned proxy; verify its existing private destination. Fresh paired inspection requires11groups per role plus collector denial, with canonical costs and owned-container cleanup. Stop on uncertainty before models.',
        'Prepare exact one-task required-use engineering plans using existing service/IntegrationCaseSet and canonical scope reviews under standing finite delegation. Freeze ASE versus managed before dispatch. No automatic engine switch.',
        'Run normal eval managed CLI with the explicit ASE scheduler on one public task, then the separately selected managed engine on that task. Each plan validates its three protected calibration cases before its one task turn. Two model reservations maximum, no retries.',
        'Reopen canonical task, prompt, protected grade, zero-retry, token-capture, positive-loading and cleanup evidence before proceeding. A failed task stays a failed result. Missing/uncertain effects, usage, grading or cleanup stop dispatch.',
        'Restore the existing proxy stopped, retain all images/runtimes/receipts and reports. Never admit, activate, qualify, replay historical tasks or claim candidate/selection value from these observations.',
    ],
    'disclosure': 'Only the exact public Python-Markdownify source/task and neutral repository-authored skill may reach the existing Codex destination on gpt-6-astra/medium. Protected tests, reference answers, calibration-only cases, other files and credentials remain outside model workers. Codex owns authentication.',
    'not_authorized': ['No installs, downloads, image pulls, provider changes, new destinations, paid calls or credential reads/copies.',
        'No image/volume/backup deletion, host configuration change, unreviewed server, activation, admission, publication or release.',
        'No Ponytail/Ruff/LibCST/candidate-value/selection campaign, corpus expansion, formal threshold change, package/docs/source-suite replay or inferred savings.'],
    'recovery': 'No automatic replay of started/uncertain workers, SDK turns or engine plans. Retain their costs and attempt records. Any uncertain common authority/accounting/cleanup stops all dependent dispatch; other safe integration implementation remains eligible.',
    'routine_unstarted_corrections': 'Standing delegation permits exact recorded first-party bookkeeping/definition corrections for unstarted phases within this original cumulative anchor and ceilings. It does not permit changing upstream code, task/test/reference bytes, worker permissions, candidate, model/destination; retrying started upstream/model execution; refunding charges; or enlarging this envelope.',
    'all_stack_complete': False, 'both_SkillsBench_journeys_complete': False,
    'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED',
    'comparisons': 'PAUSED', 'automatic_retry': False,
    'approval_reason': 'The approved85ba0df6 allowed zero models and no Docker changes or service start. This new candidate image, actual workers, public model disclosure and real task execution require applicable authorization under the user continuation and docs/aeep-toolkit/CONTINUATION.md. No architecture decision is needed.',
}
prepare.write(HERE / 'operation-review.json', review)
prepare.write(HERE / 'review-preflight.json', {'passed': True,
    'review_sha256': prepare.sha(HERE / 'operation-review.json'), 'bound_assets': len(assets),
    'free_bytes': free, 'actual_model_or_worker_operations': 0, 'builds_or_services_started': 0,
    'source_unchanged': True, 'all_stack_complete': False})
print(json.dumps(prepare.load(HERE / 'review-preflight.json')))
