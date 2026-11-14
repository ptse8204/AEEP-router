"""First-party transport substitutes; no Langfuse service, model or network runs."""

import hashlib
import json
import sqlite3

import pytest
from test_toolkit_workflow_accounting import accounting
from test_toolkit_workflow_v2 import definition

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.executors.base import BaseExecutor
from aeep.models import ExecutionReceipt, RawExecution, RouteEstimate
from aeep.templates import render
from aeep_toolkit import workflow_telemetry
from aeep_toolkit.cli import main
from aeep_toolkit.workflow_telemetry import ReceiptExportDefinition, export_receipt, spec_for


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture
def configured(tmp_path, monkeypatch):
    workflow, data, _ = definition(tmp_path)
    router, repo, scope, scope_file, _ = accounting(tmp_path, workflow)
    binding = ReceiptExportDefinition(
        request=scope.request,
        port=39067,
        enabled=True,
        deployment_review_ref=scope.request.environment_digest,
    )
    file = tmp_path / "receipt-export.json"
    file.write_text(binding.model_dump_json())
    selected = data["configurations"]["document-data"]
    selected["components"] += ["langfuse", "opentelemetry"]
    selected["telemetry"] = {"path": file.name, "sha256": sha(file)}
    workflow.write_text(json.dumps(data))
    scope = scope.model_copy(update={"workflow_sha256": sha(workflow)})
    scope_file.write_text(scope.model_dump_json())
    repo.review(repo.put("toolkit_workflow_accounting", content_digest(scope), scope))
    repo.review(repo.put("toolkit_receipt_export", content_digest(binding), binding))
    receipt = ExecutionReceipt(
        decision_id="private-path-example",
        action_id="private-prompt-example",
        capability="private-fixture",
        executor_id="fixture",
        executor_kind="command",
        status="success",
        estimated=RouteEstimate(),
        metadata={"prompt": "do not disclose", "artifact": "secret artifact bytes"},
    )
    repo.store.save_receipt(receipt)
    monkeypatch.setenv("AEEP_LANGFUSE_LOCAL_AUTH", "Basic first-party-fixture-only")
    yield workflow, repo, scope_file, binding, receipt, file
    router.store.close()


def substitute(monkeypatch, *, output=None, failure=False, before=None):
    calls = []

    class Transport(BaseExecutor):
        async def execute(self, context):
            if before:
                before()
            context.invocation_check()
            calls.append(context)
            if failure:
                raise TimeoutError("sensitive provider response must not persist")
            return RawExecution(status="success", output=output if output is not None else {})

    monkeypatch.setattr(workflow_telemetry, "HTTPExecutor", Transport)
    return calls


def invoke(value, key="export", reviewed=True):
    path, _, scope, _, receipt, *_ = value
    facts = export_receipt(
        path,
        "document-data",
        receipt.receipt_id,
        accounting=scope,
        operation_key=key + "-preview",
        reviewed_digest=None,
    )
    if not reviewed:
        return facts
    return export_receipt(
        path,
        "document-data",
        receipt.receipt_id,
        accounting=scope,
        operation_key=key,
        reviewed_digest=facts["review_sha256"],
    )


def test_cli_without_accounting_is_inert_and_does_not_resolve_receipts(
    configured, monkeypatch, capsys
):
    from aeep.router import Router

    monkeypatch.setattr(
        Router, "from_manifest", lambda *_: pytest.fail("inert preview opened store")
    )
    main(
        [
            "workflow",
            "export-telemetry",
            "--workflow",
            str(configured[0]),
            "--configuration",
            "document-data",
            "--receipt-id",
            configured[4].receipt_id,
        ]
    )
    result = json.loads(capsys.readouterr().out)
    assert result["export_performed"] is False
    assert result["receipt_resolution"] == "REQUIRES_CANONICAL_ACCOUNTING"


