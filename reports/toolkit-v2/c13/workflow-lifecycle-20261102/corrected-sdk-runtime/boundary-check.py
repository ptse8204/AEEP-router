"""Standard-library-only denial probe within each prospective component profile."""
import json,socket,sqlite3,sys
from pathlib import Path
request=json.load(sys.stdin)
c=sqlite3.connect('probe.sqlite3');c.execute('create table boundary (n integer)');c.close()
checks={'owned_sqlite_write':True}
try:Path(request['canary_path']).read_bytes()
except PermissionError:checks['outside_canary_read_denied']=True
else:raise AssertionError('outside canary readable')
try:Path('/Users/edwintse/Documents/aeep-toolkit-v2/reports/toolkit-v2/c13/workflow-accounting-20261101/composed-sdk-runtime/execution/owned-work/canonical.sqlite3').read_bytes()
except PermissionError:checks['old_graph_database_denied']=True
else:raise AssertionError('old Graph database readable')
try:socket.create_connection(('127.0.0.1',9),timeout=.1)
except PermissionError:checks['network_denied']=True
else:raise AssertionError('network allowed')
print(json.dumps({'passed':all(checks.values()),'checks':checks,'upstream_executed':False}))
