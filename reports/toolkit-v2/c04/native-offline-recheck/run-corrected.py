import asyncio,importlib.util,json,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[4]
REPORT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('corrected_probe',REPORT/'corrected-probe.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
module.ROOT=ROOT
output=REPORT/'corrected-result.json'
assert not output.exists()
started=time.monotonic()
async def run():
 try:result=await asyncio.wait_for(module.probe(ROOT/'reports/v08/offline-inspection-fixture-specs.json'),timeout=210)
 except TimeoutError:result={'passed':False,'error_type':'outer_timeout','cleanup_status':'inspect','model_turns':0,'full_conformance':False}
 result['measured_probe_elapsed_seconds']=time.monotonic()-started
 output.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'passed':result['passed'],'model_turns':0,'full_conformance':False,'elapsed_seconds':result['measured_probe_elapsed_seconds']}))
 if not result['passed']:raise SystemExit(1)
asyncio.run(run())
