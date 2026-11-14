"""Revalidate the approved pytest snapshot inventory and unlink only those copies."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import subprocess
from contextlib import closing
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[5]
INVENTORY = HERE / 'storage-candidates.json'
INVENTORY_SHA256 = 'a2b9393937837e6ac8ddff51873af2b076e12b3a864cfd35242f7d03738635d4'
STARTED = HERE / 'cleanup-started.json'
RESULT = HERE / 'cleanup-result.json'
DB_NAME = re.compile(r'worker_[a-f0-9]{32}\.sqlite3')
PLAN_NAME = re.compile(r'plan_[a-f0-9]{32}')
SIDECARS = ('-wal', '-shm', '-journal')
MARKERS = {
    'a reviewed local fixture', 'selected generated-recipe fixture',
    'Controlled fixture; not a real plugin benefit claim', 'reviewed workflow fixture',
}
PYTHON_MAPPINGS = {
    'aeep.assessment.adapters:workflow_target', 'aeep.assessment.recipes:reference_csv',
    'aeep.assessment.recipes:reference_search', 'aeep.assessment.recipes:reference_text',
    'test_v08_assessment:slow_csv', 'test_v08_assessment:custom_record',
    'test_v08_assessment:slow_record', 'test_v08_planning:search_input',
    'test_v08_planning:slow_search',
}


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def metadata(path, info):
    assert stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid(), path
    return [info.st_ino, info.st_size, info.st_blocks * 512, info.st_mtime_ns]


def opened_files():
    result = subprocess.run(['/usr/sbin/lsof', '-nP', '-Fn'], capture_output=True,
                            text=True, timeout=20, check=True)
    return {line[1:] for line in result.stdout.splitlines() if line.startswith('n')}


def inactive(path, opened):
    assert str(path) not in opened, path
    for suffix in SIDECARS:
        sidecar = path.with_name(path.name + suffix)
        assert not os.path.lexists(sidecar) and str(sidecar) not in opened, sidecar


def check_snapshot(path, marker):
    with closing(sqlite3.connect(path.as_uri()+'?mode=ro&immutable=1', uri=True)) as db:
        assert db.execute('SELECT count(*) FROM assessment_grants WHERE model_turns!=0 OR CAST(cash_usd AS NUMERIC)!=0').fetchone() == (0,), path
        state = {}
        for kind, raw in db.execute("SELECT kind,payload_json FROM assessment_records "
                                    "WHERE kind IN ('subject','mapping','environment','authorization')"):
            state.setdefault(kind, []).append(json.loads(raw))
    assert set(state) == {'subject', 'mapping', 'environment', 'authorization'}, path
    assert all(Path(subject['location']) in marker for subject in state['subject']), path
    assert all(not grant['remote_disclosure'] for grant in state['authorization']), path
    for env in state['environment']:
        assert not env['network'], path
        if env['kind'] == 'container':
            assert env['environment_id'] == 'recipe-container' and env['container_runtime'] == '/fixture/docker', path
        else:
            assert env['kind'] == 'trusted_local' and env['environment_id'] in {'local', 'test'}, path
    for mapping in state['mapping']:
        for spec in (mapping['candidate'], mapping['baseline'], *mapping.get('dependencies', [])):
            if spec['kind'] == 'command':
                assert spec['config']['argv'][:2] == ['python3', '-c'], path
                assert all(env['kind'] == 'container' for env in state['environment']), path
            else:
                assert spec['kind'] == 'python' and spec['config']['callable'] in PYTHON_MAPPINGS, path


def validate():
    assert sha(INVENTORY) == INVENTORY_SHA256
    plan = json.loads(INVENTORY.read_text())
    opened = opened_files()
    groups, preserved = [], {}
    for row in plan['rows']:
        scratch = ROOT / row['pytest_root']
        assert scratch.resolve() == scratch and scratch.is_relative_to(ROOT / '.aeep')
        log_dir = scratch.parent
        checks = log_dir / 'checks.json'
        kind = 'pytest' if scratch.name == 'pytest-tmp' else 'coverage-tests'
        check, = (check for check in json.loads(checks.read_text())['checks'] if check['name'] == kind)
        launch_root = (log_dir.parent / 'verification' / scratch.name
                       if log_dir.name == 'verification-prompt-fixture-failure' else scratch)
        assert str(launch_root) in check['argv'] and check['exit_code'] == row['check_exit_code']
        log = log_dir / (kind + '.log')
        for path in (checks, log):
            assert path.is_file() and path.resolve() == path
            preserved[path] = sha(path)
        records = []
        for fixture in row['test_fixtures']:
            test = scratch / fixture
            marker = test / 'plugin.txt'
            assert marker.resolve() == marker and marker.read_text() in MARKERS, marker
            preserved[marker] = sha(marker)
            logical_marker = launch_root / fixture / marker.name
            for path in test.glob('assessment/plan_*/attempts/worker_*.sqlite3'):
                if not DB_NAME.fullmatch(path.name):
                    continue
                assert PLAN_NAME.fullmatch(path.parents[1].name) and path.resolve() == path, path
                database = path.parents[1] / 'campaign.sqlite3'
                if not database.is_file():
                    continue
                if database not in preserved:
                    assert database.resolve() == database
                    inactive(database, opened)
                    preserved[database] = sha(database)
                inactive(path, opened)
                before = metadata(path, path.lstat())
                check_snapshot(path, {marker, logical_marker})
                assert metadata(path, path.lstat()) == before, path
                records.append([str(path.relative_to(scratch)), *before])
        records.sort()
        digest = hashlib.sha256(json.dumps(records, separators=(',', ':')).encode()).hexdigest()
        assert len(records) == row['files'] and digest == row['metadata_sha256'], scratch
        assert sum(record[3] for record in records) == row['allocated_bytes'], scratch
        groups.append((scratch, records))
    assert sum(len(records) for _, records in groups) == plan['total_files']
    return plan, groups, preserved


def cleanup(plan, groups, preserved):
    before = shutil.disk_usage(ROOT).free
    write(STARTED, {'inventory_sha256': INVENTORY_SHA256, 'files_verified': plan['total_files'],
                    'free_before_bytes': before, 'authority': 'Operator approved the verified old pytest copies only.'})
    records = []
    removed = 0
    size_removed = 0
    try:
        for scratch, copies in groups:
            directory = None
            descriptor = None
            opened = opened_files()
            try:
                for relative, *expected in copies:
                    path = scratch / relative
                    inactive(path, opened)
                    if path.parent != directory:
                        if descriptor is not None:
                            os.close(descriptor)
                            descriptor = None
                        directory = path.parent
                        assert directory.resolve() == directory
                        descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
                    actual = os.stat(path.name, dir_fd=descriptor, follow_symlinks=False)
                    assert metadata(path, actual) == expected, path
                    os.unlink(path.name, dir_fd=descriptor)
                    removed += 1
                    size_removed += actual.st_blocks * 512
            finally:
                if descriptor is not None:
                    os.close(descriptor)
            assert all(not os.path.lexists(scratch / row[0]) for row in copies)
            records.append({'root': str(scratch.relative_to(ROOT)), 'removed': len(copies),
                            'free_bytes': shutil.disk_usage(ROOT).free})
    finally:
        unchanged = all(path.is_file() and sha(path) == digest for path, digest in preserved.items())
        after = shutil.disk_usage(ROOT).free
        result = {'inventory_sha256': INVENTORY_SHA256, 'files_removed': removed,
                  'allocated_bytes_removed': size_removed, 'free_before_bytes': before, 'free_after_bytes': after,
                  'observed_free_space_change_bytes': after - before, 'groups': records,
                  'preserved_evidence_files_verified': len(preserved), 'evidence_unchanged': unchanged,
                  'completed': removed == plan['total_files'] and unchanged,
                  'docker_touched': False, 'backups_touched': False, 'comparisons': 'PAUSED'}
        write(RESULT, result)
        print(json.dumps(result))
    assert result['completed']


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute-approved', choices=[INVENTORY_SHA256])
    args = parser.parse_args()
    assert __debug__ and not STARTED.exists() and not RESULT.exists()
    plan, groups, preserved = validate()
    if args.execute_approved:
        cleanup(plan, groups, preserved)
    else:
        print(json.dumps({'inventory_sha256': INVENTORY_SHA256, 'files_verified': plan['total_files'],
                          'evidence_files_checked': len(preserved), 'files_removed': 0}))


if __name__ == '__main__':
    main()
