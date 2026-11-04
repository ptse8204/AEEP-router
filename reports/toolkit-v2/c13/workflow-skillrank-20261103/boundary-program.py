"""First-party contained probe; receives only public path names and hashes."""
import hashlib,json,os,socket,sys
from pathlib import Path
r=json.load(sys.stdin)
assert hashlib.sha256(Path('/opt/aeep-skillrank').read_bytes()).hexdigest()==r['binary_sha256']
p=Path('/tmp/aeep-catalog-positive');p.write_text('owned check');assert p.read_text()=='owned check'
assert not Path(r['host_canary']).exists() and not Path(r['docker_socket']).exists()
assert not any(name in os.environ for name in ('CODEX_HOME','OPENAI_API_KEY','ANTHROPIC_API_KEY','GH_TOKEN','GITHUB_TOKEN'))
try:Path('/etc/aeep-catalog-forbidden-write').write_text('must be denied')
except PermissionError:pass
else:raise AssertionError('root was writable')
try:socket.create_connection(('1.1.1.1',443),timeout=.2)
except OSError:pass
else:raise AssertionError('external network was reachable')
print(json.dumps({'passed':True,'binary_hash_verified':True,'owned_tmp_read_write':True,'host_canary_absent':True,
 'docker_socket_absent':True,'credential_environment_absent':True,'root_write_denied':True,'external_network_denied':True}))
