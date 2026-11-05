"""New controller profile boundary, using only a synthetic owned canary."""
import json,socket
from pathlib import Path
canary=Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/toolhive-mcp-host-canary-20261104.txt')
for action in (lambda:canary.read_bytes(),lambda:canary.write_text('denied')):
    try:action()
    except PermissionError:pass
    else:raise AssertionError('unrelated read/write allowed')
with socket.socket() as stream:
    stream.settimeout(1)
    try:stream.connect(('1.1.1.1',443))
    except PermissionError:pass
    else:raise AssertionError('external controller network allowed')
print(json.dumps({'passed':True,'synthetic_outside_read_write_denied':True,'external_network_denied':True}))
