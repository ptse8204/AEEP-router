"""Inject a coordinator-side interruption after reservation, before Docker dispatch."""
import asyncio,json,sys
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(ROOT/'integrations/toolkit'))
import controlled
from definition import prepare
from evaluate import UpstreamFixtureAdapter
from verify_controlled import verify
from aeep.assessment.models import AssessmentEnvironment
from aeep_toolkit.models import SourcePin
REPORT=Path(__file__).resolve().parent
inputs=prepare(ROOT/'examples/toolkit_offline/format-json',REPORT/'failure-suite.json',SourcePin.model_validate_json((ROOT/'examples/toolkit_offline/source.json').read_text()))
environment=AssessmentEnvironment(environment_id='toolkit-offline-fixture',kind='container',identity={'purpose':'injected interruption; no worker launch'},container_image='sha256:9e3b3712bae59607d06a162f275f0afbd916a70bcb91b544e9f350b6a6712fd7',container_runtime='/usr/local/bin/docker',container_socket='/Users/edwintse/.docker/run/docker.sock')
output=REPORT/'interrupted'
adapter=UpstreamFixtureAdapter(Path('/private/tmp/aeep-ase-c04-tt14mj6r/rebuild'),output,environment,inputs)
(REPORT/'interruption-plan.json').write_text(json.dumps(adapter.plan,indent=2)+'\n')
async def interrupted(_executor,context):
 context.invocation_check()
 raise RuntimeError('synthetic interruption after reservation')
with patch.object(controlled.ContainerExecutor,'execute',interrupted):
 try:asyncio.run(adapter.evaluate(adapter.capabilities.implementation_sha256))
 except RuntimeError:pass
 else:raise AssertionError('fault injection did not stop dispatch')
result=json.loads((output/'result.json').read_text())
assert result['trials']==[]
assert len(result['ledger']['operations'])==1
assert result['ledger']['operations'][0]['elapsed_seconds'] is None
facts=verify(output)
assert facts['execution_state']=='incomplete' and facts['verified_trials']==0 and facts['recorded_trials']==0
(REPORT/'interruption-verification.json').write_text(json.dumps(facts|{'fault_injection':True,'docker_workers_launched':0,'unresolved_operations':1},indent=2)+'\n')
print(json.dumps(facts,indent=2))
