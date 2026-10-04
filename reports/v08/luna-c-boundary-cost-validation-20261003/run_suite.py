import json, os, subprocess, sys, time
from pathlib import Path
p=Path(__file__).resolve().parent
env=os.environ.copy(); env['PYTHONPATH']='src'
results=[]
for name,cmd in json.loads((p/'commands.json').read_text()):
    started=time.monotonic()
    result=subprocess.run([sys.executable,str(p/'run_check.py'),name,'--',*cmd],env=env)
    results.append({'name':name,'command':cmd,'returncode':result.returncode,'wall_seconds':time.monotonic()-started})
    (p/'suite-progress.json').write_text(json.dumps(results,indent=2)+'\n')
    if result.returncode:
        raise SystemExit(result.returncode)
(p/'suite-complete.json').write_text(json.dumps(results,indent=2)+'\n')
