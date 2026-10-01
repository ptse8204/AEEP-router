from __future__ import annotations

import json
import sys

import pytest

from aeep.assessment.boundary import (
    REQUIRED_PROBES,
    BoundaryConformance,
    BoundaryProbe,
    BoundaryProbeDefinition,
    require_conformance,
    run_boundary_probe,
)
from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.executors.command import CommandExecutor
from aeep.models import ExecutorSpec, StrictModel

pytestmark = pytest.mark.assessment_contract


def test_managed_admission_requires_the_actual_reviewed_worker(monkeypatch):
    from types import SimpleNamespace

    from test_v08_managed_workers import binding

    from aeep.assessment.boundary import require_managed_boundaries
    from aeep.assessment.models import AssessmentEnvironment

    worker = binding()
    spec = ExecutorSpec(id="host", capability="fixture", kind="host_managed", resource_pool="fixture", description="fixture",
        config={"adapter_id": "codex-exec", "argv": [worker.binary], "instructions": "fixture",
                "managed_worker": worker.model_dump(mode="json")})
    environment = AssessmentEnvironment(environment_id="fixture", kind="codex_sandbox", identity={})
    assert "conformance_digests" not in environment.model_dump()
    with pytest.raises(ConfigurationError, match="worker boundary"):
        require_managed_boundaries(None, environment, [spec], {"host": "1" * 64})
    environment.conformance_digests = {"host": "2" * 64}
    # This fixture verifies binding checks, not effective host permissions.
    record = SimpleNamespace(schema_version="assessment.boundary-conformance.v1", adapter="codex-exec", adapter_version="1", image_digest=worker.image,
        binary_digest=worker.binary_sha256, effective_policy_digest=worker.configuration_digest, configuration_digest=None)
    monkeypatch.setattr("aeep.assessment.boundary.require_conformance", lambda *_args, **_kwargs: record)
    require_managed_boundaries(None, environment, [spec], {"host": "1" * 64})
    record.adapter = "different-adapter"
    with pytest.raises(ConfigurationError, match="differs"):
        require_managed_boundaries(None, environment, [spec], {"host": "1" * 64})


class ReviewedDefinition(StrictModel):
    purpose: str


