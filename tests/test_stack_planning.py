from __future__ import annotations

import asyncio
import json
import sys
from datetime import timedelta

import pytest
from typer.testing import CliRunner

from aeep.assessment.models import content_digest
from aeep.cli import app
from aeep.errors import ConfigurationError
from aeep.examples.stack_fixtures import fixture
from aeep.integrations import export_tools
from aeep.models import CashEstimate, ResourceVector, RouteEstimate, utc_now
from aeep.provider_setup import (
    HostManagedSetupAdapter,
    ProviderSetupDefinition,
    ProviderSetupService,
)
from aeep.router import Router
from aeep.stack_models import ArtifactContract, GoalSpec, StackPlanningConfig
from aeep.stack_planning import StackService, compatible, schema_compatibility
from aeep.stack_runtime import StackRuntime


def approved(router, goal):
    service = StackService(router)
    proposal = service.propose(goal)
    service.repository.review(content_digest(proposal))
    return service, proposal


@pytest.mark.parametrize('family', ['media', 'data', 'research'])
async def test_real_offline_execution_and_restart_without_replay(tmp_path, family):
    manifest, goal, inputs = fixture(family, database=str(tmp_path / 'state.db'))
    router = Router(manifest)
    service, proposal = approved(router, goal)
    assert proposal.status == 'READY'
    result = await StackRuntime(service).run(proposal.proposal_id, inputs)
    assert result['status'] == 'complete'
    assert len(result['receipt_ids']) == len(goal.nodes)
    await router.close()
    router = Router(manifest)
    service = StackService(router)
    try:
        with pytest.raises(ConfigurationError, match='matching completed artifact'):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
        repeated = await StackRuntime(service).run(proposal.proposal_id, inputs,
                                                   completed_outputs=result['completed_outputs'])
        assert repeated['receipt_ids'] == result['receipt_ids']
        rows = router.store._connection.execute('SELECT attempts FROM stack_runs').fetchall()
        assert rows[0][0] == len(goal.nodes)
        # Neither original input values nor output hashes' source values are stored.
        raw = '\n'.join(router.store._connection.iterdump())
        assert inputs[goal.nodes[0].node_id]['seed'] not in raw
        assert next(iter(result['outputs'].values()))['artifact'] not in raw
    finally:
        await router.close()


async def test_proposal_is_inert_deterministic_and_has_no_review_authority(monkeypatch):
    manifest, goal, _ = fixture('data')
    router = Router(manifest)
    async def forbidden(*args, **kwargs):
        pytest.fail('planning invoked an executor')
    monkeypatch.setattr(router, 'execute', forbidden)
    try:
        service = StackService(router)
        a, b = service.propose(goal), service.propose(goal)
        assert a == b
        assert not service.preflight(a.proposal_id).ready
        assert router.store._connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0] == 0
        optimized = service.optimize(a.proposal_id, 'cheapest')
        assert optimized.parent_id == a.proposal_id and optimized.proposal_id != a.proposal_id
    finally:
        await router.close()


def test_graph_cycles_duplicate_ports_and_invalid_numbers():
    _, goal, _ = fixture('data')
    raw = goal.model_dump()
    raw['nodes'][0]['depends_on'] = ['verify']
    with pytest.raises(ValueError, match='cycle'):
        GoalSpec.model_validate(raw)
    raw = goal.model_dump()
    raw['nodes'][1]['bindings'] *= 2
    with pytest.raises(ValueError, match='distinct'):
        GoalSpec.model_validate(raw)
    for value in (float('nan'), float('inf'), -1):
        with pytest.raises(ValueError):
            StackPlanningConfig(max_seconds=value)


