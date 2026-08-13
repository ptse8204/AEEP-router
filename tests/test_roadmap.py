from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from aeep.cli import app
from aeep.economics import HMACSigner, QuoteService
from aeep.errors import ApprovalRequired, ConfigurationError
from aeep.models import (
    ActionRequest,
    AgentBudget,
    AuthorizationPolicy,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Locality,
    Manifest,
    QuotaSource,
    QuotaState,
    QuoteRequest,
    RegistryConfig,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    SubscriptionQuota,
    SubscriptionResource,
    ValidationKind,
    ValidationResult,
    ValidationSpec,
)
from aeep.payments import (
    EnterprisePaymentAdapter,
    FreePaymentAdapter,
    InvoicePaymentAdapter,
    MPPPaymentAdapter,
    PrepaidBalanceAdapter,
    X402PaymentAdapter,
)
from aeep.registry import Registry
from aeep.router import Router
from aeep.sdk import (
    capability,
    executor_from_callable,
    import_cli,
    import_mcp,
    import_openapi,
    provider_from_manifest,
)
from aeep.validators import (
    CallbackValidator,
    ExactMatchValidator,
    HumanValidator,
    LLMValidator,
    RangeValidator,
    SchemaValidator,
    StateTransitionValidator,
    ValidationContext,
    validator_from_spec,
)


def _spec(
    executor_id: str,
    *,
    kind: ExecutorKind = ExecutorKind.PYTHON,
    latency: float = 100,
    resource_pool: str | None = None,
    validators: list[ValidationSpec] | None = None,
) -> ExecutorSpec:
    config = (
        {"instructions": "Return text statistics for {input.text}."}
        if kind == ExecutorKind.HOST
        else {"callable": "aeep.examples.tools:text_stats"}
    )
    return ExecutorSpec(
        id=executor_id,
        capability="text.stats",
        kind=kind,
        description=executor_id,
        input_schema={
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "characters": {"type": "integer"},
                "words": {"type": "integer"},
                "lines": {"type": "integer"},
            },
            "required": ["characters", "words", "lines"],
            "additionalProperties": False,
        },
        estimate=RouteEstimate(
            resources=ResourceVector(latency_ms=latency),
            success_probability=0.99,
            quality_score=0.99,
            risk_score=0.01,
        ),
        side_effect=SideEffect.NONE,
        locality=Locality.LOCAL,
        resource_pool=resource_pool,
        validators=validators or [],
        config=config,
    )


def _subscription(state: QuotaState = QuotaState.ABUNDANT) -> SubscriptionResource:
    return SubscriptionResource(
        id="anthropic.claude",
        provider="anthropic",
        product="claude",
        quota=SubscriptionQuota(state=state, confidence=1, source=QuotaSource.USER),
    )


def test_subscription_pressure_changes_route_and_exhaustion_rejects():
    local = _spec("local", latency=1000)
    host = _spec(
        "host",
        kind=ExecutorKind.HOST,
        latency=100,
        resource_pool="anthropic.claude",
    )
    router = Router(
        Manifest(database=":memory:", resources=[_subscription()], executors=[local, host])
    )
    request = ActionRequest(capability="text.stats", input={"text": "abc"})
    assert router.route(request).selected_executor_id == "host"

    critical = request.model_copy(deep=True)
    critical.context.subscription_quotas["anthropic.claude"] = SubscriptionQuota(
        state=QuotaState.CRITICAL,
        confidence=1,
        source=QuotaSource.USER,
    )
    assert router.route(critical).selected_executor_id == "local"

    exhausted = request.model_copy(deep=True)
    exhausted.context.subscription_quotas["anthropic.claude"] = SubscriptionQuota(
        state=QuotaState.EXHAUSTED,
        confidence=1,
        source=QuotaSource.HOST,
    )
    decision = router.route(exhausted)
    rejected = next(item for item in decision.candidates if item.executor_id == "host")
    assert not rejected.feasible
    assert "exhausted" in rejected.rejection_reasons[0]


@pytest.mark.asyncio
async def test_host_selected_outcome_metrics_counterfactual_and_reputation():
    host = _spec(
        "host",
        kind=ExecutorKind.HOST,
        latency=10,
        resource_pool="anthropic.claude",
    )
    local = _spec("local", latency=1000)
    router = Router(
        Manifest(database=":memory:", resources=[_subscription()], executors=[host, local])
    )
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    assert outcome.status == ExecutionStatus.HOST_SELECTED
    assert outcome.output["status"] == "HOST_SELECTED"
    receipt = router.record_external_outcome(
        {
            "decision_id": outcome.decision.decision_id,
            "executor_id": "host",
            "status": "success",
            "actual_resources": {
                "latency_ms": 20,
                "context_tokens": 100,
                "subscription_units": 1,
            },
            "task_valid": True,
            "quality_score": 0.9,
        }
    )
    assert receipt.task_valid is True
    reputation = router.reputation("local", "text.stats")
    assert reputation.executions == 1
    report = router.counterfactual(receipt.receipt_id)
    assert report.best_alternative_executor_id == "local"
    assert report.avoidable_subscription_units == 1
    metrics = router.metrics()
    assert metrics.successful_actions == 1
    await router.close()


