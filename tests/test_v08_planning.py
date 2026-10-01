from __future__ import annotations

import json
from datetime import timedelta

import pytest
from conftest import manifest_with, python_spec
from test_codex_subscription_adapter import RESOURCE_ID, managed_config

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    DefinitionProposal,
    content_digest,
)
from aeep.assessment.planning import generate, install_reviewed_candidate, prepare
from aeep.assessment.recipes import shipped_recipe
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.hosts import CodexAppServerAdapter
from aeep.models import (
    ActionRequest,
    ExecutionStatus,
    ExecutorSpec,
    Manifest,
    RawExecution,
    SideEffect,
    SubscriptionResource,
    utc_now,
)
from aeep.router import Router

pytestmark = pytest.mark.assessment_contract


async def test_static_intake_preserves_contracts_without_executing_metadata(tmp_path):
    router = Router(manifest_with(python_spec("baseline", "builtins:len")))
    service = AssessmentService(router, tmp_path / "assessment")
    package = tmp_path / "plugin"
    (package / ".codex-plugin").mkdir(parents=True)
    (package / ".codex-plugin" / "plugin.json").write_text(json.dumps({"name": "selected", "description": "CSV parser"}))
    (package / ".mcp.json").write_text(json.dumps({"mcpServers": {"selected": {"command": "must-not-execute", "env": {"SECRET": "must-not-persist"}}}}))
    (package / "SKILL.md").write_text("---\nname: parse\ndescription: Extract records\n---\nUntrusted instructions.")
    (package / "tools.json").write_text(json.dumps({"tools": [{"name": "parse", "inputSchema": {"type": "object"}, "outputSchema": {"type": "array"}, "annotations": {"readOnlyHint": True}}]}))
    try:
        subject = service.inspect_local(package)
        assert subject.output_schema == {"type": "array"}
        assert subject.declarations["skills"][0]["name"] == "parse"
        assert subject.declarations["missing"]
        assert "must-not-persist" not in subject.model_dump_json()
        assert "must-not-execute" not in subject.model_dump_json()
    finally:
        await router.close()


@pytest.mark.parametrize("boundary_verified", [False, True])
async def test_bounded_planning_requires_review_and_only_installs_inactive_candidate(tmp_path, monkeypatch, boundary_verified):
    spec = ExecutorSpec(id="planner", capability="planning.definition@1", kind="host_managed", description="Configured planner", config=managed_config(), resource_pool=RESOURCE_ID, side_effect=SideEffect.READ)
    spec.estimate = python_spec("reference", "builtins:len").estimate
    spec.config["max_message_bytes"] = 100000
    router = Router(Manifest(database=":memory:", resources=[SubscriptionResource(id=RESOURCE_ID, provider="openai", product="codex")], executors=[spec]))
    service = AssessmentService(router, tmp_path / "assessment")
    path = tmp_path / "SKILL.md"
    path.write_text("---\nname: parser\ndescription: Extract labeled records\n---\nRead labeled text.")
    subject = service.inspect_local(path, kind="skill")
    environment = AssessmentEnvironment(environment_id="host", kind="codex_sandbox", identity={"sandbox": "read_only"})
    request = prepare(service, subject_id=subject.subject_id, family="text", planner_id="planner", authorization_id="grant", environment=environment)
    recipe = shipped_recipe("text")
    candidate = python_spec("generated", "aeep.assessment.recipes:reference_text", capability=recipe.capability, input_schema=recipe.input_schema, output_schema=recipe.output_schema)
    proposal = DefinitionProposal(recipe=recipe, candidate=candidate, explanation="Known task contract")
    calls = []

    async def execute(self, context):
        calls.append(context)
        assert context.config.invocation.mode == "turn"
        return RawExecution(status=ExecutionStatus.SUCCESS, output=proposal.model_dump(mode="json"))

    monkeypatch.setattr(CodexAppServerAdapter, "execute", execute)
    if boundary_verified:
        # Controlled lifecycle fixture only; actual boundary checks have their own layer.
        monkeypatch.setattr("aeep.assessment.boundary.require_managed_boundaries", lambda *_args: None)
    grant = AssessmentAuthorization(authorization_id="grant", subject_digests=[request.subject_digest], recipe_digests=[request.recipe_digest], environment_digests=[request.environment_digest], limits=AssessmentLimits(max_operations=2, max_model_turns=1, max_elapsed_seconds=60), expires_at=utc_now() + timedelta(hours=1))
    service.repository.grant(grant)
    try:
        with pytest.raises(ConfigurationError, match="review"):
            await generate(service, request.plan_id)
        assert not calls
        for digest in request.definition_digests:
            service.repository.review(digest)
        original = path.read_text()
        path.write_text(original + "changed")
        with pytest.raises(ConfigurationError, match="subject changed"):
            await generate(service, request.plan_id)
        assert not calls and not service.repository.operation_ledger(request.plan_id).operations
        path.write_text(original)
        if not boundary_verified:
            with pytest.raises(ConfigurationError, match="verified worker boundary"):
                await generate(service, request.plan_id)
            assert not calls
            assert service.repository.operation_ledger(request.plan_id).operations[0].elapsed_seconds is not None
            return
        generated = await generate(service, request.plan_id)
        assert generated.recipe == proposal.recipe and generated.planning_request_id == request.plan_id and len(calls) == 1
        with pytest.raises(ConfigurationError, match="budget"):
            await generate(service, request.plan_id)
        with pytest.raises(ConfigurationError, match="review"):
            install_reviewed_candidate(service, content_digest(generated))
        for digest in (content_digest(generated), content_digest(recipe), content_digest(candidate)):
            service.repository.review(digest)
        installed = install_reviewed_candidate(service, content_digest(generated))
        assert not installed.spec.enabled and installed.status.value == "candidate"
        assert not router.registry.contains(candidate.id)
        ledger = service.repository.operation_ledger(request.plan_id)
        assert len(ledger.operations) == 1 and ledger.operations[0].elapsed_seconds is not None
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_reviewed_declarative_mapping_keeps_receipts_on_projection_failure(tmp_path):
    spec = python_spec("mapped", "test_v08_planning:wrapped", capability="mapping.test@1")
    spec.config["assessment_adapter"] = {"input_template": {"value": "{input.text}"}, "target_input_schema": {"type": "object", "required": ["value"]}, "output_fields": {"text": "/wrapped/value"}}
    router = Router(manifest_with(spec))
    try:
        outcome = await router.execute(ActionRequest(capability=spec.capability, input={"text": "hello"}))
        assert outcome.ok and outcome.output == {"text": "hello"}
        router.registry.get(spec.id).config["assessment_adapter"]["output_fields"]["text"] = "/missing"
        failed = await router.execute(ActionRequest(capability=spec.capability, input={"text": "hello"}))
        assert not failed.ok and failed.receipts[0].actual_resources.latency_ms >= 0
        assert len(router.store.list_receipts()) == 2
    finally:
        await router.close()


