from __future__ import annotations

import asyncio
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from aeep.config import load_manifest
from aeep.economic import MarketAggregateImporter, canonical_payload, verify_ed25519
from aeep.economic.trust import TrustedProviderKey, TrustStore, TrustStoreVerifier
from aeep.errors import ConfigurationError
from aeep.executors import ExecutionContext
from aeep.market_server import (
    CAPABILITY,
    EXECUTOR_FINGERPRINT,
    EXECUTOR_ID,
    PROVIDER_ID,
    ReferenceEconomicExecutor,
    ReferenceMarket,
    ReferenceQuoteProvider,
    create_app,
    reference_executor_spec,
)
from aeep.models import (
    ActionFeatures,
    ActionRequest,
    BoundedQuote,
    CurrencyAmount,
    ExecutionStatus,
    ExecutorKind,
    MarketAggregate,
    QuoteRequestV2,
    SideEffect,
    UsageStatement,
)
from aeep.qualification import RouteCandidate, RouteLifecycle, behavior_fingerprint
from aeep.router import Router
from aeep.store import ReceiptStore

NOW = datetime(2026, 8, 14, 12, tzinfo=UTC)
ROOT = Path(__file__).resolve().parents[1]


def _request(index: int = 1, *, input_bytes: int = 14_336) -> QuoteRequestV2:
    return QuoteRequestV2(
        quote_request_id=f"quote-request-{index}",
        action_id=f"action-{index}",
        capability=CAPABILITY,
        executor_id=EXECUTOR_ID,
        executor_fingerprint=EXECUTOR_FINGERPRINT,
        action_digest="sha256:" + hashlib.sha256(f"action-{index}".encode()).hexdigest(),
        input_features=ActionFeatures(
            input_bytes=input_bytes,
            input_items=1,
            text_characters=input_bytes,
            max_depth=1,
            size_bucket="2^14",
        ),
        disclosed_quote_features={"input_bytes": input_bytes},
        desired_currency="USD",
        nonce=f"reference-nonce-{index:08d}",
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=5),
    )


def _post_model(client: TestClient, path: str, model: QuoteRequestV2) -> Any:
    return client.post(
        path,
        content=model.model_dump_json(),
        headers={"content-type": "application/json"},
    )


def _complete_run(
    client: TestClient,
    index: int,
    *,
    task_valid: bool = True,
    input_bytes: int = 2048,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    request = _request(index, input_bytes=input_bytes)
    quote_response = _post_model(client, "/v1/quotes", request)
    assert quote_response.status_code == 200
    quote = quote_response.json()
    usage_response = client.post(
        "/v1/usage-statements",
        json={
            "quote_id": quote["quote_id"],
            "prepared_id": f"prepared-{index}",
            "action_id": request.action_id,
            "attempt_id": f"attempt-{index}",
            "execution_status": "SUCCESS",
            "actual_input_bytes": input_bytes,
            "started_at": (NOW - timedelta(milliseconds=index + 1)).isoformat(),
            "completed_at": NOW.isoformat(),
        },
    )
    assert usage_response.status_code == 200
    usage = usage_response.json()
    reconciliation_response = client.post(
        "/v1/reconciliations",
        json={
            "settlement_id": f"settlement-{index}",
            "usage_statement_id": usage["usage_statement_id"],
            "billed_amount": usage["provider_calculated_amount"],
            "task_valid": task_valid,
            "billing_record_reference": f"billing-record-{index}",
        },
    )
    assert reconciliation_response.status_code == 200
    return quote, usage, reconciliation_response.json()


def test_health_keys_and_signed_offer() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))

    assert client.get("/health").json() == {
        "ok": True,
        "service": "aeep-reference-market",
        "schema_version": "0.4",
        "reference_only": True,
        "unauthenticated_evidence_ingestion": False,
    }
    key_document = client.get("/.well-known/aeep-keys.json").json()
    key = TrustedProviderKey.model_validate(key_document["keys"][0])
    assert key.provider_id == PROVIDER_ID
    assert key.public_key == market.signer.public_key_base64url()

    response = client.get("/v1/offers", params={"capability": CAPABILITY})
    assert response.status_code == 200
    offer = market.offer.model_validate(response.json()["offers"][0])
    assert offer.executor_fingerprint == EXECUTOR_FINGERPRINT
    assert offer.settlement_currency == "USD"
    assert verify_ed25519(canonical_payload(offer), offer.signature, market.signer.public_key)
    assert client.get("/v1/offers", params={"capability": "other.action@1"}).json() == {
        "offers": []
    }