async def test_differential_shared_inventory_absence_and_drift(tmp_path, monkeypatch):
    from test_v08_assessment import setup_assessment
    from test_v08_incremental import environment

    from aeep.assessment.boundary import DifferentialConformance, require_differential
    from aeep.assessment.models import AssessmentEnvironment, IncrementalExperiment, UtilityPolicy

    router, service, plan, _grant = setup_assessment(tmp_path)
    repo = service.repository
    try:
        env = AssessmentEnvironment(environment_id='differential', kind='codex_sandbox', identity={})
        require_differential(repo, env, plan)  # Historical comparisons retain their meaning.
        shared = repo.put('definition', 'shared', ReviewedDefinition(purpose='shared python plus shell'))
        definition = environment().model_copy(update={'shared_definition_digest': shared})
        experiment = IncrementalExperiment(stage='qualification', exposure='required', environment=definition,
            utility=UtilityPolicy(benefit_dimensions=['wall_time_ms'], guardrail_dimensions=['wall_time_ms']))
        plan = plan.model_copy(update={'schema_version': 'assessment.plan.v4', 'comparison': plan.comparison.model_copy(
            update={'schema_version': 'assessment.comparison.v2', 'experiment': experiment})})
        with pytest.raises(ConfigurationError, match='missing'):
            require_differential(repo, env, plan)
        # These records test differential validation only. The independent
        # conformance validator is exercised above with real local probe results.
        monkeypatch.setattr('aeep.assessment.boundary.require_conformance', lambda *args, **kwargs: None)
        records = []
        for role, available, inventory in [('control', False, definition.control_inventory), ('treatment', True, definition.treatment_inventory)]:
            probe = BoundaryProbe(probe_id=role, name='candidate_access', implementation_digest='1'*64, worker_digest='2'*64,
                execution_evidence_digest='3'*64, observed={'definition_digest': content_digest(definition), 'candidate_available': available})
            probe_ref = repo.put('boundary_probe', role, probe)
            record = BoundaryConformance(schema_version='assessment.boundary-conformance.v2', conformance_id=role,
                source_digest='4'*64, worker_digest='2'*64, image_digest='sha256:'+'5'*64, binary_digest='6'*64,
                adapter='fixture', adapter_version='1', effective_policy_digest='7'*64, reviewed_inventory_digest=content_digest(inventory),
                identity_digest='8'*64, enforcement_definition_digest='9'*64, advertised_tools=list(inventory), permitted_tools=list(inventory),
                used_tools=[], probe_digests=[probe_ref], configuration_digest='a'*64, effective_inventory=inventory)
            records.append(record)
        def bind(control, treatment):
            refs = [repo.put('boundary_conformance', content_digest(record), record) for record in (control, treatment)]
            pair = DifferentialConformance(definition=definition, control_conformance_digest=refs[0], treatment_conformance_digest=refs[1])
            env.differential_conformance_digest = repo.put('differential_conformance', content_digest(pair), pair)
            env.conformance_digests = {plan.baseline_id: refs[0], plan.candidate_id: refs[1]}
        bind(*records)
        with pytest.raises(ConfigurationError, match='operator review'):
            require_differential(repo, env, plan)
        repo.review(shared)
        require_differential(repo, env, plan)
        env.conformance_digests[plan.baseline_id] = 'b'*64
        with pytest.raises(ConfigurationError, match='differs'):
            require_differential(repo, env, plan)
        bind(records[0].model_copy(update={'effective_inventory': definition.treatment_inventory}), records[1])
        with pytest.raises(ConfigurationError, match='effective inventory'):
            require_differential(repo, env, plan)
        bind(records[0].model_copy(update={'probe_digests': []}), records[1])
        with pytest.raises(ConfigurationError, match='availability probe'):
            require_differential(repo, env, plan)
        # An observed positive access probe in the control arm also fails.
        bind(records[0].model_copy(update={'probe_digests': records[1].probe_digests}), records[1])
        with pytest.raises(ConfigurationError, match='availability probe'):
            require_differential(repo, env, plan)
    finally:
        await router.close()


