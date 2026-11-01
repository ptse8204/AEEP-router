"""Trusted stdlib-only containment preparation; never import an optional SDK."""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
runtime=ROOT/'.aeep/upstream-stack-runtimes-20261101/composed-runtime'
working=HERE/'execution/owned-work'
profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
profile+='(allow file-write* (subpath '+json.dumps(str(working))+'))\n'
profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
profile+='(allow file-read* (subpath '+json.dumps(str(runtime))+'))\n'
profile+='(allow file-read* (subpath '+json.dumps(str(working))+'))\n'
profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*working.parents)) if p.is_relative_to(Path.home()))+')\n'
(HERE/'reviewed-boundary.sb').write_text(profile)
owned=HERE/'first-party-boundary-preparation';owned.mkdir(mode=0o700)
for name in ('home','tmp'):(owned/name).mkdir(mode=0o700)
test_profile=owned/'boundary.sb';test_profile.write_text(profile.replace(str(working),str(owned)))
canary=HERE/'functional-check.py';outside=HERE/'denied-preparation-write'
code=('import json,pathlib,socket,sqlite3,sys;'
 'c=sqlite3.connect(pathlib.Path.cwd()/"probe.sqlite3");'
 'c.execute("create table probe(value integer)");c.execute("insert into probe values (1)");'
 'c.commit();assert c.execute("select value from probe").fetchone()==(1,);c.close();'
 'd={"sqlite_create_write_read":True}\n'
 'try:pathlib.Path(sys.argv[1]).read_bytes()\n'
 'except PermissionError:d["home_read_denied"]=True\n'
 'try:pathlib.Path(sys.argv[2]).write_text("owned-probe")\n'
 'except PermissionError:d["outside_write_denied"]=True\n'
 'with socket.socket() as s:\n'
 ' try:s.connect(("127.0.0.1",9))\n'
 ' except PermissionError:d["network_denied"]=True\n'
 'print(json.dumps(d))')
result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(test_profile),sys.executable,'-I','-B','-S','-c',code,str(canary),str(outside)],
 cwd=owned,env={'PATH':'/usr/bin:/bin','HOME':str(owned/'home'),'TMPDIR':str(owned/'tmp'),'LC_ALL':'C'},capture_output=True,timeout=20)
passed=result.returncode==0 and not outside.exists() and json.loads(result.stdout)=={
 'sqlite_create_write_read':True,'home_read_denied':True,'outside_write_denied':True,'network_denied':True}
record={'evidence_kind':'first_party_stdlib_boundary_NOT_SDK','passed':passed,'models':0,
 'upstream_sdk_imported':False,'profile_sha256':hashlib.sha256(profile.encode()).hexdigest(),
 'test_profile_sha256':hashlib.sha256(test_profile.read_bytes()).hexdigest(),
 'profile_adaptation':'Owned preparation workspace only; actual installed-runtime check remains required after approval.',
 'retained_path':str(owned),'returncode':result.returncode,'stdout':result.stdout.decode(),
 'stderr':result.stderr[:8192].decode(errors='replace')}
(HERE/'first-party-boundary-check.json').write_text(json.dumps(record,indent=2)+'\n')
assert passed
worker=HERE/'functional-check.py'
historical=ROOT/'reports/toolkit-v2/c13/full-stack-20261030/composed-sdk-runtime'
assert worker.read_bytes()==(historical/worker.name).read_bytes()
fixture={'evidence_kind':'historical_first_party_program_fixture_binding_NOT_current_SDK',
 'worker_sha256':hashlib.sha256(worker.read_bytes()).hexdigest(),
 'historical_record':str((historical/'first-party-functional-program-check.json').relative_to(ROOT)),
 'historical_record_sha256':hashlib.sha256((historical/'first-party-functional-program-check.json').read_bytes()).hexdigest(),
 'scope':'Unchanged check-program logic has an earlier explicitly first-party builder fixture. It is not fresh SDK execution or proof of newer common runtime source.',
 'current_product_checks':'Must pass all 13 gates separately before generating an execution review.',
 'models':0,'upstream_sdk_imported':False,'executed_current_program':False}
(HERE/'first-party-functional-program-check.json').write_text(json.dumps(fixture,indent=2)+'\n')
print(json.dumps({'boundary_passed':passed,'models':0,'optional_sdk_executed':False}))