def test_reference_identity_and_offer_are_deterministic() -> None:
    first = ReferenceMarket(clock=lambda: NOW)
    second = ReferenceMarket(clock=lambda: NOW)
    assert first.signer.public_key_bytes() == second.signer.public_key_bytes()
    assert first.offer.model_dump_json() == second.offer.model_dump_json()


def test_reference_manifest_and_offer_bind_the_exact_behavior_fingerprint() -> None:
    spec = reference_executor_spec()
    manifest, _ = load_manifest(ROOT / "examples/economic_market/aeep.yaml")
    action = ActionRequest.model_validate_json(
        (ROOT / "examples/economic_market/action.json").read_text(encoding="utf-8")
    )

    assert manifest.executors == [spec]
    assert manifest.budget is not None
    assert manifest.budget.max_per_action_usd == 0.01
    assert manifest.budget.prepaid_balance_usd == 1.0
    assert manifest.economic_evidence.payment.adapter == "prepaid"
    assert action.capability == CAPABILITY
    assert action.idempotency_key == "economic-reference-cli-1"
    assert f"sha256:{behavior_fingerprint(spec)}" == EXECUTOR_FINGERPRINT
    market = ReferenceMarket(clock=lambda: NOW)
    assert market.offer.executor_fingerprint == EXECUTOR_FINGERPRINT
    trusted = TrustStore.load(ROOT / "examples/economic_market/provider-keys.json")
    assert trusted.get(PROVIDER_ID, market.signer.key_id) == market.trusted_key
    assert spec.config["economic"]["quote_disclosure"]["fields"] == [
        {
            "source": "action_features.input_bytes",
            "name": "input_bytes",
            "type": "integer",
            "minimum": 0,
            "maximum": 100_000_000,
            "required": True,
        }
    ]


@pytest.mark.asyncio
async def test_authenticated_process_serves_quote_and_prepared_http_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    token = "reference-process-test-token"
    token_env = "AEEP_REFERENCE_MARKET_TOKEN"
    monkeypatch.setenv(token_env, token)
    environment = dict(os.environ)
    existing_path = environment.get("PYTHONPATH")
    environment["PYTHONPATH"] = str(ROOT / "src") + (
        os.pathsep + existing_path if existing_path else ""
    )
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(ROOT / "examples/economic_market/server.py"),
        "--port",
        str(port),
        cwd=ROOT,
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    base_url = f"http://127.0.0.1:{port}"
    router: Router | None = None
    try:
        deadline = time.monotonic() + 10
        async with httpx.AsyncClient() as health_client:
            while True:
                if process.returncode is not None:
                    diagnostics = (
                        (await process.stderr.read()).decode()
                        if process.stderr is not None
                        else ""
                    )
                    raise AssertionError(
                        f"reference server exited during startup: {diagnostics}"
                    )
                try:
                    response = await health_client.get(
                        f"{base_url}/health", timeout=0.2
                    )
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    raise AssertionError("reference server did not become healthy")
                await asyncio.sleep(0.05)

        spec = reference_executor_spec(
            base_url=base_url,
            auth_token_env=token_env,
        )
        manifest, _ = load_manifest(
            ROOT / "examples/economic_market/aeep-authenticated.yaml"
        )
        manifest.database = ":memory:"
        manifest.executors = [spec]
        market_identity = ReferenceMarket(executor_spec=spec)
        router = Router(
            manifest,
            economic_verifier=TrustStoreVerifier(
                TrustStore((market_identity.trusted_key,))
            ),
        )
        request = ActionRequest(
            action_id="authenticated-process-action",
            capability=CAPABILITY,
            input={"text": "one two three"},
        )
        prepared = await router.prepare_route(request)
        assert prepared.feasible
        assert prepared.selected_quote_id is not None

        outcome = await router.execute_prepared(
            prepared.prepared_id,
            approved_side_effect=SideEffect.NONE,
            payment_approved=True,
        )

        assert outcome.ok
        assert outcome.output == {"characters": 13, "words": 3, "lines": 1}
        settlements = router.store.list_settlement_receipts(
            prepared_id=prepared.prepared_id
        )
        assert len(settlements) == 1
        assert settlements[0].captured_amount == CurrencyAmount(
            amount="0.0012", currency="USD"
        )
    finally:
        if router is not None:
            await router.close()
        process.terminate()
        try:
            await asyncio.wait_for(process.wait(), timeout=5)
        except TimeoutError:
            process.kill()
            await process.wait()