def test_existing_http_executor_template_and_endpoint_are_exact(configured, monkeypatch):
    spec = spec_for(configured[3])
    assert render(spec.config["json"], {"input": {"resourceSpans": []}}) == {"resourceSpans": []}
    assert (
        render(spec.config["headers"], {}, allow_env=True)["Authorization"]
        == "Basic first-party-fixture-only"
    )
    assert spec.config["allowed_hosts"] == ["127.0.0.1"] and not spec.config["trust_proxy_env"]
    assert not spec.config["follow_redirects"] and spec.config["method"] == "POST"


def test_export_minimizes_source_and_accounts_without_claiming_ingestion(configured, monkeypatch):
    calls = substitute(monkeypatch)
    result = invoke(configured)
    assert (
        result["export_performed"]
        and result["transport_accepted"]
        and not result["ingestion_verified"]
    )
    assert len(calls) == 1
    text = json.dumps(calls[0].request.input)
    for private in [
        "do not disclose",
        "secret artifact bytes",
        "private-path-example",
        "private-prompt-example",
        "Basic",
    ]:
        assert private not in text
    assert result["source_receipt_sha256"] in text
    repository = configured[1]
    record = repository.get("toolkit_receipt_export_record", result["record_ref"])
    transport = repository.get("toolkit_receipt_export_transport", result["transport_receipt_ref"])
    assert record["trace_id"] == result["trace_id"]
    assert (
        transport["execution_success"] and transport["metadata"]["response_contents_not_retained"]
    )
    ledger = repository.operation_ledger(configured[3].request.plan_id)
    assert len(ledger.operations) == 3
    assert all(row.elapsed_seconds is not None for row in ledger.operations)
    assert all(row.reserved.max_model_turns == 0 for row in ledger.operations)


@pytest.mark.parametrize(
    "output", [{"partialSuccess": {"rejectedSpans": "1"}}, {"unexpected": "private payload"}, []]
)
def test_invalid_or_partial_acceptance_stays_failed_and_charged(configured, monkeypatch, output):
    calls = substitute(monkeypatch, output=output)
    with pytest.raises(ConfigurationError, match="without verified acceptance"):
        invoke(configured)
    assert len(calls) == 1
    repo = configured[1]
    assert not repo.store._connection.execute(
        "SELECT 1 FROM assessment_operations WHERE state='reserved'"
    ).fetchone()
    assert (
        repo.store._connection.execute("SELECT count(*) FROM assessment_operations").fetchone()[0]
        == 3
    )
    assert not repo.store._connection.execute(
        "SELECT 1 FROM assessment_records WHERE kind='toolkit_receipt_export_record'"
    ).fetchone()


def test_timeout_does_not_retry_or_persist_provider_content(configured, monkeypatch):
    calls = substitute(monkeypatch, failure=True)
    with pytest.raises(ConfigurationError):
        invoke(configured)
    with pytest.raises(ConfigurationError, match="blind retry denied"):
        invoke(configured, key="different-cli-key")
    assert len(calls) == 1
    rows = (
        configured[1]
        .store._connection.execute("SELECT payload_json FROM assessment_records")
        .fetchall()
    )
    assert "sensitive provider response" not in json.dumps([list(row) for row in rows])


def test_revoked_definition_and_missing_auth_stop_before_transport(configured, monkeypatch):
    calls = substitute(monkeypatch)
    monkeypatch.delenv("AEEP_LANGFUSE_LOCAL_AUTH")
    with pytest.raises(ConfigurationError, match="authentication is unavailable"):
        invoke(configured)
    configured[1].review(content_digest(configured[3]), revoke=True)
    with pytest.raises(ConfigurationError):
        invoke(configured, key="revoked")
    assert not calls


