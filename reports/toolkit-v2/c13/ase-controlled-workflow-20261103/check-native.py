"""Run only first-party stdlib/Git preparation; preserve failed resources."""
import json
import os
import shutil
import subprocess
from pathlib import Path

import prepare

work = prepare.SCHEDULER_WORK
assert not work.exists()
work.mkdir(mode=0o700)
for name in ('home', 'tmp', 'responses', 'candidate'):
    (work / name).mkdir(mode=0o700)
outside = prepare.WORK / 'owned-outside-canary'
outside.write_text('First-party non-secret boundary canary.\n')
payload = {'outside': str(outside), 'outside_write': str(prepare.WORK / 'denied-write'),
           'git': str(prepare.TOOLS / 'git')}
profile = prepare.HERE / 'scheduler.sb'
command = [str(prepare.RUNTIME / 'bin/python'), '-I', '-B', str(prepare.HERE / 'native-check.py')]
process = subprocess.run(['/usr/bin/sandbox-exec', '-f', str(profile), *command], cwd=work,
    env={'PATH': str(prepare.TOOLS) + ':/usr/bin:/bin', 'HOME': str(work / 'home'),
         'TMPDIR': str(work / 'tmp'), 'LC_ALL': 'C', 'PYTHONDONTWRITEBYTECODE': '1'},
    input=json.dumps(payload), text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=25)
result = json.loads(process.stdout) if process.returncode == 0 else {'passed': False}
result.update(exit_code=process.returncode, actual_upstream_executed=False,
              stderr_sha256=__import__('hashlib').sha256(process.stderr.encode()).hexdigest())
prepare.write(prepare.HERE / 'native-controls.json', result)
assert result['passed'] and not (prepare.WORK / 'denied-write').exists()
# No SDK ran here. Remove only this newly created, inspected stdlib/Git fixture.
entries = list(work.rglob('*'))
assert len(entries) < 100 and all(not item.is_symlink() for item in entries)
before = prepare.snapshot(work)
assert prepare.snapshot(work) == before
shutil.rmtree(work)
result.update(owned_fixture_removed=True, retained_runtime_unchanged=True,
              scheduler_workspace_absent=True, removed_fixture_sha256=before)
prepare.write(prepare.HERE / 'native-controls.json', result)
print(json.dumps(result))