@pytest.mark.parametrize(('producer', 'consumer', 'expected'), [
    ({'type': 'string'}, {'type': 'string'}, 'compatible'),
    ({'type': 'integer'}, {'type': 'number'}, 'compatible'),
    ({'type': 'string'}, {'type': 'integer'}, 'incompatible'),
    ({'type': 'string'}, {'type': 'string', 'maxLength': 4}, 'unknown'),
    ({'$ref': 'https://private.test/schema'}, {'type': 'string'}, 'unknown'),
    (None, {'type': 'string'}, 'unknown'),
    ({'type': 'object'}, {'type': 'object', 'required': ['x']}, 'unknown'),
    ({'type': 'array'}, {'type': 'array'}, 'compatible'),
])
def test_conservative_schema_compatibility(producer, consumer, expected):
    assert schema_compatibility(producer, consumer)[0] == expected


def test_artifact_media_privacy_and_unknown_dimensions():
    source = ArtifactContract(semantic_type='image', value_schema={'type': 'string'}, media_type='image/png', confidentiality='private')
    assert compatible(source, source)[0] == 'compatible'
    assert compatible(source, source.model_copy(update={'max_width': 1024}))[0] == 'unknown'
    assert compatible(source, source.model_copy(update={'media_type': 'image/jpeg'}))[0] == 'incompatible'
    assert compatible(source, source.model_copy(update={'confidentiality': 'public'}))[0] == 'incompatible'


async def test_aggregate_budget_and_search_bounds():
    manifest, goal, _ = fixture('data')
    for spec in manifest.executors:
        spec.estimate = RouteEstimate(resources=ResourceVector(monetary_usd=2))
    goal.limits.max_cash_usd = 7
    router = Router(manifest)
    try:
        service = StackService(router)
        assert service.propose(goal).status == 'BLOCKED'
        goal.limits.max_cash_usd = 8
        assert service.propose(goal).maximum_cash_usd == 8
        goal.limits.retry_reserve = 1
        assert service.propose(goal).status == 'BLOCKED'
        goal.limits.retry_reserve = 0
        limited = StackService(router, config=StackPlanningConfig(max_expansions=1)).propose(goal)
        assert limited.status == 'BLOCKED' and not limited.search_complete
        manifest.executors[0].estimate.cash = CashEstimate()
        router.registry.get(manifest.executors[0].id).estimate.cash = CashEstimate()
        assert service.propose(goal).status == 'BLOCKED'
    finally:
        await router.close()


async def test_revoke_drift_propose_only_and_changed_inputs():
    manifest, goal, inputs = fixture('data')
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        service.repository.review(content_digest(proposal), revoke=True)
        with pytest.raises(ConfigurationError, match='review'):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
        service.repository.review(content_digest(proposal))
        router.registry.get(manifest.executors[0].id).config['unexpected'] = True
        assert not service.preflight(proposal.proposal_id).ready
    finally:
        await router.close()
    manifest, goal, inputs = fixture('data')
    goal.propose_only = True
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        with pytest.raises(ConfigurationError, match='propose-only'):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
    finally:
        await router.close()


async def test_concurrent_claims_do_not_duplicate_dispatch(monkeypatch):
    manifest, goal, inputs = fixture('data')
    router = Router(manifest)
    service, proposal = approved(router, goal)
    original = router.execute_workflow
    entered, release = asyncio.Event(), asyncio.Event()
    async def wait(*args, **kwargs):
        entered.set()
        await release.wait()
        return await original(*args, **kwargs)
    monkeypatch.setattr(router, 'execute_workflow', wait)
    first = asyncio.create_task(StackRuntime(service).run(proposal.proposal_id, inputs))
    await entered.wait()
    try:
        with pytest.raises(ConfigurationError, match=r'reconciliation|active'):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
        release.set()
        result = await first
        assert len(result['receipt_ids']) == 4
    finally:
        release.set()
        await router.close()


async def test_interruption_never_replays_unknown_node(monkeypatch):
    manifest, goal, inputs = fixture('data')
    router = Router(manifest)
    service, proposal = approved(router, goal)
    async def interrupted(*args, **kwargs):
        raise asyncio.CancelledError
    monkeypatch.setattr(router, 'execute_workflow', interrupted)
    try:
        with pytest.raises(asyncio.CancelledError):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
        with pytest.raises(ConfigurationError, match='reconciliation'):
            await StackRuntime(service).run(proposal.proposal_id, inputs)
        row = router.store._connection.execute('SELECT state, attempts FROM stack_runs').fetchone()
        assert tuple(row) == ('uncertain', 1)
    finally:
        await router.close()