def test_disabled_configuration_sends_nothing_and_reads_no_auth(configured, monkeypatch):
    path, _, scope, binding, _receipt, file = configured
    disabled = binding.model_copy(update={"enabled": False})
    file.write_text(disabled.model_dump_json())
    data = json.loads(path.read_bytes())
    data["configurations"]["document-data"]["telemetry"]["sha256"] = sha(file)
    path.write_text(json.dumps(data))
    from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition

    accounting_record = WorkflowAccountingDefinition.model_validate_json(
        scope.read_bytes()
    ).model_copy(update={"workflow_sha256": sha(path)})
    scope.write_text(accounting_record.model_dump_json())
    configured[1].review(
        configured[1].put(
            "toolkit_workflow_accounting", content_digest(accounting_record), accounting_record
        )
    )
    monkeypatch.delenv("AEEP_LANGFUSE_LOCAL_AUTH")
    calls = substitute(monkeypatch)
    result = invoke(configured)
    assert result["status"] == "disabled" and result["export_performed"] is False and not calls


def test_unknown_receipt_and_changed_definition_are_rejected(configured, monkeypatch):
    calls = substitute(monkeypatch)
    path, _, scope, *_ = configured
    with pytest.raises(ConfigurationError, match="absent from the canonical store"):
        export_receipt(
            path,
            "document-data",
            "missing",
            accounting=scope,
            operation_key="missing",
            reviewed_digest=None,
        )
    configured[-1].write_text("{}")
    with pytest.raises(ValueError):
        invoke(configured, key="changed")
    assert not calls


@pytest.mark.asyncio
async def test_campaign_receipt_binds_completed_job_selected_scope_and_original(tmp_path, monkeypatch):
    from test_toolkit_managed import prepared, record

    from aeep.assessment.models import RecipeMaterializationRequest

    router, service, adapter, path, _ = prepared(tmp_path, monkeypatch)
    repository = service.repository
    try:
        report = record(service, adapter, path)
        with router.store._immediate_transaction() as connection:
            connection.execute(
                "INSERT INTO assessment_jobs(id, plan_id, state, report_id) VALUES (?, ?, 'complete', ?)",
                ("fixture-complete", adapter.plan.plan_id, report.report_id),
            )
        with sqlite3.connect(path) as connection:
            for receipt_id, trial_id, value in connection.execute(
                "SELECT receipt_id,trial_id,payload_json FROM trial_receipts"
            ).fetchall():
                receipt = ExecutionReceipt.model_validate_json(value)
                receipt.metadata["worker_cleanup_confirmed"] = True
                connection.execute("UPDATE trial_receipts SET payload_json=? WHERE receipt_id=?",
                                   (receipt.model_dump_json(), receipt_id))
                original_path, = connection.execute("SELECT database_path FROM trial_stores WHERE trial_id=?",
                                                    (trial_id,)).fetchone()
                with sqlite3.connect(original_path) as original:
                    original.execute("UPDATE receipts SET payload_json=? WHERE receipt_id=?",
                                     (receipt.model_dump_json(), receipt_id))
        request = RecipeMaterializationRequest(
            **{name: getattr(adapter.plan, name) for name in (
                "subject_digest", "recipe_digest", "mapping_digest", "environment_digest",
                "authorization_id", "definition_digests",
            )}, seed=0,
        )
        args = (repository, content_digest(report), receipt_id, adapter.plan)
        assert workflow_telemetry.campaign_receipt(*args, request) == receipt
        assert router.store.get_receipt(receipt_id) is None
        with pytest.raises(ConfigurationError, match="scope"):
            workflow_telemetry.campaign_receipt(*args, request.model_copy(update={"recipe_digest": "e" * 64}))
        with sqlite3.connect(original_path) as original:
            original.execute("DELETE FROM receipts WHERE receipt_id=?", (receipt_id,))
        with pytest.raises(ConfigurationError, match="original attempt"):
            workflow_telemetry.campaign_receipt(*args, request)
    finally:
        await router.close()


