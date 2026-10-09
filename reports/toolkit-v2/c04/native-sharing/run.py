"""Run the existing zero-turn pair probe with a bounded outer deadline."""
import asyncio,json,time
from pathlib import Path
from scripts.probe_managed_pair import probe
ROOT=Path(__file__).resolve().parents[4]
OUTPUT=Path(__file__).with_name('integrated-result.json')
assert not OUTPUT.exists()
started=time.monotonic()
async def run():
 try:
  result=await asyncio.wait_for(probe(ROOT/'reports/v08/offline-inspection-fixture-specs.json'),timeout=210)
 except TimeoutError:
  result={'passed':False,'error_type':'outer_timeout','cleanup_status':'inspect','model_turns':0,'full_conformance':False}
 result['measured_probe_elapsed_seconds']=time.monotonic()-started
 OUTPUT.write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps({'passed':result['passed'],'model_turns':0,'full_conformance':False,'elapsed_seconds':result['measured_probe_elapsed_seconds']}))
 if not result['passed']:raise SystemExit(1)
asyncio.run(run())