@pytest.mark.parametrize('typed_worker', [False, True])
async def test_boundary_records_require_review_real_results_and_complete_probes(tmp_path, typed_worker):
    from test_v08_assessment import setup_assessment
    router, service, plan, _grant = setup_assessment(tmp_path)
    repository = service.repository
    try:
        reviewed = []
        for name in ("worker", "enforcement", "effective-policy", "inventory"):
            digest = repository.put("definition", name, ReviewedDefinition(purpose=name))
            repository.review(digest)
            reviewed.append(digest)
        worker = reviewed[0]
        if typed_worker:
            from test_v08_managed_workers import binding
            worker = binding().digest()
            worker_document = repository.put('worker_binding', worker, binding())
            assert worker_document != worker
            repository.review(worker_document)
        spec = ExecutorSpec(id="probe", capability="probe", kind="command", description="harmless fixture",
                            config={"argv": [sys.executable, "-c", 'print(\'{"allowed": true}\')'],
                                    "output": {"type": "json"}, "timeout_seconds": 2})
        probes = []
        for name in sorted(REQUIRED_PROBES):
            definition = BoundaryProbeDefinition(name=name, executor=spec, expected={"allowed": True})
            digest = repository.put("boundary_probe_definition", name, definition)
            plan = plan.model_copy(update={"plan_id": "probe-plan-" + name, "definition_digests": [*plan.definition_digests, digest]})
            repository.put("plan", plan.plan_id, plan)
            with pytest.raises(ConfigurationError, match="review"):
                await run_boundary_probe(repository, digest, worker_digest=worker, executor=CommandExecutor(), plan=plan)
            repository.review(digest)
            result = await run_boundary_probe(repository, digest, worker_digest=worker, executor=CommandExecutor(), plan=plan)
            probes.append(content_digest(result))
        # This fixture exercises record validation; it is NOT real isolation evidence.
        record = BoundaryConformance(conformance_id="fixture", source_digest="1" * 64,
            worker_digest=worker, image_digest="sha256:" + "2" * 64, binary_digest="3" * 64,
            adapter="controlled-fixture", adapter_version="1", effective_policy_digest=reviewed[2],
            reviewed_inventory_digest=reviewed[3], identity_digest="4" * 64,
            enforcement_definition_digest=reviewed[1], advertised_tools=["permitted", "catalog-only"],
            permitted_tools=["permitted"], used_tools=["permitted"], probe_digests=probes)
        digest = repository.put("boundary_conformance", "fixture", record)
        require_conformance(repository, digest, source_digest="1" * 64, worker_digest=worker, identity_digest="4" * 64)
        if typed_worker:
            repository.review(worker_document, revoke=True)
            with pytest.raises(ConfigurationError, match='enforcement review'):
                require_conformance(repository, digest, source_digest='1'*64, worker_digest=worker, identity_digest='4'*64)
            repository.review(worker_document)
        with pytest.raises(ConfigurationError, match="identity drift"):
            require_conformance(repository, digest, source_digest="0" * 64, worker_digest=worker, identity_digest="4" * 64)
        for name, changes, error in [
            ("missing", {"probe_digests": probes[:-1]}, "required probes"),
            ("duplicate", {"probe_digests": [*probes, probes[0]]}, "conflicting probes"),
            ("access", {"used_tools": ["unreviewed"]}, "unpermitted"),
        ]:
            changed = record.model_copy(update={"conformance_id": name, **changes})
            ref = repository.put("boundary_conformance", name, changed)
            with pytest.raises(ConfigurationError, match=error):
                require_conformance(repository, ref, source_digest="1" * 64, worker_digest=worker, identity_digest="4" * 64)
        bad_probe = BoundaryProbe.model_validate(repository.get("boundary_probe", probes[0]))
        bad_probe.probe_id = "false-observation"
        bad_probe.observed = {"allowed": False}
        bad_ref = repository.put("boundary_probe", bad_probe.probe_id, bad_probe)
        bad = record.model_copy(update={"probe_digests": [bad_ref, *probes[1:]]})
        bad_digest = repository.put("boundary_conformance", "bad-observation", bad)
        with pytest.raises(ConfigurationError, match="conflicting probes"):
            require_conformance(repository, bad_digest, source_digest="1" * 64, worker_digest=worker, identity_digest="4" * 64)
        # A different managed task configuration cannot borrow these local
        # observations merely by copying their worker digest.
        managed_probe = BoundaryProbe.model_validate(repository.get('boundary_probe', probes[0]))
        managed_definition = BoundaryProbeDefinition.model_validate(repository.get('boundary_probe_definition', managed_probe.implementation_digest))
        managed_definition.executor = ExecutorSpec(id='host-probe', capability='probe', kind='host_managed', resource_pool='fixture',
            description='Identity mismatch fixture', config={'adapter_id':'codex-app-server:task', 'argv':[sys.executable,'app-server'], 'instructions':'Controlled fixture'})
        managed_ref = repository.put('boundary_probe_definition', 'managed-definition', managed_definition)
        repository.review(managed_ref)
        managed_probe = managed_probe.model_copy(update={'probe_id':'managed-probe', 'implementation_digest':managed_ref})
        probe_ref = repository.put('boundary_probe', managed_probe.probe_id, managed_probe)
        changed = record.model_copy(update={'conformance_id':'managed-identity', 'probe_digests':[probe_ref,*probes[1:]]})
        ref = repository.put('boundary_conformance', changed.conformance_id, changed)
        with pytest.raises(ConfigurationError, match='probe execution evidence'):
            require_conformance(repository, ref, source_digest='1'*64, worker_digest=worker, identity_digest='4'*64)
        repository.review(reviewed[1], revoke=True)
        with pytest.raises(ConfigurationError, match="enforcement review"):
            require_conformance(repository, digest, source_digest="1" * 64, worker_digest=worker, identity_digest="4" * 64)
        if typed_worker:
            for changed, document_digest in ((binding().model_copy(update={'worker_id':'changed'}), worker_document),
                                              (binding(), '0'*64)):
                router.store._connection.execute("UPDATE assessment_records SET payload_json=?,digest=? WHERE kind='worker_binding' AND id=?",
                    (changed.model_dump_json(), document_digest, worker))
                with pytest.raises(ConfigurationError, match='worker binding differs'):
                    require_conformance(repository, digest, source_digest='1'*64, worker_digest=worker, identity_digest='4'*64)
    finally:
        await router.close()


