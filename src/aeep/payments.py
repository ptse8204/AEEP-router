"""Payment-rail-neutral reservations, captures, refunds, and local budget gates."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
from collections.abc import Awaitable, Callable, Mapping
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol, TypeVar, cast

from .economic.canonical import canonical_digest
from .errors import ApprovalRequired, ConfigurationError
from .models import (
    AgentBudget,
    AuthorizationKind,
    BillingReconciliation,
    BillingTrigger,
    BoundedQuote,
    CurrencyAmount,
    EconomicEvidenceLevel,
    FailureChargePolicy,
    LedgerEvent,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    PaymentReservationState,
    PaymentReservationV2,
    PaymentState,
    PreparedDecisionState,
    ProviderExecutionStatus,
    Quote,
    RefundReceiptV2,
    RetryChargePolicy,
    SettlementEvidence,
    SettlementReceipt,
    SettlementStatus,
    SideEffect,
    utc_now,
)
from .store import ReceiptStore


class PaymentAdapter(Protocol):
    name: str

    async def reserve(self, quote: Quote, action_id: str) -> PaymentReservation: ...

    async def capture(self, reservation: PaymentReservation) -> PaymentCapture: ...

    async def refund(self, capture: PaymentCapture, amount_usd: float) -> PaymentRefund: ...


class FreePaymentAdapter:
    name = "free"

    async def reserve(self, quote: Quote, action_id: str) -> PaymentReservation:
        if quote.monetary_usd != 0:
            raise ConfigurationError("free adapter cannot reserve a paid quote")
        return PaymentReservation(
            quote_id=quote.quote_id,
            action_id=action_id,
            adapter=self.name,
            amount_usd=0,
        )

    async def capture(self, reservation: PaymentReservation) -> PaymentCapture:
        return PaymentCapture(reservation_id=reservation.reservation_id, amount_usd=0)

    async def refund(self, capture: PaymentCapture, amount_usd: float) -> PaymentRefund:
        if amount_usd != 0:
            raise ConfigurationError("free adapter cannot refund a positive amount")
        return PaymentRefund(capture_id=capture.capture_id, amount_usd=0)


class PrepaidBalanceAdapter:
    name = "prepaid"

    def __init__(self, balance_usd: float | None) -> None:
        self.balance = Decimal(str(balance_usd)) if balance_usd is not None else None
        self.reserved: dict[str, Decimal] = {}

    async def reserve(self, quote: Quote, action_id: str) -> PaymentReservation:
        amount = Decimal(str(quote.monetary_usd))
        available = (
            self.balance - sum(self.reserved.values(), Decimal("0"))
            if self.balance is not None
            else None
        )
        if available is not None and amount > available:
            raise ConfigurationError("insufficient prepaid balance")
        reservation = PaymentReservation(
            quote_id=quote.quote_id,
            action_id=action_id,
            adapter=self.name,
            amount_usd=float(amount),
        )
        self.reserved[reservation.reservation_id] = amount
        return reservation

    async def capture(self, reservation: PaymentReservation) -> PaymentCapture:
        amount = self.reserved.pop(reservation.reservation_id, Decimal(str(reservation.amount_usd)))
        if self.balance is not None and amount > self.balance:
            raise ConfigurationError("insufficient prepaid balance")
        if self.balance is not None:
            self.balance -= amount
        return PaymentCapture(
            reservation_id=reservation.reservation_id,
            amount_usd=float(amount),
        )

    async def refund(self, capture: PaymentCapture, amount_usd: float) -> PaymentRefund:
        amount = Decimal(str(amount_usd))
        if amount > Decimal(str(capture.amount_usd)):
            raise ConfigurationError("refund exceeds captured amount")
        if self.balance is not None:
            self.balance += amount
        return PaymentRefund(capture_id=capture.capture_id, amount_usd=float(amount))


class InvoicePaymentAdapter(PrepaidBalanceAdapter):
    name = "invoice"

    def __init__(self) -> None:
        super().__init__(None)


PaymentCallback = Callable[..., Any | Awaitable[Any]]


class CallbackPaymentAdapter:
    """Bridge for x402, MPP, invoice, or enterprise settlement implementations."""

    def __init__(
        self,
        name: str,
        *,
        reserve: PaymentCallback,
        capture: PaymentCallback,
        refund: PaymentCallback,
    ) -> None:
        self.name = name
        self._reserve = reserve
        self._capture = capture
        self._refund = refund

    async def _call(self, callback: PaymentCallback, *args: Any) -> Any:
        value = callback(*args)
        return await value if inspect.isawaitable(value) else value

    async def reserve(self, quote: Quote, action_id: str) -> PaymentReservation:
        metadata = await self._call(self._reserve, quote, action_id)
        return PaymentReservation(
            quote_id=quote.quote_id,
            action_id=action_id,
            adapter=self.name,
            amount_usd=quote.monetary_usd,
            metadata=dict(metadata or {}),
        )

    async def capture(self, reservation: PaymentReservation) -> PaymentCapture:
        metadata = await self._call(self._capture, reservation)
        return PaymentCapture(
            reservation_id=reservation.reservation_id,
            amount_usd=reservation.amount_usd,
            metadata=dict(metadata or {}),
        )

    async def refund(self, capture: PaymentCapture, amount_usd: float) -> PaymentRefund:
        metadata = await self._call(self._refund, capture, amount_usd)
        return PaymentRefund(
            capture_id=capture.capture_id,
            amount_usd=amount_usd,
            metadata=dict(metadata or {}),
        )


class X402PaymentAdapter(CallbackPaymentAdapter):
    def __init__(self, **callbacks: PaymentCallback) -> None:
        super().__init__("x402", **callbacks)


class MPPPaymentAdapter(CallbackPaymentAdapter):
    def __init__(self, **callbacks: PaymentCallback) -> None:
        super().__init__("mpp", **callbacks)


class EnterprisePaymentAdapter(CallbackPaymentAdapter):
    def __init__(self, **callbacks: PaymentCallback) -> None:
        super().__init__("enterprise", **callbacks)


class PaymentAdapterV2(Protocol):
    """Exact-money payment rail used by prepared AEEP 0.4 execution."""

    name: str
    settlement_currency: str

    def validate_maximum(self, maximum_amount: CurrencyAmount) -> None: ...

    async def reserve(
        self,
        *,
        reservation: PaymentReservationV2,
    ) -> PaymentReservationV2: ...

    async def settle(
        self,
        *,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt: ...

    async def release(
        self,
        *,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> SettlementReceipt: ...

    async def refund(
        self,
        *,
        settlement: SettlementReceipt,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceiptV2: ...

    async def reconcile(self, reference: str) -> BillingReconciliation: ...

    async def capture(
        self,
        *,
        reservation: PaymentReservationV2,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt: ...


V2PaymentResult = (
    PaymentReservationV2 | SettlementReceipt | RefundReceiptV2 | BillingReconciliation
)
ResultT = TypeVar("ResultT", bound=V2PaymentResult)


class _OperationCache:
    """Process-local duplicate suppression; the store provides durable idempotency."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._records: dict[str, tuple[str, V2PaymentResult]] = {}

    async def run(
        self,
        *,
        operation: str,
        key: str,
        payload: Mapping[str, Any],
        call: Callable[[], Awaitable[ResultT]],
    ) -> ResultT:
        digest = canonical_digest({"operation": operation, "payload": payload})
        operation_key = f"{operation}:{key}"
        async with self._lock:
            existing = self._records.get(operation_key)
            if existing is not None:
                if existing[0] != digest:
                    raise ConfigurationError(
                        f"payment idempotency key {key!r} was reused with different arguments"
                    )
                return cast(ResultT, existing[1])
            result = await call()
            self._records[operation_key] = (digest, result)
            return result


