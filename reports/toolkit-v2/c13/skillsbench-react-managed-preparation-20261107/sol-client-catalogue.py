"""Ask the new bundled App Server catalogue without auth, networking, or turns."""

import json
import os
import signal
import subprocess
from pathlib import Path

PREFIX = '/opt/codex-0.159.1'
assert os.getuid() == os.getgid() == 65534
assert not Path('/var/run/docker.sock').exists()
assert Path('/proc/net/route').read_text().splitlines()[1:] == []
home = Path('/tmp/isolated-codex')
home.mkdir(mode=0o700)
env = {'PATH': PREFIX + '/codex-path:/usr/local/bin:/usr/bin:/bin', 'HOME': str(home),
       'CODEX_HOME': str(home), 'LC_ALL': 'C', 'TMPDIR': '/tmp'}
signal.alarm(35)
process = subprocess.Popen([PREFIX + '/bin/codex', 'app-server', '-c', 'mcp_servers={}',
                            '-c', 'features.apps=false'],
                           stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           env=env, cwd=home)


def send(method, params, index=None):
    request = {'method': method, 'params': params}
    if index is not None:
        request['id'] = index
    process.stdin.write((json.dumps(request) + '\n').encode())
    process.stdin.flush()
    if index is None:
        return None
    for _ in range(40):
        line = process.stdout.readline(1024 * 1024 + 1)
        assert 0 < len(line) <= 1024 * 1024
        reply = json.loads(line)
        if reply.get('id') == index:
            assert 'error' not in reply
            return reply['result']
    raise RuntimeError('App Server response not observed')


try:
    response = send('initialize', {'clientInfo': {'name': 'aeep-agent-router', 'title': 'AEEP', 'version': '0.8'},
                                   'capabilities': {'experimentalApi': True}}, 1)
    send('initialized', {})
    cursor, cursors, selected = None, set(), []
    for i in range(2, 12):
        params = {'includeHidden': False}
        if cursor is not None:
            params['cursor'] = cursor
        page = send('model/list', params, i)
        for item in page['data']:
            if (item.get('model') or item.get('id')) == 'gpt-6.1-sol':
                selected.append(sorted({row['reasoningEffort'] for row in item['supportedReasoningEfforts']}))
        cursor = page.get('nextCursor')
        if not cursor:
            break
        assert cursor not in cursors
        cursors.add(cursor)
    else:
        raise RuntimeError('App Server catalogue exceeded the page bound')
    result = {'protocol_version': response.get('userAgent'), 'visible_sol_models': len(selected),
              'medium_supported': len(selected) == 1 and 'medium' in selected[0],
              'catalogue_complete': True, 'model_turns': 0, 'account_read': False,
              'network_denied': True}
finally:
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
    signal.alarm(0)
print(json.dumps(result))
