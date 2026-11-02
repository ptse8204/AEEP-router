"""Owned standard-library image probes; no upstream scanner import."""
import hashlib,json,os,socket
from pathlib import Path
assert os.getuid()==65532
status=Path('/proc/self/status').read_text()
assert 'CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status
Path('/workspace/probe.txt').write_text('owned boundary fixture')
checks={'nonroot':True,'capabilities_dropped':True,'no_new_privileges':True,'workspace_writable':True}
try:Path('/opt/aeep-stack/forbidden-write').write_text('probe')
except (PermissionError,OSError):checks['image_write_denied']=True
else:raise AssertionError('image was writable')
assert not Path('/var/run/docker.sock').exists()
assert not Path('/Users/edwintse').exists()
checks.update(docker_socket_absent=True,host_home_not_mounted=True)
try:socket.create_connection(('1.1.1.1',443),timeout=.2)
except OSError:checks['external_network_unreachable']=True
else:raise AssertionError('external network reachable')
print(json.dumps({'passed':all(checks.values()),'checks':checks,
 'worker_sha256':hashlib.sha256(Path('/opt/aeep-stack/scanner_worker.py').read_bytes()).hexdigest(),
 'upstream_executed':False}))