def _stable_operation_id(prefix: str, key: str) -> str:
    digest = hashlib.sha256(f"{prefix}\0{key}".encode()).hexdigest()
    return f"{prefix}_{digest}"


def _currency(value: str) -> str:
    return CurrencyAmount(amount=Decimal(0), currency=value).currency


def _zero(currency: str) -> CurrencyAmount:
    return CurrencyAmount(amount=Decimal(0), currency=currency)


def _reservation_with_state(
    reservation: PaymentReservationV2,
    state: PaymentReservationState,
    *,
    at: datetime,
    reason: str | None = None,
) -> PaymentReservationV2:
    payload = reservation.model_dump(mode="python")
    payload.update(
        state=state,
        updated_at=at,
        indeterminate_reason=reason if state is PaymentReservationState.INDETERMINATE else None,
    )
    return PaymentReservationV2.model_validate(payload)


def _same_reservation_identity(
    left: PaymentReservationV2, right: PaymentReservationV2
) -> bool:
    fields = (
        "reservation_id",
        "charge_id",
        "prepared_id",
        "quote_id",
        "authorization_kind",
        "authorization_id",
        "action_id",
        "attempt_id",
        "maximum_amount",
        "adapter",
        "idempotency_key",
        "created_at",
    )
    return all(getattr(left, field) == getattr(right, field) for field in fields)


def _reservation_identity_payload(reservation: PaymentReservationV2) -> dict[str, Any]:
    fields = (
        "reservation_id",
        "charge_id",
        "prepared_id",
        "quote_id",
        "authorization_kind",
        "authorization_id",
        "action_id",
        "attempt_id",
        "maximum_amount",
        "adapter",
        "idempotency_key",
        "created_at",
    )
    return {field: getattr(reservation, field) for field in fields}


