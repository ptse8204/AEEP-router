"""Standard-library-only check. No upstream import or model execution."""
import json
import os
import socket
import subprocess
import sys
from pathlib import Path

request = json.load(sys.stdin)
checks = {}
for key, path, operation in (
    ('outside_read_denied', request['outside'], 'r'),
    ('outside_write_denied', request['outside_write'], 'w'),
    ('response_write_denied', str(Path.cwd() / 'responses/guard'), 'w'),
    ('candidate_write_denied', str(Path.cwd() / 'candidate/guard'), 'w'),
):
    try:
        with open(path, operation):
            pass
        checks[key] = False
    except PermissionError:
        checks[key] = True
try:
    with socket.create_connection(('127.0.0.1', 9), timeout=1):
        pass
    checks['network_denied'] = False
except PermissionError:
    checks['network_denied'] = True
root = Path.cwd() / 'first-party-git-check'
root.mkdir()
env = {key: os.environ[key] for key in ('PATH', 'HOME', 'TMPDIR', 'LC_ALL')}
commands = [('init', '-b', 'main'), ('config', 'user.email', 'eval@agent-skill-eval.local'),
    ('config', 'user.name', 'Skill Eval'), ('add', '.'),
    ('commit', '-m', 'Initial commit', '--allow-empty')]
for arguments in commands:
    child = subprocess.run([request['git'], *arguments], cwd=root, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=5)
    if child.returncode:
        raise RuntimeError('Owned restricted Git preparation failed')
checks['local_git_initialization'] = True
print(json.dumps({'passed': all(checks.values()), 'checks': checks, 'upstream_imports': 0, 'models': 0}))
