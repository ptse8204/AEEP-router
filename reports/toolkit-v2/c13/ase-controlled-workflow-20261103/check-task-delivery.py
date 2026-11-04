"""Inspect the actual rendered managed-host task boundary with a recording fixture.

Runs only AEEP preparation and ManagedHostExecutor against a first-party stub.
No process worker, repository code, model, credentials or grant operation.
"""
import asyncio
import hashlib
import json
from pathlib import Path

from aeep.assessment.adapters import prepare_context
from aeep.assessment.models import RecipeDefinition
from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import HostProbe,ManagedHostRegistry
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.models import ActionRequest,RawExecution

HERE=Path(__file__).resolve().parent
MARKER='Current task JSON and bound artifact paths:\n'


async def main():
    document=json.loads((HERE/'context.json').read_text());pair=WorkerPairInspection.model_validate(json.loads((HERE/'pair-shape-fixture.json').read_text()));recipe=RecipeDefinition.model_validate(json.loads((HERE/'recipe.json').read_text()));observed=[]
    class RecordingHost:
        async def probe(self):return HostProbe(adapter_id='fixture',status='ready')
        async def execute(self,context):
            public=json.loads(context.instruction.split(MARKER,1)[1])
            assert public['task']==context.request.input['task'] and public['task_id']==context.request.input['task_id']
            assert public['base_sha256']==context.request.input['base_sha256']
            assert public['editable_paths']==context.request.input['editable_paths']
            assert public['input_path']=='/workspace/repository.tar.gz' and public['output_path']=='/workspace/patch.json'
            assert 'source_b64' not in public and context.request.input['source_b64'] not in context.instruction
            assert all(key not in public for key in ['truth','tests','reference','fail_to_pass','pass_to_pass'])
            observed.append({'role':context.config.invocation.mode,'case':public['task_id'],'instruction_sha256':hashlib.sha256(context.instruction.encode()).hexdigest(),'task_basehash_edit_scope_and_paths_present':True,'archive_bytes_and_oracles_absent':True})
            return RawExecution(status='success',output={})
    registry=ManagedHostRegistry()
    for spec in [pair.control,pair.treatment]:registry.register(spec.config['adapter_id'],RecordingHost())
    executor=ManagedHostExecutor(registry)
    for case in [json.loads((HERE/'task.json').read_text())]:
        for spec in [pair.control,pair.treatment]:
            context=ExecutionContext(request=ActionRequest(capability=recipe.capability,input=case['input']),spec=spec,estimate=spec.estimate,attempt=1)
            prepared,_=prepare_context(context);raw=await executor.execute(prepared)
            assert raw.metadata['task_instruction_sha256']==observed[-1]['instruction_sha256']
    assert len(observed)==2 and len({r['instruction_sha256'] for r in observed})==1
    for task in {r['case'] for r in observed}:assert len({r['instruction_sha256'] for r in observed if r['case']==task})==1
    result={'passed':True,'recording_fixture_only':True,'actual_rendered_managed_executor_checks':len(observed),'distinct_case_instructions':1,'control_treatment_instructions_equal_per_case':True,'source_digest':document['source'],'pair_definition_digest':__import__('hashlib').sha256((HERE/'pair-shape-fixture.json').read_bytes()).hexdigest(),'checks':observed,'actual_models_workers_or_grant_operations':0,'qualification_or_usefulness_claim':False}
    (HERE/'task-delivery-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'}))


if __name__=='__main__':asyncio.run(main())
