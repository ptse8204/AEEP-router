"""Public zero-model nested-sandbox observation; runs only in the owned worker."""
import hashlib
import json
import subprocess


def stderr_class(data):
    text = data.decode("utf-8", errors="replace").lower()
    for name, markers in (("unsupported_flag", ("unexpected argument", "unrecognized option", "unknown option")), ("permission_denied", ("permission denied", "operation not permitted")), ("namespace_unavailable", ("namespace", "unshare")), ("seccomp_unavailable", ("seccomp",)), ("landlock_unavailable", ("landlock",)), ("bwrap_unavailable", ("bwrap", "bubblewrap"))):
        if any(marker in text for marker in markers):
            return name
    return "unclassified" if data else "none"

probe = 'import json; print(json.dumps({"nested_marker":"aeep-linux-probe-v1"}))'
argv = ['/opt/codex/codex', 'sandbox', '--permission-profile', 'aeep', '--include-managed-config', '--cd', '/workspace', '--', 'python3', '-c', probe]
try:
    result = subprocess.run(argv, capture_output=True, timeout=5)
    supported = result.returncode == 0 and json.loads(result.stdout).get('nested_marker') == 'aeep-linux-probe-v1'
    print(json.dumps({'nested_supported': supported, 'exit_code': result.returncode,
        'stdout_bytes': len(result.stdout), 'stderr_bytes': len(result.stderr),
        'stderr_class': stderr_class(result.stderr), 'stderr_sha256': hashlib.sha256(result.stderr).hexdigest(), 'timed_out': False}))
except subprocess.TimeoutExpired:
    print(json.dumps({'nested_supported': False, 'timed_out': True}))
except (ValueError, OSError) as exc:
    print(json.dumps({'nested_supported': False, 'error_type': type(exc).__name__}))
