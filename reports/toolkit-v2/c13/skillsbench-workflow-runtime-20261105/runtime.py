"""Package exact SkillsBench task files through the ordinary owned installer."""

from __future__ import annotations

import argparse
import importlib.util
import json
import shutil
from datetime import datetime
from pathlib import Path

from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.benchmarks import BenchmarkPack, task_input
from aeep_toolkit.file_runtime import FileRuntimeInstallation, RuntimeFile, prepare_files
from aeep_toolkit.install_runtime import snapshot
from aeep_toolkit.installation import PreviewPolicy, manifest_digest, preview
from aeep_toolkit.models import ExtensionRegistry
from aeep_toolkit.workflow import StackWorkflow
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_runtime import lifecycle_preview

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'skillsbench-managed-worker-preparation-20261105'
spec = importlib.util.spec_from_file_location('approved_workflow_helpers', PRIOR / 'run-engineering.py')
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)
WORK = driver.ROOT / '.aeep' / HERE.name
SOURCE = driver.prepared.DEFINITIONS / 'task-only-pack.json'
PRIVATE_ORIGINAL = driver.ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
WORKFLOW = WORK / 'workflow.json'
ACCOUNTING = WORK / 'accounting.json'
SCOPES = {'document-data': 'sales-pivot-analysis', 'software-engineering': 'spring-boot-jakarta-migration',
          'sales-removal-check': 'sales-pivot-analysis'}


class Scope(StrictModel):
    review_sha256: str
    purpose: str


def emit(name, value):
    driver.prepared.write(HERE / name, value)


