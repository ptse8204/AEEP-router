"""Check original task-byte transport and verifier metadata without executing tasks."""
import ast
import base64
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from aeep_toolkit.benchmarks import BenchmarkPack, asset_path, inspect_pack, task_input

source_path = HERE.parent / 'full-stack-20261030/skillsbench-pack.json'
original = json.loads(source_path.read_bytes())
root = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
inventory = json.loads((root / 'source-inventory.json').read_bytes())
by_path = {item['path']: item for item in inventory['assets']}
filtered = json.loads(source_path.read_bytes())
excluded = {}
for task in filtered['tasks']:
    removed = [asset for asset in task['assets'] if '/environment/skills/' in asset['path']]
    excluded[task['task_id']] = {asset['path']: asset['sha256'] for asset in removed}
    task['assets'] = [asset for asset in task['assets'] if asset not in removed]
    task['adaptations'].append('All bundled skills and their notices are excluded from this task-only manifest; candidate selection is separate. Original instructions, inputs, oracles and verifiers are unchanged.')
    assert task['rights_review_ref'] is None
filtered['source']['data_rights'] = 'Task-only metadata with bundled skills excluded. Asset-specific rights and runtime adaptation remain pending; no execution or provider disclosure is cleared.'
pack = BenchmarkPack.model_validate(filtered)
result = {'evidence_kind': 'read_only_actual_file_and_transport_checks', 'pack_revision': pack.source.revision,
    'original_manifest_sha256': hashlib.sha256(source_path.read_bytes()).hexdigest(),
    'source_inventory_sha256': hashlib.sha256((root / 'source-inventory.json').read_bytes()).hexdigest(),
    'bundled_skills_excluded': excluded, 'tasks': [], 'upstream_software_executed': False,
    'reference_or_counterexample_executed': False, 'rights_cleared': False,
    'provider_disclosure': False, 'comparisons': 'PAUSED', 'all_stack_complete': False}
for task in pack.tasks:
    inspect_pack(pack, root, (task.task_id,))
    public = task_input(pack, root, task.task_id)
    raw = base64.b64decode(public['task_archive_b64'], validate=True)
    expected = {asset.path: asset for asset in task.assets if asset.role in {'instruction', 'input'}}
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        assert set(archive.namelist()) == set(expected)
        for name, asset in expected.items():
            data = archive.read(name)
            assert len(data) == asset.bytes and hashlib.sha256(data).hexdigest() == asset.sha256
    tests = []
    skips = []
    shell_contracts = []
    external_rights = []
    for asset in task.assets:
        if asset.role == 'verifier' and asset.path.endswith('.py'):
            tree = ast.parse(asset_path(root, asset).read_text())
            tests.extend(node.name for node in ast.walk(tree)
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith('test_'))
            skips.extend({'line': node.lineno, 'call': ast.unparse(node.func)} for node in ast.walk(tree)
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in {'skip', 'skipif', 'importorskip', 'xfail'})
        if asset.role == 'verifier' and asset.path.endswith('test.sh'):
            script = asset_path(root, asset).read_text()
            assert 'reward.txt' in script and 'echo 1' in script and 'echo 0' in script
            shell_contracts.append({'path': asset.path, 'sha256': asset.sha256,
                'reward': 'binary file selected by pytest exit, not shell process status',
                'shell_exit_zero_literal': 'exit 0' in script,
                'mutable_installer_present': 'install.sh' in script or 'pip install' in script,
                'executed': False})
        meta = by_path.get(asset.path, {})
        if meta.get('rights_status'):
            external_rights.append({key: meta[key] for key in ('path', 'source_repository',
                'source_revision', 'source_path', 'rights_status') if key in meta})
    result['tasks'].append({'task_id': task.task_id, 'domain': task.domain, 'difficulty': task.difficulty,
        'input_archive_sha256': public['task_archive_sha256'], 'archive_bytes': len(raw),
        'expanded_public_bytes': sum(asset.bytes for asset in expected.values()),
        'public_files': len(expected), 'public_asset_hashes': {name: asset.sha256 for name, asset in expected.items()},
        'protected_asset_hashes': {asset.path: asset.sha256 for asset in task.assets if asset.role in {'oracle', 'verifier'}},
        'declared_score': task.upstream_score, 'static_test_function_names': tests,
        'skip_or_xfail_sites': skips, 'verifier_shell_contracts': shell_contracts,
        'external_rights': external_rights,
        'runtime_and_path_adaptation': 'PENDING; original task bytes transported, no adapted execution yet',
        'test_collection_and_reference': 'NOT_EXECUTED', 'functional_pack_status': 'NOT_VERIFIED'})
assert [sum(task.domain == domain for task in pack.tasks) for domain in ('document-data', 'software-engineering')] == [3, 3]
result['all_six_original_public_byte_transports_passed'] = True
result['oracle_verifier_or_bundled_skill_bytes_in_agent_transport'] = False
(HERE / 'task-only-pack.json').write_text(pack.model_dump_json(indent=2) + '\n')
(HERE / 'transport-result.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps({'transport_checks': len(result['tasks']), 'passed': True,
    'upstream_executed': False, 'rights_cleared': False, 'functional_pack_status': 'NOT_VERIFIED',
    'public_archive_bytes': {row['task_id']: row['archive_bytes'] for row in result['tasks']}}))
