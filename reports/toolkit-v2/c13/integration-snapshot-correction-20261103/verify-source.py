"""Run required first-party source gates with the normal actual-space guard."""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'src'))
from aeep.assessment.verification import verification_source_digest

OUT = HERE / 'verification'
OUT.mkdir(mode=0o700)
source = verification_source_digest(ROOT)
assert shutil.disk_usage(ROOT).free >= 50 * 1024**3 + 128 * 1024**2
checks = [
    ('compileall', ['-m', 'compileall', '-q', 'src', 'examples', 'tests']),
    ('schemas', ['scripts/generate_schemas.py', '--check']),
    ('assessment-policy', ['scripts/check_assessment_policy.py']),
    ('ruff', ['-m', 'ruff', 'check', '.']), ('mypy', ['-m', 'mypy', 'src']),
    ('pytest', ['-m', 'pytest']),
    ('coverage-tests', ['-m', 'coverage', 'run', '--branch', '-m', 'pytest']),
    ('coverage-json', ['-m', 'coverage', 'json', '-o', str(OUT / 'coverage.json')]),
    ('coverage-report', ['-m', 'coverage', 'report', '-m']),
    ('critical-coverage', ['scripts/check_critical_coverage.py', str(OUT / 'coverage.json')]),
    ('assessment-coverage', ['scripts/check_assessment_coverage.py', str(OUT / 'coverage.json')]),
    ('toolkit-integration-fixtures', ['-m', 'pytest', 'integrations/toolkit']),
    ('build', ['-m', 'build', '--no-isolation', '--outdir', str(OUT / 'dist')]),
]
env = dict(os.environ, PYTHONPATH=str(ROOT / 'src') + ':' + str(HERE.parent / 'workflow-scanner-20261102'),
    PYTHONDONTWRITEBYTECODE='1', COVERAGE_FILE=str(OUT / '.coverage'))
assert not env.get('PYTEST_ADDOPTS'), 'Unexpected inherited pytest options'
env['PYTEST_ADDOPTS'] = '-o tmp_path_retention_policy=all -o tmp_path_retention_count=10000'
removed = []
for key in list(env):
    if key.startswith(('AEEP_REAL_', 'AEEP_LIVE_')) or key in {
        'AEEP_CONTAINER_IMAGE', 'AEEP_WORKBOOK_IMAGE', 'AEEP_CATALOG_METRICS_IMAGE',
        'AEEP_CONTAINER_RUNTIME', 'AEEP_CONTAINER_SOCKET', 'AEEP_INSPECTION_FIXTURE_SPECS',
    }:
        removed.append(key)
        env.pop(key)
record = {'source_before': source, 'source_after': source, 'checks': [], 'models': 0,
    'comparisons': 'PAUSED', 'real_execution_selectors_removed': removed,
    'scope': 'Scoped v7/v8 integration preparation dependency correction and synthetic adversarial records. No SDK, scanner, container, service, model or benchmark execution. Existing unrelated CI work is present but excluded from implementation commits.',
    'capacity_samples': []}
began = time.monotonic()


def persist():
    (OUT / 'checks.json').write_text(json.dumps(record, indent=2) + '\n')


def capacity():
    free = shutil.disk_usage(ROOT).free
    record['capacity_samples'].append({'observed_at': datetime.now(UTC).isoformat(), 'free_bytes': free})
    assert free >= 50 * 1024**3, 'Normal 50 GiB host reserve crossed'
    assert time.monotonic() - began < 5400, 'Finite source-verification time exceeded'
    assert verification_source_digest(ROOT) == source, 'Source changed during verification'


persist()
for name, arguments in checks:
    capacity()
    if name in {'pytest', 'coverage-tests'}:
        arguments = [*arguments, '-p', 'aeep_fixture_cleanup']
        env['AEEP_FIXTURE_CLEANUP_RECORD'] = str(OUT / (name + '-fixture-cleanup.json'))
    else:
        env.pop('AEEP_FIXTURE_CLEANUP_RECORD', None)
    start = time.monotonic()
    stop = None
    with (OUT / (name + '.log')).open('x') as log:
        process = subprocess.Popen([sys.executable, *arguments], cwd=ROOT, env=env,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            while process.poll() is None:
                time.sleep(2)
                capacity()
                assert log.tell() < 16 * 1024**2, 'Bounded source log exceeded'
        except BaseException as error:
            stop = str(error)[:400]
            for sig, seconds in ((signal.SIGINT, 10), (signal.SIGTERM, 5), (signal.SIGKILL, 5)):
                if process.poll() is not None:
                    break
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                try:
                    process.wait(timeout=seconds)
                except subprocess.TimeoutExpired:
                    continue
            process.wait(timeout=5)
    item = {'name': name, 'argv': [sys.executable, *arguments],
        'exit_code': process.returncode if stop is None else 125,
        'process_exit_code': process.returncode, 'elapsed_seconds': time.monotonic() - start,
        'monitor_stop': stop}
    record['checks'].append(item)
    record['source_after'] = verification_source_digest(ROOT)
    persist()
    print(json.dumps(item), flush=True)
    if item['exit_code'] or record['source_after'] != source:
        raise SystemExit(1)
