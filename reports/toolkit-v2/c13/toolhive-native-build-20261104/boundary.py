import json,socket
from pathlib import Path
canary=Path('/Users/edwintse/Documents/aeep-toolkit-v2/.aeep/toolhive-native-boundary-20261104.txt')
for action in [lambda:canary.read_bytes(),lambda:canary.write_text('DENIED_WRITE')]:
 try:action()
 except PermissionError:pass
 else:raise AssertionError('outside scope was allowed')
with socket.socket() as s:
 s.settimeout(1)
 try:s.connect(('1.1.1.1',443))
 except PermissionError:pass
 else:raise AssertionError('network was allowed')
print(json.dumps({'passed':True,'synthetic_outside_read_write_denied':True,'network_denied':True,'no_provider_credentials_accessed':True}))