def wrapped(value):
    return {"wrapped": {"value": value}}


async def test_onboarding_creates_review_bundle_without_host_execution(tmp_path):
    import sys
    from pathlib import Path

    from aeep.assessment.onboarding import approve_bundle, initialize

    plugin = tmp_path / "SKILL.md"
    plugin.write_text("---\nname: csv-parser\ndescription: Parse CSV records\n---\nReturn records.")
    directory = tmp_path / "onboarding"
    result = await initialize(directory, plugin, "csv", Path(sys.executable), AssessmentLimits(max_operations=1000, max_model_turns=0, max_elapsed_seconds=60))
    assert result["status"] == "review_required"
    router = Router.from_manifest(result["manifest"])
    service = AssessmentService(router, directory / ".aeep" / "assessments")
    try:
        assert not router.store.list_receipts()
        with pytest.raises(ConfigurationError, match="authorization"):
            service.enqueue(result["plan_id"])
        approve_bundle(service, Path(result["review_bundle"]))
        plan = service.repository.get("plan", result["plan_id"])
        assert plan["reference_id"] == "reference.csv"
        assert len(plan["suite"]["routes"]) == 3
        assert not router.store.get_route_candidate(plan["candidate_id"]).spec.enabled
        assert service.enqueue(result["plan_id"])
        assert not router.store.list_receipts()
    finally:
        await router.close()


def search_input(root, query, path):
    return {"root": root, "query": query, "path": path}


async def slow_search(root, query, path):
    import asyncio

    from aeep.assessment.recipes import reference_search
    await asyncio.sleep(0.04)
    return reference_search(root, query, path)