def make_definitions():
    source = driver.check_review()
    original = driver.prepared.read(driver.prepared.DEFINITIONS / 'workflow.json')
    pack = BenchmarkPack.model_validate_json(SOURCE.read_bytes())
    source_files = tuple({asset.path for task in set(SCOPES.values()) for asset in pack.task(task).assets})
    WORK.mkdir(mode=0o700)
    carrier = WORK / 'verified-input'
    carrier.mkdir(mode=0o700)
    (WORK / 'owned').mkdir(mode=0o700)
    shutil.copyfile(SOURCE, carrier / 'pack.json')
    for relative in sorted(source_files):
        dest = carrier / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(PRIVATE_ORIGINAL / relative, dest)
    # Use the existing ordinary workflow's explicitly reviewed component metadata.
    initial = driver.prepared.read(driver.WORK / 'engineering-registry.json')
    policy = driver.prepared.read(driver.WORK / 'engineering-policy.json')
    registry = ExtensionRegistry.model_validate(initial)
    for row in initial['extensions']:
        if row['extension_id'] == 'skillsbench':
            row['source']['artifact_sha256'] = driver.prepared.sha(SOURCE)
            row['purpose'] = 'Private owned copy of the selected pinned SkillsBench task assets'
            row['install_effects'] = ['Copy the exact pack and selected task assets into a private directory.']
            row['rollback'] = 'Remove only an unchanged owned task-file installation.'
    registry = ExtensionRegistry.model_validate(initial)
    policy['reviewed_dependency_manifests'].append(manifest_digest(registry.get('skillsbench')))
    policy['free_disk_bytes'] = shutil.disk_usage(WORK).free
    policy_model = PreviewPolicy.model_validate(policy)
    closure = preview(registry, ('skillsbench',), policy_model, profile='full')
    registry_path, policy_path = WORK / 'registry.json', WORK / 'policy.json'
    driver.prepared.write(registry_path, initial)
    driver.prepared.write(policy_path, policy)
    configurations = {}
    installation_refs = {}
    for configuration, task_id in SCOPES.items():
        root = WORK / 'owned' / configuration
        files = [RuntimeFile(extension_id='skillsbench', source='pack.json', destination='pack.json',
            primary=True, sha256=driver.prepared.sha(SOURCE), size_bytes=SOURCE.stat().st_size)]
        files.extend(RuntimeFile(extension_id='skillsbench', source=asset.path, destination=asset.path,
            sha256=asset.sha256, size_bytes=asset.bytes) for asset in pack.task(task_id).assets)
        install = prepare_files(closure, policy_model, root, carrier, tuple(files))
        path = WORK / f'{configuration}-installation.json'
        driver.prepared.write(path, install.model_dump(mode='json'))
        installation_refs[configuration] = driver.binding(path)
        base = original['configurations']['software-engineering' if configuration=='software-engineering' else 'document-data']
        configurations[configuration] = base | {
            'asset_root': str(root), 'runtimes': {'task-assets': {'installation': installation_refs[configuration],
                'components': {'skillsbench': 'skillsbench'}}},
        }
    workflow = StackWorkflow.model_validate(original | {'registry': driver.binding(registry_path),
        'policy': driver.binding(policy_path), 'configurations': configurations})
    driver.prepared.write(WORKFLOW, workflow.model_dump(mode='json'))
    manifest = WORK / 'aeep.json'
    ledger = WORK / 'receipts.sqlite3'
    driver.prepared.write(manifest, {'version': '0.2', 'database': str(ledger), 'executors': []})
    actions = [(name, stage, lifecycle_preview(WORKFLOW, name, ('task-assets',), operation=stage)[0]['review_sha256'])
               for name, stages in (
                   ('document-data', ('setup', 'readiness')), ('software-engineering', ('setup', 'readiness')),
                   ('sales-removal-check', ('setup', 'remove'))) for stage in stages]
    for _, _, digest in actions:
        assert len(digest) == 64
    review = {'purpose': 'First ordinary CLI lifecycle of the two exact SkillsBench task-file packages.',
        'authority_sha256': driver.prepared.sha(HERE.parent / 'pipeline-standing-authority-20261104.json'),
        'source_sha256': source['source_sha256'], 'expires_at': source['grant']['time_only_amendment']['expires_at'],
        'workflow': driver.binding(WORKFLOW), 'registry': driver.binding(registry_path), 'policy': driver.binding(policy_path),
        'manifest': driver.binding(manifest), 'ledger': str(ledger), 'installations': installation_refs,
        'actions': actions, 'max_operations': len(actions), 'max_overhead_seconds': 45, 'models': 0, 'cash_usd': '0',
        'no_docker_effects': True, 'only_remove_unreferenced_disposable_copy': True,
        'original_private_sources_preserved': True, 'runner_sha256': driver.prepared.sha(HERE / 'runtime.py')}
    emit('operation-review.json', review)
    print(driver.prepared.sha(HERE / 'operation-review.json'))