async def test_provider_setup_unknown_billing_revocation_expiry_and_handoff():
    manifest, _, _ = fixture('data')
    router = Router(manifest)
    async def observed(definition):
        return {'connectivity': 'ready', 'authentication': 'ready', 'billing': 'unknown'}
    service = ProviderSetupService(router.store, host_adapter=HostManagedSetupAdapter(observed, revision='sha256:' + 'a' * 64))
    definition = ProviderSetupDefinition(setup_id='host', adapter='host-managed', non_charging=True,
        auth_url='https://provider.example/login', billing_url='https://provider.example/billing',
        required_checks=['connectivity', 'authentication', 'billing'])
    try:
        digest = service.define(definition)
        with pytest.raises(ConfigurationError, match='review'):
            await service.check('host')
        service.repository.review(digest)
        observation = await service.check('host')
        assert not service.ready('host')
        assert service.inspect('host')['auth_url'] == definition.auth_url
        assert observation.checks['billing'] == 'unknown'
        observation.expires_at = utc_now() - timedelta(seconds=1)
        assert 'credential' not in observation.model_dump_json()
        service.repository.review(digest, revoke=True)
        assert not service.ready('host')
        with pytest.raises(ConfigurationError, match='review'):
            await service.check('host')
    finally:
        await router.close()


@pytest.mark.parametrize('url', ['http://example.com', 'https://user:pass@example.com', 'https://example.com?token=x'])
def test_provider_setup_rejects_unsafe_urls(url):
    with pytest.raises(ValueError):
        ProviderSetupDefinition(setup_id='provider', adapter='https-readiness', endpoint=url)


def test_cli_and_tool_contracts(tmp_path):
    manifest, goal, _ = fixture('data', database=str(tmp_path / 'state.db'))
    manifest_file, goal_file = tmp_path / 'manifest.json', tmp_path / 'goal.json'
    manifest_file.write_text(manifest.model_dump_json())
    goal_file.write_text(goal.model_dump_json())
    runner = CliRunner()
    result = runner.invoke(app, ['stack', '-m', str(manifest_file), 'propose', str(goal_file)])
    assert result.exit_code == 0, result.output
    proposal = json.loads(result.output)
    result = runner.invoke(app, ['stack', '-m', str(manifest_file), 'preflight', proposal['proposal_id']])
    assert result.exit_code == 0 and not json.loads(result.output)['ready']
    tools = export_tools('mcp')
    names = {t['name'] for t in tools}
    assert {'aeep_stack_propose', 'aeep_stack_preflight', 'aeep_stack_optimize', 'aeep_stack_inspect'} <= names
    assert not {'aeep_stack_run', 'aeep_stack_approve', 'aeep_stack_setup'} & names
    assert {t['name'] for t in export_tools('mcp', profile='task') if t['name'].startswith('aeep_stack_')} == set()


async def test_safe_retry_resumes_only_failed_subgraph(monkeypatch):
    from aeep.executors.python import PythonExecutor
    from aeep.models import ExecutionStatus, RawExecution
    manifest, goal, inputs = fixture('data')
    goal.limits.retry_reserve = 1
    router = Router(manifest)
    service, proposal = approved(router, goal)
    original = PythonExecutor.execute
    calls = []
    async def fail_once(self, context):
        calls.append(context.spec.id)
        if context.spec.id == 'data.transform' and calls.count('data.transform') == 1:
            return RawExecution(status=ExecutionStatus.FAILED, error_type='SyntheticFailure')
        return await original(self, context)
    monkeypatch.setattr(PythonExecutor, 'execute', fail_once)
    try:
        partial = await StackRuntime(service).run(proposal.proposal_id, inputs)
        assert partial['status'] == 'paused'
        assert set(partial['completed_outputs']) == {'ingest'}
        result = await StackRuntime(service).run(proposal.proposal_id, inputs,
            completed_outputs=partial['completed_outputs'])
        assert result['status'] == 'complete'
        assert calls == ['data.ingest', 'data.transform', 'data.transform', 'data.summarize', 'data.verify']
        assert router.store._connection.execute('SELECT attempts FROM stack_runs').fetchone()[0] == 5
        resumed = await StackRuntime(service).run(proposal.proposal_id, inputs, completed_outputs=result['completed_outputs'])
        assert resumed['receipt_ids'] == result['receipt_ids']
        assert len(resumed['receipt_ids']) == 5
    finally:
        await router.close()