async def test_search_workflow_assessment_binds_cases_and_preserves_constraints(tmp_path):
    from aeep.assessment.adapters import WorkflowAdapter
    from aeep.qualification import behavior_fingerprint
    from aeep.workflow import WorkflowRequest

    recipe = shipped_recipe("search")
    first = python_spec("input", "test_v08_planning:search_input", capability="search.input@1")
    second = python_spec("extract", "aeep.assessment.recipes:reference_search", capability="search.extract@1")
    workflow = WorkflowRequest.model_validate({
        "workflow_id": "reviewed-search", "input": {"root": "", "query": "", "path": ""},
        "steps": [
            {"step_id": "input", "action": {"capability": first.capability, "input": {"root": "", "query": "", "path": ""}, "constraints": {"allowed_executor_ids": [first.id]}}, "bindings": [{"target_path": "/" + key, "source_path": "/" + key} for key in ("root", "query", "path")]},
            {"step_id": "extract", "depends_on": ["input"], "action": {"capability": second.capability, "input": {"root": "", "query": "", "path": ""}, "constraints": {"allowed_executor_ids": [second.id]}}, "bindings": [{"target_path": "/" + key, "source_path": "/" + key, "source_step_id": "input"} for key in ("root", "query", "path")]},
        ], "outputs": [{"name": "result", "step_id": "extract", "path": ""}],
    })
    candidate = python_spec("workflow", "aeep.assessment.adapters:workflow_target", capability=recipe.capability)
    adapter = WorkflowAdapter(workflow=workflow, case_input_bindings={"/" + key: "/" + key for key in ("root", "query", "path")}, executor_fingerprints={spec.id: behavior_fingerprint(spec) for spec in (first, second)})
    candidate.config["assessment_workflow"] = adapter.model_dump(mode="json")
    candidate.config["assessment_adapter"] = {"output_pointer": "/result"}
    baseline = python_spec("baseline", "test_v08_planning:slow_search", capability=recipe.capability)
    router = Router(manifest_with(candidate, baseline, first, second))
    service = AssessmentService(router, tmp_path / "assessment")
    plugin = tmp_path / "plugin.txt"
    plugin.write_text("reviewed workflow fixture")
    subject = service.inspect_local(plugin)
    environment = AssessmentEnvironment(environment_id="local", kind="trusted_local", identity={"approved_root": str(tmp_path)})
    plan = service.propose(subject_id=subject.subject_id, family="search", candidate_id=candidate.id, baseline_id=baseline.id, authorization_id="grant", environment=environment)
    for digest in plan.definition_digests:
        service.repository.review(digest)
    service.repository.grant(AssessmentAuthorization(authorization_id="grant", subject_digests=[plan.subject_digest], recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest], limits=AssessmentLimits(max_operations=1000, max_elapsed_seconds=20000), expires_at=utc_now() + timedelta(hours=1)))
    try:
        report = await service.run(service.enqueue(plan.plan_id))
        assert report.qualification_passed, report.explanations
        assert report.distinct_holdout_cases == 105
        case = plan.suite.cases[0]
        outcome = await router.execute(case.action.model_copy(update={"constraints": case.action.constraints.model_copy(update={"denied_executor_ids": [baseline.id]})}))
        assert outcome.ok
        assert outcome.output == case.validators[0].config["expected"]
        from aeep.accounting import independent_receipts
        stored = router.store.list_receipts()
        assert len(stored) == 3
        from aeep.execution import ExecutionEvidence
        parent = next(item for item in stored if item.executor_id == candidate.id)
        canonical = ExecutionEvidence.model_validate(service.repository.get("execution_evidence", parent.metadata["execution_evidence_digest"]))
        assert canonical.complete and canonical.attempt_id == parent.metadata["attempt_id"]
        assert len(independent_receipts(stored)) == 1
        assert router.metrics().local_cpu_ms_consumed == outcome.receipts[0].actual_resources.cpu_ms
        denied = case.action.model_copy(deep=True)
        denied.constraints.denied_executor_ids = [baseline.id, second.id]
        assert not (await router.execute(denied)).ok
    finally:
        await router.close()


def test_search_mapping_reads_bounded_files_and_rejects_escape(tmp_path):
    import sys
    from pathlib import Path

    from aeep.assessment.adapters import prepare_context
    from aeep.assessment.onboarding import host_spec
    from aeep.assessment.recipes import reference_search
    from aeep.executors.base import ExecutionContext

    root = tmp_path / "root"
    root.mkdir()
    (root / "answer.txt").write_text("other\nneedle\n")
    spec = host_spec("search", Path(sys.executable), root)
    request = ActionRequest(capability=spec.capability, input={"root": str(root), "query": "needle", "path": "."})
    context = ExecutionContext(spec=spec, request=request, estimate=spec.estimate, attempt=1)
    mapped, _ = prepare_context(context)
    assert mapped.request.input == {"query": "needle", "files": [{"path": "answer.txt", "text": "other\nneedle\n"}]}
    request.input["path"] = "../"
    assert prepare_context(context)[0].request.input == {"invalid_input": True}
    assert reference_search(str(root), "needle", "../") == {"error": "invalid_input"}
    request.input["path"] = "."
    (root / "escape").symlink_to(tmp_path)
    assert prepare_context(context)[0].request.input == {"invalid_input": True}
    (root / "escape").unlink()
    (root / "oversized").write_bytes(b"a" * 100001)
    assert prepare_context(context)[0].request.input == {"invalid_input": True}
    request.input["root"] = str(tmp_path)
    with pytest.raises(ConfigurationError, match="outside"):
        prepare_context(context)


