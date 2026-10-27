"""Run only the first-party synthetic boundary check, never the link checker."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[4]
OUT=ROOT/'reports/toolkit-v2/integration-completion/lychee-test-roots-review-20261027'
with tempfile.TemporaryDirectory(prefix='aeep-docs-boundary-only-',dir='/private/tmp') as temp:
    scratch=Path(temp).resolve()
    for name in ('home','tmp'):(scratch/name).mkdir()
    profile=(OUT/'sandbox-template.sb').read_text()
    for key,path in {'HOME':scratch/'home','TMP':scratch/'tmp','ROOT':ROOT,'AEEP':ROOT/'.aeep','GIT':ROOT/'.git','CODEX':ROOT/'.codex'}.items():
        profile=profile.replace('@'+key+'@',json.dumps(str(path)))
    path=scratch/'profile.sb';path.write_text(profile)
    result=subprocess.run(['/usr/bin/sandbox-exec','-f',str(path),sys.executable,'-I','-B',str(OUT/'sandbox-preflight.py'),str(ROOT),str(scratch)],cwd=ROOT,env={'PATH':os.defpath,'HOME':str(scratch/'home'),'TMPDIR':str(scratch/'tmp'),'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=20)
    assert result.returncode==0,result.stderr
    checks=json.loads(result.stdout);assert len(checks)==6 and all(checks.values())
assert not scratch.exists()
value={'passed':True,'observations':checks,'first_party_synthetic_boundary_only':True,'untrusted_checker_executed':False,'scratch_removed_after_check':True,'script_sha256':hashlib.sha256((OUT/'sandbox-preflight.py').read_bytes()).hexdigest()}
(OUT/'sandbox-preflight.json').write_text(json.dumps(value,indent=2)+'\n')
print(json.dumps(value))
