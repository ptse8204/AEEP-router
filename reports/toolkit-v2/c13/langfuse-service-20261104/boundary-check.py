"""Standard-library-only profile probe; no SDK, Docker, service or credentials."""
import errno,json,socket,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
work=ROOT/'.aeep/langfuse-service-20261104'
denied=[]
for name,operation in [('outside_read',lambda:(work/'outside-canary.txt').read_bytes()),
                       ('outside_write',lambda:(work/'forbidden-owned-probe.txt').write_text('OWNED_PROBE'))]:
    try:operation()
    except PermissionError:denied.append(name)
    else:raise AssertionError(name+' was allowed')
with socket.socket() as s:
    s.settimeout(1)
    try:s.connect(('1.1.1.1',443))
    except PermissionError:denied.append('external_network')
    else:raise AssertionError('external network was allowed or unexpectedly reached')
with socket.socket() as s:
    s.settimeout(1)
    try:s.connect(('127.0.0.1',39067))
    except ConnectionRefusedError:pass
    else:raise AssertionError('port should be unused during first-party preparation')
assert (HERE/'cli.sb').read_text().startswith('(version 1)')
p=work/'tmp/owned-boundary-probe.txt';p.write_text('OWNED_PROBE');assert p.read_text()=='OWNED_PROBE';p.unlink()
print(json.dumps({'passed':True,'standard_library_only':True,'denied':denied,'local_port_permitted_but_no_service_running':True,'owned_tmp_read_write':True,'sdk_or_guest_execution':False}))