def test_imported_reference_spec_remains_inactive_until_qualification() -> None:
    spec = reference_executor_spec()
    candidate = RouteCandidate(
        candidate_id="candidate-reference",
        executor_id=spec.id,
        source_id="reference-descriptor",
        provider_id=PROVIDER_ID,
        capability=CAPABILITY,
        behavior_fingerprint=behavior_fingerprint(spec),
        spec=spec,
    )

    assert candidate.status is RouteLifecycle.CANDIDATE
    assert not candidate.spec.enabled


async def test_in_process_quote_adapter_binds_a_python_reference_spec() -> None:
    spec = reference_executor_spec(kind=ExecutorKind.PYTHON)
    market = ReferenceMarket(clock=lambda: NOW, executor_spec=spec)
    provider = ReferenceQuoteProvider(market)
    request = _request().model_copy(
        update={"executor_fingerprint": f"sha256:{behavior_fingerprint(spec)}"}
    )

    quote = await provider.request_quote(request)

    assert quote.executor_fingerprint == f"sha256:{behavior_fingerprint(spec)}"
    assert (await provider.get_offers(CAPABILITY, [EXECUTOR_ID])) == (market.offer,)


async def test_in_process_executor_returns_ephemeral_signed_usage() -> None:
    spec = reference_executor_spec(kind=ExecutorKind.PYTHON)
    market = ReferenceMarket(clock=lambda: NOW, executor_spec=spec)
    text = "PRIVATE_REFERENCE_INPUT"
    request = _request(input_bytes=len(text.encode())).model_copy(
        update={"executor_fingerprint": market.executor_fingerprint}
    )
    quote = market.request_quote(request)
    raw = await ReferenceEconomicExecutor(market).execute(
        ExecutionContext(
            request=ActionRequest(
                action_id=request.action_id,
                capability=CAPABILITY,
                input={"text": text},
            ),
            spec=spec,
            estimate=spec.estimate,
            attempt=1,
            prepared_id="prepared-in-process",
            quote_id=quote.quote_id,
            attempt_id="attempt-in-process",
        )
    )

    assert raw.status is ExecutionStatus.SUCCESS
    assert raw.output == {"characters": len(text), "words": 1, "lines": 1}
    statement = UsageStatement.model_validate(raw.metadata["_economic_usage_statement"])
    assert statement.quote_id == quote.quote_id
    assert statement.prepared_id == "prepared-in-process"
    assert statement.attempt_id == "attempt-in-process"
    assert statement.provider_calculated_amount == quote.expected_amount
    assert verify_ed25519(
        canonical_payload(statement),
        statement.signature,
        market.signer.public_key,
    )
    assert text not in repr(market.__dict__)


def test_bound_quote_has_exact_price_bound_binding_and_signature() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))
    request = _request()

    response = _post_model(client, "/v1/quotes", request)

    assert response.status_code == 200
    assert response.json()["expected_amount"] == {"amount": "0.0038", "currency": "USD"}
    assert response.json()["maximum_amount"] == {"amount": "0.0050", "currency": "USD"}
    quote = BoundedQuote.model_validate(response.json())
    quote.validate_binding(request, at=NOW, maximum_ttl_seconds=600)
    assert quote.action_digest == request.action_digest
    assert quote.nonce == request.nonce
    assert verify_ed25519(canonical_payload(quote), quote.signature, market.signer.public_key)
    assert _post_model(client, "/v1/quotes", request).json() == response.json()