async def test_converter_selected_as_part_of_configuration():
    manifest, goal, inputs = fixture('data')
    goal = GoalSpec.model_validate({**goal.model_dump(), 'nodes': goal.model_dump()['nodes'][:2], 'deliverables': ['transform']})
    png = ArtifactContract(semantic_type='image', media_type='image/png', value_schema={'type': 'string'})
    jpeg = png.model_copy(update={'media_type': 'image/jpeg'})
    goal.nodes[0].outputs['artifact'] = png
    goal.nodes[1].inputs['ingest'] = jpeg
    manifest.executors[0].config['stack']['outputs']['artifact'] = png.model_dump()
    manifest.executors[1].config['stack']['inputs']['ingest'] = jpeg.model_dump()
    converter = manifest.executors[0].model_copy(deep=True)
    converter.id, converter.capability = 'image.convert', 'image.convert@1'
    converter.config['callable'] = 'aeep.examples.stack_fixtures:pass_artifact'
    converter.config['argument_mode'] = 'kwargs'
    converter.input_schema = {'type': 'object', 'properties': {'source': {'type': 'string'}}, 'required': ['source']}
    converter.config['stack'] = {'inputs': {'source': png.model_dump()}, 'outputs': {'artifact': jpeg.model_dump()}}
    converter.estimate = RouteEstimate(resources=ResourceVector(latency_ms=1000, monetary_usd=0))
    paid = converter.model_copy(deep=True)
    paid.id = 'image.fast_paid'
    paid.estimate = RouteEstimate(resources=ResourceVector(latency_ms=1, monetary_usd=0.000001))
    manifest.executors.extend([converter, paid])
    goal.policy = 'fastest'
    router = Router(manifest)
    try:
        assert StackService(router).propose(goal).status == 'BLOCKED'
        service = StackService(router, config=StackPlanningConfig(converter_ids=['image.fast_paid', 'image.convert']))
        goal.limits.max_cash_usd = 1
        paid_proposal = service.propose(goal)
        assert paid_proposal.edges[0].converter_id == 'image.fast_paid'
        goal.limits.max_cash_usd = 0
        proposal = service.propose(goal)
        assert proposal.status == 'READY'
        assert proposal.edges[0].converter_id == 'image.convert'
        assert len(proposal.components) == 3
        service.repository.review(content_digest(proposal))
        result = await StackRuntime(service).run(proposal.proposal_id, inputs)
        assert result['status'] == 'complete' and len(result['receipt_ids']) == 3
        router.registry.get('data.ingest').config['timeout_seconds'] = 30
        successor = service.propose(goal, parent_id=proposal.proposal_id)
        service.repository.review(content_digest(successor))
        amendment = StackRuntime(service).amend(proposal.proposal_id, successor.proposal_id)
        assert amendment['preserved_nodes'] == []
        resumed = await StackRuntime(service).run(successor.proposal_id, inputs)
        assert resumed['status'] == 'complete' and len(resumed['receipt_ids']) == 3
        assert router.store._connection.execute('SELECT attempts FROM stack_runs WHERE proposal_id=?', (successor.proposal_id,)).fetchone()[0] == 6
    finally:
        await router.close()


