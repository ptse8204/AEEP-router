"""Synthetic private file only; never credentials, assessment state or answers."""
import hashlib
import json
from pathlib import Path
import subprocess

path = Path('/workspace/private-state.json')
facts = {}
for operation in ('read', 'write'):
    try:
        path.read_bytes() if operation == 'read' else path.write_bytes(b'changed')
        facts[operation + '_denied'] = False
    except OSError:
        facts[operation + '_denied'] = True

def stderr_class(data):
    text = data.decode("utf-8", errors="replace").lower()
    for name, markers in (("unsupported_flag", ("unexpected argument", "unrecognized option", "unknown option")), ("permission_denied", ("permission denied", "operation not permitted")), ("namespace_unavailable", ("namespace", "unshare")), ("seccomp_unavailable", ("seccomp",)), ("landlock_unavailable", ("landlock",)), ("bwrap_unavailable", ("bwrap", "bubblewrap"))):
        if any(marker in text for marker in markers):
            return name
    return "unclassified" if data else "none"

probe = 'import json,pathlib; p=pathlib.Path("/workspace/private-state.json"); r={};\nfor op in ("read","write"):\n try:\n  p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[op+"_denied"]=False\n except OSError:r[op+"_denied"]=True\nprint(json.dumps(r))'
argv = ['/opt/codex/codex', 'sandbox', '--permission-profile', 'aeep', '--include-managed-config', '--cd', '/workspace', '--', 'python3', '-c', probe]
try:
    result = subprocess.run(argv, capture_output=True, timeout=5)
    nested = json.loads(result.stdout) if result.returncode == 0 else {}
    facts.update(nested_read_denied=nested.get('read_denied') is True,
        nested_write_denied=nested.get('write_denied') is True, nested_exit_code=result.returncode,
        stderr_class=stderr_class(result.stderr), stderr_bytes=len(result.stderr), stderr_sha256=hashlib.sha256(result.stderr).hexdigest())
except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
    facts['error_type'] = type(exc).__name__
print(json.dumps(facts))