@pytest.mark.parametrize('outcome', ['success', 'error', 'cancel'])
async def test_model_connectivity_bootstrap_is_reviewed_bounded_and_not_replayed(tmp_path, monkeypatch, outcome):
    import asyncio

    from test_v08_assessment import setup_assessment
    from test_v08_managed_workers import binding

    from aeep.assessment.boundary import prepare_model_probe
    from aeep.assessment.models import (
        AssessmentBudgetAmendment,
        AssessmentLimits,
        AssessmentScopeAmendment,
    )
    from aeep.executors.base import BaseExecutor
    from aeep.models import ExecutionStatus, ModelTokenUsage, RawExecution, ResourceAccounting

    router, service, plan, grant = setup_assessment(tmp_path)
    class Fixture(BaseExecutor):
        async def execute(self, context):
            assert context.invocation_check() == worker.digest()
            from aeep.execution import start_execution
            async def invoke(journal):
                usage = ResourceAccounting(model_usage=[ModelTokenUsage(provider='fixture', model='fixture', input_tokens=7)])
                for _ in range(2):
                    journal.append('usage.reported', 'partial', accounting=usage, accounting_mode='cumulative')
                saved = service.repository.get('execution_event', journal.journal_id + ':1')
                assert saved['accounting']['model_usage'][0]['input_tokens'] == 7
                assert saved['accounting_mode'] == 'cumulative'
                if outcome == 'error':
                    raise RuntimeError('interrupted fixture')
                if outcome == 'cancel':
                    raise asyncio.CancelledError
                return RawExecution(status=ExecutionStatus.SUCCESS,output={'connected':True})
            return await start_execution(context.attempt_id,'fixture',invoke).task
    worker = binding().model_copy(update={'credential_volume':'aeep-auth-fixture'})
    spec = ExecutorSpec(id='bootstrap',capability='aeep.conformance.connectivity@1',kind='host_managed',resource_pool='pool',description='Synthetic connectivity fixture',
        config={'adapter_id':'codex-app-server:fixture','argv':[worker.binary],'instructions':'Return connected true.',
                'invocation':{'mode':'turn'},'managed_worker':worker.model_dump(mode='json'),'timeout_seconds':2},estimate=router.registry.get('baseline').estimate)
    definition = BoundaryProbeDefinition(name='model_connectivity',executor=spec,expected={'connected':True})
    try:
        request = prepare_model_probe(service,source_plan_id=plan.plan_id,definition=definition)
        with pytest.raises(ConfigurationError,match='review'):
            await run_boundary_probe(service.repository,request.mapping_digest,worker_digest=worker.digest(),executor=Fixture(),plan=request)
        digests = {*request.definition_digests,request.subject_digest}
        definitions = {digest: json.loads(service.repository.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(digest,)).fetchone()[0]) for digest in digests}
        amendment = AssessmentScopeAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),
            subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=request.definition_digests)
        # Fixture-only budget expansion; the real release grant is never touched.
        budget = AssessmentBudgetAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),
            limits=AssessmentLimits(max_operations=grant.limits.max_operations,max_model_turns=1,max_elapsed_seconds=grant.limits.max_elapsed_seconds),expires_at=grant.expires_at)
        service.repository.approve_bundle(amendment,definitions,budget_amendment=budget)
        from aeep.hosts.codex_signin import signin_worker
        with pytest.raises(ConfigurationError,match='operator terminal'):
            await signin_worker(service, request.plan_id)
        class Process:
            returncode = 0
        async def launch(*argv, **kwargs):
            assert argv[-2:] == ('login', '--device-auth')
            assert kwargs == {'stdin':None,'stdout':None,'stderr':None}
            return Process()
        async def cleanup(_worker, operation):
            assert operation.startswith('signin:')
            return True
        with monkeypatch.context() as patch:
            patch.setattr(sys.stdin, 'isatty', lambda: True)
            patch.setattr(sys.stdout, 'isatty', lambda: True)
            patch.setattr('aeep.hosts.codex_signin.asyncio.create_subprocess_exec', launch)
            patch.setattr(type(worker), 'cleanup', cleanup)
            signed = await signin_worker(service, request.plan_id)
            assert signed.process_completed and signed.cleanup_confirmed and not signed.conformance_verified
            with pytest.raises(ConfigurationError,match='blind retry'):
                await signin_worker(service, request.plan_id)
            get = service.repository.get
            def wrong_worker(kind, identity):
                value = get(kind, identity)
                return {**value, 'worker_digest':'f'*64} if kind == 'conformance_request' else value
            with monkeypatch.context() as inner:
                inner.setattr(service.repository, 'get', wrong_worker)
                with pytest.raises(ConfigurationError,match='protected credential volume'):
                    await signin_worker(service, request.plan_id)
            failed_request = prepare_model_probe(service,source_plan_id=plan.plan_id,definition=definition)
            class FailedProcess:
                returncode = 1
            async def failed_launch(*argv, **kwargs):
                return FailedProcess()
            patch.setattr('aeep.hosts.codex_signin.asyncio.create_subprocess_exec', failed_launch)
            with pytest.raises(ConfigurationError,match='did not complete'):
                await signin_worker(service, failed_request.plan_id)
            assert service.repository.operation_ledger(failed_request.plan_id).operations[0].elapsed_seconds is not None
            unclean = prepare_model_probe(service,source_plan_id=plan.plan_id,definition=definition)
            async def cleanup_unknown(_worker, _operation):
                return False
            patch.setattr('aeep.hosts.codex_signin.asyncio.create_subprocess_exec', launch)
            patch.setattr(type(worker), 'cleanup', cleanup_unknown)
            with pytest.raises(ConfigurationError,match='cleanup is unconfirmed'):
                await signin_worker(service, unclean.plan_id)
            observation = service.repository.get('worker_signin','signin:'+unclean.plan_id)
            assert observation['process_completed'] and observation['cleanup_confirmed'] is False
        before = service.repository.operation_ledger(request.plan_id).operations
        for target, digest, implementation, message in (
            (request, worker.digest(), object(), 'controlled executor'),
            (plan, worker.digest(), Fixture(), 'separate reviewed'),
            (request, 'f'*64, Fixture(), 'dependencies differ'),
            (request.model_copy(update={'worker_digest':'f'*64}), 'f'*64, Fixture(), 'worker differs'),
            (request.model_copy(update={'definition_digests':request.definition_digests[1:]}), worker.digest(), Fixture(), 'frozen assessment'),
        ):
            with pytest.raises(ConfigurationError,match=message):
                await run_boundary_probe(service.repository, request.mapping_digest,
                    worker_digest=digest,executor=implementation,plan=target)
        for update, message in (({'config':{**spec.config, 'store_prompt':True}}, 'limited'),
                                ({'idempotent':False}, 'harmless')):
            unsafe = definition.model_copy(update={'executor':spec.model_copy(update=update)})
            proposed = prepare_model_probe(service,source_plan_id=plan.plan_id,definition=unsafe)
            service.repository.review(proposed.mapping_digest)
            with pytest.raises(ConfigurationError,match=message):
                await run_boundary_probe(service.repository,proposed.mapping_digest,
                    worker_digest=worker.digest(),executor=Fixture(),plan=proposed)
        assert service.repository.operation_ledger(request.plan_id).operations == before
        if outcome != 'success':
            with pytest.raises(RuntimeError if outcome == 'error' else asyncio.CancelledError):
                await run_boundary_probe(service.repository, request.mapping_digest,
                    worker_digest=worker.digest(), executor=Fixture(), plan=request)
            saved = [json.loads(row[0]) for row in router.store._connection.execute(
                "SELECT payload_json FROM assessment_records WHERE kind='execution_event'")]
            assert len(saved) == 5  # Two starts, one deduplicated usage, two failures.
            assert all(event['attempt_id'] == 'probe:' + request.plan_id for event in saved)
            assert sum(event['kind'] == 'usage.reported' for event in saved) == 1
            assert all(event['kind'] != 'execution.completed' for event in saved)
            operations = service.repository.operation_ledger(request.plan_id).operations
            assert all(item.elapsed_seconds is not None for item in operations)
            with pytest.raises(ConfigurationError, match='blind retry'):
                await run_boundary_probe(service.repository, request.mapping_digest,
                    worker_digest=worker.digest(), executor=Fixture(), plan=request)
            assert router.store._connection.execute('SELECT COUNT(*) FROM assessment_admissions').fetchone()[0] == 0
            return
        result = await run_boundary_probe(service.repository,request.mapping_digest,worker_digest=worker.digest(),executor=Fixture(),plan=request)
        assert result.name == 'model_connectivity'
        operations = service.repository.operation_ledger(request.plan_id).operations
        assert len(operations) == 2 and sum(item.reserved.max_model_turns for item in operations) == 1
        assert {item.stage for item in operations} == {'worker_signin','conformance_bootstrap'}
        with pytest.raises(ConfigurationError,match='blind retry'):
            await run_boundary_probe(service.repository,request.mapping_digest,worker_digest=worker.digest(),executor=Fixture(),plan=request)
        assert router.store._connection.execute('SELECT COUNT(*) FROM assessment_admissions').fetchone()[0] == 0
        # Cost attribution does not establish conformance. This deliberately
        # incomplete fixture only connects real unit-ledger operations.
        from aeep.assessment.models import AssessmentEnvironment
        cost_boundary = BoundaryConformance(conformance_id='cost-only',source_digest='a'*64,
            worker_digest=worker.digest(),image_digest=worker.image,binary_digest=worker.binary_sha256,
            adapter='fixture',adapter_version='1',effective_policy_digest='b'*64,
            reviewed_inventory_digest='c'*64,identity_digest='d'*64,enforcement_definition_digest='e'*64,
            advertised_tools=[],permitted_tools=[],used_tools=[],probe_digests=[content_digest(result)])
        boundary_digest = service.repository.put('boundary_conformance','cost-only',cost_boundary)
        with pytest.raises(ConfigurationError,match='review'):
            require_conformance(service.repository,boundary_digest,source_digest='a'*64,
                worker_digest=worker.digest(),identity_digest='d'*64)
        cost_environment = AssessmentEnvironment.model_validate(service.repository.get('environment',plan.environment_digest))
        cost_environment.conformance_digests = {'bootstrap':boundary_digest}
        environment_digest = service.repository.put('environment','cost-only',cost_environment)
        cost_plan = plan.model_copy(update={'environment_digest':environment_digest,'setup_cost_ids':[]})
        cost_ids, cost_plans = service._cost_sources(cost_plan)
        costs = service.repository.operation_ledger(plan.plan_id,cost_ids,cost_plans)
        assert {'signin:'+request.plan_id,'signin:'+failed_request.plan_id,'probe:'+request.plan_id} <= {item.operation_id for item in costs.operations}
        # Revoking the grant during login stops work and retains its setup charge.
        interrupted = prepare_model_probe(service,source_plan_id=plan.plan_id,definition=definition)
        class ActiveProcess:
            returncode = None
            def terminate(self):
                self.returncode = -15
            async def wait(self):
                return self.returncode
        active = ActiveProcess()
        async def active_launch(*_args, **_kwargs):
            return active
        async def revoke_on_wait(_seconds):
            service.repository.revoke(grant.authorization_id)
        with monkeypatch.context() as patch:
            patch.setattr(sys.stdin, 'isatty', lambda: True)
            patch.setattr(sys.stdout, 'isatty', lambda: True)
            patch.setattr('aeep.hosts.codex_signin.asyncio.create_subprocess_exec', active_launch)
            patch.setattr('aeep.hosts.codex_signin.asyncio.sleep', revoke_on_wait)
            patch.setattr(type(worker), 'cleanup', cleanup)
            with pytest.raises(ConfigurationError,match='revoked'):
                await signin_worker(service, interrupted.plan_id)
        assert active.returncode == -15
        assert service.repository.operation_ledger(interrupted.plan_id).operations[0].elapsed_seconds is not None
    finally:
        await router.close()