async def test_host_only_waits_and_records_selected_delegate_once():
    from aeep.models import ExecutorKind
    manifest, goal, inputs = fixture('data')
    goal = GoalSpec.model_validate({**goal.model_dump(), 'nodes': goal.model_dump()['nodes'][:1], 'deliverables': ['ingest']})
    spec = manifest.executors[0]
    spec.kind = ExecutorKind.DELEGATE
    spec.config = {'instructions': 'Produce the requested synthetic artifact.', 'stack': spec.config['stack']}
    manifest.executors = [spec]
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        assert proposal.components[0].no_additional_capability
        runtime = StackRuntime(service)
        waiting = await runtime.run(proposal.proposal_id, inputs)
        assert waiting['status'] == 'waiting'
        finished = await runtime.run(proposal.proposal_id, inputs, delegated_outputs={'ingest': {'artifact': 'host-result'}})
        assert finished['status'] == 'complete'
        assert len(finished['receipt_ids']) == 1
        assert router.store._connection.execute('SELECT attempts FROM stack_runs').fetchone()[0] == 1
    finally:
        await router.close()


async def test_successor_carries_attempts_deadline_and_preserved_artifacts():
    manifest, goal, inputs = fixture('data')
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        runtime = StackRuntime(service)
        result = await runtime.run(proposal.proposal_id, inputs)
        successor = service.optimize(proposal.proposal_id, 'cheapest')
        service.repository.review(content_digest(successor))
        with pytest.raises(ConfigurationError, match='allowance cannot reset'):
            await runtime.run(successor.proposal_id, inputs)
        before = router.store._connection.execute('SELECT attempts, deadline FROM stack_runs').fetchone()
        amended = runtime.amend(proposal.proposal_id, successor.proposal_id)
        assert amended['preserved_nodes'] == sorted(n.node_id for n in goal.nodes)
        resumed = await runtime.run(successor.proposal_id, inputs, completed_outputs=result['completed_outputs'])
        assert resumed['receipt_ids'] == result['receipt_ids']
        after = router.store._connection.execute('SELECT attempts, deadline FROM stack_runs WHERE proposal_id=?', (successor.proposal_id,)).fetchone()
        assert tuple(before) == tuple(after)
        with pytest.raises(ConfigurationError, match='reconcile'):
            await runtime.run(proposal.proposal_id, inputs, completed_outputs=result['completed_outputs'])
    finally:
        await router.close()


def test_schema_subset_never_accepts_unconstrained_or_nested_references():
    assert schema_compatibility({'type': 'object'}, {'type': 'object', 'properties': {'x': {'type': 'integer'}}})[0] == 'unknown'
    schema = {'type': 'object', 'properties': {'x': {'$ref': 'https://example.org/private'}}}
    assert schema_compatibility(schema, schema)[0] == 'unknown'
    with pytest.raises(ValueError, match='invalid artifact schema'):
        ArtifactContract(semantic_type='example', value_schema={'type': 'invented'})


async def test_artifact_bound_stops_before_dispatch_and_provider_ids_do_not_change_results():
    manifest, goal, inputs = fixture('data')
    for spec in manifest.executors:
        spec.id = 'other-vendor.' + spec.id
    manifest.executors.reverse()
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        result = await StackRuntime(service).run(proposal.proposal_id, inputs)
        report = json.loads(result['outputs']['verify']['artifact'])
        assert report['verified'] and report['grand_total'] == 25
        assert router.store._connection.execute('SELECT COUNT(*) FROM prepared_route_decisions').fetchone()[0] == 4
    finally:
        await router.close()
    manifest, goal, inputs = fixture('data')
    goal.nodes[0].inputs['seed'] = goal.nodes[0].inputs['seed'].model_copy(update={'max_bytes': 1})
    manifest.executors[0].config['stack']['inputs']['seed']['max_bytes'] = 1
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        result = await StackRuntime(service).run(proposal.proposal_id, inputs)
        assert result['status'] == 'paused' and result['receipt_ids'] == []
        assert router.store._connection.execute('SELECT attempts FROM stack_runs').fetchone()[0] == 0
    finally:
        await router.close()