def test_quote_nonce_and_request_id_conflicts_fail_closed() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))
    first = _request(1)
    assert _post_model(client, "/v1/quotes", first).status_code == 200

    nonce_reuse = _request(2).model_copy(update={"nonce": first.nonce})
    response = _post_model(client, "/v1/quotes", nonce_reuse)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "nonce_reuse"

    request_id_reuse = first.model_copy(update={"action_digest": "sha256:" + ("f" * 64)})
    response = _post_model(client, "/v1/quotes", request_id_reuse)
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "quote_request_conflict"


def test_quote_tampering_invalidates_signature() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    quote = market.request_quote(_request())
    tampered = quote.model_copy(
        update={"maximum_amount": CurrencyAmount(amount=Decimal("0.0060"), currency="USD")}
    )
    assert not verify_ed25519(
        canonical_payload(tampered),
        tampered.signature,
        market.signer.public_key,
    )


def test_disclosure_is_allowlisted_and_errors_do_not_echo_secrets() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))
    secret = "PRIVATE_RESUME_AND_ACCESS_TOKEN_8eea1b"
    request = _request().model_copy(update={"disclosed_quote_features": {"resume_text": secret}})

    response = _post_model(client, "/v1/quotes", request)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unapproved_disclosure"
    assert secret not in response.text
    assert secret not in repr(market.__dict__)


def test_execute_returns_statistics_and_retains_no_text_or_output() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))
    secret_text = "PRIVATE_RESUME_21c3b9"
    request = _request(input_bytes=len(secret_text.encode()))
    quote = _post_model(client, "/v1/quotes", request).json()

    response = client.post(
        "/v1/execute",
        json={
            "quote_id": quote["quote_id"],
            "prepared_id": "prepared-secret",
            "action_id": request.action_id,
            "attempt_id": "attempt-secret",
            "text": secret_text,
        },
    )

    assert response.status_code == 200
    assert response.json()["output"] == {
        "characters": len(secret_text),
        "words": 1,
        "lines": 1,
    }
    statement = UsageStatement.model_validate(response.json()["usage_statement"])
    assert verify_ed25519(
        canonical_payload(statement),
        statement.signature,
        market.signer.public_key,
    )
    assert secret_text not in repr(market.__dict__)
    assert "{'characters': 21, 'words': 1, 'lines': 1}" not in repr(market.__dict__)


def test_manifest_http_execution_shape_needs_no_economic_identifiers() -> None:
    client = TestClient(create_app(ReferenceMarket(clock=lambda: NOW)))

    response = client.post(
        "/v1/execute",
        json={
            "quote_id": None,
            "prepared_id": None,
            "action_id": "ordinary-action",
            "attempt_id": None,
            "text": "one two\nthree",
        },
    )

    assert response.status_code == 200
    assert response.json() == {"output": {"characters": 13, "words": 3, "lines": 2}}


def test_usage_and_reconciliation_are_settlement_compatible() -> None:
    market = ReferenceMarket(clock=lambda: NOW, minimum_aggregate_samples=2)
    client = TestClient(create_app(market, allow_unauthenticated_evidence=True))

    quote, usage, reconciliation = _complete_run(client, 1, input_bytes=14_336)

    assert quote["maximum_amount"]["amount"] == "0.0050"
    assert usage["provider_calculated_amount"]["amount"] == "0.0038"
    assert reconciliation["expected_amount"]["amount"] == "0.0038"
    assert reconciliation["billed_amount"]["amount"] == "0.0038"
    assert reconciliation["discrepancy"]["amount"] == "0.0000"
    assert reconciliation["status"] == "MATCHED"
    assert client.get("/v1/aggregates").json() == {"aggregates": []}