async def test_signin_client_cleanup_terminates_then_kills_without_capturing_output():
    from aeep.hosts.codex_signin import stop_process
    class HungProcess:
        returncode = None
        terminated = False
        killed = False
        def terminate(self):
            self.terminated = True
        def kill(self):
            self.killed = True
        async def wait(self):
            if not self.killed:
                raise TimeoutError
            self.returncode = -9
            return self.returncode
    process = HungProcess()
    await stop_process(process)
    assert process.terminated and process.killed
    await stop_process(None)


@pytest.mark.parametrize("dynamic,version,callback,accepted", [
    (True, "v3", "a" * 64, True),
    (True, "v3", "b" * 64, False),
    (True, "v2", None, False),
    (False, "v3", "a" * 64, False),
])
def test_composed_worker_binding_cannot_transfer_to_another_profile(
        monkeypatch, dynamic, version, callback, accepted):
    """Exercise production admission binding, independent of probe verification."""
    from test_v08_managed_workers import binding

    from aeep.assessment.boundary import require_managed_boundaries
    from aeep.assessment.models import AssessmentEnvironment
    worker = binding()
    config = {"adapter_id": "codex-app-server", "argv": [worker.binary, "app-server"],
        "instructions": "fixed fixture", "managed_worker": worker.model_dump(mode="json")}
    if dynamic:
        config["invocation"] = {"mode": "turn", "dynamic_tools_digest": "a" * 64}
    spec = ExecutorSpec(id="host", capability="fixture", kind="host_managed",
        resource_pool="fixture", description="fixture", config=config)
    values = dict(schema_version="assessment.boundary-conformance." + version,
        conformance_id="reviewed", source_digest="1"*64, worker_digest=worker.digest(),
        image_digest=worker.image, binary_digest=worker.binary_sha256,
        adapter="codex-app-server", adapter_version="1", effective_policy_digest="2"*64,
        reviewed_inventory_digest="3"*64, identity_digest="4"*64,
        enforcement_definition_digest="5"*64, advertised_tools=[], permitted_tools=[],
        used_tools=[], probe_digests=[], configuration_digest=worker.configuration_digest,
        effective_inventory={})
    if version == "v3":
        values.update(callback_binding_digest=callback, native_backend_digest="6"*64,
            composed_definition_digest="7"*64)
    record = BoundaryConformance.model_validate(values)
    calls = []
    def verified(repo, digest, **expected):
        calls.append((digest, expected))
        return record
    monkeypatch.setattr("aeep.assessment.boundary.require_conformance", verified)
    environment = AssessmentEnvironment(environment_id="fixture", kind="codex_sandbox",
        identity={}, conformance_digests={spec.id:"8"*64})
    if accepted:
        require_managed_boundaries(None, environment, [spec], {spec.id:"4"*64})
        assert calls[0][1]["worker_digest"] == worker.digest()
        assert calls[0][1]["identity_digest"] == "4"*64
    else:
        with pytest.raises(ConfigurationError, match=r"(composed boundary|composed boundary evidence)"):
            require_managed_boundaries(None, environment, [spec], {spec.id:"4"*64})
    assert len(calls) == 1


