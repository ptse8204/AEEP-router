"""Real optional SDK engineering check. Run only under the exact parent review."""
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import time
from datetime import timedelta
from decimal import Decimal
from importlib.metadata import version
from pathlib import Path

from aeep.assessment.models import (
    AssessmentAuthorization, AssessmentLimits, RecipeMaterializationRequest, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, StrictModel, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.langgraph_workflow import DispatchResult, GraphDefinition, compile_graph, invoke


class EngineeringScope(StrictModel):
    role: str
    purpose: str = 'Real LangGraph composition over owned, no-model AEEP command executors'
    review_sha256: str
    implementation_source: str


async def main():
    request = json.load(sys.stdin)
    assert set(request) == {'review_sha256', 'canary_path', 'installed_source'}
    assert version('langgraph') == '1.2.14'
    implementation = verification_source_digest(Path(__import__('aeep.assessment.verification', fromlist=['x']).__file__).resolve().parents[3])
    assert implementation == request['installed_source']
    denied = False
    try:
        Path(request['canary_path']).read_bytes()
    except PermissionError:
        denied = True
    assert denied, 'host/home read boundary failed'
    # The network denial is verified by the first-party sandbox preflight before this worker.
    from langgraph.checkpoint.memory import InMemorySaver
    store = ReceiptStore(Path.cwd()/'canonical.sqlite3')
    repo = AssessmentRepository(store)
    scopes = [EngineeringScope(role=role, review_sha256=request['review_sha256'], implementation_source=implementation)
              for role in ('subject', 'recipe', 'environment', 'mapping')]
    refs = [repo.put('toolkit_engineering_scope', item.role, item) for item in scopes]
    for ref in refs:
        repo.review(ref)
    grant = AssessmentAuthorization(
        authorization_id='langgraph-engineering-'+request['review_sha256'],
        subject_digests=[refs[0]], recipe_digests=[refs[1]], environment_digests=[refs[2]],
        limits=AssessmentLimits(max_operations=8, max_model_turns=0, max_elapsed_seconds=120, max_cash_usd=Decimal(0)),
        allowed_destinations=['local'], expires_at=utc_now()+timedelta(minutes=10),
    )
    repo.grant(grant)
    scope = RecipeMaterializationRequest(subject_digest=refs[0], recipe_digest=refs[1], environment_digest=refs[2],
        mapping_digest=refs[3], authorization_id=grant.authorization_id, definition_digests=refs, seed=0)
    repo.put('recipe_materialization_request', scope.plan_id, scope)
    executor = CommandExecutor()
    receipts = []
    revoked = False

    def authorize():
        assert not revoked, 'dispatcher revoked'
        assert verification_source_digest(Path(__import__('aeep.assessment.verification', fromlist=['x']).__file__).resolve().parents[3]) == implementation
        repo.authorize(scope)

    # Each invocation is bound to an exact graph/node/step/task before the SDK runs.
    allowed = {}
    async def dispatch(executor_id, key, task):
        authorize()
        assert executor_id == 'owned.public-calibration' and key in allowed
        expected_task, response = allowed[key]
        assert task == expected_task
        spec = ExecutorSpec(id=executor_id, capability='toolkit.public-calibration@1', kind='command',
            description='Exact owned no-model JSON echo; no shell or generated code',
            estimate={'cash':{'amount_usd':'0','upper_bound_usd':'0','evidence':{'status':'complete','source':'operator_report','trust':'self_asserted'}}},
            config={'argv':[sys.executable,'-I','-c','import json,sys;d=json.load(sys.stdin);print(json.dumps({"accepted":d["accepted"]}))'],
                    'argv_literal':True,'inherit_env':False,'stdin_json':True,'timeout_seconds':5,
                    'output':{'type':'json'},'max_output_bytes':1024})
        action = ActionRequest(capability=spec.capability,input={'accepted':response})
        repo.reserve(scope,key,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=15),stage='sdk_approved_step')
        started, clock = utc_now(), time.monotonic()
        raw = None
        try:
            context = ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,attempt_id=key,
                                       approved_side_effect=SideEffect.NONE,invocation_check=authorize)
            raw = await (await executor.start(context)).task
            receipt = ExecutionReceipt(decision_id='langgraph-'+key,action_id=action.action_id,
                capability=spec.capability,executor_id=spec.id,executor_kind=spec.kind,status=raw.status,
                started_at=started,ended_at=utc_now(),estimated=spec.estimate,actual_resources=raw.resources,
                accounting=raw.accounting,execution_success=raw.status.value=='success',error_type=raw.error_type,
                metadata={'review_sha256':request['review_sha256'],'evidence_kind':'engineering_fixture',**raw.metadata})
            store.save_receipt(receipt)
            ref=repo.put('toolkit_integration_receipt',key,receipt);receipts.append(ref)
            assert receipt.execution_success and raw.output == {'accepted':response}
            return DispatchResult(succeeded=response,evidence_ref=ref)
        finally:
            repo.finish_operation(key,elapsed_seconds=time.monotonic()-clock,
                accounting=raw.accounting if raw else None,resources=raw.resources if raw else None)

    def prepare_graph(thread, nodes, steps, outcomes, interruptions=()):
        definition=GraphDefinition(entry='validate',nodes=nodes,maximum_steps=steps,interrupt_before=interruptions)
        task=content_digest({'public_calibration':thread})
        for index,(node,success) in enumerate(outcomes):
            key=content_digest({'graph':content_digest(definition.model_dump(mode='json')),'thread':thread,
                                'task':task,'step':index,'node':node})
            allowed[key]=(task,success)
        compiled=compile_graph(definition,thread_id=thread,dispatch=dispatch,checkpointer=InMemorySaver())
        return definition,compiled,task

    checks=[]
    try:
        node=lambda success,failure:dict(executor_id='owned.public-calibration',on_success=success,on_failure=failure)
        definition,graph,task=prepare_graph('conditional',{'validate':node('end','repair'),'repair':node('validate','end')},4,
                                           [('validate',False),('repair',True),('validate',True)])
        result=await invoke(graph,definition,thread_id='conditional',task_ref=task)
        assert result['state']['steps']==3 and not result['interrupted']
        checks.append({'check':'conditional_execution','passed':True,'step_receipts':3})
        definition,graph,task=prepare_graph('bounded-loop',{'validate':node('end','validate')},2,
                                           [('validate',False),('validate',False)])
        try:
            await invoke(graph,definition,thread_id='bounded-loop',task_ref=task)
            raise AssertionError('unbounded loop accepted')
        except ValueError as error:
            assert 'ceiling' in str(error)
        checks.append({'check':'loop_ceiling','passed':True,'step_receipts':2})
        definition,graph,task=prepare_graph('interrupted',{'validate':node('end','end')},2,
                                           [('validate',True)],('validate',))
        paused=await invoke(graph,definition,thread_id='interrupted',task_ref=task)
        assert paused['interrupted'] and paused['state']['steps']==0
        finished=await invoke(graph,definition,thread_id='interrupted',task_ref=None)
        assert not finished['interrupted'] and finished['state']['steps']==1
        checks.append({'check':'interrupt_and_resume','passed':True,'step_receipts':1})
        missing=compile_graph(definition,thread_id='interrupted',dispatch=dispatch,checkpointer=InMemorySaver())
        try:
            await invoke(missing,definition,thread_id='interrupted',task_ref=None)
            raise AssertionError('lost checkpoint restarted automatically')
        except ValueError as error:
            assert 'no interrupted checkpoint' in str(error)
        revoked=True
        definition,graph,task=prepare_graph('denied',{'validate':node('end','end')},1,[('validate',True)])
        before=len(receipts)
        try:
            await invoke(graph,definition,thread_id='denied',task_ref=task)
            raise AssertionError('revoked dispatch accepted')
        except AssertionError as error:
            assert 'dispatcher revoked' in str(error)
        assert len(receipts)==before
        checks.append({'check':'lost_checkpoint_and_denied_dispatch','passed':True,'step_receipts':0})
        ledger=repo.operation_ledger(scope.plan_id)
        assert len(ledger.operations)==6 and all(op.elapsed_seconds is not None for op in ledger.operations)
        repo.put('operation_ledger',scope.plan_id,ledger)
        print(json.dumps({'sdk':'langgraph','version':version('langgraph'),'checks':checks,'receipts':receipts,
                          'operations':len(ledger.operations),'models':0,'host_home_denied':denied,
                          'recovery_scope':'same-runtime checkpoint resumption; lost state fails closed; process-restart continuation unverified',
                          'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED',
                          'all_integration_readiness':'NOT_ESTABLISHED'}))
    finally:
        await executor.close()
        store.close()


if __name__=='__main__':
    asyncio.run(main())
