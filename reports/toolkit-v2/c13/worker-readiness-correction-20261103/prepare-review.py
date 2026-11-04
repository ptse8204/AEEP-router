"""Freeze the concrete continuation, installed-wheel and docs review; no execution."""
import ast
import importlib.util
import json
import shutil
import sqlite3
from pathlib import Path

import integration as prepared
import run
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, digest

HERE, ROOT = prepared.HERE, prepared.ROOT
assert not (HERE / 'operation-review.json').exists()
for name in ('preparation-controls.json', 'packaging-controls.json', 'controller-controls.json', 'task-delivery-controls.json'):
    assert prepared.load(HERE / name)['passed']
source = verification_source_digest(ROOT)
checks_path = HERE / 'verification/checks.json'
checks = prepared.load(checks_path)
assert checks['source_before'] == checks['source_after'] == source
assert len(checks['checks']) == 13 and all(row['exit_code'] == 0 for row in checks['checks'])
context = prepared.load(HERE / 'context.json')
assert context['source'] == source
assert prepared.snapshot(prepared.RUNTIME) == context['runtime_tree_sha256']
assert not prepared.SCHEDULER_WORK.exists()
site = prepared.RUNTIME / 'lib/python3.13/site-packages/aeep_toolkit'
for name in ('ase_child.py', 'ase_contract.py'):
    assert prepared.sha(site / name) == prepared.sha(ROOT / 'src/aeep_toolkit' / name)
old = prepared.load(prepared.OLD / 'operation-review.json')
assert prepared.sha(prepared.OLD / 'operation-review.json') == 'b01793ac8e3baa0bb9d723e32498813ea224eb0672a95c51090764fc598a9600'
assert prepared.load(prepared.OLD / 'execution-result.json')['grant_after'][1] == old['grant_baseline_read_only']['model_turns']
parent = json.loads(run.docker('image', 'inspect', '--format', old['image_format'], prepared.PARENT_TAG))
assert parent == old['parent_metadata']
assert not run.docker('images', '-q', prepared.TAG)
assert run.docker('image', 'inspect', '--format', '{{.Id}}', prepared.GRADER) == prepared.GRADER
observed = json.loads(run.docker('inspect', '--format', old['proxy_inspect_format'], old['proxy_name']))
assert observed == old['proxy_metadata'] and not observed['Running']
assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
prepared.write(HERE / 'docker-preparation.json', {'usage': run.docker('system', 'df', '--format', 'json'),
    'host_free_bytes': shutil.disk_usage(ROOT).free, 'resources_changed': False})
plan = RuntimeInstallation.model_validate(prepared.load(HERE / 'package-installation.json'))
package = prepared.load(HERE / 'package-preparation.json')
assert digest(plan) == package['installation_digest'] and len(plan.wheels) == 33 and plan.storage_exception is None
package.update(runtime=plan.destination, prepared_workspace_sha256=prepared.snapshot(HERE / 'package-execution/work'),
    attempts=1, retained=True, execution=False)
docs_parent = prepared.load(HERE.parent / 'ase-runtime-contract-20261103/operation-review.json')
docs = docs_parent['docs']
docs['maximum_attempts'] = 2
docs['permitted_correction'] = 'At most two offline invocations with these same exact inputs, tools, config and sandbox. No source or tool repair/replacement. Stop after success; retain every failed result.'
docs['normalized_input_hashes'] = {}
modspec = importlib.util.spec_from_file_location('reviewed_components', HERE / 'run-components.py')
components = importlib.util.module_from_spec(modspec)
modspec.loader.exec_module(components)
assert components.tools_state(Path(docs['runtime'])) == prepared.load(Path(docs['runtime_record']))['files']
assets = {}
for path in HERE.rglob('*'):
    if not path.is_file() or '__pycache__' in path.parts or path.name in {'operation-review.json', 'review-preflight.json'}:
        continue
    if path.name.startswith('.') or 'dist' in path.parts or 'package-execution' in path.parts:
        continue
    if path.suffix == '.py':
        ast.parse(path.read_text())
    assets[str(path.resolve())] = prepared.sha(path)
