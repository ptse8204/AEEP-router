import json, os, subprocess, time
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
root=Path.cwd()
out=root/'reports/v08/steering-v1-delivery-validation'
source=verification_source_digest(root)
previous=json.loads((root/'reports/v08/steering-v1-repair-validation/results.json').read_text())
commands=[[arg.replace('steering-v1-repair-validation','steering-v1-delivery-validation') for arg in item['argv']] for item in previous['commands']]
commands.extend(item['argv'] for item in json.loads((root/'reports/v08/steering-v1-repair-validation/integration-results.json').read_text()))
env={**os.environ,'PYTHONPATH':str(root/'src'),'COVERAGE_FILE':str(out/'.coverage')}
results={'source_digest':source,'commands':[]}
print('Frozen source',source,flush=True)
for i,argv in enumerate(commands):
    started=time.perf_counter()
    log=out/f'{i:02}.log'
    with log.open('w') as stream:
        result=subprocess.run(argv,env=env,stdout=stream,stderr=subprocess.STDOUT,timeout=1500,check=False)
    unchanged=verification_source_digest(root)==source
    item={'argv':argv,'exit_code':result.returncode,'seconds':time.perf_counter()-started,'log':str(log.relative_to(root)),'source_unchanged':unchanged}
    results['commands'].append(item)
    (out/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(i,result.returncode,round(item['seconds'],2),' '.join(argv),flush=True)
    if result.returncode or not unchanged:
        print(log.read_text()[-5000:],flush=True)
        raise SystemExit(1)
