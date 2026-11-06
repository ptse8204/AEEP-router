"""Stage protected dependency audit verifier inputs without executing upstream code."""

import ast
import hashlib
import json
import shutil
from pathlib import Path

from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
ASSETS = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
PREVIOUS = C13 / 'skillsbench-contained-graders-20261105'
WORK = ROOT / '.aeep/skillsbench-dependency-audit-protected-20261105'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def put(path, data):
    with path.open('xb') as stream:
        stream.write(data)
    path.chmod(0o444)


assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
audit = json.loads((HERE / 'summary.json').read_bytes())
assert audit['passed'] and not audit['guest_code_executed']
pack = BenchmarkPack.model_validate_json((C13 / 'skillsbench-transport-20261103/task-only-pack.json').read_bytes())
task = pack.task('software-dependency-audit')
public = task_input(pack, ASSETS, task.task_id)
assert len(public['task_archive_b64']) <= 400_000

source_pin = next(asset for asset in task.assets if asset.path.endswith('/verifier/test_outputs.py'))
upstream = (ASSETS / source_pin.path).read_bytes()
assert sha(upstream) == source_pin.sha256 and len(upstream) == source_pin.bytes
original = b'/root/security_audit.csv'
destination = b'/tmp/aeep-dependency-audit/workspace/security_audit.csv'
assert upstream.count(original) == 1
adapted = upstream.replace(original, destination)
assert adapted.replace(destination, original) == upstream

# Preserve the exact identities of the four groups, including every
# parameterized field check. No fixture supplies an upstream answer here.
tree = ast.parse(upstream)
identities = []
for owner in (node for node in tree.body if isinstance(node, ast.ClassDef)):
    for method in (node for node in owner.body
                   if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')):
        prefix = 'test_outputs.py::' + owner.name + '::' + method.name
        if method.name == 'test_required_fields_non_empty':
            mark, = method.decorator_list
            assert isinstance(mark, ast.Call) and ast.unparse(mark.func) == 'pytest.mark.parametrize'
            field, values = map(ast.literal_eval, mark.args)
            assert field == 'field_name' and values == ['Package', 'Version', 'CVE_ID', 'Severity']
            identities.extend(f'{prefix}[{value}]' for value in values)
        else:
            assert not method.decorator_list
            identities.append(prefix)
assert len(identities) == len(set(identities)) == 7
assert not any(isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr in ('skip', 'skipif', 'xfail') for node in ast.walk(tree))
binding = {
    'task_id': task.task_id, 'archive_sha256': public['task_archive_sha256'],
    'output_field': 'deliverable_archive_b64', 'scratch': '/tmp/aeep-dependency-audit',
    'workspace_members': ['security_audit.csv'], 'collected_test_identities': identities,
    'intentional_skips': [], 'max_output_bytes': 262144,
}
context = WORK / 'context'
if not context.exists():
    context.mkdir(mode=0o700, parents=True)
assert not context.is_symlink() and not any(context.iterdir())
put(context / 'binding.json', (json.dumps(binding, indent=2) + '\n').encode())
put(context / 'test_outputs.py', adapted)
put(context / 'grade.py', (PREVIOUS / 'grade.py').read_bytes())
capture = ROOT / '.aeep/skillsbench-contained-graders-20261105/sales/runtime/repository_suite_native_capture.py'
put(context / capture.name, capture.read_bytes())
report = {
    'task_id': task.task_id, 'revision': pack.source.revision,
    'protected_context': str(context), 'context_file_sha256': {p.name: sha(p.read_bytes()) for p in context.iterdir()},
    'public_archive_sha256': public['task_archive_sha256'],
    'public_archive_base64_bytes': len(public['task_archive_b64']),
    'upstream_verifier_sha256': source_pin.sha256,
    'path_adaptation': {'from': original.decode(), 'to': destination.decode(), 'exact_original_reconstructed': True},
    'original_collected_identities': identities, 'protected_capture_reused': True,
    'base_image_compatibility': 'UNVERIFIED', 'archive_contents_tracked': False,
    'model_turns': 0, 'verifier_executed': False, 'database_executed_or_disclosed': False,
}
put(HERE / 'dependency-audit-protected-preparation.json', (json.dumps(report, indent=2) + '\n').encode())
print(json.dumps({'reviewed_test_identities': len(identities), 'public_archive_base64_bytes': len(public['task_archive_b64'])}))
