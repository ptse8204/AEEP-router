"""Payment-rail-neutral reservations, captures, refunds, and local budget gates."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from .errors import ApprovalRequired, ConfigurationError
from .models import (
    AgentBudget,
    LedgerEvent,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    PaymentState,
    Quote,
    SideEffect,
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

    def __init__(self, balance_usd: float) -> None:
        self.balance = Decimal(str(balance_usd))
        self.reserved: dict[str, Decimal] = {}

    async def reserve(self, quote: Quote, action_id: str) -> PaymentReservation:
        amount = Decimal(str(quote.monetary_usd))
        available = self.balance - sum(self.reserved.values(), Decimal("0"))
        if amount > available:
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
        amount = self.reserved.pop(
            reservation.reservation_id, Decimal(str(reservation.amount_usd))
        )
        if amount > self.balance:
            raise ConfigurationError("insufficient prepaid balance")
        self.balance -= amount
        return PaymentCapture(
            reservation_id=reservation.reservation_id,
            amount_usd=float(amount),
        )

    async def refund(self, capture: PaymentCapture, amount_usd: float) -> PaymentRefund:
        amount = Decimal(str(amount_usd))
        if amount > Decimal(str(capture.amount_usd)):
            raise ConfigurationError("refund exceeds captured amount")
        self.balance += amount
        return PaymentRefund(capture_id=capture.capture_id, amount_usd=float(amount))


class InvoicePaymentAdapter(PrepaidBalanceAdapter):
    name = "invoice"

    def __init__(self) -> None:
        super().__init__(float("inf"))


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


class BudgetManager:
    def __init__(
        self,
        budget: AgentBudget,
        store: ReceiptStore,
        adapter: PaymentAdapter,
    ) -> None:
        self.budget = budget
        self.store = store
        self.adapter = adapter

    def _spent_today(self) -> float:
        today = datetime.now(UTC).date()
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
            if event.event_type == "reserve"
            and event.reference_id not in captured_reservations
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
