"""Run the reviewed offline checks without changing old validation records."""
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'src'))
from aeep.assessment.verification import verification_source_digest

expected = sys.argv[1]
assert verification_source_digest(ROOT) == expected
assert shutil.disk_usage(ROOT).free > 80 * 1024**3
temp = Path(tempfile.mkdtemp(prefix='aeep-delay-validation-20261004-'))
env = {k: v for k, v in os.environ.items() if not k.startswith('AEEP_')}
env.update(PYTHONPATH=str(ROOT / 'src'), TMPDIR=str(temp),
           COVERAGE_FILE=str(OUT / 'coverage.data'), npm_config_offline='true',
           npm_config_update_notifier='false')
commands = [('06-version-correction', ['python3', '-m', 'pytest', '-ra', 'tests/test_version_consistency.py'])] + json.loads((OUT / 'commands.json').read_text())[6:]
results = json.loads((OUT / 'validation-progress.json').read_text())[:5]
lock = ROOT / 'reports/v08/verification-lock.json'
lock_sha = hashlib.sha256(lock.read_bytes()).hexdigest()
for name, argv in commands:
    assert verification_source_digest(ROOT) == expected
    env['PYTEST_ADDOPTS'] = f'--basetemp={temp / name} -o cache_dir={OUT / (name + "-cache")}'
    start = time.monotonic()
    with (OUT / (name + '.log')).open('x') as log:
        child = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=log,
                                 stderr=subprocess.STDOUT, start_new_session=True)
        reason = None
        while child.poll() is None:
            try:
                child.wait(timeout=30)
            except subprocess.TimeoutExpired:
                free = shutil.disk_usage(ROOT).free
                used = int(subprocess.check_output(['du', '-sk', str(temp)]).split()[0]) * 1024
                print(json.dumps({'check': name, 'elapsed_seconds': round(time.monotonic()-start),
                                  'free_gib': round(free/1024**3, 2)}), flush=True)
                if free < 50*1024**3 or used > 30*1024**3:
                    reason = 'storage guard'
                elif time.monotonic()-start > 1800:
                    reason = 'check deadline'
                elif verification_source_digest(ROOT) != expected:
                    reason = 'source changed'
                if reason:
                    os.killpg(child.pid, signal.SIGINT)
                    try:
                        child.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL)
                        child.wait()
        code = child.returncode
    row = {'name': name, 'argv': argv, 'returncode': code, 'guard': reason,
           'elapsed_seconds': time.monotonic()-start,
           'log_sha256': hashlib.sha256((OUT/(name+'.log')).read_bytes()).hexdigest()}
    results.append(row)
    (OUT/'remaining-validation-progress.json').write_text(json.dumps(results, indent=2)+'\n')
    print(json.dumps(row), flush=True)
    if code or reason:
        raise SystemExit(code or 1)
assert verification_source_digest(ROOT) == expected
assert hashlib.sha256(lock.read_bytes()).hexdigest() == lock_sha
with (OUT/'validation-terminal.json').open('x') as f:
    json.dump({'status': 'passed', 'source_digest': expected, 'verification_lock_sha256': lock_sha,
               'temporary_directory': str(temp), 'initial_full_suite': {'log': '06-pytest.log', 'result': '1 failed, 1218 passed, 21 skipped; required README status marker restored and targeted version test rerun; full coverage suite rerun follows'}, 'commands': results}, f, indent=2)
    f.write('\n')
