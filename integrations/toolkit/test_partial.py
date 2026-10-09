import asyncio
from pathlib import Path
from unittest.mock import patch

import controlled
import controlled_report
import pytest
import stack
import test_controlled
from receipts import FixtureRecord

from aeep.models import ExecutionStatus, RawExecution


@pytest.fixture
def fixture():
    case=test_controlled.ControlledTests('test_bad_worker_output_charged_and_stops_other_arm')
    case.setUp()
    try:
        yield case
    finally:
        case.doCleanups()


def report(case):
    plan,recipe=controlled_report.freeze(case.repo,case.request,{'evals':[{'id':'case','prompt':'current prompt'}]},case.spec)
    definition=FixtureRecord(facts={'stack':stack.manifest()})
    return controlled_report.create(Path(case.temp.name),case.repo,plan,recipe,definition,case.bridge.environment,case.bridge.results,[],incomplete=True)


def test_failure_keeps_cost_and_unknown_grade(fixture):
    async def failed(_executor,context):
        return RawExecution(status=ExecutionStatus.TIMEOUT,error_type='TIMEOUT')
    with patch.object(controlled.ContainerExecutor,'execute',failed),pytest.raises(ValueError):
        asyncio.run(fixture.bridge.dispatch(fixture.message()))
    summary=report(fixture)
    assert summary['outcome']=='NOT_ASSESSED'
    facts=summary['reviewed_analysis']
    assert facts['matched_receipts']==1 and facts['missing_trial_positions']==1
    assert facts['unresolved_operations']==0
    assert summary['cohorts'][0]['families'][0]['arms']['control']['verification']['unknown']==1
    rendered=(Path(fixture.temp.name)/'report.html').read_text()
    assert 'Missing trial positions: 1; unresolved operations: 0' in rendered
    assert 'Worker-operation elapsed seconds' in rendered


def test_interruption_keeps_unresolved_operation_and_missing_trials(fixture):
    async def interrupted(_executor,context):
        raise RuntimeError('lost worker')
    with patch.object(controlled.ContainerExecutor,'execute',interrupted),pytest.raises(RuntimeError):
        asyncio.run(fixture.bridge.dispatch(fixture.message()))
    summary=report(fixture)
    facts=summary['reviewed_analysis']
    assert facts['matched_receipts']==0 and facts['missing_trial_positions']==2
    assert facts['unresolved_operations']==1
    assert summary['cohorts']==[]
    rendered=(Path(fixture.temp.name)/'report.md').read_text()
    assert 'Missing trial positions: 2; unresolved operations: 1' in rendered
    assert 'complete evaluation-cost total' in rendered


def test_forged_exposure_is_not_promoted_to_a_partial_observation(fixture):
    async def forged(_executor,context):
        return RawExecution(status=ExecutionStatus.SUCCESS,output={
            'output':'untrusted','candidate_exposed':True,'uid':65534,
            'python_available':True,'shell_available':True})
    with patch.object(controlled.ContainerExecutor,'execute',forged),pytest.raises(ValueError):
        asyncio.run(fixture.bridge.dispatch(fixture.message()))
    summary=report(fixture)
    assert summary['outcome']=='NOT_ASSESSED'
    assert fixture.bridge.results[0]['candidate_exposed'] is None
