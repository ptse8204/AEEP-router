"""Freeze the first protected Spring Boot reference review from verified inputs."""
import ast
import hashlib
import json
import re
import shutil
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = HERE.parent
TREE = BASE/'skillsbench-spring-maven-tree-20261105'
RESOLVER = BASE/'skillsbench-spring-maven-20261105'
RUNTIME = BASE/'skillsbench-spring-runtime-20261105'
WORK = ROOT/'.aeep'/HERE.name
SOURCE = ROOT/'.aeep/skillsbench-stack-9a1f4dd5'
TREEWORK = ROOT/'.aeep'/TREE.name
PACK = BASE/'skillsbench-transport-20261103/task-only-pack.json'


def load(path):
    return json.loads(path.read_bytes())


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(path):
    files = {}
    for file in sorted(path.rglob('*')):
        assert not file.is_symlink(), file
        if not file.is_dir():
            assert file.is_file(), file
            files[file.relative_to(path).as_posix()] = sha(file)
    return files


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


previous = load(TREE/'operation-review.json')
assert load(TREE/'execution/summary.json')['passed']
assert load(RUNTIME/'runtime-execution/summary.json')['passed']
closure = load(HERE/'maven-acquisition-result.json')
assert closure['passed'] and closure['prior_cache_preserved']
lock_path = WORK/'maven-cache-lock.json'
lock = load(lock_path)
assert digest(lock) == closure['artifact_lock_sha256']
assert shutil.disk_usage(ROOT).free >= 52*1024**3
variants = ('solve', 'reference', 'missing', 'legacy-namespace')
for variant in variants:
    assert inventory(WORK/'cache'/variant) == lock, variant
staged = load(PACK)
assert staged['source']['revision'] == '9a1f4dd5f7659f75707435da3ce854b6e48321d1'
assert staged['source']['license_expression'] == 'Apache-2.0'
task = next(row for row in staged['tasks'] if row['task_id'] == 'spring-boot-jakarta-migration')
paths = []
for item in task['assets']:
    original = SOURCE/item['path']
    assert sha(original) == item['sha256'], item['path']
    if item['role'] == 'input':
        relative = item['path'].split('/workspace/', 1)[1]
        paths.append(relative)
        assert sha(WORK/'solve'/relative) == item['sha256'], relative
    elif original.name in ('solve.sh', 'test_outputs.py'):
        assert sha(WORK/'protected'/original.name) == item['sha256'], original.name
assert len(paths) == 17 and set(paths) == set(inventory(WORK/'solve'))
verifier = WORK/'protected/test_outputs.py'
ids = [
    f'test_outputs.py::{cls.name}::{node.name}'
    for cls in ast.parse(verifier.read_text()).body if isinstance(cls, ast.ClassDef)
    for node in cls.body if isinstance(node, ast.FunctionDef) and node.name.startswith('test_')
]
assert len(ids) == len(set(ids)) == 10
assert any(x.endswith('::test_jakarta_persistence_present') for x in ids)
assert any(x.endswith('::test_no_javax_validation') for x in ids)
sdk = ['sdkman-init.sh', 'sdkman-delay_upgrade', 'sdkman-platform']
assert (TREEWORK/'sdkman-delay_upgrade').stat().st_size == 0
assert 'linux' in (TREEWORK/'sdkman-platform').read_text().strip()
pins_sdk = {name: sha(TREEWORK/name) for name in sdk}
assert (WORK/'protected/observe.py').read_bytes() == (BASE/'skillsbench-sales-reference-20261105/observe.py').read_bytes()
portable = load(RUNTIME/'artifacts.json')['python']
interpreter = ROOT/'.aeep'/RUNTIME.name/portable['name']
assert sha(interpreter) == portable['sha256']
solver = WORK/'protected/solve.sh'
m = re.search(rb"cat > pom.xml << 'POMEOF'\n(.*?)\nPOMEOF\n", solver.read_bytes(), re.DOTALL)
resolved_pom = Path(load(RESOLVER/'operation-review.json')['work'])/'pom.xml'
assert m and m[1] == resolved_pom.read_bytes()
migrated = hashlib.sha256(m[1]+b'\n').hexdigest()
tool_files = inventory(WORK/'tools')
write(HERE/'preparation.json', {
    'tool_count': len(load(HERE/'toolchain.json')['toolchain']),
    'tool_files': len(tool_files), 'maven_artifact_lock_sha256': digest(lock),
    'verified_cache_copies': 4, 'upstream_test_ids': ids, 'pinned_original_inputs': 17,
    'pinned_upstream_files': len(task['assets']), 'sdkman_readonly_check': pins_sdk,
    'image_id': previous['image']['image_id'],
    'guest_runtime_probe': sha(RUNTIME/'runtime-execution/summary.json'),
    'pom_adapter': 'Dependency collection used the same heredoc body without its terminal newline. The solver output is pinned with that newline.',
    'task_executed': False, 'candidate_runs': 0, 'models': 0,
})
plan = {
    'scope': 'Run one original Spring Boot/Jakarta solver and protected verifier on its reference result and two negative controls',
    'task_id': task['task_id'], 'revision': staged['source']['revision'], 'license': 'Apache-2.0',
    'task_pack_sha256': sha(PACK), 'image': previous['image'], 'workspace_inputs': paths,
    'upstream_verifier_sha256': sha(verifier), 'upstream_oracle_sha256': sha(solver),
    'migrated_pom_sha256': migrated, 'test_identities': ids, 'maven_artifact_lock_sha256': digest(lock),
    'tool_inventory_sha256': digest(tool_files),
    'expected_controls': {
        'reference': {'reward': 1, 'passed': 10},
        'missing': {'reward': 0, 'required_fail': 'test_jakarta_persistence_present'},
        'legacy-namespace': {'reward': 0, 'required_fail': 'test_no_javax_validation'},
    },
    'network': 'none', 'maximum_operations': 26, 'maximum_reserved_seconds': 2400, 'models': 0,
    'cash_authority_usd': '0', 'automatic_retries': False,
    'adaptations': [
        'Portable CPython 3.12.16 and six checksum-pinned pure wheels replace mutable apt/uv bootstrap.',
        'Maven is offline with digest-bound cache copies and the same mirror ID.',
        'The protected pytest/CTRF bridge retains upstream test assertions and binary reward.',
        'The solver and protected grader are separate owned containers with bounded writable task mounts.',
        'Engineering reference calibration only. No bundled skills, candidate, agent, or official benchmark reproduction.',
    ],
}
plan_path = HERE/'plan.json'
write(plan_path, plan)
expires = '2026-11-08T12:00:00+00:00'
roles = {}
for role in ('subject', 'recipe', 'environment', 'mapping'):
    item = {'role': role, 'plan_sha256': sha(plan_path)}
    roles[role] = (digest(item), item)