def test_aggregates_require_settled_task_valid_cohort_and_hide_action_data() -> None:
    market = ReferenceMarket(clock=lambda: NOW, minimum_aggregate_samples=2)
    client = TestClient(create_app(market, allow_unauthenticated_evidence=True))
    assert ReferenceMarket(clock=lambda: NOW).minimum_aggregate_samples == 20
    _complete_run(client, 1, task_valid=False)
    _complete_run(client, 2, task_valid=True)
    assert client.get("/v1/aggregates").json() == {"aggregates": []}
    _complete_run(client, 3, task_valid=True)

    response = client.get("/v1/aggregates")

    assert response.status_code == 200
    payload = response.json()
    assert len(payload["aggregates"]) == 1
    aggregate_data = payload["aggregates"][0]
    aggregate = MarketAggregate.model_validate(aggregate_data)
    assert aggregate.sample_size == 2
    assert aggregate.input_bucket == "0-4KiB"
    assert aggregate.actual_cost_p50 == CurrencyAmount(amount="0.0014", currency="USD")
    assert aggregate.settlement_verified_fraction == 0
    assert aggregate.billing_reconciled_fraction == 1
    assert verify_ed25519(
        canonical_payload(aggregate),
        aggregate.signature,
        market.signer.public_key,
    )
    serialized = json.dumps(aggregate_data)
    assert "action_id" not in serialized
    assert "action_digest" not in serialized
    assert "prepared_id" not in serialized
    assert "PRIVATE_RESUME" not in serialized


def test_evidence_ingestion_requires_authentication_by_default() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    client = TestClient(create_app(market))

    assert client.post("/v1/usage-statements", json={}).status_code == 403
    assert client.post("/v1/reconciliations", json={}).status_code == 403


def test_content_type_body_limit_and_bearer_auth_fail_closed() -> None:
    market = ReferenceMarket(clock=lambda: NOW)
    request = _request()
    client = TestClient(create_app(market, bearer_token="test-token", maximum_request_bytes=512))

    assert client.get("/health").status_code == 200
    assert client.get("/v1/offers").status_code == 401
    assert (
        client.get("/v1/offers", headers={"authorization": "Bearer wrong-token"}).status_code == 401
    )
    assert (
        client.get(
            "/v1/offers",
            headers={"authorization": "Bearer test-token"},
        ).status_code
        == 200
    )

    headers = {"authorization": "Bearer test-token", "content-type": "text/plain"}
    assert (
        client.post("/v1/quotes", content=request.model_dump_json(), headers=headers).status_code
        == 415
    )
    headers["content-type"] = "application/json"
    response = client.post("/v1/quotes", content=request.model_dump_json(), headers=headers)
    assert response.status_code == 413
    assert "test-token" not in response.text


def test_signed_aggregate_response_imports_into_a_buyer_store(tmp_path: Path) -> None:
    market = ReferenceMarket(
        clock=lambda: NOW,
        minimum_aggregate_samples=1,
    )
    client = TestClient(create_app(market, allow_unauthenticated_evidence=True))
    _complete_run(client, 1, input_bytes=2048)
    response = client.get("/v1/aggregates")
    assert response.status_code == 200

    with ReceiptStore(tmp_path / "buyer.db") as store:
        importer = MarketAggregateImporter(
            store,
            TrustStoreVerifier(TrustStore((market.trusted_key,)), clock=lambda: NOW),
        )
        imported = importer.import_response(
            response.content,
            content_type=response.headers["content-type"],
        )

        assert len(imported) == 1
        assert store.get_market_aggregate(imported[0].aggregate_id) == imported[0]
        assert imported[0].settlement_verified_fraction == Decimal(0)
        assert imported[0].billing_reconciled_fraction == Decimal(1)

        tampered = response.json()
        tampered["aggregates"][0]["actual_cost_p50"]["amount"] = "0.0001"
        with pytest.raises(ConfigurationError, match="signature"):
            importer.import_response(json.dumps(tampered).encode())
        altered_unsigned = imported[0].model_copy(
            update={
                "actual_cost_p50": CurrencyAmount(amount="0.0001", currency="USD")
            }
        )
        altered = altered_unsigned.model_copy(
            update={
                "signature": market.signer.sign(canonical_payload(altered_unsigned))
            }
        )
        with pytest.raises(ConfigurationError, match="immutable content"):
            importer.import_response(
                json.dumps(
                    {"aggregates": [altered.model_dump(mode="json")]}
                ).encode()
            )
        with pytest.raises(ConfigurationError, match="application/json"):
            importer.import_response(response.content, content_type="text/plain")
        with pytest.raises(ConfigurationError, match="size limit"):
            MarketAggregateImporter(
                store,
                TrustStoreVerifier(TrustStore((market.trusted_key,)), clock=lambda: NOW),
                maximum_response_bytes=1,
            ).import_response(response.content)
