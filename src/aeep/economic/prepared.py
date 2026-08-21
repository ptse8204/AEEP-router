"""Deterministic helpers for request-bound prepared routing.

This module deliberately contains no network or persistence code.  The router
uses these helpers before calling an injected quote provider, keeping the
ordinary :meth:`aeep.router.Router.route` path entirely offline.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from ..errors import ConfigurationError
from ..models import (
    ActionRequest,
    BoundedQuote,
    CapabilityOffer,
    ExecutorSpec,
    PolicyConfig,
    PreparedRouteDecision,
    QuoteFailurePolicy,
    RateCardSnapshot,
    RouteDecision,
    RouteEstimate,
)
from ..qualification import behavior_fingerprint
from .canonical import canonical_action_digest
from .disclosure import QuoteDisclosurePolicy

_VERSIONED_CAPABILITY = re.compile(r"^[a-z0-9][a-z0-9_.-]*@[0-9]+(?:\.[0-9]+){0,2}$")


def deterministic_digest(value: Any) -> str:
    """Return a tagged SHA-256 digest of normalized, finite JSON-compatible data."""

    if not isinstance(value, Mapping):
        raise ConfigurationError("prepared digests require an object payload")
    try:
        return canonical_action_digest(value)
    except (TypeError, ValueError) as exc:
        raise ConfigurationError(str(exc)) from exc


def action_digest(request: ActionRequest) -> str:
    """Bind a quote to the bounded action without including raw data in storage."""

    if _VERSIONED_CAPABILITY.fullmatch(request.capability) is None:
        raise ConfigurationError("prepared routing requires an exact versioned capability")
    return deterministic_digest(
        {
            "capability": request.capability,
            "input": request.input,
            "constraints": request.constraints,
            "context": {
                "data_sensitivity": request.context.data_sensitivity,
                "state_locality": request.context.state_locality,
                "preferred_region": request.context.preferred_region,
                "labels": request.context.labels,
            },
            "idempotency_key": request.idempotency_key,
        }
    )


def policy_digest(policy: PolicyConfig) -> str:
    """Digest the fully merged effective policy used for the prepared decision."""

    return deterministic_digest(policy.model_dump(mode="python"))


def executor_fingerprint(spec: ExecutorSpec) -> str:
    """Return the exact qualified behavior fingerprint in protocol form."""

    return f"sha256:{behavior_fingerprint(spec)}"


def route_economic_config(spec: ExecutorSpec) -> Mapping[str, Any]:
    value = spec.config.get("economic", {})
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise ConfigurationError(f"executor {spec.id!r} economic config must be an object")
    return value


def route_explicitly_requires_quote(spec: ExecutorSpec) -> bool:
    """Return whether operator-authored config explicitly marks dynamic pricing."""

    config = route_economic_config(spec)
    return (
        any(
            config.get(name) is True
            for name in (
                "dynamic_pricing",
                "live_quote",
                "quote_required",
                "requires_binding_quote",
                "requires_live_quote",
                "paid_marketplace",
            )
        )
        or config.get("pricing") == "dynamic"
    )


def route_requires_live_quote(
    spec: ExecutorSpec,
    estimate: RouteEstimate,
    *,
    require_binding_quote_for_paid_routes: bool,
) -> bool:
    """Identify dynamic or paid provider routes; local confirmed-free routes stay offline."""

    explicitly_dynamic = route_explicitly_requires_quote(spec)
    expected = estimate.cash.amount_usd
    maximum = estimate.cash.upper_bound_usd
    known_paid = (expected is not None and expected > 0) or (maximum is not None and maximum > 0)
    confirmed_free = (
        expected == 0 and maximum == 0 and estimate.cash.evidence.status.value != "unavailable"
    )
    return explicitly_dynamic or (
        require_binding_quote_for_paid_routes
        and spec.provider_id is not None
        and (known_paid or not confirmed_free)
    )


def route_is_operator_confirmed_free(spec: ExecutorSpec, estimate: RouteEstimate) -> bool:
    """Recognize only local, operator-configured zero incremental provider cash."""

    return (
        spec.provider_id is None
        and estimate.cash.amount_usd == 0
        and estimate.cash.upper_bound_usd == 0
        and estimate.cash.evidence.status.value != "unavailable"
    )


def disclosure_policy(spec: ExecutorSpec) -> QuoteDisclosurePolicy:
    """Parse only the operator-authored route disclosure declaration."""

    config = route_economic_config(spec)
    raw = config.get("quote_disclosure")
    if raw is None:
        return QuoteDisclosurePolicy()
    if isinstance(raw, list | tuple):
        raw = {"fields": raw}
    if not isinstance(raw, Mapping):
        raise ConfigurationError(
            f"executor {spec.id!r} quote disclosure must be an object or field list"
        )
    return QuoteDisclosurePolicy.model_validate(dict(raw))


def resolve_failure_policy(
    configured: QuoteFailurePolicy,
    requested: QuoteFailurePolicy | None,
) -> QuoteFailurePolicy:
    """Allow a caller to tighten, but never weaken, operator quote requirements."""

    if requested is None or requested is configured:
        return configured
    strength = {
        QuoteFailurePolicy.ALLOW_STATIC_PRIOR: 1,
        QuoteFailurePolicy.ALLOW_VERIFIED_OFFER: 2,
        QuoteFailurePolicy.REQUIRE_BINDING_QUOTE: 3,
        QuoteFailurePolicy.TREAT_AS_UNAVAILABLE: 3,
    }
    if strength[requested] < strength[configured]:
        raise ConfigurationError("request quote policy cannot weaken operator policy")
    return requested


@dataclass(frozen=True, slots=True)
class PreparedExecutionContext:
    """Process-local payload required by the later payment/execution phase."""

    prepared: PreparedRouteDecision
    request: ActionRequest
    route_decision: RouteDecision
    selected_quote: BoundedQuote | None
    selected_offer: CapabilityOffer | None = None
    selected_rate_card: RateCardSnapshot | None = None