identity = HERE.name
with sqlite3.connect('file:'+previous['ledger']+'?mode=ro', uri=True) as conn:
    assert not conn.execute('select 1 from assessment_grants where id=?', (identity,)).fetchone()
scopes = dict(roles.values())
grant = {
    'schema_version': 'assessment.authorization.v1', 'authorization_id': identity,
    **{role+'_digests': [roles[role][0]] for role in ('subject', 'recipe', 'environment')},
    'limits': {'max_operations': 26, 'max_model_turns': 0, 'max_elapsed_seconds': 2400, 'max_cash_usd': '0'},
    'remote_disclosure': False, 'allowed_destinations': ['local'], 'automatic_admission': False,
    'issued_at': datetime.now(UTC).isoformat(), 'expires_at': expires,
}
request = {
    'schema_version': 'assessment.recipe-materialization.v1', 'plan_id': identity, 'authorization_id': identity,
    **{role+'_digest': ref for role, (ref, _) in roles.items()},
    'definition_digests': list(scopes), 'seed': 0,
}
write(HERE/'prepared.json', {'scopes': scopes, 'grant': grant, 'request': request, 'applied': False})
authority = BASE/'pipeline-standing-authority-20261104.json'
settings = RESOLVER/'maven-settings.xml'
pins = [HERE/name for name in (
    'prepare.py', 'run.py', 'entry.sh', 'preparation.json', 'plan.json', 'prepared.json',
    'stage.py', 'toolchain.json', 'stage-maven-closure.py', 'maven-acquisition-plan.json',
    'maven-acquisition-result.json',
)]
pins += [
    interpreter, settings, PACK, SOURCE/'LICENSE', authority, TREE/'operation-review.json',
    TREE/'execution/resolved-graph.json', RUNTIME/'runtime-execution/summary.json',
    lock_path, Path(previous['docker']), Path(previous['docker_config'])/'config.json',
]
pins += [WORK/'solve'/path for path in paths]
pins += [WORK/'protected'/path for path in inventory(WORK/'protected')]
pins += [TREEWORK/name for name in sdk]
review = {
    **{key: previous[key] for key in ('source', 'coordinator_source_snapshot', 'ledger', 'docker', 'docker_config', 'docker_socket')},
    **plan, 'work': str(WORK), 'settings': str(settings), 'python_archive': str(interpreter), 'expires_at': expires,
    'free_bytes_before': shutil.disk_usage(ROOT).free, 'storage_floor_bytes': 50*1024**3,
    'pins': {str(file): sha(file) for file in pins},
    'container_names': {variant: 'aeep-sb-spring-'+variant+'-20261105' for variant in variants},
    'effects': 'At most four owned offline containers retained stopped. Zero downloads, installs, image changes, models, credential reads, external services, old-resource deletion, comparative trials, admission or release.',
}
review_path = HERE/'operation-review.json'
write(review_path, review)
write(HERE/'delegated-authority.json', {
    'first_attempt': True, 'review_sha256': sha(review_path), 'standing_authority_sha256': sha(authority),
    'reason': 'First isolated execution of original SkillsBench Spring solver and protected upstream verifier. No repeat of any earlier resolver or runtime probe.',
    'recorded_at': datetime.now(UTC).isoformat(),
})
print(sha(review_path), len(pins), len(lock), review['free_bytes_before'])