async def test_completed_receipt_can_recover_lost_checkpoint_without_replay(monkeypatch):
    from aeep.stack_models import StackRecovery
    manifest, goal, inputs = fixture('data')
    router = Router(manifest)
    captured = {}
    try:
        service, proposal = approved(router, goal)
        runtime = StackRuntime(service)
        complete = runtime._complete
        def crash(identity, node_id, output, receipt_ids):
            captured.update(output=output, receipt_ids=receipt_ids, node_id=node_id)
            raise asyncio.CancelledError
        monkeypatch.setattr(runtime, '_complete', crash)
        with pytest.raises(asyncio.CancelledError):
            await runtime.run(proposal.proposal_id, inputs)
        recovery = StackRecovery(recovery_id='lost-checkpoint', proposal_id=proposal.proposal_id,
            node_id=captured['node_id'], output_digest=content_digest({'output': captured['output']}),
            receipt_ids=captured['receipt_ids'], coordinator_stopped=True)
        digest = service.repository.put('stack_recovery', recovery.recovery_id, recovery)
        with pytest.raises(ConfigurationError, match='review'):
            runtime.reconcile(recovery.recovery_id, captured['output'])
        service.repository.review(digest)
        with pytest.raises(ConfigurationError, match='match'):
            runtime.reconcile(recovery.recovery_id, {'artifact': 'wrong'})
        assert not runtime.reconcile(recovery.recovery_id, captured['output'])['allowance_refunded']
        monkeypatch.setattr(runtime, '_complete', complete)
        result = await runtime.run(proposal.proposal_id, inputs,
            completed_outputs={captured['node_id']: captured['output']})
        assert result['status'] == 'complete' and len(result['receipt_ids']) == 4
        assert router.store._connection.execute('SELECT attempts FROM stack_runs').fetchone()[0] == 4
    finally:
        await router.close()


@pytest.mark.skipif(sys.platform == "win32", reason="native task integration requires POSIX; Windows uses WSL")
def test_reviewed_stack_task_profile_is_explicit_and_keeps_operator_ceiling(tmp_path, monkeypatch):
    import sys

    from aeep.assessment.onboarding import reference_spec
    from aeep.economic.prepared import executor_fingerprint
    from aeep.hosts.codex_sandbox import NativeSandboxConfig
    from aeep.mcp.server import AEEPToolService
    from aeep.models import ExecutorKind, Manifest, TaskScope
    from aeep.profiles import bind_service, from_scope, teardown
    from aeep.stack_models import TaskNode
    root = tmp_path.resolve()
    monkeypatch.setattr(NativeSandboxConfig, 'argv', lambda self, command: command)
    native = NativeSandboxConfig(binary=str(root / 'fixture'), binary_sha256='sha256:' + 'a' * 64, project_root=str(root))
    spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND, 'config': {
        'argv': [sys.executable, '-I', '-c', 'import json; print(json.dumps({"records":[]}))'],
        'argv_literal': True, 'output': {'type': 'json'}, 'native_sandbox': native.model_dump(mode='json'), 'timeout_seconds': 1}})
    string = ArtifactContract(semantic_type='text', value_schema={'type': 'string'})
    records = ArtifactContract(semantic_type='records', value_schema={'type': 'array'})
    spec.config['stack'] = {'inputs': {'text': string.model_dump(), 'delimiter': string.model_dump()}, 'outputs': {'records': records.model_dump()}}
    manifest = root / 'manifest.json'
    manifest.write_text(Manifest(database=str(root / 'state.db'), executors=[spec]).model_dump_json())
    async def exercise():
        router = Router.from_manifest(manifest)
        service = StackService(router)
        activation = None
        try:
            scope = TaskScope(scope_id='stack', project_root=str(root), executor_fingerprints={spec.id: executor_fingerprint(spec)},
                max_attempts=2, max_attempt_seconds=1, expires_at=utc_now() + timedelta(minutes=5))
            service.repository.review(service.repository.put('task_scope', scope.scope_id, scope))
            ordinary = from_scope(router, scope.scope_id, profile_id='ordinary', host='task-service')
            assert 'stack_execution' not in ordinary.model_dump()
            profile = from_scope(router, scope.scope_id, profile_id='stack', host='task-service', stack_execution=True)
            service.repository.review(service.repository.put('capability_profile', profile.profile_id, profile))
            assert 'aeep_stack_run' not in {t['name'] for t in AEEPToolService(router, profile='task').list_tools()}
            unbound_goal = GoalSpec(goal_id='profile-assembly', nodes=[TaskNode(node_id='read', capability=spec.capability,
                inputs={'text': string, 'delimiter': string}, outputs={'records': records})], deliverables=['read'], propose_only=False)
            unbound_proposal = service.propose(unbound_goal)
            assert not service.preflight(unbound_proposal.proposal_id).ready
            assert service.preflight(unbound_proposal.proposal_id, task_profile=profile.profile_id).ready
            activation, tools = bind_service(router, profile.profile_id)
            assert 'aeep_stack_run' in {t['name'] for t in tools.list_tools()}
            goal = GoalSpec(goal_id='scoped-stack', nodes=[TaskNode(node_id='read', capability=spec.capability,
                inputs={'text': string, 'delimiter': string}, outputs={'records': records})], deliverables=['read'], propose_only=False)
            proposal = service.propose(goal)
            assert service.preflight(proposal.proposal_id).ready
            assert router.store._connection.execute('SELECT 1 FROM assessment_reviews WHERE digest=?', (content_digest(proposal),)).fetchone() is None
            arguments = {'proposal_id': proposal.proposal_id, 'inputs': {'read': {'text': 'a\n1', 'delimiter': ','}}}
            assert (await tools.call('aeep_stack_run', {**arguments, 'approved_side_effect': 'write'}))['isError']
            result = await tools.call('aeep_stack_run', arguments)
            assert result['structuredContent']['status'] == 'complete', result
            assert len(result['structuredContent']['receipt_ids']) == 1
            service.repository.review(content_digest(proposal), revoke=True)
            assert not service.preflight(proposal.proposal_id).ready
        finally:
            if activation:
                teardown(router, activation.activation_id)
            await router.close()
    asyncio.run(exercise())