def _callback_reference(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        reference = value.get("external_reference")
        if reference is None:
            return None
        if not isinstance(reference, str):
            raise ConfigurationError("payment callback external_reference must be a string")
        return reference
    raise ConfigurationError("payment callback must return metadata or an external reference")


def _validate_settlement_request(
    reservation: PaymentReservationV2,
    actual_amount: CurrencyAmount,
    evidence: SettlementEvidence,
) -> None:
    if actual_amount.currency != reservation.maximum_amount.currency:
        raise ConfigurationError("settlement currency does not match reservation")
    if actual_amount.amount > reservation.maximum_amount.amount:
        raise ConfigurationError("settlement amount exceeds reserved maximum")
    if evidence.charge_id != reservation.charge_id:
        raise ConfigurationError("settlement evidence charge does not match reservation")
    provider_amount = evidence.provider_calculated_amount
    if provider_amount is not None:
        if provider_amount.currency != actual_amount.currency:
            raise ConfigurationError("provider amount currency does not match settlement")
        if provider_amount.amount != actual_amount.amount:
            raise ConfigurationError("provider amount does not match settlement amount")


class LocalLedgerPaymentAdapter:
    """Deterministic local reference rail with exact reservation accounting."""

    def __init__(
        self,
        *,
        name: str = "local-ledger",
        settlement_currency: str = "USD",
        balance: CurrencyAmount | None = None,
        unlimited_budget: bool = False,
        free_only: bool = False,
        provider_id: str | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.name = name
        self.settlement_currency = _currency(settlement_currency)
        if balance is not None and balance.currency != self.settlement_currency:
            raise ConfigurationError("payment balance currency does not match settlement currency")
        if unlimited_budget and balance is not None:
            raise ConfigurationError("an unlimited payment rail cannot also declare a balance")
        self._balance = balance.amount if balance is not None else Decimal(0)
        self._unlimited_budget = unlimited_budget
        self._free_only = free_only
        self._provider_id = provider_id or f"local.{name}"
        self._clock = clock
        self._operations = _OperationCache()
        self._reservations: dict[str, PaymentReservationV2] = {}
        self._charge_reservations: dict[str, str] = {}
        self._settlements: dict[str, SettlementReceipt] = {}
        self._reservation_settlements: dict[str, str] = {}
        self._refunds: dict[str, RefundReceiptV2] = {}

    @property
    def available_balance(self) -> CurrencyAmount | None:
        if self._unlimited_budget:
            return None
        outstanding = sum(
            (
                item.maximum_amount.amount
                for item in self._reservations.values()
                if item.state
                in {
                    PaymentReservationState.RESERVED,
                    PaymentReservationState.SETTLING,
                    PaymentReservationState.INDETERMINATE,
                    PaymentReservationState.DISPUTED,
                }
            ),
            Decimal(0),
        )
        return CurrencyAmount(
            amount=max(Decimal(0), self._balance - outstanding),
            currency=self.settlement_currency,
        )

    def validate_maximum(self, maximum_amount: CurrencyAmount) -> None:
        """Reject statically incompatible holds without contacting the rail."""

        if maximum_amount.currency != self.settlement_currency:
            raise ConfigurationError("payment reservation currency does not match adapter")
        if self._free_only and maximum_amount.amount != 0:
            raise ConfigurationError("free adapter cannot reserve a paid amount")

    async def _reserve_external(self, reservation: PaymentReservationV2) -> Any:
        return None

    async def _settle_external(
        self,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> Any:
        return None

    async def _release_external(
        self,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> Any:
        return None

    async def _refund_external(
        self,
        settlement: SettlementReceipt,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> Any:
        return None

    async def _reconcile_external(self, reference: str) -> BillingReconciliation | None:
        return None

    def _known_reservation(self, reservation: PaymentReservationV2) -> PaymentReservationV2:
        known = self._reservations.get(reservation.reservation_id)
        if known is None:
            self._reservations[reservation.reservation_id] = reservation
            self._charge_reservations[reservation.charge_id] = reservation.reservation_id
            return reservation
        if not _same_reservation_identity(known, reservation):
            raise ConfigurationError("payment reservation identity changed")
        return known

    async def reserve(
        self,
        *,
        reservation: PaymentReservationV2,
    ) -> PaymentReservationV2:
        async def create() -> PaymentReservationV2:
            if reservation.adapter != self.name:
                raise ConfigurationError("payment reservation adapter does not match")
            self.validate_maximum(reservation.maximum_amount)
            if reservation.state is not PaymentReservationState.RESERVED:
                raise ConfigurationError("new payment reservation must be RESERVED")
            existing = self._reservations.get(reservation.reservation_id)
            if existing is not None:
                if existing != reservation:
                    raise ConfigurationError("payment reservation ID collision")
                return existing
            charge_reservation = self._charge_reservations.get(reservation.charge_id)
            if charge_reservation is not None:
                raise ConfigurationError("payment charge already has a reservation")
            available = self.available_balance
            if available is not None and reservation.maximum_amount.amount > available.amount:
                raise ConfigurationError("insufficient payment balance")
            await self._reserve_external(reservation)
            self._reservations[reservation.reservation_id] = reservation
            self._charge_reservations[reservation.charge_id] = reservation.reservation_id
            return reservation

        return await self._operations.run(
            operation="reserve",
            key=reservation.idempotency_key,
            payload={"reservation": reservation},
            call=create,
        )

    def _validate_settlement_request(
        self,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
    ) -> None:
        _validate_settlement_request(reservation, actual_amount, evidence)

    async def settle(
        self,
        *,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        async def create() -> SettlementReceipt:
            self._validate_settlement_request(reservation, actual_amount, evidence)
            known = self._known_reservation(reservation)
            if known.state not in {
                PaymentReservationState.RESERVED,
                PaymentReservationState.SETTLING,
                PaymentReservationState.INDETERMINATE,
            }:
                raise ConfigurationError("payment reservation cannot be settled in its current state")
            if reservation.reservation_id in self._reservation_settlements:
                raise ConfigurationError("payment reservation was already settled")
            reference = _callback_reference(
                await self._settle_external(
                    reservation, actual_amount, evidence, idempotency_key
                )
            )
            released = reservation.maximum_amount.amount - actual_amount.amount
            receipt = SettlementReceipt(
                settlement_id=_stable_operation_id("settlement", idempotency_key),
                charge_id=reservation.charge_id,
                prepared_id=reservation.prepared_id,
                quote_id=reservation.quote_id,
                authorization_kind=reservation.authorization_kind,
                authorization_id=reservation.authorization_id,
                reservation_id=reservation.reservation_id,
                attempt_id=reservation.attempt_id,
                reserved_amount=reservation.maximum_amount,
                captured_amount=actual_amount,
                released_amount=CurrencyAmount(
                    amount=released,
                    currency=reservation.maximum_amount.currency,
                ),
                payment_rail=self.name,
                external_reference=reference or evidence.external_reference,
                status=SettlementStatus.SETTLED,
                evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
                settled_at=self._clock(),
            )
            if not self._unlimited_budget:
                if actual_amount.amount > self._balance:
                    raise ConfigurationError("insufficient payment balance at settlement")
                self._balance -= actual_amount.amount
            settled = _reservation_with_state(
                reservation, PaymentReservationState.SETTLED, at=receipt.settled_at
            )
            self._reservations[reservation.reservation_id] = settled
            self._settlements[receipt.settlement_id] = receipt
            self._reservation_settlements[reservation.reservation_id] = receipt.settlement_id
            return receipt

        return await self._operations.run(
            operation="settle",
            key=idempotency_key,
            payload={
                "reservation": _reservation_identity_payload(reservation),
                "actual_amount": actual_amount,
                "evidence": evidence,
            },
            call=create,
        )

    async def capture(
        self,
        *,
        reservation: PaymentReservationV2,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        """Backward-compatible full-capture wrapper for a V2 reservation."""

        return await self.settle(
            reservation=reservation,
            actual_amount=reservation.maximum_amount,
            evidence=evidence,
            idempotency_key=idempotency_key,
        )

    async def release(
        self,
        *,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> SettlementReceipt:
        if not reason:
            raise ConfigurationError("payment release requires a reason")

        async def create() -> SettlementReceipt:
            known = self._known_reservation(reservation)
            if known.state not in {
                PaymentReservationState.RESERVED,
                PaymentReservationState.SETTLING,
            }:
                raise ConfigurationError("payment reservation cannot be released in its current state")
            if reservation.reservation_id in self._reservation_settlements:
                raise ConfigurationError("payment reservation was already settled")
            reference = _callback_reference(
                await self._release_external(reservation, reason, idempotency_key)
            )
            receipt = SettlementReceipt(
                settlement_id=_stable_operation_id("release", idempotency_key),
                charge_id=reservation.charge_id,
                prepared_id=reservation.prepared_id,
                quote_id=reservation.quote_id,
                authorization_kind=reservation.authorization_kind,
                authorization_id=reservation.authorization_id,
                reservation_id=reservation.reservation_id,
                attempt_id=reservation.attempt_id,
                reserved_amount=reservation.maximum_amount,
                captured_amount=_zero(reservation.maximum_amount.currency),
                released_amount=reservation.maximum_amount,
                payment_rail=self.name,
                external_reference=reference,
                status=SettlementStatus.RELEASED,
                evidence_level=EconomicEvidenceLevel.PAYMENT_SETTLEMENT,
                settled_at=self._clock(),
            )
            released = _reservation_with_state(
                reservation, PaymentReservationState.RELEASED, at=receipt.settled_at
            )
            self._reservations[reservation.reservation_id] = released
            self._settlements[receipt.settlement_id] = receipt
            self._reservation_settlements[reservation.reservation_id] = receipt.settlement_id
            return receipt

        return await self._operations.run(
            operation="release",
            key=idempotency_key,
            payload={
                "reservation": _reservation_identity_payload(reservation),
                "reason": reason,
            },
            call=create,
        )

    async def refund(
        self,
        *,
        settlement: SettlementReceipt,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceiptV2:
        if not reason:
            raise ConfigurationError("payment refund requires a reason")

        async def create() -> RefundReceiptV2:
            if amount.currency != settlement.captured_amount.currency:
                raise ConfigurationError("refund currency does not match settlement")
            known = self._settlements.get(settlement.settlement_id)
            if known is not None and known != settlement:
                raise ConfigurationError("settlement identity changed")
            if known is None:
                self._settlements[settlement.settlement_id] = settlement
            refunded = sum(
                (
                    item.amount.amount
                    for item in self._refunds.values()
                    if item.settlement_id == settlement.settlement_id
                ),
                Decimal(0),
            )
            if refunded + amount.amount > settlement.captured_amount.amount:
                raise ConfigurationError("refund exceeds unrefunded captured amount")
            reference = _callback_reference(
                await self._refund_external(
                    settlement, amount, reason, idempotency_key
                )
            )
            receipt = RefundReceiptV2(
                refund_id=_stable_operation_id("refund", idempotency_key),
                settlement_id=settlement.settlement_id,
                charge_id=settlement.charge_id,
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
                refunded_at=self._clock(),
                external_reference=reference,
            )
            self._refunds[receipt.refund_id] = receipt
            if not self._unlimited_budget:
                self._balance += amount.amount
            return receipt

        return await self._operations.run(
            operation="refund",
            key=idempotency_key,
            payload={
                "settlement": settlement,
                "amount": amount,
                "reason": reason,
            },
            call=create,
        )

    async def reconcile(self, reference: str) -> BillingReconciliation:
        if not reference:
            raise ConfigurationError("billing reconciliation requires a reference")

        async def create() -> BillingReconciliation:
            external = await self._reconcile_external(reference)
            if external is not None:
                return external
            raise ConfigurationError(
                "billing reconciliation requires independent external billing evidence"
            )

        return await self._operations.run(
            operation="reconcile",
            key=f"reconcile:{reference}",
            payload={"reference": reference},
            call=create,
        )


class FreePaymentAdapterV2(LocalLedgerPaymentAdapter):
    def __init__(
        self,
        *,
        settlement_currency: str = "USD",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(
            name="free",
            settlement_currency=settlement_currency,
            balance=_zero(_currency(settlement_currency)),
            free_only=True,
            clock=clock,
        )


class PrepaidBalanceAdapterV2(LocalLedgerPaymentAdapter):
    def __init__(
        self,
        balance: CurrencyAmount,
        *,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(
            name="prepaid",
            settlement_currency=balance.currency,
            balance=balance,
            clock=clock,
        )


class InvoicePaymentAdapterV2(LocalLedgerPaymentAdapter):
    def __init__(
        self,
        *,
        unlimited_budget: bool,
        settlement_currency: str = "USD",
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        if not unlimited_budget:
            raise ConfigurationError("invoice adapter requires an explicit unlimited-budget policy")
        super().__init__(
            name="invoice",
            settlement_currency=settlement_currency,
            unlimited_budget=True,
            clock=clock,
        )


class CallbackPaymentAdapterV2(LocalLedgerPaymentAdapter):
    """V2 bridge for operator-owned payment rails with typed local validation."""

    def __init__(
        self,
        name: str,
        *,
        reserve: PaymentCallback,
        settle: PaymentCallback,
        release: PaymentCallback,
        refund: PaymentCallback,
        reconcile: PaymentCallback,
        settlement_currency: str = "USD",
        provider_id: str | None = None,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        super().__init__(
            name=name,
            settlement_currency=settlement_currency,
            unlimited_budget=True,
            provider_id=provider_id,
            clock=clock,
        )
        self._reserve_callback = reserve
        self._settle_callback = settle
        self._release_callback = release
        self._refund_callback = refund
        self._reconcile_callback = reconcile

    @staticmethod
    async def _call(callback: PaymentCallback, *args: Any) -> Any:
        value = callback(*args)
        return await value if inspect.isawaitable(value) else value

    async def _reserve_external(self, reservation: PaymentReservationV2) -> Any:
        return await self._call(self._reserve_callback, reservation)

    async def _settle_external(
        self,
        reservation: PaymentReservationV2,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> Any:
        return await self._call(
            self._settle_callback,
            reservation,
            actual_amount,
            evidence,
            idempotency_key,
        )

    async def _release_external(
        self,
        reservation: PaymentReservationV2,
        reason: str,
        idempotency_key: str,
    ) -> Any:
        return await self._call(
            self._release_callback, reservation, reason, idempotency_key
        )

    async def _refund_external(
        self,
        settlement: SettlementReceipt,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> Any:
        return await self._call(
            self._refund_callback,
            settlement,
            amount,
            reason,
            idempotency_key,
        )

    async def _reconcile_external(self, reference: str) -> BillingReconciliation | None:
        result = await self._call(self._reconcile_callback, reference)
        if not isinstance(result, BillingReconciliation):
            raise ConfigurationError("reconcile callback must return BillingReconciliation")
        if result.provider_id != self._provider_id:
            raise ConfigurationError("reconcile callback returned the wrong provider identity")
        return result


def billable_amount_for_terms(
    *,
    billing_trigger: BillingTrigger,
    failure_charge_policy: FailureChargePolicy,
    retry_charge_policy: RetryChargePolicy,
    maximum_amount: CurrencyAmount,
    fixed_authorized_amount: CurrencyAmount | None,
    execution_status: ProviderExecutionStatus,
    provider_started: bool,
    result_accepted: bool | None,
    actual_usage_amount: CurrencyAmount | None,
    fixed_attempt_fee: CurrencyAmount | None = None,
    attempt_number: int = 1,
) -> CurrencyAmount | None:
    """Resolve structured signed terms without inventing an unknown charge.

    ``fixed_authorized_amount`` is populated only when the signed authorization
    itself establishes the exact charge (for example, a fixed-price offer).
    Dynamic quotes leave it unset and therefore still require actual usage.
    """

    if attempt_number < 1:
        raise ValueError("attempt_number must be positive")
    for amount in (actual_usage_amount, fixed_authorized_amount, fixed_attempt_fee):
        if amount is None:
            continue
        if amount.currency != maximum_amount.currency:
            raise ConfigurationError("billing amount currency does not match authorization")
        if amount.amount > maximum_amount.amount:
            raise ConfigurationError("billing amount exceeds authorized maximum")

    if execution_status is ProviderExecutionStatus.INDETERMINATE:
        # An unknown external outcome cannot satisfy a signed success/failure
        # trigger. Preserve unknown cost for reconciliation instead of treating
        # uncertainty as a no-charge failure.
        return None

    if retry_charge_policy is RetryChargePolicy.MANUAL_RECONCILIATION:
        return None
    if (
        retry_charge_policy is RetryChargePolicy.FIRST_ATTEMPT_ONLY
        and attempt_number > 1
    ):
        return _zero(maximum_amount.currency)

    success = execution_status is ProviderExecutionStatus.SUCCESS
    if retry_charge_policy is RetryChargePolicy.SUCCESSFUL_ATTEMPT_ONLY and not success:
        return _zero(maximum_amount.currency)
    if billing_trigger is BillingTrigger.MANUAL_RECONCILIATION:
        return None
    if billing_trigger is BillingTrigger.ON_PROVIDER_START and not provider_started:
        return _zero(maximum_amount.currency)
    trigger_failed = (
        billing_trigger is BillingTrigger.ON_SUCCESS and not success
    ) or (
        billing_trigger is BillingTrigger.ON_ACCEPTED_RESULT and result_accepted is not True
    )
    if not trigger_failed and success:
        if fixed_authorized_amount is not None:
            return fixed_authorized_amount
        if actual_usage_amount is not None:
            return actual_usage_amount
        return _zero(maximum_amount.currency) if maximum_amount.amount == 0 else None

    if failure_charge_policy is FailureChargePolicy.NO_CHARGE:
        return _zero(maximum_amount.currency)
    if failure_charge_policy is FailureChargePolicy.CHARGE_ACTUAL_USAGE:
        return actual_usage_amount
    if failure_charge_policy is FailureChargePolicy.CHARGE_FIXED_ATTEMPT_FEE:
        return fixed_attempt_fee
    if failure_charge_policy is FailureChargePolicy.CHARGE_MAXIMUM:
        return maximum_amount
    return None


def billable_amount_for_execution(
    quote: BoundedQuote,
    *,
    execution_status: ProviderExecutionStatus,
    provider_started: bool,
    result_accepted: bool | None,
    actual_usage_amount: CurrencyAmount | None,
    fixed_attempt_fee: CurrencyAmount | None = None,
    attempt_number: int = 1,
) -> CurrencyAmount | None:
    """Apply a bounded quote's signed billing policy to observed execution."""

    if fixed_attempt_fee is not None:
        raise ConfigurationError(
            "fixed attempt fee must come from the signed quote, not the caller"
        )
    return billable_amount_for_terms(
        billing_trigger=quote.billing_trigger,
        failure_charge_policy=quote.failure_charge_policy,
        retry_charge_policy=quote.retry_charge_policy,
        maximum_amount=quote.maximum_amount,
        fixed_authorized_amount=None,
        execution_status=execution_status,
        provider_started=provider_started,
        result_accepted=result_accepted,
        actual_usage_amount=actual_usage_amount,
        fixed_attempt_fee=quote.fixed_attempt_fee,
        attempt_number=attempt_number,
    )


class BudgetManager:
    def __init__(
        self,
        budget: AgentBudget,
        store: ReceiptStore,
        adapter: PaymentAdapter,
        *,
        adapter_v2: PaymentAdapterV2 | None = None,
        settlement_currency: str = "USD",
        unlimited_budget: bool = False,
        clock: Callable[[], datetime] = utc_now,
    ) -> None:
        self.budget = budget
        self.store = store
        self.adapter = adapter
        self.adapter_v2 = adapter_v2
        self.settlement_currency = _currency(settlement_currency)
        self.unlimited_budget = unlimited_budget
        self._clock = clock

    def _spent_today(self) -> float:
        today = self._clock().astimezone(UTC).date()
        return sum(
            event.amount_usd
            for event in self.store.list_ledger_events()
            if event.event_type == "capture" and event.occurred_at.date() == today
        )

    def _prepaid_committed(self) -> float:
        events = self.store.list_ledger_events()
        captured_reservations = {
            str(event.metadata.get("reservation_id"))
            for event in events
            if event.event_type == "capture"
        }
        outstanding = sum(
            event.amount_usd
            for event in events
            if event.event_type == "reserve" and event.reference_id not in captured_reservations
        )
        captured = sum(event.amount_usd for event in events if event.event_type == "capture")
        refunded = sum(event.amount_usd for event in events if event.event_type == "refund")
        return outstanding + captured - refunded

    async def reserve(
        self,
        quote: Quote,
        *,
        action_id: str,
        approved_side_effect: SideEffect,
        human_approved: bool = False,
    ) -> PaymentReservation:
        if approved_side_effect.rank < SideEffect.FINANCIAL.rank:
            raise ApprovalRequired(
                "payment reservation requires financial approval",
                executor_id=quote.executor_id,
                required_level=SideEffect.FINANCIAL.value,
            )
        amount = quote.monetary_usd
        if amount > self.budget.max_per_action_usd:
            raise ConfigurationError("quote exceeds max_per_action_usd")
        if self._spent_today() + amount > self.budget.daily_marketplace_limit_usd:
            raise ConfigurationError("quote exceeds remaining daily marketplace budget")
        if (
            self.adapter.name == "prepaid"
            and self._prepaid_committed() + amount > self.budget.prepaid_balance_usd
        ):
            raise ConfigurationError("quote exceeds remaining prepaid balance")
        authorization = self.budget.authorization
        requires_human = authorization.financial_actions_require_human or (
            amount > authorization.auto_approve_under_usd
        )
        if requires_human and not human_approved:
            raise ApprovalRequired(
                "payment requires explicit human approval",
                executor_id=quote.executor_id,
                required_level="human_financial_approval",
            )
        reservation = await self.adapter.reserve(quote, action_id)
        self.store.save_payment_object(reservation)
        self.store.save_ledger_event(
            LedgerEvent(
                event_type="reserve",
                amount_usd=reservation.amount_usd,
                action_id=action_id,
                reference_id=reservation.reservation_id,
                metadata={"quote_id": quote.quote_id, "adapter": self.adapter.name},
            )
        )
        return reservation

    async def capture(self, reservation_id: str) -> PaymentCapture:
        reservation = self.store.get_payment_reservation(reservation_id)
        if reservation is None or reservation.state != PaymentState.RESERVED:
            raise ConfigurationError("payment reservation is unavailable")
        capture = await self.adapter.capture(reservation)
        capture.metadata.setdefault("action_id", reservation.action_id)
        reservation.state = PaymentState.CAPTURED
        self.store.save_payment_object(reservation)
        self.store.save_payment_object(capture)
        self.store.save_ledger_event(
            LedgerEvent(
                event_type="capture",
                amount_usd=capture.amount_usd,
                action_id=reservation.action_id,
                reference_id=capture.capture_id,
                metadata={"reservation_id": reservation.reservation_id},
            )
        )
        return capture

    async def refund(self, capture_id: str, amount_usd: float) -> PaymentRefund:
        capture = self.store.get_payment_capture(capture_id)
        if capture is None:
            raise ConfigurationError("payment capture is unavailable")
        refund = await self.adapter.refund(capture, amount_usd)
        self.store.save_payment_object(refund)
        self.store.save_ledger_event(
            LedgerEvent(
                event_type="refund",
                amount_usd=refund.amount_usd,
                action_id=str(capture.metadata.get("action_id", "unknown")),
                reference_id=refund.refund_id,
                metadata={"capture_id": capture.capture_id},
            )
        )
        return refund

    def _require_v2_adapter(self) -> PaymentAdapterV2:
        if self.adapter_v2 is None:
            raise ConfigurationError("a V2 payment adapter is not configured")
        if self.adapter_v2.settlement_currency != self.settlement_currency:
            raise ConfigurationError(
                "payment adapter currency does not match router settlement currency"
            )
        return self.adapter_v2

    def _authorize_v2(
        self,
        maximum_amount: CurrencyAmount,
        *,
        executor_id: str,
        payment_approved: bool,
        human_approved: bool,
    ) -> None:
        if maximum_amount.currency != self.settlement_currency:
            raise ConfigurationError("payment currency does not match router settlement currency")
        if not payment_approved:
            raise ApprovalRequired(
                "payment reservation requires operator payment approval",
                executor_id=executor_id,
                required_level="payment_approval",
            )
        if maximum_amount.amount > Decimal(str(self.budget.max_per_action_usd)):
            raise ConfigurationError("quote exceeds max_per_action_usd")
        authorization = self.budget.authorization
        requires_human = authorization.financial_actions_require_human or (
            maximum_amount.amount > Decimal(str(authorization.auto_approve_under_usd))
        )
        if requires_human and not human_approved:
            raise ApprovalRequired(
                "payment requires explicit human approval",
                executor_id=executor_id,
                required_level="human_financial_approval",
            )

    def authorize_v2(
        self,
        maximum_amount: CurrencyAmount,
        *,
        executor_id: str,
        payment_approved: bool,
        human_approved: bool = False,
    ) -> None:
        """Validate payment authority before a caller claims prepared work."""

        adapter = self._require_v2_adapter()
        adapter.validate_maximum(maximum_amount)
        self._authorize_v2(
            maximum_amount,
            executor_id=executor_id,
            payment_approved=payment_approved,
            human_approved=human_approved,
        )

    def _claim_v2_operation(
        self,
        operation: str,
        idempotency_key: str,
        request_digest: str,
    ) -> dict[str, object] | None:
        return self.store.claim_payment_operation(
            operation, idempotency_key, request_digest
        )

    @staticmethod
    def _result_id(claim: dict[str, object], expected_type: str) -> str:
        if claim.get("state") != "complete" or claim.get("status") != expected_type:
            raise ConfigurationError("payment operation is already in progress")
        ids = claim.get("receipt_ids")
        if not isinstance(ids, list) or len(ids) != 1 or not isinstance(ids[0], str):
            raise ConfigurationError("payment operation has an invalid stored result")
        return ids[0]

    def _mark_v2_operation_executing(
        self,
        operation: str,
        idempotency_key: str,
        claim: dict[str, object] | None,
    ) -> None:
        if claim is None or claim.get("state") in {"claimed", "indeterminate"}:
            self.store.mark_payment_operation_executing(operation, idempotency_key)

    def _mark_v2_operation_indeterminate(
        self,
        operation: str,
        idempotency_key: str,
    ) -> None:
        self.store.mark_payment_operation_indeterminate(operation, idempotency_key)

    def _complete_v2_operation(
        self,
        operation: str,
        idempotency_key: str,
        result: V2PaymentResult,
    ) -> None:
        if isinstance(result, PaymentReservationV2):
            result_id = result.reservation_id
        elif isinstance(result, SettlementReceipt):
            result_id = result.settlement_id
        elif isinstance(result, RefundReceiptV2):
            result_id = result.refund_id
        else:
            result_id = result.reconciliation_id
        self.store.complete_payment_operation(
            operation,
            idempotency_key,
            result_type=type(result).__name__,
            result_id=result_id,
        )

    def _mark_reservation_indeterminate(
        self,
        reservation: PaymentReservationV2,
        *,
        expected_state: PaymentReservationState,
        reason: str,
    ) -> None:
        current = self.store.get_payment_reservation_v2(reservation.reservation_id)
        if current is None or current.state is PaymentReservationState.INDETERMINATE:
            return
        if current.state is not expected_state:
            return
        updated = _reservation_with_state(
            current,
            PaymentReservationState.INDETERMINATE,
            at=self._clock(),
            reason=reason,
        )
        self.store.transition_payment_reservation_v2(
            current.reservation_id,
            expected_state=expected_state,
            updated=updated,
        )

    async def reserve_v2(
        self,
        *,
        prepared_id: str,
        quote_id: str | None,
        authorization_kind: AuthorizationKind,
        authorization_id: str,
        action_id: str,
        attempt_id: str,
        charge_id: str,
        maximum_amount: CurrencyAmount,
        idempotency_key: str,
        claim_token: str,
        payment_approved: bool,
        human_approved: bool = False,
        executor_id: str = "prepared-route",
    ) -> PaymentReservationV2:
        """Atomically hold budget, then idempotently reserve the configured rail."""

        self.authorize_v2(
            maximum_amount,
            executor_id=executor_id,
            payment_approved=payment_approved,
            human_approved=human_approved,
        )
        adapter = self._require_v2_adapter()
        if not claim_token or len(claim_token) > 256:
            raise ConfigurationError("payment reservation requires a bounded claim token")
        if not authorization_id or len(authorization_id) > 200:
            raise ConfigurationError("payment authorization ID must be non-empty and bounded")
        if authorization_kind is AuthorizationKind.SIGNED_QUOTE:
            if quote_id != authorization_id:
                raise ConfigurationError("signed-quote authorization must match quote ID")
        elif quote_id is not None:
            raise ConfigurationError("offer and rate-card authorization cannot carry a quote ID")
        request = {
            "prepared_id": prepared_id,
            "quote_id": quote_id,
            "authorization_kind": authorization_kind,
            "authorization_id": authorization_id,
            "action_id": action_id,
            "attempt_id": attempt_id,
            "charge_id": charge_id,
            "maximum_amount": maximum_amount,
            "adapter": adapter.name,
            "claim_token": claim_token,
        }
        request_digest = canonical_digest(request)
        claim = self._claim_v2_operation("reserve", idempotency_key, request_digest)
        if claim is not None and claim.get("state") == "complete":
            reservation_id = self._result_id(claim, PaymentReservationV2.__name__)
            existing = self.store.get_payment_reservation_v2(reservation_id)
            if existing is None:
                raise ConfigurationError("stored payment reservation is missing")
            return existing

        reservation_id = _stable_operation_id("reserve", idempotency_key)
        stored = self.store.get_payment_reservation_v2(reservation_id)
        if stored is None:
            now = self._clock()
            candidate = PaymentReservationV2(
                reservation_id=reservation_id,
                charge_id=charge_id,
                prepared_id=prepared_id,
                quote_id=quote_id,
                authorization_kind=authorization_kind,
                authorization_id=authorization_id,
                action_id=action_id,
                attempt_id=attempt_id,
                maximum_amount=maximum_amount,
                adapter=adapter.name,
                idempotency_key=idempotency_key,
                created_at=now,
                updated_at=now,
            )
            budget_limit = None
            prepaid_limit = None
            if not self.unlimited_budget:
                budget_limit = CurrencyAmount(
                    amount=Decimal(str(self.budget.daily_marketplace_limit_usd)),
                    currency=self.settlement_currency,
                )
                if adapter.name == "prepaid":
                    prepaid_limit = CurrencyAmount(
                        amount=Decimal(str(self.budget.prepaid_balance_usd)),
                        currency=self.settlement_currency,
                    )
            period_start = now.astimezone(UTC).replace(
                hour=0, minute=0, second=0, microsecond=0
            )
            stored = self.store.reserve_payment_v2(
                candidate,
                claim_token=claim_token,
                budget_limit=budget_limit,
                prepaid_limit=prepaid_limit,
                unlimited_budget=self.unlimited_budget,
                period_start=None if self.unlimited_budget else period_start,
            )
        else:
            expected = {
                "prepared_id": stored.prepared_id,
                "quote_id": stored.quote_id,
                "authorization_kind": stored.authorization_kind,
                "authorization_id": stored.authorization_id,
                "action_id": stored.action_id,
                "attempt_id": stored.attempt_id,
                "charge_id": stored.charge_id,
                "maximum_amount": stored.maximum_amount,
                "adapter": stored.adapter,
                "claim_token": claim_token,
            }
            if canonical_digest(expected) != request_digest:
                raise ConfigurationError("payment reservation idempotency conflict")

        self._mark_v2_operation_executing("reserve", idempotency_key, claim)
        adapter_reservation = (
            _reservation_with_state(
                stored, PaymentReservationState.RESERVED, at=self._clock()
            )
            if stored.state is PaymentReservationState.INDETERMINATE
            else stored
        )
        try:
            reserved = await adapter.reserve(reservation=adapter_reservation)
            if reserved != adapter_reservation:
                raise ConfigurationError("payment adapter changed the reservation")
            if stored.state is PaymentReservationState.INDETERMINATE:
                reserved = self.store.transition_payment_reservation_v2(
                    stored.reservation_id,
                    expected_state=PaymentReservationState.INDETERMINATE,
                    updated=_reservation_with_state(
                        stored, PaymentReservationState.RESERVED, at=self._clock()
                    ),
                )
            else:
                reserved = stored
            self._complete_v2_operation("reserve", idempotency_key, reserved)
            return reserved
        except Exception:
            self._mark_reservation_indeterminate(
                stored,
                expected_state=stored.state,
                reason="payment reservation adapter failed",
            )
            self._mark_v2_operation_indeterminate("reserve", idempotency_key)
            raise

    def _load_completed_settlement(
        self,
        claim: dict[str, object],
    ) -> SettlementReceipt:
        settlement_id = self._result_id(claim, SettlementReceipt.__name__)
        receipt = self.store.get_settlement_receipt(settlement_id)
        if receipt is None:
            raise ConfigurationError("stored settlement receipt is missing")
        return receipt

    async def settle_v2(
        self,
        reservation_id: str,
        *,
        actual_amount: CurrencyAmount,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        adapter = self._require_v2_adapter()
        reservation = self.store.get_payment_reservation_v2(reservation_id)
        if reservation is None:
            raise ConfigurationError("payment reservation is unavailable")
        _validate_settlement_request(reservation, actual_amount, evidence)
        request_digest = canonical_digest(
            {
                "reservation": _reservation_identity_payload(reservation),
                "actual_amount": actual_amount,
                "evidence": evidence,
            }
        )
        claim = self._claim_v2_operation("settle", idempotency_key, request_digest)
        if claim is not None and claim.get("state") == "complete":
            return self._load_completed_settlement(claim)

        settlement_id = _stable_operation_id("settlement", idempotency_key)
        existing = self.store.get_settlement_receipt(settlement_id)
        if existing is not None:
            self._complete_v2_operation("settle", idempotency_key, existing)
            return existing
        prepared = self.store.get_prepared_decision(reservation.prepared_id)
        if prepared is None or prepared.state is not PreparedDecisionState.SETTLING:
            raise ConfigurationError("prepared decision is not ready for settlement")
        reservation = self.store.claim_payment_settlement_v2(
            reservation_id,
            idempotency_key=idempotency_key,
            updated_at=self._clock(),
        )
        self._mark_v2_operation_executing("settle", idempotency_key, claim)
        try:
            receipt = await adapter.settle(
                reservation=reservation,
                actual_amount=actual_amount,
                evidence=evidence,
                idempotency_key=idempotency_key,
            )
            if receipt.settlement_id != settlement_id:
                raise ConfigurationError("payment adapter returned an unexpected settlement ID")
            if (
                receipt.reservation_id != reservation.reservation_id
                or receipt.charge_id != reservation.charge_id
                or receipt.prepared_id != reservation.prepared_id
                or receipt.quote_id != reservation.quote_id
                or receipt.authorization_kind != reservation.authorization_kind
                or receipt.authorization_id != reservation.authorization_id
                or receipt.attempt_id != reservation.attempt_id
                or receipt.reserved_amount != reservation.maximum_amount
                or receipt.captured_amount != actual_amount
                or receipt.released_amount.amount
                != reservation.maximum_amount.amount - actual_amount.amount
                or receipt.payment_rail != adapter.name
                or receipt.status
                not in {SettlementStatus.COMPLETED, SettlementStatus.SETTLED}
            ):
                raise ConfigurationError("payment adapter returned an invalid settlement")
            receipt = self.store.store_settlement_and_transition(receipt)
            self._complete_v2_operation("settle", idempotency_key, receipt)
            return receipt
        except Exception:
            self._mark_reservation_indeterminate(
                reservation,
                expected_state=PaymentReservationState.SETTLING,
                reason="payment settlement adapter failed",
            )
            self._mark_v2_operation_indeterminate("settle", idempotency_key)
            raise

    async def capture_v2(
        self,
        reservation_id: str,
        *,
        evidence: SettlementEvidence,
        idempotency_key: str,
    ) -> SettlementReceipt:
        reservation = self.store.get_payment_reservation_v2(reservation_id)
        if reservation is None:
            raise ConfigurationError("payment reservation is unavailable")
        return await self.settle_v2(
            reservation_id,
            actual_amount=reservation.maximum_amount,
            evidence=evidence,
            idempotency_key=idempotency_key,
        )

    async def release_v2(
        self,
        reservation_id: str,
        *,
        reason: str,
        idempotency_key: str,
    ) -> SettlementReceipt:
        if not reason:
            raise ConfigurationError("payment release requires a reason")
        adapter = self._require_v2_adapter()
        reservation = self.store.get_payment_reservation_v2(reservation_id)
        if reservation is None:
            raise ConfigurationError("payment reservation is unavailable")
        request_digest = canonical_digest(
            {
                "reservation": _reservation_identity_payload(reservation),
                "reason": reason,
            }
        )
        claim = self._claim_v2_operation("release", idempotency_key, request_digest)
        if claim is not None and claim.get("state") == "complete":
            return self._load_completed_settlement(claim)
        settlement_id = _stable_operation_id("release", idempotency_key)
        existing = self.store.get_settlement_receipt(settlement_id)
        if existing is not None:
            self._complete_v2_operation("release", idempotency_key, existing)
            return existing
        prepared = self.store.get_prepared_decision(reservation.prepared_id)
        if prepared is None or prepared.state is not PreparedDecisionState.RESERVED:
            raise ConfigurationError("prepared decision is not releasable")
        reservation = self.store.claim_payment_release_v2(
            reservation_id,
            idempotency_key=idempotency_key,
            updated_at=self._clock(),
        )
        self._mark_v2_operation_executing("release", idempotency_key, claim)
        try:
            receipt = await adapter.release(
                reservation=reservation,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            if (
                receipt.settlement_id != settlement_id
                or receipt.reservation_id != reservation.reservation_id
                or receipt.captured_amount.amount != 0
                or receipt.released_amount != reservation.maximum_amount
                or receipt.charge_id != reservation.charge_id
                or receipt.prepared_id != reservation.prepared_id
                or receipt.quote_id != reservation.quote_id
                or receipt.authorization_kind != reservation.authorization_kind
                or receipt.authorization_id != reservation.authorization_id
                or receipt.attempt_id != reservation.attempt_id
                or receipt.payment_rail != adapter.name
                or receipt.status is not SettlementStatus.RELEASED
            ):
                raise ConfigurationError("payment adapter returned an invalid release")
            receipt = self.store.store_settlement_and_transition(receipt)
            self._complete_v2_operation("release", idempotency_key, receipt)
            return receipt
        except Exception:
            self._mark_reservation_indeterminate(
                reservation,
                expected_state=PaymentReservationState.SETTLING,
                reason="payment release adapter failed",
            )
            self._mark_v2_operation_indeterminate("release", idempotency_key)
            raise

    async def refund_v2(
        self,
        settlement_id: str,
        *,
        amount: CurrencyAmount,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceiptV2:
        if not reason:
            raise ConfigurationError("payment refund requires a reason")
        adapter = self._require_v2_adapter()
        settlement = self.store.get_settlement_receipt(settlement_id)
        if settlement is None:
            raise ConfigurationError("payment settlement is unavailable")
        if settlement.payment_rail != adapter.name:
            raise ConfigurationError("refund adapter does not match the settlement rail")
        if amount.currency != settlement.captured_amount.currency:
            raise ConfigurationError("refund currency does not match settlement")
        request_digest = canonical_digest(
            {"settlement": settlement, "amount": amount, "reason": reason}
        )
        claim = self._claim_v2_operation("refund", idempotency_key, request_digest)
        if claim is not None and claim.get("state") == "complete":
            refund_id = self._result_id(claim, RefundReceiptV2.__name__)
            existing = self.store.get_refund_receipt_v2(refund_id)
            if existing is None:
                raise ConfigurationError("stored refund receipt is missing")
            return existing
        refund_id = _stable_operation_id("refund", idempotency_key)
        existing = self.store.get_refund_receipt_v2(refund_id)
        if existing is not None:
            self._complete_v2_operation("refund", idempotency_key, existing)
            return existing
        self.store.authorize_refund_v2(
            refund_id=refund_id,
            settlement_id=settlement_id,
            amount=amount,
            idempotency_key=idempotency_key,
            request_digest=request_digest,
            authorized_at=self._clock(),
        )
        self._mark_v2_operation_executing("refund", idempotency_key, claim)
        try:
            receipt = await adapter.refund(
                settlement=settlement,
                amount=amount,
                reason=reason,
                idempotency_key=idempotency_key,
            )
            if receipt.refund_id != refund_id:
                raise ConfigurationError("payment adapter returned an unexpected refund ID")
            if (
                receipt.settlement_id != settlement.settlement_id
                or receipt.charge_id != settlement.charge_id
                or receipt.amount != amount
                or receipt.reason != reason
                or receipt.idempotency_key != idempotency_key
            ):
                raise ConfigurationError("payment adapter returned an invalid refund")
            receipt = self.store.complete_refund_v2(receipt)
            self._complete_v2_operation("refund", idempotency_key, receipt)
            return receipt
        except Exception:
            authorization = self.store.get_refund_authorization_v2(refund_id)
            if authorization is not None and authorization["state"] != "COMPLETED":
                self.store.mark_refund_authorization_indeterminate(
                    refund_id,
                    updated_at=self._clock(),
                )
            self._mark_v2_operation_indeterminate("refund", idempotency_key)
            raise

    async def reconcile_v2(
        self,
        reference: str,
        *,
        idempotency_key: str | None = None,
    ) -> BillingReconciliation:
        adapter = self._require_v2_adapter()
        key = idempotency_key or reference
        request_digest = canonical_digest({"reference": reference})
        claim = self._claim_v2_operation("reconcile", key, request_digest)
        if claim is not None and claim.get("state") == "complete":
            reconciliation_id = self._result_id(claim, BillingReconciliation.__name__)
            existing = self.store.get_billing_reconciliation(reconciliation_id)
            if existing is None:
                raise ConfigurationError("stored billing reconciliation is missing")
            return existing
        self._mark_v2_operation_executing("reconcile", key, claim)
        try:
            reconciliation = await adapter.reconcile(reference)
            settlement = self.store.get_settlement_receipt(reconciliation.settlement_id)
            if settlement is None:
                raise ConfigurationError("billing reconciliation settlement is unavailable")
            if settlement.payment_rail != adapter.name:
                raise ConfigurationError(
                    "billing reconciliation adapter does not match settlement rail"
                )
            if reconciliation.expected_amount != settlement.captured_amount:
                raise ConfigurationError(
                    "billing reconciliation expected amount does not match settlement"
                )
            if not (
                reconciliation.invoice_reference
                or reconciliation.billing_record_reference
                or reconciliation.evidence_digest
            ):
                raise ConfigurationError(
                    "billing reconciliation requires independent billing evidence"
                )
            reconciliation = self.store.save_billing_reconciliation(reconciliation)
            self._complete_v2_operation("reconcile", key, reconciliation)
            return reconciliation
        except Exception:
            self._mark_v2_operation_indeterminate("reconcile", key)
            raise
