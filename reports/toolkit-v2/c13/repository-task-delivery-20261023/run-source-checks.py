"""Single integrated non-metered verification; no workers, installers or model calls."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.verification import verification_source_digest

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent / 'validation'
OUT.mkdir(exist_ok=True)
assert not (OUT / 'checks.json').exists(), 'Inspect existing results; do not replay automatically.'
assert shutil.disk_usage(ROOT).free > 51 * 1024**3
source = verification_source_digest(ROOT)
coverage = ROOT / '.aeep/repository-task-delivery-20261023/.coverage'
coverage_json = coverage.parent / 'coverage.json'
coverage.parent.mkdir(exist_ok=True)
environment = dict(os.environ, PYTHONPATH='src', COVERAGE_FILE=str(coverage))
checks = []
commands = [
    ['-m', 'pytest', 'integrations/toolkit'],
    ['-m', 'compileall', '-q', 'src', 'examples', 'tests'],
    ['scripts/generate_schemas.py', '--check'],
    ['-m', 'pytest'],
    ['-m', 'coverage', 'run', '--branch', '-m', 'pytest'],
    ['-m', 'coverage', 'report', '-m'],
    ['-m', 'coverage', 'json', '-o', str(coverage_json)],
    ['scripts/check_critical_coverage.py', str(coverage_json)],
    ['scripts/check_assessment_coverage.py', str(coverage_json)],
    ['-m', 'ruff', 'check', '.'],
    ['scripts/check_assessment_policy.py'],
    ['-m', 'mypy', 'src'],
    ['-m', 'build', '--no-isolation', '--outdir', str(OUT / 'artifacts')],
]
try:
    for index, command in enumerate(commands):
        assert verification_source_digest(ROOT) == source, 'Source changed; inspect before continuing.'
        log = OUT / f'{index:02d}.log'
        began = time.monotonic()
        with log.open('x') as output:
            result = subprocess.run([sys.executable, *command], cwd=ROOT, env=environment,
                stdout=output, stderr=subprocess.STDOUT, timeout=3600)
        checks.append({'argv':[sys.executable,*command], 'returncode':result.returncode,
            'seconds':time.monotonic()-began, 'log':str(log.relative_to(ROOT))})
        (OUT / 'checks.json').write_text(json.dumps(checks, indent=2) + '\n')
        print(json.dumps(checks[-1]), flush=True)
        if result.returncode:
            break
finally:
    (OUT / 'source-stability.json').write_text(json.dumps({'source_digest':source,
        'source_unchanged':verification_source_digest(ROOT)==source,
        'completed_checks':len(checks), 'all_passed':len(checks)==len(commands) and all(c['returncode']==0 for c in checks)}, indent=2)+'\n')