@pytest.mark.parametrize('family', ['media', 'data', 'research'])
async def test_domain_variants_missing_provider_and_setup_required(family):
    manifest, goal, _ = fixture(family)
    goal.constraints.require_local = True
    router = Router(manifest)
    try:
        assert StackService(router).propose(goal).status == 'READY'
    finally:
        await router.close()
    manifest.executors[0].config['stack']['setup_ids'] = ['operator-signin']
    router = Router(manifest)
    try:
        service = StackService(router)
        proposal = service.propose(goal)
        assert proposal.status == 'NEEDS_SETUP'
        check = service.preflight(proposal.proposal_id)
        assert not check.ready and check.setup_requirements[0]['setup_id'] == 'operator-signin'
        assert router.store._connection.execute('SELECT COUNT(*) FROM receipts').fetchone()[0] == 0
    finally:
        await router.close()
    manifest.executors.pop(0)
    router = Router(manifest)
    try:
        assert StackService(router).propose(goal).status == 'BLOCKED'
    finally:
        await router.close()


async def test_registry_contract_replacement_invalidates_exact_proposal():
    manifest, goal, _ = fixture('data')
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        changed = router.registry.get('data.ingest').model_copy(deep=True)
        changed.config['stack']['outputs']['artifact']['media_type'] = 'application/json'
        router.registry.replace(changed)
        assert not service.preflight(proposal.proposal_id).ready
    finally:
        await router.close()


async def test_amendment_uses_original_idempotency_not_replacement_claim():
    manifest, goal, inputs = fixture('data')
    manifest.executors[0].idempotent = False
    router = Router(manifest)
    try:
        service, proposal = approved(router, goal)
        result = await StackRuntime(service).run(proposal.proposal_id, inputs)
        assert result['status'] == 'complete'
        router.registry.get('data.ingest').idempotent = True
        successor = service.propose(goal, parent_id=proposal.proposal_id)
        service.repository.review(content_digest(successor))
        with pytest.raises(ConfigurationError, match='consequential'):
            StackRuntime(service).amend(proposal.proposal_id, successor.proposal_id)
    finally:
        await router.close()
