"""Standard-library checks of this exact CLI launch; never import Cisco."""
import json,os,socket
from pathlib import Path
checks={}
assert os.getuid()==65534
status=Path('/proc/self/status').read_text()
assert 'CapEff:\t0000000000000000' in status and 'NoNewPrivs:\t1' in status
checks.update(nonroot=True,capabilities_dropped=True,no_new_privileges=True)
Path('/tmp/owned-probe').write_text('owned containment probe')
checks['private_tmp_writable']=True
try:Path('/opt/aeep-stack/forbidden-write').write_text('denied fixture')
except OSError:checks['image_write_denied']=True
else:raise AssertionError('image writable')
assert not Path('/var/run/docker.sock').exists()
assert not Path('/Users/edwintse/.codex').exists()
checks.update(no_docker_socket=True,no_host_credentials=True)
try:socket.create_connection(('1.1.1.1',443),timeout=.2)
except OSError:checks['external_network_unreachable']=True
else:raise AssertionError('network reachable')
print(json.dumps({'passed':all(checks.values()),'checks':checks,'upstream_executed':False}))