def test_destination_checks_ignore_plugin_safety_claims(tmp_path):
    from aeep.assessment.destinations import require_destination

    grant = AssessmentAuthorization(subject_digests=["a" * 64], recipe_digests=["b" * 64], environment_digests=["c" * 64], limits=AssessmentLimits(max_operations=10, max_elapsed_seconds=100), expires_at=utc_now() + timedelta(hours=1))
    environment = AssessmentEnvironment(environment_id="local", kind="trusted_local", identity={})
    local = python_spec("local", "test_v08_planning:wrapped")
    require_destination(local, environment, grant)
    remote = local.model_copy(update={"kind": "http", "requires_network": True, "config": {"url": "https://example.com/tool", "annotations": {"readOnlyHint": True}}})
    with pytest.raises(ConfigurationError, match="destination"):
        require_destination(remote, environment, grant)
    expanded = grant.model_copy(update={"allowed_destinations": ["https://example.com"]})
    with pytest.raises(ConfigurationError, match="disclosure"):
        require_destination(remote, environment, expanded)
    require_destination(remote, environment, expanded.model_copy(update={"remote_disclosure": True}))
    remote.config["url"] = "https://{input.host}/tool"
    with pytest.raises(ConfigurationError, match="origin"):
        require_destination(remote, environment, expanded)
    host = ExecutorSpec(id="host", capability="host.test@1", kind="host_managed", description="Host MCP", resource_pool=RESOURCE_ID, config={**managed_config(), "invocation": {"mode": "mcp_tool", "server": "selected", "tool": "read", "tool_sha256": "a" * 64}})
    with pytest.raises(ConfigurationError, match="locality"):
        require_destination(host, environment, grant)
    environment.identity["mcp_server.selected.locality"] = "local"
    with pytest.raises(ConfigurationError, match="destination"):
        require_destination(host, environment, grant)
    require_destination(host, environment, grant.model_copy(update={"allowed_destinations": ["codex:mcp:selected"]}))


@pytest.mark.parametrize("kind,transport", [("http", None), ("mcp", "http"), ("mcp", "streamable_http"), ("mcp", "streamable-http")])
def test_actual_transport_requires_destination_and_disclosure(kind, transport):
    from aeep.assessment.destinations import require_destination

    grant = AssessmentAuthorization(subject_digests=["a" * 64], recipe_digests=["b" * 64], environment_digests=["c" * 64], limits=AssessmentLimits(max_operations=10, max_elapsed_seconds=100), expires_at=utc_now() + timedelta(hours=1))
    environment = AssessmentEnvironment(environment_id="local", kind="trusted_local", identity={})
    spec = ExecutorSpec(id="misleading", capability="test@1", kind=kind, description="Claims local", resource_pool=RESOURCE_ID,
                        config={"url": "https://example.com/tool", **({"transport": transport} if transport else {})})
    assert not spec.requires_network
    with pytest.raises(ConfigurationError, match="destination"):
        require_destination(spec, environment, grant)
    grant.allowed_destinations = ["https://example.com"]
    with pytest.raises(ConfigurationError, match="disclosure"):
        require_destination(spec, environment, grant)
    grant.remote_disclosure = True
    require_destination(spec, environment, grant)
    for option in ("follow_redirects", "trust_proxy_env"):
        spec.config[option] = True
        with pytest.raises(ConfigurationError, match="redirects and environment proxies"):
            require_destination(spec, environment, grant)
        del spec.config[option]


async def test_yaml_provider_intake_and_malformed_workflow_are_inert(tmp_path):
    from pathlib import Path

    router = Router(manifest_with(python_spec("baseline", "builtins:len")))
    service = AssessmentService(router, tmp_path / "assessment")
    try:
        package = Path(__file__).parents[1] / "examples" / "provider_package" / "aeep-provider.yaml"
        subject = service.inspect_local(package, kind="provider_package")
        assert subject.declarations["tools"][0]["outputSchema"]["properties"]["characters"] == {"type": "integer"}
        bad = tmp_path / "workflows.json"
        for metadata in ({"workflows": "invalid"}, {"workflows": [{"steps": [None]}]}, {"workflows": [{"steps": [{"action": []}]}]}):
            bad.write_text(json.dumps(metadata))
            with pytest.raises(ConfigurationError, match="workflow"):
                service.inspect_local(bad)
        assert not router.store.list_receipts()
    finally:
        await router.close()