for name in docs['documents']:
    assets[str(ROOT / name)] = prepared.sha(ROOT / name)
for path in (ROOT / 'Makefile', ROOT / '.markdownlint-cli2.jsonc', ROOT / '.lychee.toml',
        Path(docs['runtime_record']), run.BASE / 'aeep.json', prepared.TOOLS / 'git',
        HERE.parent / 'repository-usefulness-pilot-20261029/review-budget.py',
        HERE.parent / 'repository-usefulness-pilot-20261029/run-collector.py',
        HERE.parent / 'repository-usefulness-pilot-20261029/trial-evidence.py',
        *[prepared.OLD / name for name in ('run.py', 'prepare.py', 'context.json', 'pair-base.json',
            'recipe-base.json', 'task.json', 'operation-review.json', 'execution-started.json', 'execution-result.json')],
        *[prepared.WORK / 'build-context' / name for name in ('Dockerfile', 'candidate/SKILL.md', 'candidate/LICENSE')]):
    assets[str(path)] = prepared.sha(path)
assets.update(prepared.scheduler().executable_dependencies)
assets.update(docs['executable_dependencies'])
for wheel in plan.wheels:
    assets[str(Path(plan.wheelhouse) / wheel.filename)] = wheel.sha256
for case in prepared.recipe().generator_config['cases']:
    truth = case['truth']
    for record in [truth['source'], truth['tests'], *truth['wheels'], case['reference']]:
        path = Path(record['path'])
        assert path.stat().st_size == record['size_bytes'] and prepared.sha(path) == record['sha256']
        assets[str(path)] = record['sha256']
with sqlite3.connect((run.BASE / 'aeep.sqlite3').as_uri() + '?mode=ro', uri=True) as connection:
    before = connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone()
    cost = connection.execute("SELECT digest FROM assessment_records WHERE kind='setup_cost' AND id='setup_cost_42230aae382b4717a11f0b76ac87ec28'").fetchone()
    scope = connection.execute("SELECT digest FROM assessment_records WHERE kind='recipe_materialization_request' AND id='ase-stack-owned-build-20261103'").fetchone()
    assert not connection.execute("SELECT 1 FROM assessment_operations WHERE id='setup_cost_42230aae382b4717a11f0b76ac87ec28'").fetchone()