@pytest.mark.parametrize("invalid_callback", [False, True])
async def test_composed_conformance_rejects_legacy_only_or_unbacked_callback(tmp_path, invalid_callback):
    """Canonical fixture records never substitute for a native-issued callback."""
    from test_v08_assessment import setup_assessment
    from test_v08_pair_inspection import definition as paired_definition

    from aeep.assessment.boundary import COMPOSED_PROBES
    from aeep.execution import EventJournal
    from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
    from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
    from aeep.hosts.workers import binding_from_config
    from aeep.models import RawExecution
    router, service, _plan, _grant = setup_assessment(tmp_path)
    repo = service.repository
    try:
        pair = paired_definition(task_profile=True)
        specs = [pair.control.model_copy(deep=True), pair.treatment.model_copy(deep=True)]
        callbacks, backends = {}, {}
        class CallbackDefinition(StrictModel):
            identity: dict[str, str]
        for role, spec in zip(("control", "treatment"), specs, strict=True):
            worker = binding_from_config(spec.managed_host_config().managed_worker)
            backend = content_digest(ReviewedDefinition(purpose="synthetic native binding " + role))
            identity = {"worker_digest":worker.digest(), "native_backend_digest":backend,
                "implementation_digest":CodexDynamicTools.implementation_digest()}
            callback = repo.put("codex_dynamic_tools", role, CallbackDefinition(identity=identity))
            repo.review(callback)
            callbacks[worker.digest()] = callback
            backends[worker.digest()] = backend
            spec.config["invocation"] = {"mode":"turn" if role == "control" else "dynamic_tool",
                "local_profile":"capable_local", "dynamic_tools_digest":callback,
                **({"server":"fixture", "tool":"fixed", "tool_sha256":"a"*64} if role == "treatment" else {})}
        composite = ComposedPairDefinition(control=specs[0], treatment=specs[1],
            differential=pair.differential, shared_versions=pair.shared_versions,
            callback_bindings=callbacks, native_backends=backends)
        composite_ref = repo.put("composed_pair_definition", "fixture-composite", composite)
        repo.review(composite_ref)
        worker = binding_from_config(specs[0].managed_host_config().managed_worker)
        repo.review(repo.put("worker_binding", worker.digest(), worker))
        reviewed = []
        for name in ("enforcement", "effective-policy", "inventory"):
            ref = repo.put("definition", name, ReviewedDefinition(purpose=name))
            repo.review(ref)
            reviewed.append(ref)
        expected = {"synthetic":True}
        journal = EventJournal("synthetic-composed")
        journal.append("artifact.created", "fixed-synthetic", evidence_ref=content_digest(expected))
        journal.append("execution.completed", "fixed-terminal")
        evidence = journal.evidence("fixture", RawExecution(status="success",
            metadata={"boundary_digest":worker.digest()}))
        evidence_ref = repo.put("execution_evidence", content_digest(evidence), evidence)
        probes = []
        names = REQUIRED_PROBES | {"candidate_access"}
        if invalid_callback:
            names |= COMPOSED_PROBES
        for name in sorted(names):
            definition = BoundaryProbeDefinition(name=name, executor=ExecutorSpec(
                id="synthetic", capability="probe", kind="command", description="Never launched",
                config={"argv":[sys.executable,"-c","pass"]}), expected=expected)
            ref = repo.put("boundary_probe_definition", name, definition)
            repo.review(ref)
            probe = BoundaryProbe(probe_id=name, name=name, implementation_digest=ref,
                worker_digest=worker.digest(), execution_evidence_digest=evidence_ref, observed=expected)
            probes.append(repo.put("boundary_probe", name, probe))
        record = BoundaryConformance(schema_version="assessment.boundary-conformance.v3",
            conformance_id="synthetic", source_digest="1"*64, worker_digest=worker.digest(),
            image_digest=worker.image, binary_digest=worker.binary_sha256, adapter="codex-app-server:control",
            adapter_version="1", effective_policy_digest=reviewed[1], reviewed_inventory_digest=reviewed[2],
            identity_digest="2"*64, enforcement_definition_digest=reviewed[0], advertised_tools=[],
            permitted_tools=[], used_tools=[], probe_digests=probes, configuration_digest=worker.configuration_digest,
            effective_inventory={}, callback_binding_digest=callbacks[worker.digest()],
            native_backend_digest=backends[worker.digest()], composed_definition_digest=composite_ref)
        ref = repo.put("boundary_conformance", "fixture", record)
        error = "host receipt is missing" if invalid_callback else "required probes missing"
        with pytest.raises(ConfigurationError, match=error):
            require_conformance(repo, ref, source_digest="1"*64, worker_digest=worker.digest(), identity_digest="2"*64)
        # Matching reviewed strings cannot authorize a different native backend.
        wrong = record.model_copy(update={"conformance_id":"wrong-backend", "native_backend_digest":"0"*64})
        wrong_ref = repo.put("boundary_conformance", "wrong-backend", wrong)
        with pytest.raises(ConfigurationError, match="backend or worker binding differs"):
            require_conformance(repo, wrong_ref, source_digest="1"*64, worker_digest=worker.digest(), identity_digest="2"*64)
    finally:
        await router.close()