def verify(pinned, identity):
    assert pinned['runner_sha256'] == driver.prepared.sha(HERE / 'runtime.py')
    assert pinned['source_sha256'] == driver.check_review()['source_sha256']
    assert pinned['authority_sha256'] == driver.prepared.sha(HERE.parent / 'pipeline-standing-authority-20261104.json')
    assert shutil.disk_usage(WORK).free >= driver.RESERVE and utc_now() < datetime.fromisoformat(pinned['expires_at'])
    references = [pinned[k] for k in ('workflow', 'registry', 'policy', 'manifest')] + list(pinned['installations'].values())
    assert all(driver.prepared.sha(ref['path']) == ref['sha256'] for ref in references)
    limits = AssessmentLimits(max_operations=pinned['max_operations'],
                              max_elapsed_seconds=pinned['max_overhead_seconds'] * pinned['max_operations'])
    scope = Scope(review_sha256=identity, purpose=pinned['purpose'])
    ref = content_digest(scope)
    grant = AssessmentAuthorization(authorization_id=HERE.name,
        subject_digests=[ref], recipe_digests=[ref], environment_digests=[ref], limits=limits,
        expires_at=datetime.fromisoformat(pinned['expires_at']), allowed_destinations=['local'], remote_disclosure=False)
    request = RecipeMaterializationRequest(plan_id=grant.authorization_id, subject_digest=ref, recipe_digest=ref,
        mapping_digest=ref, environment_digest=ref, authorization_id=grant.authorization_id, definition_digests=[ref], seed=0)
    definition = WorkflowAccountingDefinition(schema_version='aeep.toolkit.workflow-accounting.v2',
        workflow_sha256=pinned['workflow']['sha256'], configurations=tuple(SCOPES),
        operations=('setup', 'readiness', 'remove'), source_digest=pinned['source_sha256'],
        manifest_path=pinned['manifest']['path'], manifest_sha256=pinned['manifest']['sha256'],
        request=request, maximum_overhead_seconds=pinned['max_overhead_seconds'])
    driver.prepared.write(ACCOUNTING, definition.model_dump(mode='json'))
    emit('started.json', {'review_sha256': identity, 'models': 0})
    with ReceiptStore(pinned['ledger']) as store:
        repo = AssessmentRepository(store)
        assert repo.put('toolkit_skillsbench_private_assets', ref, scope) == ref
        definition_ref = repo.put('toolkit_workflow_accounting', content_digest(definition), definition)
        repo.approve_bundle(grant, {ref: scope.model_dump(mode='json'), definition_ref: definition.model_dump(mode='json')})
        results = []
        protected = {}
        for name, stage, expected in pinned['actions']:
            current, _ = lifecycle_preview(WORKFLOW, name, ('task-assets',), operation=stage)
            assert current['review_sha256'] == expected and not current['blockers']
            cli = driver.cli(stage, '--workflow', WORKFLOW, '--configuration', name, '--runtime', 'task-assets',
                '--accounting', ACCOUNTING, '--operation-id', name+'-'+stage, '--reviewed-digest', expected)
            plan = FileRuntimeInstallation.model_validate(driver.prepared.read(pinned['installations'][name]['path']))
            path = Path(plan.destination)
            if stage == 'setup':
                assert cli['complete'] and path.is_dir()
                pack = BenchmarkPack.model_validate_json((path/'pack.json').read_bytes())
                assert task_input(pack, path, SCOPES[name]) == task_input(pack, PRIVATE_ORIGINAL, SCOPES[name])
                if name != 'sales-removal-check':
                    protected[name] = snapshot(path)
            elif stage == 'readiness':
                assert cli['observations']['task-assets']['installed'] is True
                assert cli['observations']['task-assets']['functional_readiness'] == 'NOT_VERIFIED'
            else:
                assert name == 'sales-removal-check' and cli['complete'] and not path.exists()
            results.append({'configuration': name, 'stage': stage, 'review_sha256': expected,
                            'workflow_accounting': cli['workflow_accounting']})
        assert all(snapshot(WORK/'owned'/name) == old for name, old in protected.items())
        operations = repo.operation_ledger(request.plan_id)
        assert len(operations.operations) == len(pinned['actions'])
        assert all(item.elapsed_seconds is not None and item.reserved.max_model_turns == 0 for item in operations.operations)
        emit('result.json', {'passed': True, 'steps': results, 'retained_private_packages': protected,
             'disposable_copy_removed': True, 'docker_resources_changed': False, 'model_turns': 0,
             'functional_readiness': 'SEPARATE_ENGINEERING_EVIDENCE',
             'ledger_sha256': content_digest(operations)})
        print(json.dumps({'passed': True, 'retained_packages': list(protected), 'operations': len(operations.operations)}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--execute')
    args = parser.parse_args()
    path = HERE / 'operation-review.json'
    if args.prepare:
        make_definitions()
    elif args.execute == driver.prepared.sha(path) and not (HERE / 'started.json').exists():
        verify(driver.prepared.read(path), args.execute)
    else:
        raise SystemExit('Exact first lifecycle review required.')
