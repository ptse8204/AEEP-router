"""Standard-library-only installed check boundary probe."""
import json,socket,sys
from pathlib import Path
request=json.load(sys.stdin);work=Path(request['workspace'])
(work/'owned-probe.txt').write_text('owned sandbox fixture')
try:Path(request['outside_canary']).read_bytes()
except PermissionError:pass
else:raise AssertionError('other home file readable')
try:Path(request['outside_canary']).with_name('forbidden-write').write_text('denied')
except PermissionError:pass
else:raise AssertionError('outside write permitted')
try:socket.create_connection(('1.1.1.1',443),timeout=.2)
except OSError:pass
else:raise AssertionError('network permitted')
print(json.dumps({'passed':True,'outside_read_denied':True,'outside_write_denied':True,'network_denied':True}))
