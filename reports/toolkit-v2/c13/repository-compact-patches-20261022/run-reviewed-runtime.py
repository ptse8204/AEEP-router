"""Run the exact reviewed calls once, then reopen their canonical evidence."""
import subprocess,sys
from pathlib import Path

here=Path(__file__).resolve().parent
root=here.parents[3]
assert len(sys.argv)==2
for name,args in [('run.py',[sys.argv[1]]),('audit-execution.py',[])]:
    completed=subprocess.run([sys.executable,str(here/name),*args],cwd=root,check=False)
    if completed.returncode:
        raise SystemExit(completed.returncode)
