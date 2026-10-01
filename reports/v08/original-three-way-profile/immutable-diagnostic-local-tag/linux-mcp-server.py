"""Fixed synthetic diagnostic; MCP stdout is protocol JSON only."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys

TOOL = {'name': 'sandbox_probe', 'description': 'Observe a fixed synthetic Linux sandbox boundary.', 'inputSchema': {'type': 'object', 'properties': {}, 'additionalProperties': False}}
PATH = Path('/workspace/private-state.json')
PATH.write_bytes(b'aeep-public-canary-v1')

def stderr_class(data):
    text = data.decode('utf-8', errors='replace').lower()
    for name, markers in (('unsupported_flag', ('unexpected argument', 'unrecognized option', 'unknown option')), ('permission_denied', ('permission denied', 'operation not permitted')), ('namespace_unavailable', ('namespace', 'unshare')), ('seccomp_unavailable', ('seccomp',)), ('landlock_unavailable', ('landlock',)), ('bwrap_unavailable', ('bwrap', 'bubblewrap'))):
        if any(marker in text for marker in markers):
            return name
    return 'unclassified' if data else 'none'

def observe():
    code = 'import json,pathlib;p=pathlib.Path("/workspace/private-state.json");r={"marker":True};\nfor op in ("read","write"):\n try:\n  p.read_bytes() if op=="read" else p.write_bytes(b"changed");r[op+"_denied"]=False\n except OSError:r[op+"_denied"]=True\nprint(json.dumps(r))'
    argv = ['/opt/codex/codex', 'sandbox', '--permission-profile', 'aeep', '--include-managed-config', '--cd', '/workspace', '--', 'python3', '-c', code]
    facts = {'server_canary_readable': PATH.read_bytes() == b'aeep-public-canary-v1'}
    try:
        result = subprocess.run(argv, capture_output=True, timeout=5)
        facts.update(exit_code=result.returncode, stderr_class=stderr_class(result.stderr), stderr_bytes=len(result.stderr), stderr_sha256=hashlib.sha256(result.stderr).hexdigest(), stdout_bytes=len(result.stdout))
        facts['child'] = json.loads(result.stdout) if result.returncode == 0 else None
    except (OSError, ValueError, subprocess.TimeoutExpired) as exc:
        facts['error_type'] = type(exc).__name__
    facts['canary_unchanged'] = PATH.read_bytes() == b'aeep-public-canary-v1'
    return facts

for line in sys.stdin:
    message = json.loads(line)
    if 'id' not in message:
        continue
    method = message.get('method')
    if method == 'initialize':
        result = {'protocolVersion': message.get('params', {}).get('protocolVersion', '2025-11-25'), 'serverInfo': {'name': 'linux-boundary-diagnostic', 'version': '1'}, 'capabilities': {'tools': {}}}
    elif method == 'tools/list':
        result = {'tools': [TOOL]}
    elif method == 'tools/call' and message.get('params', {}).get('name') == 'sandbox_probe' and message.get('params', {}).get('arguments', {}) == {}:
        facts = observe()
        result = {'content': [{'type': 'text', 'text': json.dumps(facts)}], 'structuredContent': facts, 'isError': False}
    else:
        print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'error': {'code': -32601, 'message': 'Unsupported fixed diagnostic request'}}), flush=True)
        continue
    print(json.dumps({'jsonrpc': '2.0', 'id': message['id'], 'result': result}), flush=True)
