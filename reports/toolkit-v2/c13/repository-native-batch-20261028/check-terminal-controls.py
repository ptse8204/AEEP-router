"""Exercise the actual collector against private copies of terminal evidence;no dispatch."""
import ast
import asyncio
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace

from aeep.assessment.models import RecipeDefinition,RecipeMaterializationRequest
from aeep.attempts import ExecutionAttemptState
from aeep.errors import ConfigurationError

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'repository-large-archives-20261027/runtime-execution'

async def main():
    review=json.loads((OLD/'operation-review.json').read_text());parent=json.loads((ROOT/review['parent_review']).read_text());request=RecipeMaterializationRequest.model_validate(review['request']);recipe=RecipeDefinition.model_validate(parent['recipe']);plan=request.plan_id
    tree=ast.parse((HERE/'run.py').read_text());outer=next(n for n in tree.body if isinstance(n,ast.AsyncFunctionDef) and n.name=='main');observe=next(n for n in ast.walk(outer) if isinstance(n,ast.AsyncFunctionDef) and n.name=='observe')
    wrapper=ast.FunctionDef(name='make_observer_fixture',args=ast.arguments(posonlyargs=[],args=[],kwonlyargs=[],kw_defaults=[],defaults=[]),body=[ast.Assign(targets=[ast.Name(id='calls',ctx=ast.Store())],value=ast.Constant(0)),copy.deepcopy(observe),ast.Return(value=ast.Name(id='observe',ctx=ast.Load()))],decorator_list=[])
    compiled=compile(ast.fix_missing_locations(ast.Module(body=[wrapper],type_ignores=[])),'ACTUAL-FIRST-PARTY-COLLECTOR-FIXTURE','exec')
    sys.path.insert(0,str(HERE))
    try:
        spec=importlib.util.spec_from_file_location('actual_report_collector_fixture',HERE/'run.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    finally:sys.path.pop(0)
    checks=[]
    for mode in ('completed','known_failed','nonterminal','cleanup_uncertain','incomplete_journal','completed_default','mixed_default'):
        with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-terminal-control-',dir=ROOT/'.aeep') as temp:
            base=Path(temp);operation=plan+'-call-1';directory=base/plan/'recipe-operations';directory.mkdir(parents=True)
            original_call=4 if mode=='known_failed' else 1
            source=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/.aeep/assessments')/plan/'recipe-operations'/(plan+'-call-'+str(original_call)+'.sqlite3')
            with sqlite3.connect('file:'+str(source)+'?mode=ro',uri=True) as original,sqlite3.connect(directory/(operation+'.sqlite3')) as fixture:original.backup(fixture)
            if mode=='nonterminal':
                with sqlite3.connect(directory/(operation+'.sqlite3')) as fixture:
                    value=json.loads(fixture.execute('SELECT payload_json FROM execution_attempts').fetchone()[0]);value['state']=next(s.value for s in ExecutionAttemptState if s not in (ExecutionAttemptState.COMPLETED,ExecutionAttemptState.FAILED));fixture.execute('UPDATE execution_attempts SET payload_json=?',(json.dumps(value),));fixture.commit()
            if mode=='incomplete_journal':
                with sqlite3.connect(directory/(operation+'.sqlite3')) as fixture:
                    value=json.loads(fixture.execute("SELECT payload_json FROM assessment_records WHERE kind='execution_evidence'").fetchone()[0]);value['complete']=False;fixture.execute("UPDATE assessment_records SET payload_json=? WHERE kind='execution_evidence'",(json.dumps(value),));fixture.commit()
            receipts=[];observations=[]
            async def invoke(*args,**kwargs):
                assert args[2] is (recipe.extension.reference if mode.endswith('_default') else recipe.extension.grader)
                if mode=='known_failed':raise ConfigurationError('SYNTHETIC transport failure with copied real terminal evidence')
                value=json.loads((OLD/'raw-observation-1.json').read_text())['output']
                return (value['evaluation'] if mode=='completed_default' else value),None
            scope={**module.__dict__,'HERE':base,'ROOT':ROOT,'request':request,'recipe':recipe,'review':{'maximum_contained_calls':1},'parent':parent,'service':SimpleNamespace(directory=base),'repo':SimpleNamespace(authorize=lambda *a:None,operation_ledger=lambda *a:SimpleNamespace(operations=[SimpleNamespace(operation_id=operation,elapsed_seconds=1.)])),'child_seconds':[],'receipts':receipts,'observations':observations,'verify_assets':lambda:None,'invoke':invoke,'subprocess':SimpleNamespace(check_output=lambda *a,**kw:b'owned-container' if mode=='cleanup_uncertain' else b'')}
            exec(compiled,scope);collector=scope['make_observer_fixture']();payload={'fixture_only':True};digest=hashlib.sha256(json.dumps(payload,separators=(',',':')).encode()).hexdigest()
            try:await collector('SYNTHETIC-'+mode,payload,digest,'default' if mode.endswith('_default') else 'operator')
            except ValueError:assert mode=='mixed_default'
            except module.CaseExecutionFailure:assert mode=='known_failed'
            except module.StopDispatch:assert mode in ('nonterminal','cleanup_uncertain','incomplete_journal')
            else:assert mode in ('completed','completed_default')
            assert len(observations)==1
            assert len(receipts)==(1 if mode in ('completed','known_failed','completed_default','mixed_default') else 0)
            if mode=='known_failed':assert receipts[0]['attempt_state']=='FAILED'
            checks.append({'fixture':mode,'passed':True})
        assert not base.exists()
    value={'passed':True,'actual_observe_function_exercised':True,'fixtures':checks,'canonical_evidence_copied_read_only':True,'actual_database_unchanged':True,'all_network_process_and_assessment_dispatch_replaced':True,'synthetic_resources_removed':True,'no_models_builds_installs_or_external_execution':True,'fixture_does_not_approve_execution_or_supply_benchmark_evidence':True}
    (HERE/'terminal-control-check-profile-routing.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))

if __name__=='__main__':asyncio.run(main())
