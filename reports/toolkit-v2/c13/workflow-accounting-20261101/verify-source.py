"""Record the existing thirteen source gates; never execute an optional SDK."""
from __future__ import annotations
import json,os,shutil,subprocess,sys,time
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent/'verification'
OUT.mkdir(exist_ok=True)
assert shutil.disk_usage(ROOT).free>50*1024**3+128*1024**2
source=verification_source_digest(ROOT)
checks=[('compileall',['-m','compileall','-q','src','examples','tests']),
('schemas',['scripts/generate_schemas.py','--check']),
('assessment-policy',['scripts/check_assessment_policy.py']),
('ruff',['-m','ruff','check','.']),('mypy',['-m','mypy','src']),
('pytest',['-m','pytest']),('coverage-tests',['-m','coverage','run','--branch','-m','pytest']),
('coverage-json',['-m','coverage','json','-o',str(OUT/'coverage.json')]),
('coverage-report',['-m','coverage','report','-m']),
('critical-coverage',['scripts/check_critical_coverage.py',str(OUT/'coverage.json')]),
('assessment-coverage',['scripts/check_assessment_coverage.py',str(OUT/'coverage.json')]),
('toolkit-integration-fixtures',['-m','pytest','integrations/toolkit']),
('build',['-m','build','--no-isolation','--outdir',str(OUT/'dist')])]
record={'source_before':source,'source_after':source,'checks':[],'models':0,
'evidence_kind':'first_party_engineering_checks','comparative_campaigns':'PAUSED',
'scope':'Optional workflow ledger scope, atomic outstanding-operation guard, plan linkage and exclusive wrapper measurements. No optional SDK, real benchmark, model or usefulness claim.'}
env=dict(os.environ,PYTHONPATH=str(ROOT/'src'),PYTHONDONTWRITEBYTECODE='1')
for name,args in checks:
 assert verification_source_digest(ROOT)==source,'source changed during verification'
 started=time.monotonic()
 with (OUT/(name+'.log')).open('x') as log:
  result=subprocess.run([sys.executable,*args],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
 record['checks'].append({'name':name,'argv':[sys.executable,*args],
 'exit_code':result.returncode,'elapsed_seconds':time.monotonic()-started})
 record['source_after']=verification_source_digest(ROOT)
 (OUT/'checks.json').write_text(json.dumps(record,indent=2)+'\n')
 print(json.dumps(record['checks'][-1]),flush=True)
 if result.returncode or record['source_after']!=source:break