@pytest.mark.asyncio
async def test_task_validator_is_distinct_and_can_fail_execution():
    spec = _spec(
        "validated",
        validators=[
            ValidationSpec(
                kind=ValidationKind.RANGE,
                config={"path": "characters", "minimum": 99},
            )
        ],
    )
    router = Router(Manifest(database=":memory:", executors=[spec]))
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    assert not outcome.ok
    receipt = outcome.receipts[0]
    assert receipt.transport_success is True
    assert receipt.execution_success is True
    assert receipt.schema_valid is True
    assert receipt.task_valid is False
    assert receipt.validation_results[-1].kind == ValidationKind.RANGE
    await router.close()


def test_quotes_acceptance_and_signed_receipts_are_tamper_evident():
    signer = HMACSigner(b"x" * 32, key_id="provider-key")
    registry = Registry([_spec("local")])
    service = QuoteService(registry, signer=signer)
    request = QuoteRequest(
        action=ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    quote = service.quote(request)[0]
    assert quote.signature is not None
    acceptance = service.accept(quote, action_id=request.action.action_id)
    assert acceptance.signature is not None
    tampered = quote.model_copy(update={"monetary_usd": 1})
    with pytest.raises(Exception, match="signature"):
        service.accept(tampered, action_id=request.action.action_id)


@pytest.mark.asyncio
async def test_local_registry_discovers_only_requested_capability(tmp_path):
    descriptor = provider_from_manifest(
        Manifest(database=":memory:", executors=[_spec("remote.local")]),
        provider_id="provider-a",
        name="Provider A",
    )
    catalog = tmp_path / "provider.json"
    catalog.write_text(descriptor.model_dump_json(indent=2), encoding="utf-8")
    router = Router(
        Manifest(
            database=":memory:",
            registries=[RegistryConfig(id="local", kind="local", path=str(catalog))],
        )
    )
    decision = await router.route_with_discovery(
        ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    assert decision.selected_executor_id == "remote.local"
    assert list(router.providers) == ["provider-a"]
    await router.close()


@pytest.mark.asyncio
async def test_budget_reserve_capture_and_refund():
    spec = _spec("paid")
    spec.estimate.resources.monetary_usd = 0.25
    router = Router(
        Manifest(
            database=":memory:",
            budget=AgentBudget(
                daily_marketplace_limit_usd=2,
                max_per_action_usd=1,
                prepaid_balance_usd=2,
                authorization=AuthorizationPolicy(
                    auto_approve_under_usd=0.5,
                    financial_actions_require_human=False,
                ),
            ),
            executors=[spec],
        )
    )
    request = QuoteRequest(
        action=ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    quote = router.quotes(request)[0]
    reservation = await router.reserve_quote_payment(
        quote.quote_id,
        action_id=request.action.action_id,
        approved_side_effect=SideEffect.FINANCIAL,
    )
    capture = await router.capture_payment(reservation.reservation_id)
    refund = await router.refund_payment(capture.capture_id, 0.1)
    assert reservation.amount_usd == capture.amount_usd == 0.25
    assert refund.amount_usd == 0.1
    assert [event.event_type for event in router.store.list_ledger_events()] == [
        "refund",
        "capture",
        "reserve",
    ]
    await router.close()


def test_sdk_importers_generate_safe_provider_descriptors(tmp_path):
    cli = import_cli(
        provider_id="demo",
        capability_name="demo.echo@1",
        argv=["echo"],
    )
    assert cli.executors[0].config["stdin_json"] is True
    assert cli.executors[0].config["argv"] == ["echo"]

    mcp = import_mcp(
        provider_id="demo",
        capability_name="demo.echo@1",
        tool="echo",
        transport="stdio",
        endpoint="python",
    )
    assert mcp.executors[0].kind == ExecutorKind.MCP

    openapi_path = tmp_path / "openapi.yaml"
    openapi_path.write_text(
        """
openapi: 3.1.0
info: {title: Demo, version: '1'}
servers: [{url: https://example.com/api/}]
paths:
  /items/{id}:
    get:
      operationId: get_item
      responses:
        '200':
          description: ok
          content:
            application/json:
              schema: {type: object}
    post:
      operationId: update_item
      responses: {'200': {description: ok}}
""",
        encoding="utf-8",
    )
    imported = import_openapi(openapi_path, provider_id="demo")
    assert len(imported.executors) == 2
    assert imported.executors[0].config["url"].endswith("items/{input.id}")
    assert imported.executors[1].side_effect == SideEffect.WRITE
    assert imported.executors[1].safe_to_auto_execute is False


@pytest.mark.asyncio
async def test_all_validator_modes_and_callback_trust():
    context = ValidationContext(
        input={"state": "new"},
        output={"value": 5, "state": "done"},
    )
    assert (await SchemaValidator({"type": "object"}).validate(context)).valid is True
    assert (await SchemaValidator({"type": "array"}).validate(context)).valid is False
    assert (await ExactMatchValidator(5, path="value").validate(context)).valid is True
    assert (await ExactMatchValidator(6, path="value").validate(context)).valid is False
    assert (
        await RangeValidator(path="value", minimum=1, maximum=10).validate(context)
    ).valid is True
    assert (await RangeValidator(path="value", minimum=10).validate(context)).valid is False
    transition = StateTransitionValidator(
        {"new": ["done"]}, before_path="state", after_path="state"
    )
    assert (await transition.validate(context)).valid is True

    async def async_callback(_context):
        return ValidationResult(kind=ValidationKind.CALLBACK, valid=True)

    assert (await CallbackValidator(async_callback).validate(context)).valid is True
    assert (await CallbackValidator(lambda _: False).validate(context)).valid is False
    assert (await CallbackValidator(lambda _: None).validate(context)).valid is None
    assert (await LLMValidator(lambda _: True).validate(context)).trust.value == "self_asserted"
    assert (await HumanValidator(lambda _: True).validate(context)).trust.value == "attested"
    with pytest.raises(ConfigurationError, match=r"config\.schema"):
        validator_from_spec(ValidationSpec(kind=ValidationKind.SCHEMA), {})
    with pytest.raises(ConfigurationError, match="registered callback"):
        validator_from_spec(ValidationSpec(kind=ValidationKind.DOWNSTREAM), {})


@pytest.mark.asyncio
async def test_payment_adapters_cover_free_prepaid_invoice_and_callback_rails():
    registry = Registry([_spec("paid")])
    request = QuoteRequest(
        action=ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    paid_quote = QuoteService(registry).quote(request)[0]
    paid_quote.monetary_usd = 0.25

    free_quote = paid_quote.model_copy(update={"monetary_usd": 0.0})
    free = FreePaymentAdapter()
    reservation = await free.reserve(free_quote, request.action.action_id)
    capture = await free.capture(reservation)
    assert (await free.refund(capture, 0)).amount_usd == 0
    with pytest.raises(ConfigurationError, match="paid quote"):
        await free.reserve(paid_quote, request.action.action_id)
    with pytest.raises(ConfigurationError, match="positive amount"):
        await free.refund(capture, 1)

    prepaid = PrepaidBalanceAdapter(0.3)
    reservation = await prepaid.reserve(paid_quote, request.action.action_id)
    capture = await prepaid.capture(reservation)
    assert (await prepaid.refund(capture, 0.1)).amount_usd == 0.1
    with pytest.raises(ConfigurationError, match="insufficient"):
        await PrepaidBalanceAdapter(0.1).reserve(paid_quote, request.action.action_id)
    with pytest.raises(ConfigurationError, match="exceeds"):
        await prepaid.refund(capture, 1)
    assert (await InvoicePaymentAdapter().reserve(paid_quote, "act")).adapter == "invoice"

    async def metadata(*_args):
        return {"rail": "ok"}

    for adapter_type in (X402PaymentAdapter, MPPPaymentAdapter, EnterprisePaymentAdapter):
        adapter = adapter_type(reserve=metadata, capture=metadata, refund=metadata)
        held = await adapter.reserve(paid_quote, "act")
        captured = await adapter.capture(held)
        refunded = await adapter.refund(captured, 0.1)
        assert refunded.metadata == {"rail": "ok"}


@pytest.mark.asyncio
async def test_budget_rejects_missing_financial_and_human_approval():
    spec = _spec("paid")
    spec.estimate.resources.monetary_usd = 0.25
    router = Router(
        Manifest(
            database=":memory:",
            budget=AgentBudget(
                daily_marketplace_limit_usd=1,
                max_per_action_usd=0.5,
                prepaid_balance_usd=1,
                authorization=AuthorizationPolicy(financial_actions_require_human=True),
            ),
            executors=[spec],
        )
    )
    request = QuoteRequest(
        action=ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    quote = router.quotes(request)[0]
    with pytest.raises(ApprovalRequired, match="financial approval"):
        await router.reserve_quote_payment(quote.quote_id, action_id="act")
    with pytest.raises(ApprovalRequired, match="human approval"):
        await router.reserve_quote_payment(
            quote.quote_id,
            action_id="act",
            approved_side_effect=SideEffect.FINANCIAL,
        )
    await router.close()


@pytest.mark.asyncio
async def test_router_signs_receipt_and_rejects_bad_attestation():
    signer = HMACSigner(b"s" * 32, key_id="local")
    router = Router(
        Manifest(database=":memory:", executors=[_spec("local")]), signer=signer
    )
    outcome = await router.execute(
        ActionRequest(capability="text.stats", input={"text": "abc"})
    )
    signed = router.signed_receipt(outcome.receipts[0].receipt_id)
    assert signer.verify_receipt(signed)
    signed.receipt.actual_resources.latency_ms += 1
    assert not signer.verify_receipt(signed)
    with pytest.raises(ConfigurationError, match="attested"):
        router.record_observation(
            {
                "executor_id": "local",
                "capability": "text.stats",
                "trust": "attested",
            }
        )
    await router.close()


def test_sdk_decorator_and_import_errors(tmp_path):
    @capability("demo.echo@1", description="Echo")
    def echo(value):
        return value

    executor = executor_from_callable(echo)
    assert executor.config["callable"].endswith(":echo")
    with pytest.raises(ConfigurationError, match="not decorated"):
        executor_from_callable(lambda: None)
    with pytest.raises(ConfigurationError, match="non-empty argv"):
        import_cli(provider_id="demo", capability_name="demo.x@1", argv=[])
    assert import_mcp(
        provider_id="demo",
        capability_name="demo.x@1",
        tool="x",
        transport="http",
        endpoint="https://example.com/mcp",
    ).executors[0].requires_network
    invalid = tmp_path / "invalid.yaml"
    invalid.write_text("openapi: 3.1.0\n", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="paths"):
        import_openapi(invalid, provider_id="demo", base_url="https://example.com")


def test_roadmap_cli_surfaces(tmp_path):
    runner = CliRunner()
    manifest = tmp_path / "aeep.yaml"
    assert runner.invoke(app, ["init", str(manifest)]).exit_code == 0
    common = ["--manifest", str(manifest), "--compact"]

    metrics = runner.invoke(app, ["metrics", *common])
    assert metrics.exit_code == 0
    assert json.loads(metrics.stdout)["decisions"] == 0

    quoted = runner.invoke(
        app,
        ["quote", "text.stats", "-i", '{"text":"abc"}', *common],
    )
    assert quoted.exit_code == 0, quoted.output
    quote_payload = json.loads(quoted.stdout)["quotes"][0]
    accepted = runner.invoke(
        app,
        [
            "accept-quote",
            quote_payload["quote_id"],
            quote_payload["quote_request_id"],
            *common,
        ],
    )
    assert accepted.exit_code == 0, accepted.output

    executed = runner.invoke(
        app,
        ["run", "text.stats", "-i", '{"text":"abc"}', *common],
    )
    assert executed.exit_code == 0, executed.output
    receipt_id = json.loads(executed.stdout)["receipts"][0]["receipt_id"]
    assert runner.invoke(app, ["counterfactual", receipt_id, *common]).exit_code == 0
    assert runner.invoke(app, ["reputation", "local", "text.stats", *common]).exit_code == 0

    published = runner.invoke(
        app,
        [
            "publish",
            "--provider-id",
            "demo",
            "--name",
            "Demo",
            *common,
        ],
    )
    assert published.exit_code == 0, published.output
    imported_cli = runner.invoke(
        app,
        [
            "import",
            "cli",
            "--provider-id",
            "demo",
            "--capability",
            "demo.echo@1",
            "--argv",
            '["echo"]',
            "--compact",
        ],
    )
    assert imported_cli.exit_code == 0, imported_cli.output
    imported_mcp = runner.invoke(
        app,
        [
            "import",
            "mcp",
            "--provider-id",
            "demo",
            "--capability",
            "demo.echo@1",
            "--tool",
            "echo",
            "--endpoint",
            "python",
            "--compact",
        ],
    )
    assert imported_mcp.exit_code == 0, imported_mcp.output

    openapi = tmp_path / "openapi.yaml"
    openapi.write_text(
        """
openapi: 3.1.0
info: {title: Demo, version: '1'}
servers: [{url: https://example.com}]
paths: {}
""",
        encoding="utf-8",
    )
    imported_openapi = runner.invoke(
        app,
        [
            "import",
            "openapi",
            str(openapi),
            "--provider-id",
            "demo",
            "--compact",
        ],
    )
    assert imported_openapi.exit_code == 0, imported_openapi.output
