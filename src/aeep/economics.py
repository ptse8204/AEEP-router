"""Capability quotes and signed receipts using a provider-neutral canonical envelope."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Any

from pydantic import BaseModel

from .errors import ConfigurationError
from .models import (
    ExecutionReceipt,
    Quote,
    QuoteAcceptance,
    QuoteRequest,
    SignatureEnvelope,
    SignedExecutionReceipt,
)
from .registry import Registry


def _canonical(value: BaseModel | dict[str, Any]) -> bytes:
    payload = value.model_dump(mode="json") if isinstance(value, BaseModel) else value
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _legacy_receipt_payload(receipt: ExecutionReceipt) -> dict[str, Any]:
    payload = receipt.model_dump(mode="json")
    payload.pop("accounting", None)
    payload.get("actual_resources", {}).pop("cached_input_tokens", None)
    estimated = payload.get("estimated", {})
    estimated.pop("cash", None)
    estimated.pop("subscription_usage", None)
    estimated.get("resources", {}).pop("cached_input_tokens", None)
    return payload


class HMACSigner:
    """Minimal local signer; the algorithm is explicit so it is not mistaken for PKI."""

    def __init__(self, key: bytes, *, key_id: str) -> None:
        if len(key) < 32:
            raise ValueError("signing key must contain at least 32 bytes")
        self.key = key
        self.key_id = key_id

    def sign(self, value: BaseModel | dict[str, Any]) -> SignatureEnvelope:
        digest = hmac.new(self.key, _canonical(value), hashlib.sha256).digest()
        encoded = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
        return SignatureEnvelope(key_id=self.key_id, value=encoded)

    def verify(self, value: BaseModel | dict[str, Any], signature: SignatureEnvelope) -> bool:
        if signature.key_id != self.key_id or signature.algorithm != "hmac-sha256":
            return False
        return hmac.compare_digest(self.sign(value).value, signature.value)

    def sign_receipt(self, receipt: ExecutionReceipt) -> SignedExecutionReceipt:
        return SignedExecutionReceipt(
            receipt=receipt,
            signature=self.sign(receipt),
            canonical_version=2,
        )

    def verify_receipt(self, signed: SignedExecutionReceipt) -> bool:
        payload: BaseModel | dict[str, Any] = (
            signed.receipt
            if signed.canonical_version == 2
            else _legacy_receipt_payload(signed.receipt)
        )
        return self.verify(payload, signed.signature)


class QuoteService:
    def __init__(self, registry: Registry, *, signer: HMACSigner | None = None) -> None:
        self.registry = registry
        self.signer = signer

    def quote(self, request: QuoteRequest, *, ttl_seconds: int = 300) -> list[Quote]:
        requested_ids = set(request.executor_ids or [])
        quotes: list[Quote] = []
        for spec in self.registry.find(request.action.capability):
            if requested_ids and spec.id not in requested_ids:
                continue
            quote = Quote(
                quote_request_id=request.quote_request_id,
                provider_id=spec.provider_id or "local",
                executor_id=spec.id,
                capability=spec.capability,
                monetary_usd=spec.estimate.resources.monetary_usd,
                estimate=spec.estimate.model_copy(deep=True),
                expires_at=datetime.now(UTC) + timedelta(seconds=max(1, ttl_seconds)),
                terms={"currency": "USD", "source": "static-prior"},
            )
            if self.signer is not None:
                unsigned = quote.model_copy(update={"signature": None})
                quote.signature = self.signer.sign(unsigned)
            quotes.append(quote)
        return quotes

    def accept(
        self,
        quote: Quote,
        *,
        action_id: str,
        max_amount_usd: float | None = None,
    ) -> QuoteAcceptance:
        now = datetime.now(UTC)
        if quote.expires_at < now:
            raise ConfigurationError("quote has expired")
        if max_amount_usd is not None and quote.monetary_usd > max_amount_usd:
            raise ConfigurationError("quote exceeds accepted maximum")
        if quote.signature is not None:
            if self.signer is None:
                raise ConfigurationError("cannot verify signed quote without its signer")
            unsigned = quote.model_copy(update={"signature": None})
            if not self.signer.verify(unsigned, quote.signature):
                raise ConfigurationError("quote signature is invalid")
        acceptance = QuoteAcceptance(
            quote_id=quote.quote_id,
            action_id=action_id,
            accepted_amount_usd=quote.monetary_usd,
        )
        if self.signer is not None:
            acceptance.signature = self.signer.sign(
                acceptance.model_copy(update={"signature": None})
            )
        return acceptance
