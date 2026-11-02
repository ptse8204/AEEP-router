"""Standard-library-only profile check, before any private package installation."""
import hashlib,json,shutil,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
work=HERE/'package-execution/work';runtime=ROOT/'.aeep/workflow-scanner-20261102/installed-runtime'
assert not work.exists()
profile='(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n(allow file-write* (literal "/dev/null"))\n'
profile+='(allow file-write* (subpath '+json.dumps(str(work))+'))\n'
profile+='(deny file-read* (subpath '+json.dumps(str(Path.home().resolve()))+'))\n'
for path in (runtime,work):profile+='(allow file-read* (subpath '+json.dumps(str(path))+'))\n'
profile+='(allow file-read-metadata '+' '.join('(literal '+json.dumps(str(p))+')' for p in dict.fromkeys((*runtime.parents,*work.parents)) if p.is_relative_to(Path.home()))+')\n'
(HERE/'package.sb').write_text(profile)
work.mkdir(parents=True,mode=0o700)
program=work/'owned-boundary.py';program.write_bytes((HERE/'package-boundary.py').read_bytes())
owned={program:hashlib.sha256(program.read_bytes()).hexdigest()}
result=None
try:
 process=subprocess.run(['/usr/bin/sandbox-exec','-f',str(HERE/'package.sb'),sys.executable,'-I','-B',str(program)],
  input=json.dumps({'outside_canary':str(HERE/'package-check.py'),'workspace':str(work)}),capture_output=True,text=True,
  cwd=work,env={'PATH':'/usr/bin:/bin','HOME':str(work),'TMPDIR':str(work),'LC_ALL':'C'},timeout=10)
 result={'passed':process.returncode==0,'stdout':process.stdout,'stderr':process.stderr,
  'profile_sha256':hashlib.sha256(profile.encode()).hexdigest(),'evidence_kind':'standard_library_only',
  'installed':False,'upstream_executed':False,'models':0}
 (HERE/'native-boundary-preparation.json').write_text(json.dumps(result,indent=2)+'\n')
 assert result['passed'],result
finally:
 for path,value in owned.items():assert hashlib.sha256(path.read_bytes()).hexdigest()==value
 assert set(p.name for p in work.iterdir())<={'owned-boundary.py','owned-probe.txt'}
 shutil.rmtree(work) # Only this standard-library fixture, never a runtime or prior resource.
print(json.dumps(result))