@pytest.mark.asyncio
async def test_real_http_executor_checks_authority_before_creating_client(monkeypatch):
    from aeep.executors.base import ExecutionContext
    from aeep.executors.http import HTTPExecutor
    from aeep.models import ActionRequest

    definition = ReceiptExportDefinition(
        request={
            "plan_id": "fixture",
            "subject_digest": "a" * 64,
            "recipe_digest": "b" * 64,
            "mapping_digest": "c" * 64,
            "environment_digest": "d" * 64,
            "definition_digests": [],
            "authorization_id": "fixture",
            "seed": 0,
        },
        port=39067,
        deployment_review_ref="e" * 64,
    )
    spec = spec_for(definition)
    monkeypatch.setenv("AEEP_LANGFUSE_LOCAL_AUTH", "Basic fixture-only")
    monkeypatch.setattr("aeep.executors.http.validate_http_url", _valid_fixture_url)
    monkeypatch.setattr(
        "aeep.executors.http.httpx.AsyncClient",
        lambda **_: pytest.fail("denied request opened client"),
    )

    def denied():
        raise ConfigurationError("revoked")

    executor = HTTPExecutor()
    raw = await executor.execute(
        ExecutionContext(
            request=ActionRequest(capability=spec.capability, input={}),
            spec=spec,
            estimate=spec.estimate,
            attempt=1,
            invocation_check=denied,
        )
    )
    assert raw.status.value == "failed" and raw.error_type == "ConfigurationError"


def test_revocation_at_invocation_retains_charges_without_disclosure(configured, monkeypatch):
    calls = substitute(
        monkeypatch, before=lambda: configured[1].review(content_digest(configured[3]), revoke=True)
    )
    with pytest.raises(ConfigurationError, match="without verified acceptance"):
        invoke(configured)
    assert not calls
    assert (
        configured[1]
        .store._connection.execute("SELECT count(*) FROM assessment_operations")
        .fetchone()[0]
        == 3
    )


def test_source_receipt_change_invalidates_exact_preview(configured, monkeypatch):
    calls = substitute(monkeypatch)
    facts = invoke(configured, reviewed=False)
    path, repo, scope, _, receipt, _ = configured
    repo.store.save_receipt(receipt.model_copy(update={"error_type": "changed"}))
    with pytest.raises(ConfigurationError, match="preview changed"):
        export_receipt(
            path,
            "document-data",
            receipt.receipt_id,
            accounting=scope,
            operation_key="changed-receipt",
            reviewed_digest=facts["review_sha256"],
        )
    assert not calls


async def _valid_fixture_url(*args, **kwargs):
    return None


def test_full_ledger_path_uses_real_http_serialization_without_a_network(configured, monkeypatch):
    import httpx

    seen = []
    actual_client = httpx.AsyncClient

    def response(request):
        seen.append(request)
        assert request.url == "http://127.0.0.1:39067/api/public/otel/v1/traces"
        assert request.headers["authorization"] == "Basic first-party-fixture-only"
        assert request.headers["x-langfuse-ingestion-version"] == "4"
        return httpx.Response(200, json={})

    monkeypatch.setattr("aeep.executors.http.validate_http_url", _valid_fixture_url)
    monkeypatch.setattr(
        "aeep.executors.http.httpx.AsyncClient",
        lambda **kwargs: actual_client(transport=httpx.MockTransport(response), **kwargs),
    )
    result = invoke(configured)
    assert len(seen) == 1 and result["transport_accepted"] and not result["ingestion_verified"]
    payload = json.loads(seen[0].content)
    assert payload["resourceSpans"][0]["scopeSpans"][0]["spans"][0]["traceId"] == result["trace_id"]
    transport = configured[1].get(
        "toolkit_receipt_export_transport", result["transport_receipt_ref"]
    )
    assert transport["actual_resources"]["network_bytes"] > len(seen[0].content)
    assert transport["metadata"]["observed_resource_dimensions"] == ["latency_ms", "network_bytes"]


@pytest.mark.parametrize("port", [True, 0, 80, 65536, "3030"])
def test_destination_cannot_be_a_url_credential_or_coerced_port(configured, port):
    data = configured[3].model_dump(mode="json") | {"port": port}
    with pytest.raises(ValueError):
        ReceiptExportDefinition.model_validate(data)