review = {**{key: old[key] for key in ('proxy_name', 'proxy_id', 'proxy_image', 'proxy_memory_bytes', 'network_id',
        'proxy_inspect_format', 'image_format', 'public_model_task', 'public_source_archive', 'protected_calibration_tasks')},
    'purpose': 'Corrected ordinary readiness and two separately selected evaluator engineering journeys; independent current-wheel and offline docs checks. No comparative campaign.',
    'source_digest': source, 'source_checks': str(checks_path), 'assets': assets,
    'parent_metadata': parent, 'proxy_metadata': observed, 'output_image_tag': prepared.TAG,
    'build': 'One local --pull=false --network=none build from retained original control. Exactly two COPYs and three existing /bin mkdir/chmod/ln RUNs; no install/download. Final0555directories/0444files/nonroot identity and canonical native skill symlink. Inspect only five new layer headers and the two public reviewed files before workers; no archive retained.',
    'candidate_source': prepared.load(HERE / 'source.json'),
    'runtime': str(prepared.RUNTIME), 'runtime_tree_sha256': context['runtime_tree_sha256'],
    'ASE_revision': prepared.ASE_REVISION, 'ASE_wheel_sha256': prepared.ASE_ARTIFACT,
    'runtime_scope': context['runtime_scope'], 'engines': ['agent-skill-eval', 'managed'],
    'maximum_model_turns': 2, 'maximum_operations': 144, 'maximum_reserved_seconds': 6200,
    'cash_usd': 0, 'minimum_free_bytes': 50*1024**3, 'review_expires_at': '2026-11-05T12:00:00Z',
    'original_cumulative_anchor': prepared.load(prepared.OLD / 'execution-started.json')['grant_before'],
    'current_grant_read_only': before,
    'budget_basis': 'Original cumulative envelope, never reset: four prior operations remain charged. Inert upper projections68+67campaign operations, four new build/pair/wrapper operations and one measured historical static-inspection settlement total144 including the old four. Each actual canonical preview and reservation must fit before dispatch; otherwise stop. Conservative reserved seconds fit6200; not a duration estimate.',
    'historical_static_inspection': {'cost_id': 'setup_cost_42230aae382b4717a11f0b76ac87ec28', 'cost_digest': cost[0],
        'request_id': 'ase-stack-owned-build-20261103', 'request_digest': scope[0], 'elapsed_seconds': .0025820829905569553},
    'phases': ['Validate source/approval/artifacts/storage/retained parent/proxy; start one fresh bounded attempt and guard the ORIGINAL cumulative ledger.',
        'Settle the recorded historical static inspection once under its original exact scope. Keep all old costs/reservations unchanged.',
        'Build one corrected image, bind actual produced digest and new-layer metadata; keep the old failed image and all other resources.',
        'Fresh paired inspection and collector denial. Preserve partial failures and both journals; failed or uncertain readiness prevents model execution.',
        'Ordinary workflow prepare-worker-readiness, then existing delegated exact operator review and require_conformance/require_candidate_access checks. No readiness self-approval.',
        'Ordinary eval managed run: one real ASE-scheduled controlled task, then one separately selected managed-engine task. No automatic engine switch; one turn each, existing protected calibration before dispatch.',
        'Verify canonical task/prompt/grading/token categories/positive loading/zero retries/accounting/cleanup after each turn before continuing. Pass or fail are valid grades; unknown observations stop.',
        'Stop the owned proxy back to its original state. Retain images/runtimes/receipts and old failures.',
        'Independent current-wheel installation/checks and exact cached offline docs checks; no terminal successful check is repeated.'],
    'package': package, 'docs': docs,
    'accounting': 'Original ledger with raw costs and counters. Wrapper overhead excludes nested canonical execution and measured setup intervals. Missing costs never become zero; complete product-wide accounting remains an open gate. Package commands retain canonical receipts separately; docs retain actual engineering timings.',
    'disclosure': old['disclosure'].replace('neutral repository-authored skill', 'exact nonrecursive stack-check repository-authored skill'),
    'recovery': 'No automatic replay of a started worker, scheduler or model task. Preserve partial effects/charges and stop dependent work on uncertain accounting, cleanup or authority. Independent package/docs remain eligible after a settled component failure; common uncertainty stops dispatch.',
    'routine_unstarted_corrections': 'Standing delegation permits exact recorded first-party bookkeeping/definition corrections for UNSTARTED phases inside this original anchor/envelope. No upstream/candidate/task/test/reference/permission/model/destination changes or repeated started engine attempt. Package has one install/check attempt; docs permit at most two exact-input offline invocations. No refunds or larger ceilings.',
    'not_authorized': ['Downloads, pulls, new dependencies, credential reading/copying, new providers/destinations or cash.',
        'Deleting images/volumes/backups, host activation, unreviewed services, admission, publication or release.',
        'Any comparative campaign, formal qualification claim, threshold change, old successful source/SDK/scanner replay, or inferred savings.'],
    'all_stack_complete': False, 'both_SkillsBench_journeys_complete': False,
    'candidate_usefulness': 'NOT_ASSESSED', 'selection_usefulness': 'NOT_ASSESSED', 'comparisons': 'PAUSED', 'automatic_engine_retry': False,
    'approval_reason': 'The b01793ac worker attempt is terminal. This changes the candidate name/native alias/image commands, rechecks workers on verified current readiness code, and installs a changed wheel. Earlier exact reviews bind the older artifacts and cannot authorize this correction. CONTINUATION.md and the user continuation reserve untrusted installation/execution/provisioning authority. No architecture or budget decision is needed.'}
prepared.write(HERE / 'operation-review.json', review)
print(json.dumps({'review_sha256': prepared.sha(HERE / 'operation-review.json'), 'assets': len(assets),
    'cumulative_operations': 144, 'model_turns': 2, 'private_wheels': 33, 'docs_inputs': len(docs['documents']), 'execution': False}))