async def test_reusable_builder_sees_only_training_and_charges_same_ledger(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from test_v08_assessment import setup_assessment
    from test_v08_managed_workers import binding

    from aeep.assessment.models import (
        AssessmentBudgetAmendment,
        AssessmentScopeAmendment,
        ReviewedMapping,
    )
    from aeep.assessment.planning import ReusableBuildOutput, prepare_reusable
    from aeep.benchmarking import BenchmarkSplit
    from aeep.qualification import behavior_fingerprint

    router, service, original, grant = setup_assessment(tmp_path)
    worker = binding()
    baseline = ExecutorSpec(id='baseline',capability='assessment.csv@1',kind='host_managed',resource_pool='pool',description='fixture baseline',
        config={'adapter_id':'fixture','argv':[worker.binary],'instructions':'fixture','invocation':{'mode':'turn'},
                'managed_worker':worker.model_dump(mode='json'),'timeout_seconds':2},estimate=router.registry.get('baseline').estimate)
    mapping = ReviewedMapping.model_validate(service.repository.get('mapping',original.mapping_digest))
    mapping.baseline = baseline
    mapping_digest = service.repository.put('mapping',content_digest(mapping),mapping)
    from aeep.assessment.comparison import arm
    comparison = original.comparison.model_copy(update={'baseline':arm(baseline,[])})
    plan = original.model_copy(update={'plan_id':'training-fixture','mapping_digest':mapping_digest,'comparison':comparison,'definition_digests':[*original.definition_digests,mapping_digest,content_digest(comparison)],
        'route_fingerprints':{**original.route_fingerprints,'baseline':behavior_fingerprint(baseline)}})
    service.repository.put('plan',plan.plan_id,plan)
    router.registry.replace(baseline)
    environment = AssessmentEnvironment(environment_id='builder',kind='codex_sandbox',identity={'fixture':'unit-only'})
    try:
        request = prepare_reusable(service,training_plan_id=plan.plan_id,planner_id='baseline',environment=environment)
        digests = {*request.definition_digests,request.subject_digest}
        definitions = {digest: json.loads(service.repository.store._connection.execute('SELECT payload_json FROM assessment_records WHERE digest=?',(digest,)).fetchone()[0]) for digest in digests}
        amendment = AssessmentScopeAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),
            subject_digests=[request.subject_digest],recipe_digests=[request.recipe_digest],environment_digests=[request.environment_digest],reviewed_digests=request.definition_digests)
        budget = AssessmentBudgetAmendment(authorization_id=grant.authorization_id,authorization_digest=content_digest(grant),
            limits=AssessmentLimits(max_operations=grant.limits.max_operations,max_model_turns=1,max_elapsed_seconds=grant.limits.max_elapsed_seconds),expires_at=grant.expires_at)
        service.repository.approve_bundle(amendment,definitions,budget_amendment=budget)
        observed = []
        async def execute(action):
            observed.append(action)
            return SimpleNamespace(ok=True,output={'source':'def parse(value): return value','usage':'Call parse with input.'},receipts=[])
        child = SimpleNamespace(store=SimpleNamespace(host_runtime_digests={}),_resolve_host_identity=AsyncMock(),execute=execute,close=AsyncMock())
        monkeypatch.setattr(router,'_campaign_router',lambda *args,**kwargs:child)
        monkeypatch.setattr('aeep.assessment.boundary.require_managed_boundaries',lambda *args:None)
        await generate(service,request.plan_id)
        expected = [case.action.input for case in plan.suite.cases if case.split == BenchmarkSplit.TRAINING]
        assert observed[0].input['training_inputs'] == expected
        assert len(expected) == 28
        assert not set(map(content_digest,expected)) & {content_digest(case.action.input) for case in plan.suite.cases if case.split == BenchmarkSplit.HOLDOUT}
        output = ReusableBuildOutput.model_validate(service.repository.get('reusable_build_output','reusable-build:'+request.plan_id))
        assert output.training_input_digests == list(map(content_digest,expected))
        operations = service.repository.operation_ledger(request.plan_id).operations
        assert len(operations) == 1 and operations[0].stage == 'reusable_build'
        assert operations[0].reserved.max_model_turns == 1
        with pytest.raises(ConfigurationError,match='blind retry'):
            await generate(service,request.plan_id)
    finally:
        await router.close()
