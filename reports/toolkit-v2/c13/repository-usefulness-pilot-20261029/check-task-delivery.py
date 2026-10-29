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
    document=json.loads((HERE/'collector-definitions.json').read_text());pair=WorkerPairInspection.model_validate(document['definitions'][document['pair_definition_digest']]);recipe=RecipeDefinition.model_validate(document['definitions'][document['requests'][0]['recipe_digest']]);observed=[]
    class RecordingHost:
        async def probe(self):return HostProbe(adapter_id='fixture',status='ready')
        async def execute(self,context):
            public=json.loads(context.instruction.split(MARKER,1)[1])
            assert public['task']==context.request.input['task'] and public['task_id']==context.request.input['task_id']
            assert public['base_sha256']==context.request.input['base_sha256']
            assert public['editable_paths']==context.request.input['editable_paths']
            assert public['input_path']=='/workspace/repository.tar.gz' and public['output_path']=='/workspace/patch.json.gz'
            assert 'source_b64' not in public and context.request.input['source_b64'] not in context.instruction
            assert all(key not in public for key in ['truth','tests','reference','fail_to_pass','pass_to_pass'])
            observed.append({'role':context.config.invocation.mode,'case':public['task_id'],'instruction_sha256':hashlib.sha256(context.instruction.encode()).hexdigest(),'task_basehash_edit_scope_and_paths_present':True,'archive_bytes_and_oracles_absent':True})
            return RawExecution(status='success',output={})
    registry=ManagedHostRegistry()
    for spec in [pair.control,pair.treatment]:registry.register(spec.config['adapter_id'],RecordingHost())
    executor=ManagedHostExecutor(registry)
    for case in recipe.generator_config['cases']:
        for spec in [pair.control,pair.treatment]:
            context=ExecutionContext(request=ActionRequest(capability=recipe.capability,input=case['input']),spec=spec,estimate=spec.estimate,attempt=1)
            prepared,_=prepare_context(context);raw=await executor.execute(prepared)
            assert raw.metadata['task_instruction_sha256']==observed[-1]['instruction_sha256']
    assert len(observed)==42 and len({r['instruction_sha256'] for r in observed})==21
    for task in {r['case'] for r in observed}:assert len({r['instruction_sha256'] for r in observed if r['case']==task})==1
    prior=json.loads((HERE.parent/'repository-model-fault-correction-20261023/collector-definitions.json').read_text());old=prior['definitions'][prior['pair_definition_digest']]['control']['config']['instructions'];assert MARKER not in old and '{input' not in old
    result={'passed':True,'recording_fixture_only':True,'actual_rendered_managed_executor_checks':len(observed),'distinct_case_instructions':21,'control_treatment_instructions_equal_per_case':True,'source_digest':document['source_digest'],'pair_definition_digest':document['pair_definition_digest'],'checks':observed,'old_constant_template_rejected':True,'actual_models_workers_or_grant_operations':0,'qualification_or_usefulness_claim':False}
    (HERE/'task-delivery-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:v for k,v in result.items() if k!='checks'}))


if __name__=='__main__':asyncio.run(main())
