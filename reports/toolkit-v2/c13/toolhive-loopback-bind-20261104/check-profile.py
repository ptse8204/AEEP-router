"""First-party socket control. This does not run ToolHive or a container."""
import json
import socket
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
review = json.loads((HERE / 'operation-review.json').read_bytes())
program = """
import errno,json,socket
r={}
for port in (39068,39069):
 for name,kind in [('tcp',socket.SOCK_STREAM),('udp',socket.SOCK_DGRAM)]:
  with socket.socket(socket.AF_INET,kind) as s:
   try:
    s.bind(('127.0.0.1',port))
    if name=='tcp':s.listen(1)
    r[str(port)+'/'+name]='allowed'
   except OSError as e:r[str(port)+'/'+name]=errno.errorcode.get(e.errno)
print(json.dumps(r))
"""
out = subprocess.run(
    ['/usr/bin/sandbox-exec', '-f', review['controller_profile'],
     review['python'], '-I', '-B', '-c', program],
    env=review['environment'], cwd=review['work'], check=True,
    capture_output=True, text=True, timeout=8,
)
facts = json.loads(out.stdout)
assert facts == {'39068/tcp': 'allowed', '39068/udp': 'allowed',
                 '39069/tcp': 'EPERM', '39069/udp': 'EPERM'}
print(json.dumps({
    'passed': True, 'first_party_socket_control': facts, 'toolhive_executed': False,
    'wildcard_limitation_observed_in_development': True, 'profile_sha256':
        __import__('hashlib').sha256(Path(review['controller_profile']).read_bytes()).hexdigest(),
}, indent=2))
