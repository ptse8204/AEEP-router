"""Economic action router.

The router deliberately separates *feasibility* from *preference*:

1. Validate action input against each executor contract.
2. Reject routes that violate safety, budget, privacy, or capacity constraints.
3. Rank only feasible routes with an explainable multi-objective policy.
4. Execute with conservative fallback semantics and persist receipts.
5. Blend future estimates with observed outcomes.

This makes AEEP useful as both a read-only profiler/recommender and an active
execution control plane.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import re
import secrets
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from threading import RLock
from typing import Any, Literal

from .accounting import (
    aggregate_accounting,
    cash_accounting_for_reporting,
    cash_accounting_from_settlement,
    cash_accounting_from_usage_statement,
    cash_estimate_from_offer,
    cash_estimate_from_quote,
    mirror_actual_cash,
)
from .artifact_store import ContentArtifactStore
from .attempts import AttemptService, ExecutionAttempt, ExecutionAttemptState
from .cache_affinity import estimate_cache_affinity
from .capacity import CapacityObservation, CapacityWindow, observation_quota
from .config import load_manifest
from .discovery import CompositeProviderRegistry
from .economic.aggregates import MarketAggregateSelector
from .economic.canonical import canonical_digest, canonical_payload
from .economic.disclosure import QuoteDisclosureError, disclose_quote_features
from .economic.prepared import (
    PreparedExecutionContext,
    action_digest,
    deterministic_digest,
    disclosure_policy,
    executor_fingerprint,
    resolve_failure_policy,
    route_explicitly_requires_quote,
    route_is_operator_confirmed_free,
    route_requires_live_quote,
)
from .economic.quotes import (
    CompositeQuoteProvider,
    QuoteCandidate,
    QuoteErrorCode,
    QuoteProvider,
    RemoteQuoteProvider,
    RemoteQuoteProviderConfig,
    acquire_top_k_quotes,
)
from .economic.trust import (
    TrustStore,
    TrustStoreVerifier,
    merge_trusted_provider_keys,
)
from .economics import HMACSigner, QuoteService
from .errors import (
    ApprovalRequired,
    ConfigurationError,
    NoRouteError,
)
from .estimator import HistoricalEstimator, action_features, evidence_cohort_digest
from .executors import (
    CommandExecutor,
    DelegateExecutor,
    HostExecutor,
    HTTPExecutor,
    ManagedHostExecutor,
    MCPExecutor,
    PythonExecutor,
)
from .executors.base import BaseExecutor, ExecutionContext
from .hosts import CodexAppServerAdapter, ManagedHostAdapter, ManagedHostRegistry
from .models import (
    ActionApprovalRecord,
    ActionConstraints,
    ActionContext,
    ActionRequest,
    ApprovalSource,
    AuthorizationKind,
    BenchmarkEntry,
    BenchmarkResult,
    BillingTrigger,
    BoundedQuote,
    CacheAffinityEstimate,
    CacheAffinityObservation,
    CacheAffinityReceipt,
    CandidateRanking,
    CandidateScore,
    CapabilityOffer,
    CashAccounting,
    CashClassification,
    CashEstimate,
    CashEvidence,
    CompactAlternative,
    CompactExecutionOutcome,
    CompactReceipt,
    CompactRouteDecision,
    CounterfactualAlternative,
    CounterfactualReport,
    CurrencyAmount,
    EconomicEvidenceLevel,
    EconomicEvidenceLink,
    EconomicMetrics,
    EstimateSource,
    EvidenceSource,
    EvidenceStatus,
    ExecutionOutcome,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ExternalOutcomeReport,
    Manifest,
    MeasurementEvidence,
    Observation,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    PaymentReservationState,
    PaymentReservationV2,
    PinnedRateCardAuthorizationConfig,
    PolicyConfig,
    PolicyValuation,
    PreparedDecisionState,
    PreparedRouteDecision,
    PreparedRouteTransition,
    PricingDispute,
    ProviderDescriptor,
    ProviderExecutionStatus,
    ProviderReputation,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    QuoteFailure,
    QuoteFailurePolicy,
    QuoteRequest,
    QuoteRequestV2,
    RateCardSnapshot,
    RejectedCandidate,
    ResourceAccounting,
    ResourceVector,
    RouteBypassReason,
    RouteDecision,
    RouteDisposition,
    RouteEstimate,
    SettlementEvidence,
    SettlementReceipt,
    SideEffect,
    SignedExecutionReceipt,
    SubscriptionQuota,
    SubscriptionResource,
    TrustLevel,
    UsageStatement,
    ValidationKind,
    ValidationResult,
    new_id,
    utc_now,
)
from .payments import (
    BudgetManager,
    FreePaymentAdapterV2,
    InvoicePaymentAdapterV2,
    PaymentAdapter,
    PaymentAdapterV2,
    PrepaidBalanceAdapter,
    PrepaidBalanceAdapterV2,
    billable_amount_for_execution,
    billable_amount_for_terms,
)
from .policy import builtin_policies, merge_constraints, policy_with_constraints, resolve_policy
from .provider_ingest import ProviderPackageIngestor
from .provider_package import (
    ArtifactStatus,
    EvidenceAcceptanceStatus,
    FingerprintStatus,
    PackageIntegrityStatus,
    SmokeStatus,
    SmokeTestReport,
    portable_route_fingerprint,
    runtime_route_identity_matches,
)
from .qualification import (
    QualificationCase,
    QualificationCondition,
    QualificationReport,
    RouteCandidate,
    RouteLifecycle,
    behavior_fingerprint,
    require_static_qualification,
)
from .registry import Registry, validate_json
from .runtime import detect_compute_availability
from .scoring import policy_valuation_amount, score_candidate
from .store import ReceiptStore
from .telemetry import start_span, trace_id_from_span
from .validators import ValidationContext, ValidatorCallback, run_validators
from .workflow import (
    WorkflowExecutionOutcome,
    WorkflowRequest,
    WorkflowStatus,
    pointer_get,
    pointer_replace,
    schema_pointer_exists,
)

_EXECUTOR_TYPES: dict[ExecutorKind, type[BaseExecutor]] = {
    ExecutorKind.COMMAND: CommandExecutor,
    ExecutorKind.PYTHON: PythonExecutor,
    ExecutorKind.HTTP: HTTPExecutor,
    ExecutorKind.MCP: MCPExecutor,
    ExecutorKind.HOST: HostExecutor,
    ExecutorKind.DELEGATE: DelegateExecutor,
}


def _provider_artifact_root(value: str, manifest_path: Path | None) -> Path:
    root = Path(value).expanduser()
    if not root.is_absolute() and manifest_path is not None:
        root = manifest_path.parent / root
    return root


class Router:
    """Route and execute agent actions using a manifest-backed registry.

    A Router is safe to reuse for many actions. Reuse is recommended because MCP
    clients and historical estimates are cached. Call :meth:`close` when done.
    """

    def __init__(
        self,
        manifest: Manifest,
        *,
        manifest_path: str | Path | None = None,
        store: ReceiptStore | None = None,
        validator_callbacks: Mapping[str, ValidatorCallback] | None = None,
        signer: HMACSigner | None = None,
        payment_adapter: PaymentAdapter | None = None,
        payment_adapter_v2: PaymentAdapterV2 | None = None,
        quote_provider: QuoteProvider | None = None,
        economic_verifier: TrustStoreVerifier | None = None,
        market_aggregate_selector: MarketAggregateSelector | None = None,
        clock: Callable[[], datetime] | None = None,
        unlimited_economic_budget: bool | None = None,
        executor_overrides: Mapping[ExecutorKind, BaseExecutor] | None = None,
        managed_host_adapters: Mapping[str, ManagedHostAdapter] | None = None,
    ) -> None:
        normalized = manifest.model_copy(deep=True)
        policies = builtin_policies()
        policies.update(normalized.policies)
        normalized.policies = policies
        if normalized.default_policy not in normalized.policies:
            raise ConfigurationError(f"default policy {normalized.default_policy!r} is not defined")
        self.manifest = normalized
        configured_unlimited = normalized.economic_evidence.payment.unlimited_budget
        if unlimited_economic_budget is True and not configured_unlimited:
            raise ConfigurationError(
                "unlimited economic budget cannot exceed the manifest payment policy"
            )
        effective_unlimited_budget = (
            configured_unlimited
            if unlimited_economic_budget is None
            else configured_unlimited and unlimited_economic_budget
        )
        self.manifest_path = Path(manifest_path).resolve() if manifest_path else None
        self._route_activation_lock = RLock()
        self.registry = Registry(normalized.executors)
        self.resources = {resource.id: resource for resource in normalized.resources}
        self.provider_registry = CompositeProviderRegistry(normalized.registries)
        self.providers: dict[str, ProviderDescriptor] = {}
        self.store = store or ReceiptStore(normalized.database)
        self.attempts = AttemptService(self.store)
        self._worker_id = f"router-{secrets.token_hex(12)}"
        for candidate in self.store.list_route_candidates():
            if candidate.status == RouteLifecycle.ACTIVE:
                report = self.store.get_qualification_report(
                    candidate.qualification_report_id or ""
                )
                qualification_is_current = (
                    report is not None
                    and report.passed
                    and report.candidate_id == candidate.candidate_id
                    and report.behavior_fingerprint == candidate.behavior_fingerprint
                )
                if (
                    candidate.behavior_fingerprint != behavior_fingerprint(candidate.spec)
                    or not qualification_is_current
                ):
                    candidate.status = RouteLifecycle.SUSPENDED
                    candidate.spec.enabled = False
                    candidate.reason = (
                        "stored active route lacks matching passed qualification evidence"
                    )
                    self.store.save_route_candidate(candidate)
                elif self.registry.contains(candidate.executor_id):
                    raise ConfigurationError(
                        f"active candidate {candidate.executor_id!r} collides with a manifest route"
                    )
                else:
                    self.registry.register(candidate.spec)
        self.estimator = HistoricalEstimator(self.store)
        self.validator_callbacks = dict(validator_callbacks or {})
        self.quote_service = QuoteService(self.registry, signer=signer)
        self._economic_clock = clock or utc_now
        self._owned_quote_clients: list[RemoteQuoteProvider] = []
        trust_path: Path | None = None
        configured_keys = (
            economic_verifier.store.list_keys() if economic_verifier is not None else []
        )
        if economic_verifier is None:
            configured_path = Path(normalized.economic_evidence.trust_store.path).expanduser()
            if configured_path.is_file():
                trust_path = configured_path
                try:
                    configured_keys = TrustStore.load(configured_path).list_keys()
                except (OSError, ValueError) as exc:
                    raise ConfigurationError(
                        "operator trust store is not readable or valid"
                    ) from exc
        if (
            normalized.economic_evidence.live_quotes.enabled
            or normalized.economic_evidence.market_aggregates.enabled
        ):
            if economic_verifier is not None:
                configured_keys = economic_verifier.store.list_keys()
            try:
                merged_trust = merge_trusted_provider_keys(
                    configured_keys,
                    self.store.list_provider_signing_keys(),
                )
            except ValueError as exc:
                raise ConfigurationError(str(exc)) from exc
            if not merged_trust.list_keys():
                raise ConfigurationError("enabled live quotes require an operator-trusted key")
            economic_verifier = TrustStoreVerifier(
                merged_trust,
                clock=self._economic_clock,
            )
            for trusted_key in merged_trust.list_keys():
                if self.store.get_provider_signing_key(
                    trusted_key.provider_id, trusted_key.key_id
                ) is None:
                    self.store.save_provider_signing_key(trusted_key)
            if quote_provider is None and normalized.economic_evidence.live_quotes.enabled:
                quote_provider, owned_clients = self._configured_quote_provider(
                    normalized,
                    economic_verifier,
                )
                self._owned_quote_clients.extend(owned_clients)
        self.prepared_quote_provider = quote_provider
        self.economic_verifier = economic_verifier
        self.market_aggregate_selector = market_aggregate_selector
        if (
            self.market_aggregate_selector is None
            and normalized.economic_evidence.market_aggregates.enabled
        ):
            if economic_verifier is None:
                raise ConfigurationError(
                    "enabled market aggregates require an operator trust-store verifier"
                )
            self.market_aggregate_selector = MarketAggregateSelector(
                self.store,
                economic_verifier,
                config=normalized.economic_evidence.market_aggregates,
                settlement_currency=normalized.economic_evidence.settlement_currency,
                clock=self._economic_clock,
            )
        self._configured_economic_keys = list(configured_keys)
        self._economic_trust_path = trust_path
        self.signer = signer
        if payment_adapter_v2 is not None and normalized.budget is None:
            raise ConfigurationError("a V2 payment adapter requires an explicit agent budget")
        configured_v2 = payment_adapter_v2
        if normalized.budget is not None and configured_v2 is None:
            adapter_name = normalized.economic_evidence.payment.adapter
            if adapter_name == "free":
                configured_v2 = FreePaymentAdapterV2(
                    settlement_currency=normalized.economic_evidence.settlement_currency,
                    clock=self._economic_clock,
                )
            elif adapter_name == "prepaid":
                configured_v2 = PrepaidBalanceAdapterV2(
                    CurrencyAmount(
                        amount=Decimal(str(normalized.budget.prepaid_balance_usd)),
                        currency=normalized.economic_evidence.settlement_currency,
                    ),
                    clock=self._economic_clock,
                )
            elif adapter_name == "invoice":
                if not effective_unlimited_budget:
                    raise ConfigurationError(
                        "invoice payments require explicit unlimited_economic_budget"
                    )
                configured_v2 = InvoicePaymentAdapterV2(
                    unlimited_budget=True,
                    settlement_currency=normalized.economic_evidence.settlement_currency,
                    clock=self._economic_clock,
                )
            else:
                raise ConfigurationError(
                    f"payment adapter {adapter_name!r} must be injected explicitly"
                )
        self.budget_manager = (
            BudgetManager(
                normalized.budget,
                self.store,
                payment_adapter or PrepaidBalanceAdapter(normalized.budget.prepaid_balance_usd),
                adapter_v2=configured_v2,
                settlement_currency=normalized.economic_evidence.settlement_currency,
                unlimited_budget=effective_unlimited_budget,
                clock=self._economic_clock,
            )
            if normalized.budget is not None
            else None
        )
        self._executors: dict[ExecutorKind, BaseExecutor] = dict(executor_overrides or {})
        self.managed_hosts = ManagedHostRegistry()
        configured_hosts = dict(managed_host_adapters or {})
        codex_specs = [
            spec
            for spec in normalized.executors
            if spec.kind is ExecutorKind.MANAGED_HOST
            and spec.managed_host_config().adapter_id == CodexAppServerAdapter.adapter_id
        ]
        if codex_specs and CodexAppServerAdapter.adapter_id not in configured_hosts:
            bindings = {
                (spec.resource_pool, spec.managed_host_config().argv) for spec in codex_specs
            }
            if len(bindings) != 1:
                raise ConfigurationError(
                    "Codex App Server routes must share one argv and resource binding"
                )
            configured_hosts[CodexAppServerAdapter.adapter_id] = (
                CodexAppServerAdapter.from_executor(
                    codex_specs[0],
                    principal_salt=secrets.token_bytes(32),
                    manifest_directory=(self.manifest_path.parent if self.manifest_path else None),
                )
            )
        for adapter_id in sorted(configured_hosts):
            self.managed_hosts.register(adapter_id, configured_hosts[adapter_id])
        if ExecutorKind.MANAGED_HOST in self._executors and configured_hosts:
            raise ConfigurationError(
                "managed-host executor override cannot be combined with adapter registrations"
            )
        self._executors.setdefault(
            ExecutorKind.MANAGED_HOST, ManagedHostExecutor(self.managed_hosts)
        )
        self._validated_decisions: dict[str, str] = {}
        self._prepared_contexts: dict[str, PreparedExecutionContext] = {}
        self._closed = False

    def _configured_quote_provider(
        self,
        manifest: Manifest,
        verifier: TrustStoreVerifier,
    ) -> tuple[QuoteProvider, list[RemoteQuoteProvider]]:
        """Build clients only from explicit route config and global operator policy."""

        economic = manifest.economic_evidence
        if economic.network.allow_redirects:
            raise ConfigurationError("economic quote redirects are not supported")
        if economic.network.trust_environment_proxy:
            raise ConfigurationError("economic quote clients never use ambient proxy settings")
        sources: dict[str, QuoteProvider] = {}
        clients: list[RemoteQuoteProvider] = []
        provider_configs: dict[
            str,
            tuple[str, str | None, str | None, dict[str, Any]],
        ] = {}
        for spec in manifest.executors:
            route_config = spec.config.get("economic")
            if route_config is None:
                continue
            if not isinstance(route_config, Mapping):
                raise ConfigurationError(f"executor {spec.id!r} economic config must be an object")
            endpoint = route_config.get("quote_endpoint")
            if endpoint is None:
                continue
            if not isinstance(endpoint, str) or not endpoint:
                raise ConfigurationError(
                    f"executor {spec.id!r} quote_endpoint must be an absolute URL"
                )
            if spec.provider_id is None:
                raise ConfigurationError(
                    f"executor {spec.id!r} needs provider_id for remote quotes"
                )
            if any(
                name in route_config
                for name in ("auth_token", "authorization", "bearer_token", "token")
            ):
                raise ConfigurationError(
                    f"executor {spec.id!r} must reference quote credentials by environment name"
                )
            auth_token_env = route_config.get("auth_token_env")
            if auth_token_env is not None and (
                not isinstance(auth_token_env, str)
                or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", auth_token_env) is None
            ):
                raise ConfigurationError(
                    f"executor {spec.id!r} auth_token_env must be an environment identifier"
                )
            offers_endpoint = route_config.get("offers_endpoint")
            if offers_endpoint is not None and not isinstance(offers_endpoint, str):
                raise ConfigurationError(
                    f"executor {spec.id!r} offers_endpoint must be an absolute URL"
                )
            existing = provider_configs.get(spec.provider_id)
            if existing is not None:
                if (
                    existing[0] != endpoint
                    or existing[1] != offers_endpoint
                    or existing[2] != auth_token_env
                ):
                    raise ConfigurationError(
                        f"provider {spec.provider_id!r} has conflicting economic endpoints"
                    )
                existing[3][spec.id] = disclosure_policy(spec)
                continue
            provider_configs[spec.provider_id] = (
                endpoint,
                offers_endpoint,
                auth_token_env,
                {spec.id: disclosure_policy(spec)},
            )

        for provider_id, (
            endpoint,
            offers_endpoint,
            auth_token_env,
            policies,
        ) in provider_configs.items():
            headers: dict[str, str] = {}
            if auth_token_env is not None:
                token = os.getenv(auth_token_env)
                if token is None or not token:
                    raise ConfigurationError(
                        f"required quote credential environment {auth_token_env!r} is not set"
                    )
                headers["Authorization"] = f"Bearer {token}"
            client = RemoteQuoteProvider(
                RemoteQuoteProviderConfig(
                    provider_id=provider_id,
                    quote_endpoint=endpoint,
                    offers_endpoint=offers_endpoint,
                    allowed_hosts=economic.network.allowed_quote_hosts,
                    allow_private_networks=economic.network.allow_private_addresses,
                    allow_insecure_http=False,
                    per_provider_timeout_seconds=(
                        economic.live_quotes.per_provider_timeout_seconds
                    ),
                    total_timeout_seconds=economic.live_quotes.total_timeout_seconds,
                    maximum_request_bytes=economic.live_quotes.maximum_response_bytes,
                    maximum_response_bytes=economic.live_quotes.maximum_response_bytes,
                    maximum_clock_skew_seconds=(economic.live_quotes.maximum_clock_skew_seconds),
                    maximum_quote_ttl_seconds=(economic.live_quotes.maximum_quote_ttl_seconds),
                ),
                verifier,
                headers=headers,
                clock=self._economic_clock,
                disclosure_policies=policies,
            )
            sources[provider_id] = client
            clients.append(client)
        if not sources:
            raise ConfigurationError(
                "live quotes are enabled but no executor has an operator-configured "
                "economic.quote_endpoint"
            )
        if len(sources) == 1:
            return next(iter(sources.values())), clients
        executor_sources = {
            executor_id: provider_id
            for provider_id, (_, _, _, policies) in provider_configs.items()
            for executor_id in policies
        }
        return CompositeQuoteProvider(
            sources,
            executor_sources=executor_sources,
        ), clients

    @classmethod
    def from_manifest(cls, path: str | Path | None = None) -> Router:
        manifest, manifest_path = load_manifest(path)
        signer = None
        if manifest.signing is not None:
            secret = os.getenv(manifest.signing.secret_env)
            if secret is None:
                raise ConfigurationError(
                    f"required signing secret environment variable "
                    f"{manifest.signing.secret_env!r} is not set"
                )
            signer = HMACSigner(secret.encode("utf-8"), key_id=manifest.signing.key_id)
        return cls(manifest, manifest_path=manifest_path, signer=signer)

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConfigurationError("router is closed")

    def _policy_for(self, request: ActionRequest) -> PolicyConfig:
        policy_name = request.policy or self.manifest.default_policy
        policy = resolve_policy(policy_name, self.manifest.policies)
        return policy_with_constraints(policy, request.constraints)

    @staticmethod
    def _fill_runtime_context(request: ActionRequest) -> ActionRequest:
        """Fill host-detectable capacity fields without overwriting caller knowledge."""

        request = request.model_copy(deep=True)
        detected = detect_compute_availability()
        compute = request.context.compute
        if compute.available_memory_mb is None:
            compute.available_memory_mb = detected.available_memory_mb
        if compute.available_cpu_fraction is None:
            compute.available_cpu_fraction = detected.available_cpu_fraction
        return request

    def _persist_decision(self, decision: RouteDecision) -> None:
        """Persist an audit copy using the manifest's privacy controls."""

        stored = decision.model_copy(deep=True)
        persistence = self.manifest.persistence
        if not persistence.store_action_inputs:
            stored.action.input = {"__aeep_redacted__": True}
        if not persistence.store_action_context:
            stored.action.context = ActionContext(
                data_sensitivity=decision.action.context.data_sensitivity,
                state_locality=decision.action.context.state_locality,
                labels={"aeep.persistence": "context-redacted"},
            )
        self.store.save_decision(stored)

    @staticmethod
    def _decision_digest(decision: RouteDecision) -> str:
        payload = decision.model_dump(mode="json")
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    @staticmethod
    def _safe_receipt_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
        allowed = {
            "adapter_id",
            "actual_model",
            "approval_evidence_digest",
            "argument_mode",
            "callable",
            "executable",
            "exit_code",
            "host",
            "ipc_bytes",
            "method",
            "prepared_id",
            "authorization_kind",
            "authorization_id",
            "quote_id",
            "attempt_id",
            "charge_id",
            "usage_statement_id",
            "settlement_id",
            "cash_evidence_level",
            "protocol_version",
            "resource_pool",
            "schema_cache_hit",
            "response_bytes",
            "response_truncated",
            "status_code",
            "stderr_bytes",
            "stderr_truncated",
            "stdout_bytes",
            "stdout_truncated",
            "tool",
            "tool_call_count",
            "model_turn_count",
            "tool_selection_rounds",
            "implementation_schema_bytes",
            "output_schema_bytes",
            "result_bytes",
            "thread_identity_digest",
            "turn_identity_digest",
            "tool_schema_tokens_estimate",
        }
        return {
            key: value
            for key, value in metadata.items()
            if key in allowed and isinstance(value, (str, int, float, bool, type(None)))
        }

    def _save_receipt(self, receipt: ExecutionReceipt) -> None:
        existing = self.store.get_receipt(receipt.receipt_id)
        if existing is not None:
            if (
                receipt.executor_fingerprint != existing.executor_fingerprint
                or receipt.cohort_digest != existing.cohort_digest
            ):
                raise ConfigurationError("persisted receipt evidence binding is immutable")
        elif self.registry.contains(receipt.executor_id):
            self._bind_receipt_evidence(self.registry.get(receipt.executor_id), receipt)
        persisted = receipt.model_copy(deep=True)
        persisted.metadata = self._safe_receipt_metadata(persisted.metadata)
        persisted.validation_results = [
            result.model_copy(
                update={
                    "detail": (
                        f"{result.kind.value} validation passed"
                        if result.valid is True
                        else f"{result.kind.value} validation failed"
                        if result.valid is False
                        else f"{result.kind.value} validation was indeterminate"
                    )
                }
            )
            for result in persisted.validation_results
        ]
        if persisted.error_type is not None or persisted.error_message is not None:
            persisted.error_type = {
                ExecutionStatus.TIMEOUT: "timeout",
                ExecutionStatus.REJECTED: "rejected",
                ExecutionStatus.FAILED: "execution_failed",
            }.get(persisted.status, "execution_error")
            persisted.error_message = persisted.error_type
        self.store.save_receipt(persisted)

    def _create_claimed_attempt(
        self,
        *,
        decision_id: str,
        prepared_id: str | None,
        action_digest_value: str,
        spec: ExecutorSpec,
        attempt_id: str | None = None,
    ) -> ExecutionAttempt:
        now = self._economic_now()
        prior = self.store.execution_attempt_for_decision(decision_id)
        if prior is not None and prior.state in {
            ExecutionAttemptState.INDETERMINATE,
            ExecutionAttemptState.DISPUTED,
        }:
            raise ConfigurationError(
                "decision has an unresolved external invocation; blind retry denied"
            )
        attempt = self.store.create_execution_attempt(
            ExecutionAttempt(
                attempt_id=attempt_id or new_id("attempt"),
                decision_id=decision_id,
                prepared_id=prepared_id,
                action_digest=action_digest_value,
                executor_id=spec.id,
                executor_fingerprint=executor_fingerprint(spec),
                side_effect=spec.side_effect,
                idempotent=spec.idempotent,
                retry_eligible=(
                    spec.idempotent and spec.side_effect.rank <= SideEffect.READ.rank
                ),
                created_at=now,
                updated_at=now,
            )
        )
        return self.store.claim_execution_attempt(
            attempt.attempt_id,
            owner_id=self._worker_id,
            claimed_at=now,
            lease_expires_at=now + timedelta(hours=1),
        )

    def _advance_attempt(
        self,
        attempt: ExecutionAttempt,
        target: ExecutionAttemptState,
        *,
        reason: str | None = None,
        **updates: Any,
    ) -> ExecutionAttempt:
        return self.store.transition_execution_attempt(
            attempt.attempt_id,
            expected_state=attempt.state,
            expected_version=attempt.version,
            target_state=target,
            updated_at=self._economic_now(),
            reason=reason,
            **updates,
        )

    @staticmethod
    def _terminal_attempt_state(
        receipt: ExecutionReceipt, *, retry_eligible: bool
    ) -> ExecutionAttemptState:
        succeeded = (
            receipt.status
            in {
                ExecutionStatus.SUCCESS,
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
            }
            and receipt.output_valid is not False
            and receipt.task_valid is not False
        )
        if succeeded:
            return ExecutionAttemptState.COMPLETED
        if receipt.status is ExecutionStatus.REJECTED:
            return ExecutionAttemptState.REJECTED
        if receipt.status in {ExecutionStatus.TIMEOUT, ExecutionStatus.UNKNOWN} and not retry_eligible:
            return ExecutionAttemptState.INDETERMINATE
        return ExecutionAttemptState.FAILED

    @staticmethod
    def _bind_receipt_evidence(spec: ExecutorSpec, receipt: ExecutionReceipt) -> None:
        fingerprint, cohort = evidence_cohort_digest(spec, receipt.action_features)
        if receipt.executor_fingerprint not in {None, fingerprint}:
            raise ConfigurationError("receipt executor fingerprint does not match runtime route")
        if receipt.cohort_digest not in {None, cohort}:
            raise ConfigurationError("receipt evidence cohort does not match runtime route")
        receipt.executor_fingerprint = fingerprint
        receipt.cohort_digest = cohort

    def _observe_receipt(self, spec: ExecutorSpec, receipt: ExecutionReceipt) -> None:
        if receipt.status in {
            ExecutionStatus.DELEGATED,
            ExecutionStatus.HOST_SELECTED,
            ExecutionStatus.UNKNOWN,
        }:
            return
        self.store.save_observation(
            Observation(
                observation_id=f"obs_{receipt.receipt_id}",
                provider_id=spec.provider_id or "local",
                executor_id=spec.id,
                capability=receipt.capability,
                executor_fingerprint=receipt.executor_fingerprint,
                cohort_digest=receipt.cohort_digest,
                receipt_id=receipt.receipt_id,
                resources=receipt.actual_resources,
                accounting=receipt.accounting,
                transport_success=receipt.transport_success,
                execution_success=receipt.execution_success,
                schema_valid=receipt.schema_valid,
                task_valid=receipt.task_valid,
                quality_score=receipt.quality_score,
                trust=TrustLevel.OBSERVED,
                observed_at=receipt.ended_at,
            )
        )

    def _subscription_quota(
        self, spec: ExecutorSpec, context: ActionContext
    ) -> SubscriptionQuota | None:
        if not spec.resource_pool:
            return None
        resource = self.resources.get(spec.resource_pool)
        if isinstance(resource, SubscriptionResource) and spec.kind is ExecutorKind.MANAGED_HOST:
            capacity = self.store.latest_capacity_observation(resource.id)
            if capacity is not None:
                return observation_quota(
                    capacity,
                    unit=resource.unit,
                    now=self._economic_now(),
                )
        override = context.subscription_quotas.get(spec.resource_pool)
        if override is not None:
            return override
        if not isinstance(resource, SubscriptionResource):
            return None
        observed = self.store.latest_quota_observation(resource.id)
        return observed.quota if observed is not None else resource.quota

    def observe_quota(
        self,
        resource_id: str,
        quota: SubscriptionQuota | dict[str, Any],
        *,
        note: str | None = None,
    ) -> QuotaObservation:
        self._ensure_open()
        if resource_id not in self.resources:
            raise ConfigurationError(f"unknown subscription resource {resource_id!r}")
        quota_model = (
            quota
            if isinstance(quota, SubscriptionQuota)
            else SubscriptionQuota.model_validate(quota)
        )
        resource = self.resources[resource_id]
        if quota_model.unit == "provider_unit":
            quota_model.unit = resource.unit
        elif quota_model.unit != resource.unit:
            raise ConfigurationError("quota unit does not match subscription resource")
        observation = QuotaObservation(
            resource_id=resource_id,
            quota=quota_model,
            note=note,
        )
        self.store.save_quota_observation(observation)
        return observation

    def subscription_status(self) -> list[dict[str, Any]]:
        self._ensure_open()
        values: list[dict[str, Any]] = []
        for resource_id in sorted(self.resources):
            resource = self.resources[resource_id]
            if not isinstance(resource, SubscriptionResource):
                continue
            observed = self.store.latest_quota_observation(resource_id)
            values.append(
                {
                    **resource.model_dump(mode="json"),
                    "quota": (observed.quota if observed else resource.quota).model_dump(
                        mode="json"
                    ),
                    "last_observed_at": observed.observed_at if observed else None,
                }
            )
        return values

    def _cache_adjusted_estimate(
        self,
        spec: ExecutorSpec,
        estimate: RouteEstimate,
        policy: PolicyConfig,
        context: ActionContext,
    ) -> tuple[RouteEstimate, CacheAffinityEstimate | None]:
        cache = context.cache_affinity
        if (
            not policy.cache_affinity.enabled
            or cache is None
            or cache.route_id != spec.id
            or cache.provider != (spec.provider_id or "local")
        ):
            return estimate, None
        config = spec.config.get("cache_affinity")
        if not isinstance(config, Mapping) or not isinstance(
            config.get("warm_resources"), Mapping
        ):
            return estimate, None
        try:
            warm = ResourceVector.model_validate(config["warm_resources"])
        except ValueError as exc:
            raise ConfigurationError(
                f"executor {spec.id!r} cache warm_resources are invalid"
            ) from exc
        latest = self.store.latest_cache_affinity_observation(
            cache.cache_scope_key_hmac,
            spec.id,
        )
        affinity = estimate_cache_affinity(
            cache,
            cold_resources=estimate.resources,
            warm_resources=warm,
            latest=latest,
            half_life_seconds=policy.cache_affinity.half_life_seconds,
            at=self._economic_now(),
        )
        adjusted = estimate.model_copy(deep=True)
        adjusted.resources = affinity.expected_resources
        adjusted.source = EstimateSource.BLENDED
        return adjusted, affinity

    def _cache_receipt(
        self,
        affinity: CacheAffinityEstimate | None,
        context: ActionContext,
        resources: ResourceVector,
    ) -> CacheAffinityReceipt | None:
        cache = context.cache_affinity
        if affinity is None or cache is None:
            return None
        total_input = resources.input_tokens
        hit_rate = (
            resources.cached_input_tokens / total_input if total_input else None
        )
        receipt = CacheAffinityReceipt(
            predicted_warm_probability=affinity.warm_probability,
            predicted_common_prefix_tokens=cache.common_prefix_tokens_estimate,
            predicted_eligible_cached_tokens=cache.eligible_cached_tokens_estimate,
            predicted_cache_read_tokens=round(
                affinity.warm_probability * cache.eligible_cached_tokens_estimate
            ),
            predicted_cache_write_tokens=round(
                (1 - affinity.warm_probability) * cache.eligible_cached_tokens_estimate
            ),
            actual_input_tokens=resources.input_tokens,
            actual_cached_input_tokens=resources.cached_input_tokens,
            actual_cache_write_tokens=resources.cache_write_input_tokens,
            actual_output_tokens=resources.output_tokens,
            actual_reasoning_output_tokens=resources.reasoning_output_tokens,
            cache_hit_rate=hit_rate,
            cache_scope_key_hmac=cache.cache_scope_key_hmac,
            stable_prefix_digest_hmac=cache.stable_prefix_digest_hmac,
            context_compaction_events=cache.compaction_generation,
            context_reset_reason=cache.context_reset_reason,
            warm_state_reused=resources.cached_input_tokens > 0,
        )
        self.store.save_cache_affinity_observation(
            CacheAffinityObservation(
                scope_key_hmac=cache.cache_scope_key_hmac,
                route_id=cache.route_id,
                stable_prefix_digest_hmac=cache.stable_prefix_digest_hmac,
                state_digest_hmac=cache.previous_state_digest_hmac,
                cache_hit=receipt.warm_state_reused,
                cached_input_tokens=resources.cached_input_tokens,
                cache_write_input_tokens=resources.cache_write_input_tokens,
                compaction_generation=cache.compaction_generation,
                observed_at=self._economic_now(),
            )
        )
        return receipt

    def route(self, request: ActionRequest | dict[str, Any]) -> RouteDecision:
        """Validate, filter, rank, explain, and persist an action decision."""

        routing_started = time.perf_counter()
        self._ensure_open()
        request_model = (
            request if isinstance(request, ActionRequest) else ActionRequest.model_validate(request)
        )
        request_model = self._fill_runtime_context(request_model)
        policy = self._policy_for(request_model)
        features = action_features(request_model.input)
        compatible, schema_errors = self.registry.compatible(
            request_model.capability, request_model.input
        )

        candidates: list[CandidateScore] = []
        for spec in compatible:
            cold_estimate = self.estimator.estimate(spec, policy, features)
            cold = score_candidate(
                spec,
                cold_estimate,
                policy,
                request_model.context,
                self._subscription_quota(spec, request_model.context),
            )
            if not cold.feasible:
                candidates.append(cold)
                continue
            estimate, affinity = self._cache_adjusted_estimate(
                spec,
                cold_estimate,
                policy,
                request_model.context,
            )
            scored = score_candidate(
                spec,
                estimate,
                policy,
                request_model.context,
                self._subscription_quota(spec, request_model.context),
            )
            scored.cache_affinity = affinity
            candidates.append(scored)

        # Preserve input-contract failures in the explanation so an agent can fix
        # its action instead of receiving a vague "no route" result.
        for executor_id, error in sorted(schema_errors.items()):
            spec = self.registry.get(executor_id)
            candidates.append(
                CandidateScore(
                    executor_id=executor_id,
                    feasible=False,
                    rejection_reasons=[error],
                    estimate=spec.estimate.model_copy(deep=True),
                    resource_pool=spec.resource_pool,
                    subscription_quota=self._subscription_quota(spec, request_model.context),
                )
            )

        feasible = [item for item in candidates if item.feasible and item.score is not None]
        feasible.sort(
            key=lambda item: (
                item.score.total if item.score is not None else float("inf"),
                item.executor_id,
            )
        )
        for rank, candidate in enumerate(feasible, start=1):
            candidate.rank = rank

        rejected = [item for item in candidates if not item.feasible]
        rejected.sort(key=lambda item: item.executor_id)
        ordered = [*feasible, *rejected]
        selected = feasible[0].executor_id if feasible else None
        disposition = RouteDisposition.SELECTED
        bypass_reason: RouteBypassReason | None = None
        baseline_executor_id: str | None = None
        expected_net_benefit: float | None = None
        abstention = policy.routing_abstention
        if feasible and abstention.enabled:
            allowed = policy.constraints.allowed_executor_ids
            configured_baseline = abstention.baseline_executor_id
            baseline = next(
                (
                    item
                    for item in feasible
                    if item.executor_id == configured_baseline
                ),
                None,
            )
            if len(feasible) == 1:
                baseline = feasible[0]
                bypass_reason = RouteBypassReason.ONLY_ONE_FEASIBLE_ROUTE
            elif allowed is not None and len(allowed) == 1:
                baseline = next(
                    (item for item in feasible if item.executor_id == allowed[0]),
                    None,
                )
                if baseline is not None:
                    bypass_reason = RouteBypassReason.PINNED_EXECUTOR
            elif baseline is not None and baseline.score is not None and feasible[0].score is not None:
                overhead_score = (
                    policy.weights.normalized()["latency"]
                    * math.log1p(
                        abstention.overhead_p95_ms / policy.references.latency_ms
                    )
                )
                expected_net_benefit = (
                    baseline.score.total - feasible[0].score.total - overhead_score
                )
                if expected_net_benefit <= abstention.minimum_score_gain:
                    bypass_reason = RouteBypassReason.OPTIMIZATION_VALUE_BELOW_OVERHEAD
            if baseline is not None:
                baseline_executor_id = baseline.executor_id
            if bypass_reason is not None and baseline is not None:
                disposition = RouteDisposition.BYPASS_ROUTER
                selected = baseline.executor_id

        if not candidates and not self.registry.find(request_model.capability):
            explanation = f"No enabled executor advertises capability {request_model.capability!r}."
        elif selected is None:
            reason_count = sum(len(item.rejection_reasons) for item in rejected)
            explanation = (
                f"No executor is feasible for {request_model.capability!r}; "
                f"{len(rejected)} candidate(s) produced {reason_count} rejection reason(s)."
            )
        else:
            winner = next(item for item in feasible if item.executor_id == selected)
            score = winner.score.total if winner.score is not None else 0.0
            if disposition is RouteDisposition.BYPASS_ROUTER:
                assert bypass_reason is not None
                explanation = (
                    f"Bypassed route optimization and retained {selected!r}: "
                    f"{bypass_reason.value.replace('_', ' ')}. Hard constraints still passed."
                )
            else:
                explanation = (
                    f"Selected {selected!r} from {len(feasible)} feasible route(s) under "
                    f"policy {policy.name!r}; lower score is better (winner {score:.6f})."
                )
            if winner.cache_affinity is not None:
                explanation += (
                    f" Cache affinity predicted {winner.cache_affinity.warm_probability:.1%} "
                    f"warm probability and {winner.cache_affinity.expected_reusable_input_tokens} "
                    "reusable input tokens."
                )

        decision = RouteDecision(
            action=request_model,
            policy=policy,
            selected_executor_id=selected,
            disposition=disposition,
            baseline_executor_id=baseline_executor_id,
            bypass_reason=bypass_reason,
            routing_overhead_ms=(time.perf_counter() - routing_started) * 1000.0,
            expected_net_benefit=expected_net_benefit,
            candidates=ordered,
            action_features=features,
            explanation=explanation,
        )
        self._persist_decision(decision)
        self._validated_decisions[decision.decision_id] = self._decision_digest(decision)
        return decision

    def _economic_now(self) -> datetime:
        value = self._economic_clock()
        if value.tzinfo is None or value.utcoffset() is None:
            raise ConfigurationError("economic clock must return a timezone-aware datetime")
        return value.astimezone(UTC)

    def _effective_policy_digest(self, policy: PolicyConfig) -> str:
        """Bind prepared execution to policy and all material economic configuration."""

        return deterministic_digest(
            {
                "policy": policy.model_dump(mode="python"),
                "economic_evidence": self.manifest.economic_evidence.model_dump(mode="python"),
            }
        )

    def _refresh_economic_verifier(self) -> TrustStoreVerifier | None:
        """Refresh current key state so an out-of-process revocation wins immediately."""

        configured_keys = self._configured_economic_keys
        if self._economic_trust_path is not None:
            try:
                configured_keys = TrustStore.load(self._economic_trust_path).list_keys()
            except (OSError, ValueError) as exc:
                raise ConfigurationError(
                    "operator economic trust store cannot be refreshed"
                ) from exc
        if not configured_keys and self.economic_verifier is None:
            return None
        try:
            merged = merge_trusted_provider_keys(
                configured_keys,
                self.store.list_provider_signing_keys(),
            )
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        for key in merged.list_keys():
            stored = self.store.get_provider_signing_key(key.provider_id, key.key_id)
            if stored is None:
                self.store.save_provider_signing_key(key)
            elif key.status.value == "revoked" and stored.status.value != "revoked":
                assert key.revoked_at is not None
                self.store.revoke_provider_signing_key(
                    key.provider_id,
                    key.key_id,
                    revoked_at=key.revoked_at,
                )
            elif key.status.value == "retired" and stored.status.value == "active":
                self.store.retire_provider_signing_key(key.provider_id, key.key_id)
        self.economic_verifier = TrustStoreVerifier(merged, clock=self._economic_clock)
        return self.economic_verifier

    def _verify_economic_record(
        self,
        record: CapabilityOffer | BoundedQuote,
        *,
        provider_id: str,
        capability: str,
        signed_at: datetime,
    ) -> str | None:
        """Return a sanitized verification failure, or ``None`` when trusted now."""

        verifier = self._refresh_economic_verifier()
        if verifier is None:
            return "no operator trust-store verifier is configured"
        payload = canonical_payload(record)
        current = verifier.verify(
            payload,
            record.signature,
            provider_id,
            capability=capability,
        )
        if not current.valid:
            return current.reason
        historical = verifier.verify(
            payload,
            record.signature,
            provider_id,
            capability=capability,
            signed_at=signed_at,
            allow_historical=True,
        )
        return None if historical.valid else historical.reason

    def _maximum_acceptable_amount(
        self,
        policy: PolicyConfig,
        context: ActionContext,
        currency: str,
    ) -> CurrencyAmount | None:
        limits = [
            Decimal(str(value))
            for value in (
                policy.constraints.max_cost_usd,
                context.compute.monetary_budget_remaining_usd,
                (
                    self.manifest.budget.max_per_action_usd
                    if self.manifest.budget is not None
                    else None
                ),
            )
            if value is not None
        ]
        return CurrencyAmount(amount=min(limits), currency=currency) if limits else None

    @staticmethod
    def _ranking_amounts(
        estimate: RouteEstimate,
        *,
        currency: str,
    ) -> tuple[CurrencyAmount | None, CurrencyAmount | None]:
        expected = (
            CurrencyAmount(amount=estimate.cash.amount_usd, currency=currency)
            if estimate.cash.amount_usd is not None
            else None
        )
        maximum = (
            CurrencyAmount(amount=estimate.cash.upper_bound_usd, currency=currency)
            if estimate.cash.upper_bound_usd is not None
            else None
        )
        return expected, maximum

    @staticmethod
    def _append_quote_failure(
        failures: list[QuoteFailure],
        *,
        executor_id: str,
        provider_id: str | None,
        code: str,
        reason: str,
        retryable: bool = False,
    ) -> None:
        failures.append(
            QuoteFailure(
                executor_id=executor_id,
                provider_id=provider_id,
                code=code[:100],
                reason=reason[:2000],
                retryable=retryable,
            )
        )

    async def prepare_route(
        self,
        request: ActionRequest | dict[str, Any],
        *,
        quote_policy: QuoteFailurePolicy | None = None,
        deadline: datetime | None = None,
    ) -> PreparedRouteDecision:
        """Prepare one immutable, request-bound route decision without executing it.

        Unlike :meth:`route`, this explicit API may use the configured economic
        network.  Candidate qualification and every non-price hard constraint
        are evaluated before the bounded top-K quote acquisition.
        """

        self._ensure_open()
        preparation_started = time.perf_counter()
        created_at = self._economic_now()
        if deadline is not None:
            if deadline.tzinfo is None or deadline.utcoffset() is None:
                raise ConfigurationError("prepared route deadline must be timezone-aware")
            deadline = deadline.astimezone(UTC)
            if deadline <= created_at:
                raise ConfigurationError("prepared route deadline has already elapsed")

        original = (
            request.model_copy(deep=True)
            if isinstance(request, ActionRequest)
            else ActionRequest.model_validate(request)
        )
        bound_action_digest = action_digest(original)
        request_model = self._fill_runtime_context(original)
        policy = self._policy_for(request_model)
        bound_policy_digest = self._effective_policy_digest(policy)
        features = action_features(request_model.input)
        economic = self.manifest.economic_evidence
        failure_policy = resolve_failure_policy(
            economic.requirements.quote_failure_policy,
            quote_policy,
        )
        if (
            failure_policy is QuoteFailurePolicy.ALLOW_VERIFIED_OFFER
            and not economic.requirements.allow_verified_static_offer
        ) or (
            failure_policy is QuoteFailurePolicy.ALLOW_STATIC_PRIOR
            and not economic.requirements.allow_static_prior
        ):
            raise ConfigurationError("requested quote fallback is disabled by operator policy")

        compatible, schema_errors = self.registry.compatible(
            request_model.capability,
            request_model.input,
        )
        specs = {spec.id: spec for spec in compatible}
        estimates: dict[str, RouteEstimate] = {}
        initial_scores: dict[str, CandidateScore] = {}
        rejected_reasons: dict[str, list[str]] = {}
        rejected_quote_ids: dict[str, str] = {}

        non_price_policy = policy.model_copy(deep=True)
        non_price_policy.constraints.max_cost_usd = None
        non_price_context = request_model.context.model_copy(deep=True)
        non_price_context.compute.monetary_budget_remaining_usd = None

        for spec in compatible:
            try:
                self._require_active_spec(spec)
            except NoRouteError as exc:
                rejected_reasons[spec.id] = [str(exc)]
                continue
            cold_estimate = self.estimator.estimate(spec, policy, features)
            cold = score_candidate(
                spec,
                cold_estimate,
                non_price_policy,
                non_price_context,
                self._subscription_quota(spec, request_model.context),
            )
            if not cold.feasible:
                rejected_reasons[spec.id] = list(cold.rejection_reasons)
                estimates[spec.id] = cold_estimate
                continue
            estimate, affinity = self._cache_adjusted_estimate(
                spec,
                cold_estimate,
                policy,
                request_model.context,
            )
            estimates[spec.id] = estimate
            initial = score_candidate(
                spec,
                estimate,
                non_price_policy,
                non_price_context,
                self._subscription_quota(spec, request_model.context),
            )
            initial.cache_affinity = affinity
            if initial.feasible and initial.score is not None:
                initial_scores[spec.id] = initial
            else:
                rejected_reasons[spec.id] = list(initial.rejection_reasons)

        for executor_id, error in schema_errors.items():
            rejected_reasons[executor_id] = [error]
            specs[executor_id] = self.registry.get(executor_id)
            estimates[executor_id] = specs[executor_id].estimate.model_copy(deep=True)

        aggregate_selector = self.market_aggregate_selector
        if aggregate_selector is not None:
            refreshed_verifier = self._refresh_economic_verifier()
            if refreshed_verifier is not None:
                aggregate_selector.verifier = refreshed_verifier
            for executor_id in tuple(initial_scores):
                spec = specs[executor_id]
                if spec.provider_id is None:
                    continue
                route_economic = spec.config.get("economic", {})
                region = (
                    route_economic.get("region")
                    if isinstance(route_economic, dict)
                    and isinstance(route_economic.get("region"), str)
                    else None
                )
                account_tier = (
                    route_economic.get("account_tier")
                    if isinstance(route_economic, dict)
                    and isinstance(route_economic.get("account_tier"), str)
                    else None
                )
                prior = aggregate_selector.select(
                    capability=spec.capability,
                    provider_id=spec.provider_id,
                    executor_id=spec.id,
                    executor_fingerprint=executor_fingerprint(spec),
                    input_bucket=features.size_bucket,
                    region=region,
                    account_tier=account_tier,
                )
                if prior is None or prior.expected_cash is None:
                    continue
                estimate = estimates[executor_id].model_copy(deep=True)
                estimate.cash = CashEstimate(
                    amount_usd=prior.expected_cash.amount,
                    upper_bound_usd=estimate.cash.upper_bound_usd,
                    evidence=MeasurementEvidence(
                        status=EvidenceStatus.COMPLETE,
                        source=EvidenceSource.STATIC_ESTIMATE,
                        trust=TrustLevel.VERIFIED,
                        evidence_id=prior.source_aggregate_id,
                        observed_at=prior.aggregate.generated_at,
                    ),
                )
                estimates[executor_id] = estimate
                rescored = score_candidate(
                    spec,
                    estimate,
                    non_price_policy,
                    non_price_context,
                    self._subscription_quota(spec, request_model.context),
                )
                if rescored.feasible and rescored.score is not None:
                    initial_scores[executor_id] = rescored

        leading = sorted(
            initial_scores.values(),
            key=lambda item: (
                item.score.total if item.score is not None else float("inf"),
                item.executor_id,
            ),
        )
        pinned_authorizations: dict[
            str,
            tuple[PinnedRateCardAuthorizationConfig, RateCardSnapshot, CurrencyAmount],
        ] = {}
        for pinned_candidate in leading:
            executor_id = pinned_candidate.executor_id
            pinned = economic.requirements.pinned_rate_cards.get(executor_id)
            if pinned is None:
                continue
            snapshot = self.store.get_rate_card_snapshot(pinned.rate_card_snapshot_id)
            if snapshot is None:
                rejected_reasons[executor_id] = [
                    "operator-pinned rate-card snapshot is unavailable"
                ]
                continue
            try:
                maximum = pinned.authorized_maximum(snapshot, at=created_at)
            except ValueError as exc:
                rejected_reasons[executor_id] = [str(exc)]
                continue
            if maximum.currency != economic.settlement_currency:
                rejected_reasons[executor_id] = [
                    "pinned rate-card currency differs from settlement currency"
                ]
                continue
            spec = specs[executor_id]
            if spec.provider_id is not None and snapshot.provider != spec.provider_id:
                rejected_reasons[executor_id] = [
                    "pinned rate-card provider differs from the exact route provider"
                ]
                continue
            estimate = estimates[executor_id].model_copy(deep=True)
            estimate.cash = CashEstimate(
                amount_usd=maximum.amount,
                upper_bound_usd=maximum.amount,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.PINNED_RATE_TABLE,
                    trust=TrustLevel.VERIFIED,
                    evidence_id=snapshot.snapshot_id,
                    observed_at=snapshot.retrieved_at,
                ),
            )
            estimates[executor_id] = estimate
            rescored = score_candidate(
                specs[executor_id],
                estimate,
                non_price_policy,
                non_price_context,
                self._subscription_quota(specs[executor_id], request_model.context),
            )
            if not rescored.feasible or rescored.score is None:
                rejected_reasons[executor_id] = list(rescored.rejection_reasons)
                continue
            initial_scores[executor_id] = rescored
            pinned_authorizations[executor_id] = (pinned, snapshot, maximum)
        leading = sorted(
            (
                rescored_candidate
                for executor_id, rescored_candidate in initial_scores.items()
                if executor_id not in rejected_reasons
            ),
            key=lambda item: (
                item.score.total if item.score is not None else float("inf"),
                item.executor_id,
            ),
        )
        quote_required_ids = [
            candidate.executor_id
            for candidate in leading
            if route_requires_live_quote(
                specs[candidate.executor_id],
                estimates[candidate.executor_id],
                require_binding_quote_for_paid_routes=(
                    economic.requirements.require_binding_quote_for_paid_routes
                ),
            )
            and candidate.executor_id not in pinned_authorizations
        ]
        quote_failures: list[QuoteFailure] = []
        request_by_id: dict[str, QuoteRequestV2] = {}
        request_by_executor: dict[str, QuoteRequestV2] = {}
        disclosed_by_executor: dict[str, dict[str, str | int | bool | None]] = {}
        quote_candidates: list[QuoteCandidate] = []
        accepted_quotes: dict[str, BoundedQuote] = {}
        valid_offers: dict[str, CapabilityOffer] = {}
        authorized_offers: dict[str, CapabilityOffer] = {}
        quote_latency_ms = Decimal(0)
        quote_request_count = 0

        quote_provider = self.prepared_quote_provider
        live_ready = (
            economic.enabled and economic.live_quotes.enabled and quote_provider is not None
        )
        top_k_ids = set(quote_required_ids[: economic.live_quotes.top_k]) if live_ready else set()
        request_expiry = created_at + timedelta(
            seconds=economic.live_quotes.maximum_quote_ttl_seconds
        )
        if deadline is not None:
            request_expiry = min(request_expiry, deadline)

        for executor_id in quote_required_ids:
            spec = specs[executor_id]
            if not live_ready:
                self._append_quote_failure(
                    quote_failures,
                    executor_id=executor_id,
                    provider_id=spec.provider_id,
                    code=QuoteErrorCode.CONFIGURATION.value,
                    reason=(
                        "live quote acquisition is disabled or has no configured quote provider"
                    ),
                )
                continue
            if executor_id not in top_k_ids:
                self._append_quote_failure(
                    quote_failures,
                    executor_id=executor_id,
                    provider_id=spec.provider_id,
                    code="NOT_SHORTLISTED",
                    reason="candidate was outside the configured live-quote top-K shortlist",
                )
                continue
            if spec.provider_id is None:
                self._append_quote_failure(
                    quote_failures,
                    executor_id=executor_id,
                    provider_id=None,
                    code=QuoteErrorCode.CONFIGURATION.value,
                    reason="a live-quoted route requires an exact provider identity",
                )
                continue
            if quote_provider is None:  # pragma: no cover - narrowed by live_ready
                raise ConfigurationError("live quote provider disappeared during preparation")
            try:
                self._require_active_spec(spec)
                disclosed = disclose_quote_features(
                    disclosure_policy(spec),
                    action_input=request_model.input,
                    action_features=features,
                )
            except (ConfigurationError, QuoteDisclosureError, ValueError) as exc:
                self._append_quote_failure(
                    quote_failures,
                    executor_id=executor_id,
                    provider_id=spec.provider_id,
                    code="DISCLOSURE_POLICY",
                    reason=str(exc),
                )
                continue
            quote_request = QuoteRequestV2(
                quote_request_id=new_id("qreq"),
                action_id=request_model.action_id,
                capability=request_model.capability,
                executor_id=spec.id,
                executor_fingerprint=executor_fingerprint(spec),
                action_digest=bound_action_digest,
                input_features=features,
                disclosed_quote_features=disclosed,
                desired_currency=economic.settlement_currency,
                maximum_acceptable_amount=self._maximum_acceptable_amount(
                    policy,
                    request_model.context,
                    economic.settlement_currency,
                ),
                nonce=secrets.token_urlsafe(24),
                created_at=created_at,
                expires_at=request_expiry,
            )
            self.store.save_quote_request_v2(quote_request)
            request_by_id[quote_request.quote_request_id] = quote_request
            request_by_executor[executor_id] = quote_request
            disclosed_by_executor[executor_id] = dict(disclosed)
            quote_candidates.append(
                QuoteCandidate(
                    provider_id=spec.provider_id,
                    request=quote_request,
                    provider=quote_provider,
                )
            )

        if quote_candidates:
            if quote_provider is None:  # pragma: no cover - quote construction invariant
                raise ConfigurationError("live quote provider disappeared during preparation")
            quote_started = time.perf_counter()
            total_timeout = economic.live_quotes.total_timeout_seconds
            if deadline is not None:
                total_timeout = min(
                    total_timeout,
                    max(0.0, (deadline - self._economic_now()).total_seconds()),
                )
            offer_failure: str | None = None
            if total_timeout > 0:
                try:
                    offers = await asyncio.wait_for(
                        quote_provider.get_offers(
                            request_model.capability,
                            [candidate.request.executor_id for candidate in quote_candidates],
                        ),
                        timeout=total_timeout,
                    )
                except TimeoutError:
                    offers = ()
                    offer_failure = "offer acquisition exceeded the total quote deadline"
                except Exception:
                    offers = ()
                    offer_failure = "offer provider failed"
                now = self._economic_now()
                for offer in offers:
                    offer_spec = specs.get(offer.executor_id)
                    if offer_spec is None or offer.executor_id not in request_by_executor:
                        continue
                    offer_reason: str | None = None
                    if (
                        offer.provider_id != offer_spec.provider_id
                        or offer.capability != request_model.capability
                        or offer.executor_fingerprint != executor_fingerprint(offer_spec)
                        or offer.settlement_currency != economic.settlement_currency
                    ):
                        offer_reason = (
                            "offer identity, capability, fingerprint, or currency binding failed"
                        )
                    elif not offer.valid_at(now):
                        offer_reason = "offer is not currently valid"
                    elif offer.issued_at > now + timedelta(
                        seconds=economic.live_quotes.maximum_clock_skew_seconds
                    ):
                        offer_reason = "offer issue time exceeds the configured clock skew"
                    elif (
                        status := self.store.capability_offer_status(offer.offer_id)
                    ) is not None and status["status"] == "revoked":
                        offer_reason = "offer was revoked by the local operator"
                    else:
                        offer_reason = self._verify_economic_record(
                            offer,
                            provider_id=offer.provider_id,
                            capability=offer.capability,
                            signed_at=offer.issued_at,
                        )
                    if offer_reason is not None:
                        self._append_quote_failure(
                            quote_failures,
                            executor_id=offer_spec.id,
                            provider_id=offer_spec.provider_id,
                            code="INVALID_OFFER",
                            reason=offer_reason,
                        )
                        continue
                    try:
                        self.store.save_capability_offer(offer)
                    except ConfigurationError:
                        self._append_quote_failure(
                            quote_failures,
                            executor_id=offer_spec.id,
                            provider_id=offer_spec.provider_id,
                            code="INVALID_OFFER",
                            reason="immutable offer evidence conflicted with local storage",
                        )
                        continue
                    previous = valid_offers.get(offer_spec.id)
                    if previous is None or (offer.valid_until, offer.offer_id) > (
                        previous.valid_until,
                        previous.offer_id,
                    ):
                        valid_offers[offer_spec.id] = offer

                elapsed = time.perf_counter() - quote_started
                remaining = total_timeout - elapsed
                if remaining > 0:
                    acquisition = await acquire_top_k_quotes(
                        quote_candidates,
                        top_k=len(quote_candidates),
                        total_timeout_seconds=remaining,
                    )
                    quote_request_count = len(quote_candidates)
                    for failure in acquisition.failures:
                        self._append_quote_failure(
                            quote_failures,
                            executor_id=failure.executor_id,
                            provider_id=failure.provider_id,
                            code=failure.code.value,
                            reason=failure.reason,
                            retryable=failure.code
                            in {QuoteErrorCode.NETWORK, QuoteErrorCode.TIMEOUT},
                        )
                    returned_quotes = acquisition.quotes
                else:
                    returned_quotes = ()
                    for candidate in quote_candidates:
                        self._append_quote_failure(
                            quote_failures,
                            executor_id=candidate.request.executor_id,
                            provider_id=candidate.provider_id,
                            code=QuoteErrorCode.TOTAL_TIMEOUT.value,
                            reason="total quote acquisition deadline exceeded",
                            retryable=True,
                        )
                if offer_failure is not None and not returned_quotes:
                    for candidate in quote_candidates:
                        self._append_quote_failure(
                            quote_failures,
                            executor_id=candidate.request.executor_id,
                            provider_id=candidate.provider_id,
                            code="OFFER_UNAVAILABLE",
                            reason=offer_failure,
                            retryable=True,
                        )
            else:
                returned_quotes = ()
                for candidate in quote_candidates:
                    self._append_quote_failure(
                        quote_failures,
                        executor_id=candidate.request.executor_id,
                        provider_id=candidate.provider_id,
                        code=QuoteErrorCode.TOTAL_TIMEOUT.value,
                        reason="prepared route deadline elapsed before quote acquisition",
                    )

            for returned_quote in returned_quotes:
                returned_request = request_by_id.get(returned_quote.quote_request_id)
                executor_id = (
                    returned_request.executor_id
                    if returned_request is not None
                    else returned_quote.executor_id
                )
                returned_spec = specs.get(executor_id)
                quote_reason: str | None = None
                now = self._economic_now()
                if returned_request is None or returned_spec is None:
                    quote_reason = "quote does not bind to a requested shortlist candidate"
                elif returned_quote.provider_id != returned_spec.provider_id:
                    quote_reason = "quote provider identity does not match the route"
                elif executor_fingerprint(returned_spec) != returned_request.executor_fingerprint:
                    quote_reason = "route fingerprint changed during quote acquisition"
                elif returned_quote.issued_at > now + timedelta(
                    seconds=economic.live_quotes.maximum_clock_skew_seconds
                ):
                    quote_reason = "quote issue time exceeds the configured clock skew"
                elif returned_quote.expires_at > returned_request.expires_at:
                    quote_reason = "quote expiry exceeds its request expiry"
                else:
                    try:
                        returned_quote.validate_binding(
                            returned_request,
                            at=max(now, returned_quote.issued_at),
                            maximum_ttl_seconds=(economic.live_quotes.maximum_quote_ttl_seconds),
                        )
                    except ValueError as exc:
                        quote_reason = str(exc)
                if quote_reason is None:
                    bound_offer = valid_offers.get(executor_id)
                    if returned_quote.offer_id is not None and (
                        bound_offer is None
                        or bound_offer.offer_id != returned_quote.offer_id
                        or bound_offer.provider_id != returned_quote.provider_id
                        or bound_offer.capability != returned_quote.capability
                        or bound_offer.executor_id != returned_quote.executor_id
                        or bound_offer.executor_fingerprint
                        != returned_quote.executor_fingerprint
                        or bound_offer.settlement_currency
                        != returned_quote.maximum_amount.currency
                        or bound_offer.terms_digest != returned_quote.terms_digest
                        or bound_offer.billing_trigger != returned_quote.billing_trigger
                        or bound_offer.failure_charge_policy
                        != returned_quote.failure_charge_policy
                        or bound_offer.retry_charge_policy != returned_quote.retry_charge_policy
                        or bound_offer.fixed_attempt_fee
                        != returned_quote.fixed_attempt_fee
                    ):
                        quote_reason = "quote offer binding is missing, revoked, or inconsistent"
                if quote_reason is None:
                    quote_reason = self._verify_economic_record(
                        returned_quote,
                        provider_id=returned_quote.provider_id,
                        capability=returned_quote.capability,
                        signed_at=returned_quote.issued_at,
                    )
                if quote_reason is not None:
                    rejected_quote_ids[executor_id] = returned_quote.quote_id
                    self._append_quote_failure(
                        quote_failures,
                        executor_id=executor_id,
                        provider_id=(
                            returned_spec.provider_id
                            if returned_spec is not None
                            else returned_quote.provider_id
                        ),
                        code=QuoteErrorCode.BINDING.value,
                        reason=quote_reason,
                    )
                    continue
                try:
                    self.store.save_bounded_quote_and_use_nonce(
                        returned_quote,
                        used_at=now,
                    )
                except ConfigurationError:
                    self._append_quote_failure(
                        quote_failures,
                        executor_id=executor_id,
                        provider_id=returned_quote.provider_id,
                        code=QuoteErrorCode.REPLAY.value,
                        reason="quote nonce or immutable evidence was already used",
                    )
                    continue
                accepted_quotes[executor_id] = returned_quote
            quote_latency_ms = Decimal(str((time.perf_counter() - quote_started) * 1000.0))

        evidence_by_executor: dict[str, EconomicEvidenceLevel] = {}
        quote_id_by_executor: dict[str, str] = {}
        expected_by_executor: dict[str, CurrencyAmount | None] = {}
        maximum_by_executor: dict[str, CurrencyAmount | None] = {}
        adjusted_scores: dict[str, CandidateScore] = {}

        for initial_candidate in leading:
            executor_id = initial_candidate.executor_id
            if executor_id in rejected_reasons:
                continue
            spec = specs[executor_id]
            estimate = estimates[executor_id].model_copy(deep=True)
            needs_quote = executor_id in quote_required_ids
            accepted_quote = accepted_quotes.get(executor_id)
            pinned_authorization = pinned_authorizations.get(executor_id)
            evidence_level = (
                EconomicEvidenceLevel.OPERATOR_ATTESTED
                if route_is_operator_confirmed_free(spec, estimate)
                else EconomicEvidenceLevel.STATIC_PRIOR
                if estimate.cash.amount_usd is not None or estimate.cash.upper_bound_usd is not None
                else EconomicEvidenceLevel.UNKNOWN
            )

            if pinned_authorization is not None:
                _, _, pinned_maximum = pinned_authorization
                evidence_level = EconomicEvidenceLevel.STATIC_PRIOR
                expected_by_executor[executor_id] = pinned_maximum
                maximum_by_executor[executor_id] = pinned_maximum
            elif accepted_quote is not None:
                try:
                    estimate.cash = cash_estimate_from_quote(accepted_quote)
                except ValueError as exc:
                    rejected_reasons[executor_id] = [str(exc)]
                    continue
                evidence_level = EconomicEvidenceLevel.SIGNED_QUOTE
                quote_id_by_executor[executor_id] = accepted_quote.quote_id
                expected_by_executor[executor_id] = accepted_quote.expected_amount
                maximum_by_executor[executor_id] = accepted_quote.maximum_amount
            elif needs_quote and failure_policy is QuoteFailurePolicy.ALLOW_VERIFIED_OFFER:
                fallback_offer = valid_offers.get(executor_id)
                if fallback_offer is None:
                    rejected_reasons[executor_id] = [
                        "binding quote failed and no valid verified offer is available"
                    ]
                    continue
                if any(
                    rule.per_unit_amount is not None
                    for rule in fallback_offer.pricing_rules
                ):
                    rejected_reasons[executor_id] = [
                        "usage-priced offers require a request-bound signed quote"
                    ]
                    continue
                quantities = {
                    key: Decimal(value)
                    for key, value in disclosed_by_executor.get(executor_id, {}).items()
                    if isinstance(value, int) and not isinstance(value, bool)
                }
                try:
                    estimate.cash = cash_estimate_from_offer(fallback_offer, quantities)
                except ValueError as exc:
                    rejected_reasons[executor_id] = [str(exc)]
                    continue
                if estimate.cash.upper_bound_usd is None:
                    rejected_reasons[executor_id] = [
                        "verified offer does not provide a request-bounded maximum"
                    ]
                    continue
                evidence_level = EconomicEvidenceLevel.PUBLISHED_OFFER
                authorized_offers[executor_id] = fallback_offer
                expected_by_executor[executor_id], maximum_by_executor[executor_id] = (
                    self._ranking_amounts(
                        estimate,
                        currency=economic.settlement_currency,
                    )
                )
            elif needs_quote and failure_policy is QuoteFailurePolicy.ALLOW_STATIC_PRIOR:
                if estimate.cash.upper_bound_usd is None:
                    rejected_reasons[executor_id] = [
                        "binding quote failed and the static cash maximum is unknown"
                    ]
                    continue
                expected_by_executor[executor_id], maximum_by_executor[executor_id] = (
                    self._ranking_amounts(
                        estimate,
                        currency=economic.settlement_currency,
                    )
                )
                evidence_level = EconomicEvidenceLevel.STATIC_PRIOR
            elif needs_quote:
                rejected_reasons[executor_id] = [
                    "required binding quote is unavailable; cash was not treated as zero"
                ]
                continue
            else:
                expected_by_executor[executor_id], maximum_by_executor[executor_id] = (
                    self._ranking_amounts(
                        estimate,
                        currency=economic.settlement_currency,
                    )
                )

            maximum_amount = maximum_by_executor.get(executor_id)
            if maximum_amount is not None and self.manifest.budget is not None:
                per_action_limit = Decimal(str(self.manifest.budget.max_per_action_usd))
                if maximum_amount.amount > per_action_limit:
                    rejected_reasons[executor_id] = [
                        "maximum authorized cash exceeds the agent max-per-action budget"
                    ]
                    continue
            if (
                maximum_amount is not None
                and maximum_amount.amount > 0
                and economic.payment.adapter == "free"
            ):
                rejected_reasons[executor_id] = [
                    "configured free payment adapter cannot authorize a paid route"
                ]
                continue

            if (
                needs_quote
                and accepted_quote is None
                and evidence_level is not EconomicEvidenceLevel.PUBLISHED_OFFER
            ):
                rejected_reasons[executor_id] = [
                    "fallback evidence is not request-bound and cannot authorize prepared paid "
                    "execution in AEEP 0.5"
                ]
                continue
            if (
                economic.enabled
                and pinned_authorization is None
                and evidence_level.rank < economic.requirements.minimum_evidence_level.rank
            ):
                rejected_reasons[executor_id] = [
                    f"economic evidence {evidence_level.value} is below required "
                    f"{economic.requirements.minimum_evidence_level.value}"
                ]
                continue

            try:
                self._require_active_spec(spec)
            except NoRouteError as exc:
                rejected_reasons[executor_id] = [str(exc)]
                continue
            current_fingerprint = executor_fingerprint(spec)
            bound_quote_request = request_by_executor.get(executor_id)
            if (
                bound_quote_request is not None
                and current_fingerprint != bound_quote_request.executor_fingerprint
            ):
                rejected_reasons[executor_id] = [
                    "route fingerprint changed after quote acquisition; requalification is required"
                ]
                continue
            scored = score_candidate(
                spec,
                estimate,
                policy,
                request_model.context,
                self._subscription_quota(spec, request_model.context),
            )
            if not scored.feasible or scored.score is None:
                rejected_reasons[executor_id] = list(scored.rejection_reasons)
                continue
            if accepted_quote is not None and accepted_quote.expected_amount is None:
                scored.score.cash_uncertainty += policy.uncertainty_penalty
                scored.score.total += policy.uncertainty_penalty
            adjusted_scores[executor_id] = scored
            evidence_by_executor[executor_id] = evidence_level

        feasible = sorted(
            adjusted_scores.values(),
            key=lambda item: (
                item.score.total if item.score is not None else float("inf"),
                item.executor_id,
            ),
        )
        rankings: list[CandidateRanking] = []
        for rank, ranked_candidate in enumerate(feasible, start=1):
            ranked_candidate.rank = rank
            score = ranked_candidate.score.total if ranked_candidate.score is not None else None
            rankings.append(
                CandidateRanking(
                    executor_id=ranked_candidate.executor_id,
                    executor_fingerprint=executor_fingerprint(specs[ranked_candidate.executor_id]),
                    rank=rank,
                    score=Decimal(str(score)) if score is not None else None,
                    quote_id=quote_id_by_executor.get(ranked_candidate.executor_id),
                    expected_amount=expected_by_executor.get(ranked_candidate.executor_id),
                    maximum_amount=maximum_by_executor.get(ranked_candidate.executor_id),
                    evidence_level=evidence_by_executor[ranked_candidate.executor_id],
                    explanation="lower policy score is preferred after hard feasibility",
                )
            )

        selected_executor_id = feasible[0].executor_id if feasible else None
        selected_quote = (
            accepted_quotes.get(selected_executor_id) if selected_executor_id is not None else None
        )
        selected_offer = (
            authorized_offers.get(selected_executor_id)
            if selected_executor_id is not None
            else None
        )
        selected_rate_card_authorization = (
            pinned_authorizations.get(selected_executor_id)
            if selected_executor_id is not None
            else None
        )
        selected_rate_card_config = (
            selected_rate_card_authorization[0]
            if selected_rate_card_authorization is not None
            else None
        )
        selected_rate_card = (
            selected_rate_card_authorization[1]
            if selected_rate_card_authorization is not None
            else None
        )
        selected_fingerprint = (
            executor_fingerprint(specs[selected_executor_id])
            if selected_executor_id is not None
            else None
        )
        selected_maximum = (
            maximum_by_executor.get(selected_executor_id)
            if selected_executor_id is not None
            else None
        )

        for executor_id in set(specs) - {item.executor_id for item in feasible}:
            if executor_id not in rejected_reasons:
                rejected_reasons[executor_id] = ["candidate was not economically available"]
        rejected = tuple(
            RejectedCandidate(
                executor_id=executor_id,
                executor_fingerprint=executor_fingerprint(specs[executor_id]),
                reasons=tuple(dict.fromkeys(rejected_reasons[executor_id])),
                quote_id=rejected_quote_ids.get(executor_id),
            )
            for executor_id in sorted(rejected_reasons)
        )

        route_candidates: list[CandidateScore] = list(feasible)
        for item in rejected:
            estimate = estimates.get(item.executor_id, specs[item.executor_id].estimate)
            route_candidates.append(
                CandidateScore(
                    executor_id=item.executor_id,
                    feasible=False,
                    rejection_reasons=list(item.reasons),
                    estimate=estimate,
                    resource_pool=specs[item.executor_id].resource_pool,
                    subscription_quota=self._subscription_quota(
                        specs[item.executor_id],
                        request_model.context,
                    ),
                )
            )
        explanation = (
            f"Prepared {selected_executor_id!r} from {len(feasible)} feasible route(s); "
            f"requested {quote_request_count} live quote(s)."
            if selected_executor_id is not None
            else (
                f"No route is feasible after prepared economic validation; "
                f"requested {quote_request_count} live quote(s)."
            )
        )
        route_decision = RouteDecision(
            action=request_model,
            policy=policy,
            selected_executor_id=selected_executor_id,
            candidates=route_candidates,
            action_features=features,
            explanation=explanation,
        )
        self._persist_decision(route_decision)
        self._validated_decisions[route_decision.decision_id] = self._decision_digest(
            route_decision
        )

        expires_at = request_expiry
        if selected_quote is not None:
            expires_at = min(expires_at, selected_quote.expires_at)
        if selected_offer is not None:
            expires_at = min(expires_at, selected_offer.valid_until)
        if selected_rate_card is not None and selected_rate_card.effective_until is not None:
            expires_at = min(expires_at, selected_rate_card.effective_until)
        if self._economic_now() >= expires_at:
            raise ConfigurationError("prepared decision expired before preparation completed")
        preparation_latency_ms = Decimal(str((time.perf_counter() - preparation_started) * 1000.0))
        expected_accounting = ResourceAccounting()
        if selected_executor_id is not None:
            selected_spec = specs[selected_executor_id]
            selected_estimate = adjusted_scores[selected_executor_id].estimate
            if route_is_operator_confirmed_free(selected_spec, selected_estimate):
                expected_accounting = ResourceAccounting(
                    cash=CashAccounting(
                        status=EvidenceStatus.COMPLETE,
                        components=[
                            CashEvidence(
                                charge_id=f"free:{bound_action_digest.removeprefix('sha256:')}",
                                amount=Decimal(0),
                                currency=economic.settlement_currency,
                                classification=CashClassification.VERIFIED,
                                evidence=MeasurementEvidence(
                                    status=EvidenceStatus.COMPLETE,
                                    source=(EvidenceSource.CONFIRMED_NO_INCREMENTAL_CHARGE),
                                    trust=TrustLevel.VERIFIED,
                                ),
                            )
                        ],
                    )
                )

        prepared = PreparedRouteDecision(
            action_id=request_model.action_id,
            action_digest=bound_action_digest,
            effective_policy_digest=bound_policy_digest,
            selected_executor_id=selected_executor_id,
            selected_executor_fingerprint=selected_fingerprint,
            selected_quote_id=selected_quote.quote_id if selected_quote is not None else None,
            selected_offer_id=selected_offer.offer_id if selected_offer is not None else None,
            selected_rate_card_id=(
                selected_rate_card_config.rate_card_snapshot_id
                if selected_rate_card_config is not None
                else None
            ),
            authorization_kind=(
                AuthorizationKind.SIGNED_QUOTE
                if selected_quote is not None
                else AuthorizationKind.PUBLISHED_OFFER
                if selected_offer is not None
                else AuthorizationKind.PINNED_RATE_CARD
                if selected_rate_card is not None
                else None
            ),
            authorization_id=(
                selected_quote.quote_id
                if selected_quote is not None
                else selected_offer.offer_id
                if selected_offer is not None
                else selected_rate_card_config.rate_card_snapshot_id
                if selected_rate_card_config is not None
                else None
            ),
            authorization_rate_ids=(
                selected_rate_card_config.rate_ids
                if selected_rate_card_config is not None
                else ()
            ),
            authorization_meter_quantities=(
                selected_rate_card_config.meter_quantities
                if selected_rate_card_config is not None
                else ()
            ),
            quote_ids=tuple(
                accepted_quotes[executor_id].quote_id for executor_id in sorted(accepted_quotes)
            ),
            candidate_rankings=tuple(rankings),
            rejected_candidates=rejected,
            quote_failures=tuple(
                sorted(
                    quote_failures,
                    key=lambda item: (item.executor_id, item.code, item.reason),
                )
            ),
            disclosed_quote_features=(
                disclosed_by_executor.get(selected_executor_id, {})
                if selected_executor_id is not None
                else {}
            ),
            expected_accounting=expected_accounting,
            maximum_cash_authorization=selected_maximum,
            quote_failure_policy=failure_policy,
            preparation_latency_ms=preparation_latency_ms,
            quote_latency_ms=quote_latency_ms,
            quote_request_count=quote_request_count,
            created_at=created_at,
            expires_at=expires_at,
        )
        self.store.save_prepared_decision(prepared)
        self._prepared_contexts[prepared.prepared_id] = PreparedExecutionContext(
            prepared=prepared,
            request=original,
            route_decision=route_decision,
            selected_quote=selected_quote,
            selected_offer=selected_offer,
            selected_rate_card=selected_rate_card,
        )
        return prepared

    def get_prepared_decision(self, prepared_id: str) -> PreparedRouteDecision:
        """Return sanitized prepared evidence, expiring stale unclaimed decisions."""

        self._ensure_open()
        prepared = self.store.get_prepared_decision(prepared_id)
        if prepared is None:
            raise ConfigurationError(f"unknown prepared decision {prepared_id!r}")
        now = self._economic_now()
        if prepared.state is PreparedDecisionState.PREPARED and now >= prepared.expires_at:
            self.store.save_prepared_transition(
                PreparedRouteTransition(
                    prepared_id=prepared.prepared_id,
                    from_state=PreparedDecisionState.PREPARED,
                    to_state=PreparedDecisionState.EXPIRED,
                    occurred_at=now,
                    reason="prepared decision TTL expired",
                )
            )
            self._prepared_contexts.pop(prepared_id, None)
            refreshed = self.store.get_prepared_decision(prepared_id)
            if refreshed is None:  # pragma: no cover - transition FK invariant
                raise ConfigurationError("prepared decision disappeared after expiration")
            return refreshed
        return prepared

    show_prepared_decision = get_prepared_decision

    def _prepared_offer(
        self,
        prepared: PreparedRouteDecision,
        spec: ExecutorSpec,
    ) -> CapabilityOffer | None:
        if prepared.selected_offer_id is None:
            return None
        offer = self.store.get_capability_offer(prepared.selected_offer_id)
        status = self.store.capability_offer_status(prepared.selected_offer_id)
        if offer is None or status is None or status.get("status") != "active":
            raise ConfigurationError("prepared capability offer is unavailable or revoked")
        if (
            offer.provider_id != spec.provider_id
            or offer.capability != spec.capability
            or offer.executor_id != spec.id
            or offer.executor_fingerprint != executor_fingerprint(spec)
            or offer.settlement_currency
            != self.manifest.economic_evidence.settlement_currency
        ):
            raise ConfigurationError("prepared capability offer binding changed")
        now = self._economic_now()
        if not offer.valid_from <= now < offer.valid_until:
            raise ConfigurationError("prepared capability offer is not currently valid")
        reason = self._verify_economic_record(
            offer,
            provider_id=offer.provider_id,
            capability=offer.capability,
            signed_at=offer.issued_at,
        )
        if reason is not None:
            raise ConfigurationError(f"prepared capability offer is not trusted: {reason}")
        quantities = {
            key: Decimal(value)
            for key, value in prepared.disclosed_quote_features.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        bounded = cash_estimate_from_offer(offer, quantities).upper_bound_usd
        maximum = prepared.maximum_cash_authorization
        if (
            bounded is None
            or maximum is None
            or maximum.currency != offer.settlement_currency
            or maximum.amount != bounded
        ):
            raise ConfigurationError("prepared capability offer maximum cannot be reproduced")
        return offer

    def _prepared_rate_card(
        self,
        prepared: PreparedRouteDecision,
        spec: ExecutorSpec | None,
        *,
        historical: bool = False,
    ) -> RateCardSnapshot | None:
        """Recompute an exact pinned authorization without trusting an estimate mirror."""

        if prepared.selected_rate_card_id is None:
            return None
        if (
            prepared.authorization_kind is not AuthorizationKind.PINNED_RATE_CARD
            or prepared.authorization_id != prepared.selected_rate_card_id
        ):
            raise ConfigurationError("prepared pinned rate-card authorization is inconsistent")
        snapshot = self.store.get_rate_card_snapshot(prepared.selected_rate_card_id)
        if snapshot is None:
            raise ConfigurationError("prepared pinned rate-card snapshot is unavailable")
        if not historical and spec is None:
            raise ConfigurationError("current pinned rate-card validation requires its route")
        if (
            not historical
            and spec is not None
            and spec.provider_id is not None
            and snapshot.provider != spec.provider_id
        ):
            raise ConfigurationError("prepared rate-card provider binding changed")

        stored_config = PinnedRateCardAuthorizationConfig(
            rate_card_snapshot_id=prepared.selected_rate_card_id,
            meter_quantities=prepared.authorization_meter_quantities,
        )
        if stored_config.rate_ids != prepared.authorization_rate_ids:
            raise ConfigurationError("prepared rate-card quantities differ from authorized rates")
        if not historical:
            assert spec is not None
            current_config = self.manifest.economic_evidence.requirements.pinned_rate_cards.get(
                spec.id
            )
            if current_config is None or current_config != stored_config:
                raise ConfigurationError("operator-pinned rate-card authorization changed")
        try:
            maximum = stored_config.authorized_maximum(
                snapshot,
                at=prepared.created_at if historical else self._economic_now(),
            )
        except ValueError as exc:
            raise ConfigurationError(str(exc)) from exc
        if maximum != prepared.maximum_cash_authorization:
            raise ConfigurationError("prepared pinned rate-card maximum cannot be reproduced")
        return snapshot

    def _historical_prepared_offer(
        self,
        prepared: PreparedRouteDecision,
        reservation: PaymentReservationV2,
        receipt: ExecutionReceipt,
    ) -> CapabilityOffer:
        """Verify the immutable offer basis used before invocation, even if later revoked."""

        if (
            prepared.authorization_kind is not AuthorizationKind.PUBLISHED_OFFER
            or prepared.selected_offer_id is None
            or prepared.authorization_id != prepared.selected_offer_id
        ):
            raise ConfigurationError("prepared decision has no published-offer basis")
        offer = self.store.get_capability_offer(
            prepared.selected_offer_id,
            include_revoked=True,
        )
        if offer is None:
            raise ConfigurationError("historical capability offer is unavailable")
        status = self.store.capability_offer_status(prepared.selected_offer_id)
        revoked_text = status.get("revoked_at") if status is not None else None
        revoked_at = (
            datetime.fromisoformat(revoked_text) if revoked_text is not None else None
        )
        if (
            status is None
            or status.get("status") not in {"active", "revoked"}
            or (revoked_at is not None and revoked_at < reservation.created_at)
        ):
            raise ConfigurationError("capability offer was not active when cash was reserved")
        if (
            offer.executor_id != prepared.selected_executor_id
            or offer.executor_fingerprint != prepared.selected_executor_fingerprint
            or offer.capability != receipt.capability
            or offer.executor_id != receipt.executor_id
            or offer.settlement_currency
            != self.manifest.economic_evidence.settlement_currency
            or not offer.valid_from <= reservation.created_at < offer.valid_until
        ):
            raise ConfigurationError("historical capability offer binding is inconsistent")
        verifier = self._refresh_economic_verifier()
        if verifier is None:
            raise ConfigurationError("historical offer has no operator trust-store verifier")
        result = verifier.verify(
            canonical_payload(offer),
            offer.signature,
            offer.provider_id,
            capability=offer.capability,
            signed_at=offer.issued_at,
            allow_historical=True,
        )
        if not result.valid:
            raise ConfigurationError(f"historical capability offer is not trusted: {result.reason}")
        quantities = {
            key: Decimal(value)
            for key, value in prepared.disclosed_quote_features.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        bounded = cash_estimate_from_offer(offer, quantities).upper_bound_usd
        maximum = prepared.maximum_cash_authorization
        if (
            bounded is None
            or maximum is None
            or maximum.currency != offer.settlement_currency
            or maximum.amount != bounded
        ):
            raise ConfigurationError("historical offer maximum cannot be reproduced")
        return offer

    def rehydrate_prepared(
        self,
        prepared_id: str,
        request: ActionRequest | dict[str, Any],
    ) -> PreparedRouteDecision:
        """Bind caller-resupplied input to a stored decision without re-routing or networking."""

        prepared = self.get_prepared_decision(prepared_id)
        if prepared.state is not PreparedDecisionState.PREPARED:
            raise ConfigurationError(
                f"prepared decision cannot be rebound from state {prepared.state.value}"
            )
        original = (
            request.model_copy(deep=True)
            if isinstance(request, ActionRequest)
            else ActionRequest.model_validate(request)
        )
        if original.action_id != prepared.action_id:
            raise ConfigurationError("resupplied action ID does not match prepared decision")
        if action_digest(original) != prepared.action_digest:
            raise ConfigurationError("resupplied action does not match prepared action digest")
        request_model = self._fill_runtime_context(original)
        policy = self._policy_for(request_model)
        if self._effective_policy_digest(policy) != prepared.effective_policy_digest:
            raise ConfigurationError("resupplied action resolves to a different effective policy")
        if prepared.selected_executor_id is None:
            raise NoRouteError("prepared decision has no feasible selected route")
        spec = self.registry.get(prepared.selected_executor_id)
        self._require_active_spec(spec)
        if executor_fingerprint(spec) != prepared.selected_executor_fingerprint:
            raise NoRouteError("prepared executor fingerprint changed; requalification is required")
        validate_json(original.input, spec.input_schema, label=f"input for {spec.id}")
        features = action_features(original.input)
        estimate = self.estimator.estimate(spec, policy, features)
        selected_quote = (
            self.store.get_bounded_quote(prepared.selected_quote_id)
            if prepared.selected_quote_id is not None
            else None
        )
        if prepared.selected_quote_id is not None and selected_quote is None:
            raise ConfigurationError("stored selected quote is unavailable")
        if selected_quote is not None:
            if (
                selected_quote.action_digest != prepared.action_digest
                or selected_quote.executor_id != spec.id
                or selected_quote.executor_fingerprint != executor_fingerprint(spec)
            ):
                raise ConfigurationError("stored selected quote binding is inconsistent")
            estimate.cash = cash_estimate_from_quote(selected_quote)
        selected_offer = self._prepared_offer(prepared, spec)
        if selected_offer is not None:
            quantities = {
                key: Decimal(value)
                for key, value in prepared.disclosed_quote_features.items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            estimate.cash = cash_estimate_from_offer(selected_offer, quantities)
        selected_rate_card = self._prepared_rate_card(prepared, spec)
        if selected_rate_card is not None:
            maximum = prepared.maximum_cash_authorization
            if maximum is None:  # pragma: no cover - prepared model invariant
                raise ConfigurationError("pinned rate-card authorization has no maximum")
            estimate.cash = CashEstimate(
                amount_usd=maximum.amount,
                upper_bound_usd=maximum.amount,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.PINNED_RATE_TABLE,
                    trust=TrustLevel.VERIFIED,
                    evidence_id=selected_rate_card.snapshot_id,
                    observed_at=selected_rate_card.retrieved_at,
                ),
            )
        candidate = score_candidate(
            spec,
            estimate,
            policy,
            request_model.context,
            self._subscription_quota(spec, request_model.context),
        )
        if not candidate.feasible or candidate.score is None:
            raise NoRouteError(
                "stored route no longer satisfies current hard policy: "
                + "; ".join(candidate.rejection_reasons)
            )
        candidate.rank = 1
        route_decision = RouteDecision(
            action=request_model,
            policy=policy,
            selected_executor_id=spec.id,
            candidates=[candidate],
            action_features=features,
            explanation="Rehydrated the exact stored prepared route; no routing or network occurred.",
        )
        self._persist_decision(route_decision)
        self._validated_decisions[route_decision.decision_id] = self._decision_digest(
            route_decision
        )
        self._prepared_contexts[prepared_id] = PreparedExecutionContext(
            prepared=prepared,
            request=original,
            route_decision=route_decision,
            selected_quote=selected_quote,
            selected_offer=selected_offer,
            selected_rate_card=selected_rate_card,
        )
        return prepared

    def _prepared_context(
        self,
        prepared_id: str,
        request: ActionRequest | dict[str, Any] | None = None,
    ) -> PreparedExecutionContext:
        """Return the process-local action only after every durable binding is rechecked."""

        prepared = self.get_prepared_decision(prepared_id)
        if prepared.state is not PreparedDecisionState.PREPARED:
            raise ConfigurationError(
                f"prepared decision is not executable from state {prepared.state.value}"
            )
        context = self._prepared_contexts.get(prepared_id)
        if context is None and request is not None:
            self.rehydrate_prepared(prepared_id, request)
            context = self._prepared_contexts.get(prepared_id)
        if context is None:
            raise ConfigurationError(
                "prepared action payload is unavailable in this process; raw input was not "
                "persisted and the action must be prepared again"
            )
        if action_digest(context.request) != prepared.action_digest:
            raise ConfigurationError("prepared action digest no longer matches its original input")
        current_policy = self._policy_for(self._fill_runtime_context(context.request))
        if self._effective_policy_digest(current_policy) != prepared.effective_policy_digest:
            raise ConfigurationError("effective policy changed after route preparation")
        if context.route_decision.selected_executor_id != prepared.selected_executor_id:
            raise ConfigurationError("prepared route decision binding is inconsistent")
        if prepared.selected_executor_id is None:
            raise NoRouteError("prepared decision has no feasible selected route")
        spec = self.registry.get(prepared.selected_executor_id)
        self._require_active_spec(spec)
        if executor_fingerprint(spec) != prepared.selected_executor_fingerprint:
            raise NoRouteError("prepared executor fingerprint changed; requalification is required")
        selected_quote = context.selected_quote
        if prepared.selected_quote_id is not None:
            stored_quote = self.store.get_bounded_quote(prepared.selected_quote_id)
            if selected_quote is None or stored_quote != selected_quote:
                raise ConfigurationError(
                    "selected quote is unavailable or differs from stored evidence"
                )
            reason = self._verify_economic_record(
                selected_quote,
                provider_id=selected_quote.provider_id,
                capability=selected_quote.capability,
                signed_at=selected_quote.issued_at,
            )
            if reason is not None:
                raise ConfigurationError(f"selected quote is no longer trusted: {reason}")
            if selected_quote.expires_at <= self._economic_now():
                raise ConfigurationError("selected quote has expired")
        selected_offer = self._prepared_offer(prepared, spec)
        if context.selected_offer != selected_offer:
            raise ConfigurationError("selected offer is unavailable or differs from stored evidence")
        selected_rate_card = self._prepared_rate_card(prepared, spec)
        if context.selected_rate_card != selected_rate_card:
            raise ConfigurationError(
                "selected rate-card snapshot is unavailable or differs from stored evidence"
            )
        return PreparedExecutionContext(
            prepared=prepared,
            request=context.request.model_copy(deep=True),
            route_decision=context.route_decision.model_copy(deep=True),
            selected_quote=(selected_quote.model_copy(deep=True) if selected_quote else None),
            selected_offer=(selected_offer.model_copy(deep=True) if selected_offer else None),
            selected_rate_card=(
                selected_rate_card.model_copy(deep=True) if selected_rate_card else None
            ),
        )

    def _transition_prepared(
        self,
        prepared_id: str,
        from_state: PreparedDecisionState,
        to_state: PreparedDecisionState,
        reason: str,
    ) -> PreparedRouteDecision:
        self.store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=prepared_id,
                from_state=from_state,
                to_state=to_state,
                occurred_at=self._economic_now(),
                reason=reason,
            )
        )
        updated = self.store.get_prepared_decision(prepared_id)
        if updated is None:  # pragma: no cover - transition foreign-key invariant
            raise ConfigurationError("prepared decision disappeared after transition")
        return updated

    def _reservation_for_prepared(self, prepared_id: str) -> PaymentReservationV2 | None:
        matches = self.store.list_payment_reservations_v2(
            prepared_id=prepared_id,
            limit=2,
        )
        if len(matches) > 1:
            raise ConfigurationError("prepared decision has multiple payment reservations")
        return matches[0] if matches else None

    def _receipt_for_prepared_recovery(
        self,
        prepared: PreparedRouteDecision,
        reservation: PaymentReservationV2,
    ) -> ExecutionReceipt | None:
        if prepared.selected_executor_id is None:
            return None
        matches = self.store.list_receipts_for_prepared(
            prepared.prepared_id,
            action_id=prepared.action_id,
            executor_id=prepared.selected_executor_id,
            attempt_id=reservation.attempt_id,
            charge_id=reservation.charge_id,
            limit=2,
        )
        return matches[0] if len(matches) == 1 else None

    def _mark_economic_indeterminate(self, prepared_id: str, reason: str) -> None:
        """Preserve a hold and make an uncertain post-invocation state explicit."""

        now = self._economic_now()
        reservation = self._reservation_for_prepared(prepared_id)
        if reservation is not None and reservation.state in {
            PaymentReservationState.RESERVED,
            PaymentReservationState.SETTLING,
        }:
            self.store.transition_payment_reservation_v2(
                reservation.reservation_id,
                expected_state=reservation.state,
                updated=reservation.model_copy(
                    update={
                        "state": PaymentReservationState.INDETERMINATE,
                        "updated_at": max(now, reservation.updated_at),
                        "indeterminate_reason": reason[:2000],
                    }
                ),
            )
        prepared = self.store.get_prepared_decision(prepared_id)
        if prepared is not None and prepared.state in {
            PreparedDecisionState.INVOKING,
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
        }:
            self._transition_prepared(
                prepared_id,
                prepared.state,
                PreparedDecisionState.INDETERMINATE,
                reason,
            )
        attempt = self.store.execution_attempt_for_prepared(prepared_id)
        if attempt is not None and attempt.state in {
            ExecutionAttemptState.RESERVED,
            ExecutionAttemptState.INVOKING,
            ExecutionAttemptState.VALIDATING,
            ExecutionAttemptState.SETTLING,
        }:
            self._advance_attempt(
                attempt,
                ExecutionAttemptState.INDETERMINATE,
                reason=reason,
            )

    def _verify_usage_statement(
        self,
        statement: UsageStatement,
        *,
        prepared: PreparedRouteDecision,
        spec: ExecutorSpec | None,
        attempt_id: str,
        local_receipt: ExecutionReceipt | None = None,
    ) -> None:
        quote_id = prepared.selected_quote_id
        quote = self.store.get_bounded_quote(quote_id) if quote_id is not None else None
        if quote is None:
            raise ConfigurationError("usage statement selected quote is unavailable")
        expected_provider = spec.provider_id if spec is not None else quote.provider_id
        expected_executor = spec.id if spec is not None else quote.executor_id
        expected_capability = spec.capability if spec is not None else quote.capability
        expected = (
            (statement.quote_id, quote_id, "quote"),
            (statement.prepared_id, prepared.prepared_id, "prepared decision"),
            (statement.action_id, prepared.action_id, "action"),
            (statement.attempt_id, attempt_id, "attempt"),
            (statement.provider_id, expected_provider, "provider"),
            (statement.executor_id, expected_executor, "executor"),
            (
                statement.executor_fingerprint,
                prepared.selected_executor_fingerprint,
                "executor fingerprint",
            ),
        )
        for actual, wanted, label in expected:
            if wanted is None or actual != wanted:
                raise ConfigurationError(f"usage statement {label} binding does not match")
        if local_receipt is not None and (
            local_receipt.capability != expected_capability
            or local_receipt.executor_id != expected_executor
        ):
            raise ConfigurationError("local receipt differs from immutable quote bindings")
        now = self._economic_now()
        maximum_skew = timedelta(
            seconds=self.manifest.economic_evidence.live_quotes.maximum_clock_skew_seconds
        )
        if statement.issued_at > now + maximum_skew:
            raise ConfigurationError("usage statement issue time exceeds configured clock skew")
        if statement.issued_at < prepared.created_at - maximum_skew:
            raise ConfigurationError("usage statement predates the prepared decision")
        if (
            statement.provider_calculated_amount is not None
            and statement.provider_calculated_amount.currency
            != quote.maximum_amount.currency
        ):
            raise ConfigurationError("usage statement currency does not match its quote")
        if local_receipt is not None:
            lower = local_receipt.started_at - maximum_skew
            upper = local_receipt.ended_at + maximum_skew
            for instant, label in (
                (statement.started_at, "start"),
                (statement.completed_at, "completion"),
                (statement.issued_at, "issuance"),
            ):
                if instant is not None and not lower <= instant <= upper:
                    raise ConfigurationError(
                        f"usage statement {label} is outside the local attempt chronology"
                    )
        verifier = self._refresh_economic_verifier()
        if verifier is None:
            raise ConfigurationError("usage statement has no operator trust-store verifier")
        result = verifier.verify(
            canonical_payload(statement),
            statement.signature,
            statement.provider_id,
            capability=expected_capability,
            signed_at=statement.issued_at,
            allow_historical=True,
        )
        if not result.valid:
            raise ConfigurationError(f"usage statement is not trusted: {result.reason}")

    @staticmethod
    def _provider_status_for_local(status: ExecutionStatus) -> ProviderExecutionStatus:
        return {
            ExecutionStatus.SUCCESS: ProviderExecutionStatus.SUCCESS,
            ExecutionStatus.FAILED: ProviderExecutionStatus.FAILED,
            ExecutionStatus.REJECTED: ProviderExecutionStatus.REJECTED,
            ExecutionStatus.TIMEOUT: ProviderExecutionStatus.TIMEOUT,
        }.get(status, ProviderExecutionStatus.INDETERMINATE)

    @staticmethod
    def _provider_status_consistent(
        local: ExecutionStatus,
        provider: ProviderExecutionStatus,
    ) -> bool:
        if local is ExecutionStatus.SUCCESS:
            return provider is ProviderExecutionStatus.SUCCESS
        if local is ExecutionStatus.TIMEOUT:
            return provider is ProviderExecutionStatus.TIMEOUT
        if local in {ExecutionStatus.FAILED, ExecutionStatus.REJECTED}:
            return provider in {
                ProviderExecutionStatus.FAILED,
                ProviderExecutionStatus.REJECTED,
            }
        return provider is ProviderExecutionStatus.INDETERMINATE

    @staticmethod
    def _billable_amount_for_offer(
        offer: CapabilityOffer,
        prepared: PreparedRouteDecision,
        receipt: ExecutionReceipt,
    ) -> CurrencyAmount | None:
        """Resolve only exact offer pricing; a bound is never guessed as actual."""

        maximum = prepared.maximum_cash_authorization
        if maximum is None or maximum.currency != offer.settlement_currency:
            return None
        quantities = {
            key: Decimal(value)
            for key, value in prepared.disclosed_quote_features.items()
            if isinstance(value, int) and not isinstance(value, bool)
        }
        estimate = cash_estimate_from_offer(offer, quantities)
        exact = (
            CurrencyAmount(amount=estimate.amount_usd, currency=offer.settlement_currency)
            if estimate.amount_usd is not None
            else None
        )
        if exact is None:
            return None
        if (
            offer.billing_trigger is BillingTrigger.ON_PROVIDER_START
            and receipt.status is not ExecutionStatus.SUCCESS
        ):
            return None
        local = receipt.accounting.cash.actual_cash_cost(offer.settlement_currency)
        local_amount = (
            CurrencyAmount(amount=local, currency=offer.settlement_currency)
            if local is not None
            else None
        )
        return billable_amount_for_terms(
            billing_trigger=offer.billing_trigger,
            failure_charge_policy=offer.failure_charge_policy,
            retry_charge_policy=offer.retry_charge_policy,
            maximum_amount=maximum,
            fixed_authorized_amount=exact,
            execution_status=Router._provider_status_for_local(receipt.status),
            provider_started=(
                receipt.status is ExecutionStatus.SUCCESS
                or offer.billing_trigger is BillingTrigger.ON_ATTEMPT
            ),
            result_accepted=(
                receipt.status is ExecutionStatus.SUCCESS
                and receipt.output_valid is not False
                and receipt.task_valid is not False
            ),
            actual_usage_amount=local_amount,
            fixed_attempt_fee=offer.fixed_attempt_fee,
        )

    @staticmethod
    def _economic_link_id(charge_id: str, evidence_type: str, evidence_id: str) -> str:
        digest = hashlib.sha256(
            f"{charge_id}\0{evidence_type}\0{evidence_id}".encode()
        ).hexdigest()
        return f"link_{digest}"

    def _save_economic_link(
        self,
        *,
        charge_id: str,
        evidence_level: EconomicEvidenceLevel,
        evidence_type: str,
        evidence_id: str,
        payload: Any,
        authoritative: bool,
        supersedes_link_id: str | None = None,
    ) -> EconomicEvidenceLink:
        link_id = self._economic_link_id(charge_id, evidence_type, evidence_id)
        candidate = EconomicEvidenceLink(
            link_id=link_id,
            charge_id=charge_id,
            evidence_level=evidence_level,
            evidence_type=evidence_type,
            evidence_id=evidence_id,
            payload_digest=canonical_digest(payload),
            authoritative=authoritative,
            supersedes_link_id=supersedes_link_id,
            created_at=self._economic_now(),
        )
        existing = self.store.get_economic_evidence_link(link_id)
        if existing is not None:
            stable = {"created_at"}
            if existing.model_dump(exclude=stable) != candidate.model_dump(exclude=stable):
                raise ConfigurationError("economic evidence link identity conflicts")
            return existing
        return self.store.save_economic_evidence_link(candidate)

    def _finalize_recovered_settlement(
        self,
        *,
        prepared: PreparedRouteDecision,
        reservation: PaymentReservationV2,
        settlement: SettlementReceipt,
        receipt: ExecutionReceipt,
    ) -> None:
        """Idempotently finish local audit records after the payment rail settled."""

        receipt.accounting.cash = cash_accounting_from_settlement(
            settlement,
            prior=receipt.accounting.cash,
        )
        receipt.actual_resources.monetary_usd = mirror_actual_cash(receipt.accounting)
        receipt.metadata.update(
            {
                "settlement_id": settlement.settlement_id,
                "cash_evidence_level": settlement.evidence_level.value,
            }
        )
        prior_links = [
            link
            for link in self.store.list_economic_evidence_links(
                charge_id=reservation.charge_id,
                limit=1_000,
            )
            if not link.authoritative
        ]
        self._save_economic_link(
            charge_id=reservation.charge_id,
            evidence_level=settlement.evidence_level,
            evidence_type="settlement_receipt",
            evidence_id=settlement.settlement_id,
            payload=settlement,
            authoritative=True,
            supersedes_link_id=(prior_links[-1].link_id if prior_links else None),
        )
        self._save_receipt(receipt)
        try:
            if prepared.selected_executor_id is not None:
                self._observe_receipt(
                    self.registry.get(prepared.selected_executor_id),
                    receipt,
                )
        except (ConfigurationError, KeyError):
            # Route drift/removal after invocation must not invalidate settled evidence.
            pass
        self.store.complete_payment_operation(
            "settle",
            f"{prepared.prepared_id}:settle",
            result_type=type(settlement).__name__,
            result_id=settlement.settlement_id,
        )
        action_binding = self.store.get_prepared_action_idempotency(prepared.prepared_id)
        if action_binding is not None:
            self.store.complete_prepared_action_idempotency(
                prepared.prepared_id,
                action_digest=prepared.action_digest,
                decision_id=receipt.decision_id,
                status=receipt.status.value,
                receipt_id=receipt.receipt_id,
            )
        self._prepared_contexts.pop(prepared.prepared_id, None)

    async def _invoke_prepared_once(
        self,
        context: PreparedExecutionContext,
        *,
        spec: ExecutorSpec,
        attempt_id: str,
        charge_id: str,
        approval_id: str | None = None,
        durable_attempt: ExecutionAttempt,
        approved_side_effect: SideEffect,
    ) -> tuple[ExecutionOutcome, ExecutionReceipt, object | None, ExecutionAttempt]:
        """Invoke exactly the prepared route once and return unpersisted evidence."""

        decision = context.route_decision
        candidate = next(
            (
                item
                for item in decision.candidates
                if item.executor_id == spec.id and item.feasible
            ),
            None,
        )
        if candidate is None:
            raise ConfigurationError("prepared route no longer has its selected candidate")
        started_at = self._economic_now()
        with start_span(
            "aeep.execute_prepared",
            {
                "aeep.prepared_id": context.prepared.prepared_id,
                "aeep.action_id": context.prepared.action_id,
                "aeep.executor_id": spec.id,
                "aeep.attempt_id": attempt_id,
            },
        ) as span:
            raw = await self._executor_for(spec.kind).execute(
                ExecutionContext(
                    request=decision.action,
                    spec=spec,
                    estimate=candidate.estimate,
                    attempt=1,
                    prepared_id=context.prepared.prepared_id,
                    quote_id=context.prepared.selected_quote_id,
                    attempt_id=attempt_id,
                    approved_side_effect=approved_side_effect,
                )
            )
            durable_attempt = self._advance_attempt(
                durable_attempt,
                ExecutionAttemptState.VALIDATING,
                reason="prepared executor returned; validating locally",
                external_thread_digest=raw.metadata.get("thread_identity_digest"),
                external_turn_digest=raw.metadata.get("turn_identity_digest"),
            )
            usage_payload: object | None = raw.metadata.pop(
                "_economic_usage_statement", None
            )
            output = raw.output
            if isinstance(output, dict) and "usage_statement" in output:
                usage_payload = output.get("usage_statement")
                output = output.get("output")

            output_valid: bool | None = None
            task_valid: bool | None = None
            results: list[ValidationResult] = []
            error_type = raw.error_type
            error_message = raw.error_message
            if raw.status is ExecutionStatus.SUCCESS and spec.output_schema is not None:
                try:
                    validate_json(output, spec.output_schema, label=f"output from {spec.id}")
                    output_valid = True
                    results.append(
                        ValidationResult(
                            kind=ValidationKind.SCHEMA,
                            valid=True,
                            quality_score=1.0,
                            trust=TrustLevel.OBSERVED,
                        )
                    )
                except Exception as exc:
                    output_valid = False
                    error_type = type(exc).__name__
                    error_message = str(exc)
                    results.append(
                        ValidationResult(
                            kind=ValidationKind.SCHEMA,
                            valid=False,
                            quality_score=0.0,
                            detail=str(exc),
                            trust=TrustLevel.OBSERVED,
                        )
                    )
            if raw.status is ExecutionStatus.SUCCESS and output_valid is not False:
                additional = await run_validators(
                    spec.validators,
                    ValidationContext(input=decision.action.input, output=output),
                    self.validator_callbacks,
                )
                results.extend(additional)
                task_valid = (
                    all(
                        result.valid is True
                        for validator, result in zip(spec.validators, additional, strict=True)
                        if validator.required
                    )
                    if spec.validators
                    else output_valid
                )
                if task_valid is False:
                    error_type = "TaskValidationError"
                    error_message = "required task validation failed"

            ended_at = self._economic_now()
            quality_values = [
                result.quality_score for result in results if result.quality_score is not None
            ]
            receipt = ExecutionReceipt(
                decision_id=decision.decision_id,
                action_id=decision.action.action_id,
                capability=decision.action.capability,
                executor_id=spec.id,
                executor_kind=spec.kind,
                status=raw.status,
                attempt=1,
                started_at=started_at,
                ended_at=ended_at,
                estimated=candidate.estimate,
                action_features=decision.action_features,
                actual_resources=raw.resources,
                accounting=raw.accounting,
                cache_affinity=self._cache_receipt(
                    candidate.cache_affinity,
                    decision.action.context,
                    raw.resources,
                ),
                transport_success=raw.status is ExecutionStatus.SUCCESS,
                execution_success=(True if raw.status is ExecutionStatus.SUCCESS else None),
                schema_valid=output_valid,
                task_valid=task_valid,
                quality_score=(
                    sum(quality_values) / len(quality_values)
                    if quality_values
                    else candidate.estimate.quality_score
                    if raw.status is ExecutionStatus.SUCCESS and task_valid is not False
                    else None
                ),
                validation_results=results,
                output_valid=output_valid,
                error_type=error_type,
                error_message=error_message,
                trace_id=trace_id_from_span(span),
                metadata={
                    **raw.metadata,
                    "exit_code": raw.exit_code,
                    "prepared_id": context.prepared.prepared_id,
                    "authorization_kind": (
                        context.prepared.authorization_kind.value
                        if context.prepared.authorization_kind is not None
                        else None
                    ),
                    "authorization_id": context.prepared.authorization_id,
                    "quote_id": context.prepared.selected_quote_id,
                    "attempt_id": attempt_id,
                    "charge_id": charge_id,
                },
                approval_id=approval_id,
            )
            durable_attempt = self._advance_attempt(
                durable_attempt,
                ExecutionAttemptState.SETTLING,
                reason="prepared validation completed; settlement pending",
            )
        success = (
            raw.status is ExecutionStatus.SUCCESS
            and output_valid is not False
            and task_valid is not False
        )
        outcome = ExecutionOutcome(
            ok=success,
            status=raw.status,
            output=output,
            decision=decision,
            receipts=[receipt],
        )
        return outcome, receipt, usage_payload, durable_attempt

    async def execute_prepared(
        self,
        prepared_id: str,
        *,
        request: ActionRequest | dict[str, Any] | None = None,
        approved_side_effect: SideEffect = SideEffect.READ,
        payment_approved: bool = False,
        human_approved: bool = False,
        allow_unsafe_executor: bool = False,
    ) -> ExecutionOutcome:
        """Run prepared execution behind a per-call post-invocation safety boundary."""

        invocation_marker = [False]
        try:
            return await self._execute_prepared_impl(
                prepared_id,
                request=request,
                approved_side_effect=approved_side_effect,
                payment_approved=payment_approved,
                human_approved=human_approved,
                allow_unsafe_executor=allow_unsafe_executor,
                invocation_marker=invocation_marker,
            )
        except ConfigurationError as exc:
            if "legacy canonicalization is historical-only" in str(exc):
                current = self.store.get_prepared_decision(prepared_id)
                if current is not None and current.state is PreparedDecisionState.PREPARED:
                    self.store.save_prepared_transition(
                        PreparedRouteTransition(
                            prepared_id=prepared_id,
                            from_state=PreparedDecisionState.PREPARED,
                            to_state=PreparedDecisionState.CANCELLED,
                            occurred_at=self._economic_now(),
                            reason="legacy authorization cannot start after RFC 8785 cutover",
                        )
                    )
                    self._prepared_contexts.pop(prepared_id, None)
            raise
        except Exception:
            if invocation_marker[0]:
                with suppress(Exception):
                    self._mark_economic_indeterminate(
                        prepared_id,
                        "post-invocation processing did not complete",
                    )
                context = self._prepared_contexts.get(prepared_id)
                if context is not None and context.request.idempotency_key is not None:
                    self.store.mark_idempotency_indeterminate(
                        context.request.idempotency_key
                    )
            raise

    async def execute_prepared_with_fallback(
        self,
        prepared_id: str,
        *,
        request: ActionRequest | dict[str, Any] | None = None,
        approved_side_effect: SideEffect = SideEffect.READ,
        payment_approved: bool = False,
        human_approved: bool = False,
        allow_unsafe_executor: bool = False,
    ) -> ExecutionOutcome:
        """Execute once, then optionally prepare one fresh, safe fallback.

        This explicit API never retries an uncertain attempt. The first attempt
        must have reached a durable SETTLED state with a determinate FAILED or
        REJECTED result, and its route must be idempotent and no more
        consequential than a read. The failed executor is denied in a newly
        identified action, forcing a new digest, quote, reservation, and route
        decision. :meth:`execute_prepared` itself remains exact and single-use.
        """

        initial_context = self._prepared_context(prepared_id, request)
        initial_request = initial_context.request.model_copy(deep=True)
        initial_spec = self.registry.get(
            initial_context.prepared.selected_executor_id or ""
        )
        effective_policy = self._policy_for(
            self._fill_runtime_context(initial_request)
        )
        first = await self.execute_prepared(
            prepared_id,
            approved_side_effect=approved_side_effect,
            payment_approved=payment_approved,
            human_approved=human_approved,
            allow_unsafe_executor=allow_unsafe_executor,
        )
        if first.status not in {ExecutionStatus.FAILED, ExecutionStatus.REJECTED}:
            return first
        stored = self.store.get_prepared_decision(prepared_id)
        fallback = effective_policy.fallback
        if (
            stored is None
            or stored.state is not PreparedDecisionState.SETTLED
            or not fallback.enabled
            or fallback.max_attempts < 2
            or not initial_spec.idempotent
            or initial_spec.side_effect.rank > SideEffect.READ.rank
        ):
            return first

        fresh = initial_request.model_copy(deep=True)
        fresh.action_id = new_id("act")
        fresh.idempotency_key = new_id("fallback")
        fresh.constraints.denied_executor_ids = sorted(
            {
                *fresh.constraints.denied_executor_ids,
                initial_spec.id,
            }
        )
        prepared_fallback = await self.prepare_route(fresh)
        if not prepared_fallback.feasible:
            return first
        return await self.execute_prepared(
            prepared_fallback.prepared_id,
            approved_side_effect=approved_side_effect,
            payment_approved=payment_approved,
            human_approved=human_approved,
            allow_unsafe_executor=allow_unsafe_executor,
        )

    async def _execute_prepared_impl(
        self,
        prepared_id: str,
        *,
        request: ActionRequest | dict[str, Any] | None = None,
        approved_side_effect: SideEffect = SideEffect.READ,
        payment_approved: bool = False,
        human_approved: bool = False,
        allow_unsafe_executor: bool = False,
        invocation_marker: list[bool],
    ) -> ExecutionOutcome:
        """Reserve, invoke exactly one prepared route, and settle its actual charge."""

        self._ensure_open()
        context = self._prepared_context(prepared_id, request)
        prepared = context.prepared
        if prepared.selected_executor_id is None or prepared.maximum_cash_authorization is None:
            raise NoRouteError("prepared decision has no executable bounded route")
        spec = self.registry.get(prepared.selected_executor_id)
        self._require_active_spec(spec)
        if spec.side_effect.rank > approved_side_effect.rank and spec.kind not in {
            ExecutorKind.DELEGATE,
            ExecutorKind.HOST,
        }:
            raise ApprovalRequired(
                f"executor {spec.id!r} requires {spec.side_effect.value!r} approval; "
                f"approved level is {approved_side_effect.value!r}",
                executor_id=spec.id,
                required_level=spec.side_effect.value,
            )
        if (
            not spec.safe_to_auto_execute
            and spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}
            and not allow_unsafe_executor
        ):
            raise ApprovalRequired(
                f"executor {spec.id!r} requires explicit unsafe-executor approval",
                executor_id=spec.id,
                required_level="unsafe_executor",
            )

        # Re-evaluate current hard feasibility for same-process and rehydrated calls.
        live_request = self._fill_runtime_context(context.request)
        live_policy = self._policy_for(live_request)
        live_estimate = self.estimator.estimate(
            spec, live_policy, action_features(live_request.input)
        )
        if context.selected_quote is not None:
            live_estimate.cash = cash_estimate_from_quote(context.selected_quote)
        elif context.selected_offer is not None:
            quantities = {
                key: Decimal(value)
                for key, value in prepared.disclosed_quote_features.items()
                if isinstance(value, int) and not isinstance(value, bool)
            }
            live_estimate.cash = cash_estimate_from_offer(context.selected_offer, quantities)
        elif context.selected_rate_card is not None:
            live_estimate.cash = CashEstimate(
                amount_usd=prepared.maximum_cash_authorization.amount,
                upper_bound_usd=prepared.maximum_cash_authorization.amount,
                evidence=MeasurementEvidence(
                    status=EvidenceStatus.COMPLETE,
                    source=EvidenceSource.PINNED_RATE_TABLE,
                    trust=TrustLevel.VERIFIED,
                    evidence_id=context.selected_rate_card.snapshot_id,
                    observed_at=context.selected_rate_card.retrieved_at,
                ),
            )
        current = score_candidate(
            spec,
            live_estimate,
            live_policy,
            live_request.context,
            self._subscription_quota(spec, live_request.context),
        )
        if not current.feasible:
            raise NoRouteError(
                "prepared route no longer satisfies current hard policy: "
                + "; ".join(current.rejection_reasons)
            )

        authorization_kind = prepared.authorization_kind
        authorization_id = prepared.authorization_id
        is_authorized_cash = authorization_kind is not None and authorization_id is not None
        if is_authorized_cash:
            if self.budget_manager is None:
                raise ConfigurationError("prepared paid execution requires an agent budget")
            self.budget_manager.authorize_v2(
                prepared.maximum_cash_authorization,
                executor_id=spec.id,
                payment_approved=payment_approved,
                human_approved=human_approved,
            )
        elif (
            prepared.maximum_cash_authorization.amount != 0
            or prepared.expected_accounting.cash.actual_cash_cost(
                prepared.maximum_cash_authorization.currency
            )
            != Decimal(0)
        ):
            raise ConfigurationError("quote-free prepared execution is not confirmed free")

        claim_token = secrets.token_urlsafe(24)
        idempotency_key = context.request.idempotency_key
        attempt_id = new_id("attempt")
        charge_id = f"charge_{hashlib.sha256(prepared_id.encode()).hexdigest()}"
        durable_attempt = self._create_claimed_attempt(
            decision_id=prepared_id,
            prepared_id=prepared_id,
            action_digest_value=prepared.action_digest,
            spec=spec,
            attempt_id=attempt_id,
        )
        approval_id: str | None = None
        if (
            spec.side_effect.rank > SideEffect.READ.rank
            or payment_approved
            or human_approved
        ):
            approval = ActionApprovalRecord(
                action_digest=prepared.action_digest,
                policy_digest=prepared.effective_policy_digest,
                prepared_id=prepared_id,
                attempt_id=attempt_id,
                granted_side_effect=approved_side_effect,
                payment_approved=payment_approved,
                human_approved=human_approved,
                source=ApprovalSource.EMBEDDED_CALLER,
                granted_at=self._economic_now(),
            )
            self.store.save_action_approval(approval)
            approval_id = approval.approval_id
        reservation: PaymentReservationV2 | None = None
        prepared_claimed = False
        invocation_started = False
        try:
            if idempotency_key is not None:
                self.store.claim_prepared_decision_with_action_idempotency(
                    prepared_id,
                    claim_token=claim_token,
                    claimed_at=self._economic_now(),
                    idempotency_key=idempotency_key,
                    action_digest=prepared.action_digest,
                )
            else:
                self.store.claim_prepared_decision(
                    prepared_id,
                    claim_token=claim_token,
                    claimed_at=self._economic_now(),
                )
            prepared_claimed = True
            if is_authorized_cash:
                assert self.budget_manager is not None
                assert authorization_kind is not None and authorization_id is not None
                reservation = await self.budget_manager.reserve_v2(
                    prepared_id=prepared_id,
                    quote_id=prepared.selected_quote_id,
                    authorization_kind=authorization_kind,
                    authorization_id=authorization_id,
                    action_id=prepared.action_id,
                    attempt_id=attempt_id,
                    charge_id=charge_id,
                    maximum_amount=prepared.maximum_cash_authorization,
                    idempotency_key=f"{prepared_id}:reserve",
                    claim_token=claim_token,
                    payment_approved=payment_approved,
                    human_approved=human_approved,
                    executor_id=spec.id,
                )
                durable_attempt = self._advance_attempt(
                    durable_attempt,
                    ExecutionAttemptState.RESERVED,
                    reason="cash reservation recorded",
                    cash_reservation_ids=(reservation.reservation_id,),
                )
                # The hold does not grant execution authority. Recheck route and
                # economic trust after reservation and immediately before INVOKING.
                if self._economic_now() >= prepared.expires_at:
                    raise ConfigurationError(
                        "prepared decision expired while reserving payment"
                    )
                self._require_active_spec(spec)
                if executor_fingerprint(spec) != prepared.selected_executor_fingerprint:
                    raise NoRouteError(
                        "prepared executor drifted after reservation; invocation denied"
                    )
                if context.selected_quote is not None:
                    if context.selected_quote.expires_at <= self._economic_now():
                        raise ConfigurationError("selected quote expired while reserving payment")
                    reason = self._verify_economic_record(
                        context.selected_quote,
                        provider_id=context.selected_quote.provider_id,
                        capability=context.selected_quote.capability,
                        signed_at=context.selected_quote.issued_at,
                    )
                    if reason is not None:
                        raise ConfigurationError(
                            f"selected quote trust changed after reservation: {reason}"
                        )
                elif context.selected_offer is not None:
                    self._prepared_offer(prepared, spec)
                elif context.selected_rate_card is not None:
                    self._prepared_rate_card(prepared, spec)
                post_reserve_request = self._fill_runtime_context(context.request)
                post_reserve_policy = self._policy_for(post_reserve_request)
                if (
                    self._effective_policy_digest(post_reserve_policy)
                    != prepared.effective_policy_digest
                ):
                    raise ConfigurationError("effective policy changed while reserving payment")
                post_reserve_estimate = self.estimator.estimate(
                    spec,
                    post_reserve_policy,
                    action_features(post_reserve_request.input),
                )
                if context.selected_quote is not None:
                    post_reserve_estimate.cash = cash_estimate_from_quote(
                        context.selected_quote
                    )
                elif context.selected_offer is not None:
                    quantities = {
                        key: Decimal(value)
                        for key, value in prepared.disclosed_quote_features.items()
                        if isinstance(value, int) and not isinstance(value, bool)
                    }
                    post_reserve_estimate.cash = cash_estimate_from_offer(
                        context.selected_offer,
                        quantities,
                    )
                elif context.selected_rate_card is not None:
                    post_reserve_estimate.cash = CashEstimate(
                        amount_usd=prepared.maximum_cash_authorization.amount,
                        upper_bound_usd=prepared.maximum_cash_authorization.amount,
                        evidence=MeasurementEvidence(
                            status=EvidenceStatus.COMPLETE,
                            source=EvidenceSource.PINNED_RATE_TABLE,
                            trust=TrustLevel.VERIFIED,
                            evidence_id=context.selected_rate_card.snapshot_id,
                            observed_at=context.selected_rate_card.retrieved_at,
                        ),
                    )
                post_reserve_score = score_candidate(
                    spec,
                    post_reserve_estimate,
                    post_reserve_policy,
                    post_reserve_request.context,
                    self._subscription_quota(spec, post_reserve_request.context),
                )
                if not post_reserve_score.feasible:
                    raise NoRouteError(
                        "prepared route became infeasible while reserving payment: "
                        + "; ".join(post_reserve_score.rejection_reasons)
                    )
                if context.selected_quote is not None:
                    self._save_economic_link(
                        charge_id=charge_id,
                        evidence_level=EconomicEvidenceLevel.SIGNED_QUOTE,
                        evidence_type="bounded_quote",
                        evidence_id=context.selected_quote.quote_id,
                        payload=context.selected_quote,
                        authoritative=False,
                    )
                with self._route_activation_lock:
                    # This is the same-process authorization point. Supported
                    # activation/suspension mutations take the same lock, so a
                    # route cannot be revoked between this final check and the
                    # durable RESERVED -> INVOKING transition.
                    self._require_active_spec(spec)
                    if (
                        executor_fingerprint(spec)
                        != prepared.selected_executor_fingerprint
                    ):
                        raise NoRouteError(
                            "prepared executor drifted at the invocation gate"
                        )
                    self.store.claim_prepared_for_paid_invocation(
                        prepared_id,
                        claim_token=claim_token,
                        expected_action_digest=prepared.action_digest,
                        expected_policy_digest=prepared.effective_policy_digest,
                        expected_executor_id=spec.id,
                        expected_executor_fingerprint=(
                            prepared.selected_executor_fingerprint or ""
                        ),
                        expected_authorization_kind=authorization_kind,
                        expected_authorization_id=authorization_id,
                        invoked_at=self._economic_now(),
                    )
                invocation_started = True
                invocation_marker[0] = True
            else:
                durable_attempt = self._advance_attempt(
                    durable_attempt,
                    ExecutionAttemptState.RESERVED,
                    reason="zero cash and capacity reservation recorded",
                )
                self.store.claim_prepared_for_invocation(
                    prepared_id,
                    claim_token=claim_token,
                    expected_action_digest=prepared.action_digest,
                    expected_policy_digest=prepared.effective_policy_digest,
                    expected_executor_fingerprint=(prepared.selected_executor_fingerprint or ""),
                    invoked_at=self._economic_now(),
                )
                invocation_started = True
                invocation_marker[0] = True
            durable_attempt = self._advance_attempt(
                durable_attempt,
                ExecutionAttemptState.INVOKING,
                reason="prepared external invocation boundary entered",
                invocation_start_digest=deterministic_digest(
                    {
                        "attempt_id": attempt_id,
                        "executor_fingerprint": durable_attempt.executor_fingerprint,
                        "prepared_id": prepared_id,
                    }
                ),
            )
            if idempotency_key is not None:
                self.store.mark_idempotency_executing(idempotency_key)
            outcome, receipt, usage_payload, durable_attempt = await self._invoke_prepared_once(
                context,
                spec=spec,
                attempt_id=attempt_id,
                charge_id=charge_id,
                approval_id=approval_id,
                durable_attempt=durable_attempt,
                approved_side_effect=approved_side_effect,
            )
            # Persist a sanitized local execution fact before any usage parsing or
            # payment call. Recovery may enrich this receipt, but must never need
            # to repeat the external action to prove that invocation returned.
            self._save_receipt(receipt)
        except Exception:
            if invocation_started:
                self._mark_economic_indeterminate(
                    prepared_id, "external invocation or evidence processing raised"
                )
                if idempotency_key is not None:
                    self.store.mark_idempotency_indeterminate(idempotency_key)
            else:
                can_abandon_action_claim = reservation is None
                if reservation is not None and self.budget_manager is not None:
                    try:
                        await self.budget_manager.release_v2(
                            reservation.reservation_id,
                            reason="pre-invocation failure released the reservation",
                            idempotency_key=f"{prepared_id}:preinvoke-release",
                        )
                    except Exception:
                        # Retain the exact action binding while the hold is
                        # unresolved. Recovery may resume only its durable intent.
                        can_abandon_action_claim = False
                    else:
                        can_abandon_action_claim = True
                if (
                    idempotency_key is not None
                    and prepared_claimed
                    and can_abandon_action_claim
                ):
                    with suppress(Exception):
                        self.store.abandon_prepared_action_idempotency(
                            prepared_id,
                            action_digest=prepared.action_digest,
                            abandoned_at=self._economic_now(),
                            claim_token=claim_token,
                        )
                stored_attempt = self.store.get_execution_attempt(attempt_id)
                if stored_attempt is not None and stored_attempt.state in {
                    ExecutionAttemptState.CLAIMED,
                    ExecutionAttemptState.RESERVED,
                }:
                    with suppress(Exception):
                        self._advance_attempt(
                            stored_attempt,
                            ExecutionAttemptState.FAILED,
                            reason="prepared execution failed before invocation",
                        )
            raise

        if reservation is None:
            receipt.accounting.cash = prepared.expected_accounting.cash.model_copy(deep=True)
            receipt.actual_resources.monetary_usd = mirror_actual_cash(receipt.accounting)
            receipt.metadata["cash_evidence_level"] = EconomicEvidenceLevel.OPERATOR_ATTESTED.value
            self._transition_prepared(
                prepared_id,
                PreparedDecisionState.INVOKING,
                PreparedDecisionState.SETTLING,
                "confirmed-free execution completed",
            )
            self._transition_prepared(
                prepared_id,
                PreparedDecisionState.SETTLING,
                PreparedDecisionState.SETTLED,
                "confirmed-free accounting finalized",
            )
            self._save_receipt(receipt)
            self._observe_receipt(spec, receipt)
            durable_attempt = self._advance_attempt(
                durable_attempt,
                self._terminal_attempt_state(
                    receipt, retry_eligible=durable_attempt.retry_eligible
                ),
                reason="confirmed-free prepared execution finalized",
                terminal_receipt_ids=(receipt.receipt_id,),
            )
            if idempotency_key is not None:
                self.store.complete_idempotency(
                    idempotency_key,
                    decision_id=context.route_decision.decision_id,
                    status=outcome.status.value,
                    receipt_ids=[receipt.receipt_id],
                )
            self._prepared_contexts.pop(prepared_id, None)
            return outcome

        try:
            self._transition_prepared(
                prepared_id,
                PreparedDecisionState.INVOKING,
                PreparedDecisionState.AWAITING_USAGE,
                "external invocation returned; evaluating usage",
            )
        except Exception:
            self._mark_economic_indeterminate(
                prepared_id,
                "post-invocation state transition failed",
            )
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            raise
        usage_statement: UsageStatement | None = None
        try:
            if usage_payload is not None:
                usage_statement = (
                    usage_payload
                    if isinstance(usage_payload, UsageStatement)
                    else UsageStatement.model_validate(usage_payload)
                )
                self._verify_usage_statement(
                    usage_statement,
                    prepared=prepared,
                    spec=spec,
                    attempt_id=attempt_id,
                    local_receipt=receipt,
                )
                self.store.save_usage_statement(usage_statement)
                usage_link = self._save_economic_link(
                    charge_id=charge_id,
                    evidence_level=EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
                    evidence_type="usage_statement",
                    evidence_id=usage_statement.usage_statement_id,
                    payload=usage_statement,
                    authoritative=False,
                )
                receipt.accounting.cash = cash_accounting_from_usage_statement(
                    usage_statement,
                    charge_id=charge_id,
                    prior=receipt.accounting.cash,
                )
                receipt.metadata["usage_statement_id"] = usage_statement.usage_statement_id
            else:
                usage_link = None
        except Exception:
            self._mark_economic_indeterminate(
                prepared_id, "provider usage evidence is invalid or conflicting"
            )
            self._save_receipt(receipt)
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            raise

        if usage_statement is not None and not self._provider_status_consistent(
            receipt.status, usage_statement.execution_status
        ):
            self._mark_economic_indeterminate(
                prepared_id,
                "local and provider execution status evidence conflict",
            )
            receipt.metadata["cash_evidence_level"] = (
                EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT.value
            )
            self._save_receipt(receipt)
            self._observe_receipt(spec, receipt)
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            return outcome.model_copy(update={"ok": False})

        quote = context.selected_quote
        if quote is None:
            offer = context.selected_offer
            rate_card = context.selected_rate_card
            basis_amount: CurrencyAmount | None = None
            basis_level = EconomicEvidenceLevel.UNKNOWN
            basis_type = ""
            basis_id = ""
            basis_payload: CapabilityOffer | RateCardSnapshot | None = None
            if offer is not None and usage_statement is None:
                basis_amount = self._billable_amount_for_offer(offer, prepared, receipt)
                basis_level = EconomicEvidenceLevel.PUBLISHED_OFFER
                basis_type = "capability_offer"
                basis_id = offer.offer_id
                basis_payload = offer
            elif rate_card is not None and usage_statement is None:
                result_accepted = (
                    receipt.status is ExecutionStatus.SUCCESS
                    and receipt.schema_valid is not False
                    and receipt.task_valid is not False
                )
                basis_amount = (
                    prepared.maximum_cash_authorization if result_accepted else None
                )
                basis_level = EconomicEvidenceLevel.STATIC_PRIOR
                basis_type = "rate_card_snapshot"
                basis_id = prepared.selected_rate_card_id or ""
                basis_payload = rate_card
            if basis_payload is None or basis_amount is None:
                self._mark_economic_indeterminate(
                    prepared_id,
                    "non-quote authorization charge is not safely determinable",
                )
                self._save_receipt(receipt)
                if idempotency_key is not None:
                    self.store.mark_idempotency_indeterminate(idempotency_key)
                return outcome.model_copy(update={"ok": False})
            self._transition_prepared(
                prepared_id,
                PreparedDecisionState.AWAITING_USAGE,
                PreparedDecisionState.SETTLING,
                "fixed non-quote authorization charge determined",
            )
            assert self.budget_manager is not None
            basis_link = self._save_economic_link(
                charge_id=charge_id,
                evidence_level=basis_level,
                evidence_type=basis_type,
                evidence_id=basis_id,
                payload=basis_payload,
                authoritative=False,
            )
            basis_evidence = SettlementEvidence(
                charge_id=charge_id,
                evidence_level=basis_level,
                evidence_digest=canonical_digest(basis_payload),
            )
            try:
                settlement = await self.budget_manager.settle_v2(
                    reservation.reservation_id,
                    actual_amount=basis_amount,
                    evidence=basis_evidence,
                    idempotency_key=f"{prepared_id}:settle",
                )
            except Exception:
                self._mark_economic_indeterminate(
                    prepared_id, "payment settlement adapter failed"
                )
                if idempotency_key is not None:
                    self.store.mark_idempotency_indeterminate(idempotency_key)
                raise
            receipt.accounting.cash = cash_accounting_from_settlement(
                settlement,
                prior=receipt.accounting.cash,
            )
            receipt.actual_resources.monetary_usd = mirror_actual_cash(receipt.accounting)
            receipt.metadata.update(
                {
                    "settlement_id": settlement.settlement_id,
                    "cash_evidence_level": settlement.evidence_level.value,
                }
            )
            self._save_economic_link(
                charge_id=charge_id,
                evidence_level=settlement.evidence_level,
                evidence_type="settlement_receipt",
                evidence_id=settlement.settlement_id,
                payload=settlement,
                authoritative=True,
                supersedes_link_id=basis_link.link_id,
            )
            self._save_receipt(receipt)
            self._observe_receipt(spec, receipt)
            durable_attempt = self._advance_attempt(
                durable_attempt,
                self._terminal_attempt_state(
                    receipt, retry_eligible=durable_attempt.retry_eligible
                ),
                reason="prepared settlement finalized",
                terminal_receipt_ids=(receipt.receipt_id,),
            )
            if idempotency_key is not None:
                self.store.complete_prepared_action_idempotency(
                    prepared_id,
                    action_digest=prepared.action_digest,
                    decision_id=context.route_decision.decision_id,
                    status=outcome.status.value,
                    receipt_id=receipt.receipt_id,
                )
            self._prepared_contexts.pop(prepared_id, None)
            return outcome

        provider_status = (
            usage_statement.execution_status
            if usage_statement is not None
            else self._provider_status_for_local(receipt.status)
        )
        actual_usage_amount = (
            usage_statement.provider_calculated_amount
            if usage_statement is not None
            else (
                CurrencyAmount(
                    amount=known_local_amount,
                    currency=quote.maximum_amount.currency,
                )
                if (
                    known_local_amount := receipt.accounting.cash.actual_cash_cost(
                        quote.maximum_amount.currency
                    )
                )
                is not None
                else None
            )
        )
        if (
            actual_usage_amount is not None
            and actual_usage_amount.amount > quote.maximum_amount.amount
        ):
            if usage_statement is not None:
                self.store.save_pricing_dispute(
                    PricingDispute(
                        dispute_id=new_id("dispute"),
                        prepared_id=prepared_id,
                        quote_id=quote.quote_id,
                        usage_statement_id=usage_statement.usage_statement_id,
                        provider_id=quote.provider_id,
                        quoted_maximum=quote.maximum_amount,
                        provider_claimed_amount=actual_usage_amount,
                        reason="provider usage amount exceeds the signed quote maximum",
                        created_at=self._economic_now(),
                    )
                )
            self._mark_economic_indeterminate(
                prepared_id, "provider claimed an amount above the signed maximum"
            )
            current_prepared = self.store.get_prepared_decision(prepared_id)
            if current_prepared is not None and current_prepared.state is PreparedDecisionState.INDETERMINATE:
                self._transition_prepared(
                    prepared_id,
                    PreparedDecisionState.INDETERMINATE,
                    PreparedDecisionState.DISPUTED,
                    "provider amount exceeds signed maximum",
                )
            self._save_receipt(receipt)
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            return outcome.model_copy(update={"ok": False})

        if quote.billing_trigger is BillingTrigger.ON_ATTEMPT:
            provider_started = True
        elif usage_statement is None:
            provider_started = receipt.status is ExecutionStatus.SUCCESS
        else:
            provider_started = (
                usage_statement.started_at is not None
                or usage_statement.execution_status is ProviderExecutionStatus.SUCCESS
            )
        provider_start_ambiguous = (
            quote.billing_trigger is BillingTrigger.ON_PROVIDER_START
            and not provider_started
        )
        actual_amount = (
            None
            if provider_start_ambiguous
            else billable_amount_for_execution(
                quote,
                execution_status=provider_status,
                provider_started=provider_started,
                result_accepted=(
                    receipt.status is ExecutionStatus.SUCCESS
                    and receipt.output_valid is not False
                    and receipt.task_valid is not False
                ),
                actual_usage_amount=actual_usage_amount,
            )
        )
        if receipt.status is ExecutionStatus.TIMEOUT and usage_statement is None:
            actual_amount = None
        if actual_amount is None:
            self._mark_economic_indeterminate(
                prepared_id, "actual billable amount is not safely determinable"
            )
            receipt.metadata["cash_evidence_level"] = (
                EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT.value
                if usage_statement is not None
                else EconomicEvidenceLevel.UNKNOWN.value
            )
            self._save_receipt(receipt)
            self._observe_receipt(spec, receipt)
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            return outcome.model_copy(update={"ok": False})

        self._transition_prepared(
            prepared_id,
            PreparedDecisionState.AWAITING_USAGE,
            PreparedDecisionState.SETTLING,
            "actual charge determined from signed billing policy",
        )
        evidence = SettlementEvidence(
            charge_id=charge_id,
            evidence_level=(
                EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT
                if usage_statement is not None
                else EconomicEvidenceLevel.OPERATOR_ATTESTED
            ),
            usage_statement_id=(
                usage_statement.usage_statement_id if usage_statement is not None else None
            ),
            evidence_digest=(
                canonical_digest(usage_statement) if usage_statement is not None else None
            ),
            provider_calculated_amount=(
                actual_usage_amount if actual_usage_amount == actual_amount else None
            ),
        )
        try:
            assert self.budget_manager is not None
            settlement = await self.budget_manager.settle_v2(
                reservation.reservation_id,
                actual_amount=actual_amount,
                evidence=evidence,
                idempotency_key=f"{prepared_id}:settle",
            )
        except Exception:
            self._mark_economic_indeterminate(prepared_id, "payment settlement adapter failed")
            if idempotency_key is not None:
                self.store.mark_idempotency_indeterminate(idempotency_key)
            raise

        receipt.accounting.cash = cash_accounting_from_settlement(
            settlement,
            prior=receipt.accounting.cash,
        )
        receipt.actual_resources.monetary_usd = mirror_actual_cash(receipt.accounting)
        receipt.metadata.update(
            {
                "settlement_id": settlement.settlement_id,
                "cash_evidence_level": settlement.evidence_level.value,
            }
        )
        self._save_economic_link(
            charge_id=charge_id,
            evidence_level=settlement.evidence_level,
            evidence_type="settlement_receipt",
            evidence_id=settlement.settlement_id,
            payload=settlement,
            authoritative=True,
            supersedes_link_id=(usage_link.link_id if usage_link is not None else None),
        )
        self._save_receipt(receipt)
        self._observe_receipt(spec, receipt)
        durable_attempt = self._advance_attempt(
            durable_attempt,
            self._terminal_attempt_state(
                receipt, retry_eligible=durable_attempt.retry_eligible
            ),
            reason="prepared settlement finalized",
            terminal_receipt_ids=(receipt.receipt_id,),
        )
        if idempotency_key is not None:
            self.store.complete_prepared_action_idempotency(
                prepared_id,
                action_digest=prepared.action_digest,
                decision_id=context.route_decision.decision_id,
                status=outcome.status.value,
                receipt_id=receipt.receipt_id,
            )
        self._prepared_contexts.pop(prepared_id, None)
        return outcome

    async def economic_recover(self) -> dict[str, object]:
        """Resume only payment settlement; never repeat an external action."""

        self._ensure_open()
        scanned = settled = released = unresolved = 0
        items: list[dict[str, str]] = []
        for operation in self.store.released_payment_operations_needing_finalization():
            scanned += 1
            try:
                settlement = self.store.get_settlement_receipt(operation["settlement_id"])
                if (
                    settlement is None
                    or settlement.prepared_id != operation["prepared_id"]
                    or settlement.reservation_id != operation["reservation_id"]
                ):
                    raise ConfigurationError("durable release finalization evidence conflicts")
                self.store.complete_payment_operation(
                    "release",
                    operation["idempotency_key"],
                    result_type=type(settlement).__name__,
                    result_id=settlement.settlement_id,
                )
            except Exception:
                unresolved += 1
                items.append(
                    {"prepared_id": operation["prepared_id"], "result": "unresolved"}
                )
                continue
            released += 1
            items.append(
                {"prepared_id": operation["prepared_id"], "result": "release-finalized"}
            )
        for prepared in self.store.released_prepared_actions_needing_abandonment():
            scanned += 1
            try:
                self.store.abandon_prepared_action_idempotency(
                    prepared.prepared_id,
                    action_digest=prepared.action_digest,
                    abandoned_at=self._economic_now(),
                )
            except Exception:
                unresolved += 1
                items.append(
                    {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                )
                continue
            items.append(
                {
                    "prepared_id": prepared.prepared_id,
                    "result": "released-action-abandoned",
                }
            )
        for action in self.store.free_actions_needing_finalization():
            scanned += 1
            receipt_id = action["receipt_id"]
            decision_id = action["decision_id"]
            status = action["status"]
            if receipt_id is None or decision_id is None or status is None:
                unresolved += 1
                items.append(
                    {"prepared_id": action["prepared_id"], "result": "unresolved"}
                )
                continue
            try:
                free_prepared = self.store.get_prepared_decision(action["prepared_id"])
                free_receipt = self.store.get_receipt(receipt_id)
                if free_prepared is None or free_receipt is None:
                    raise ConfigurationError(
                        "confirmed-free recovery evidence is incomplete"
                    )
                self.store.settle_recovered_free_prepared(
                    action["prepared_id"],
                    receipt_id=receipt_id,
                    recovered_at=self._economic_now(),
                )
                free_receipt.accounting.cash = (
                    free_prepared.expected_accounting.cash.model_copy(deep=True)
                )
                free_receipt.actual_resources.monetary_usd = mirror_actual_cash(
                    free_receipt.accounting
                )
                free_receipt.metadata["cash_evidence_level"] = (
                    EconomicEvidenceLevel.OPERATOR_ATTESTED.value
                )
                self._save_receipt(free_receipt)
                try:
                    if free_prepared.selected_executor_id is not None:
                        self._observe_receipt(
                            self.registry.get(free_prepared.selected_executor_id),
                            free_receipt,
                        )
                except (ConfigurationError, KeyError):
                    pass
                self.store.complete_prepared_action_idempotency(
                    action["prepared_id"],
                    action_digest=action["action_digest"],
                    decision_id=decision_id,
                    status=status,
                    receipt_id=receipt_id,
                )
            except Exception:
                unresolved += 1
                items.append(
                    {"prepared_id": action["prepared_id"], "result": "unresolved"}
                )
                continue
            settled += 1
            items.append(
                {"prepared_id": action["prepared_id"], "result": "free-finalized"}
            )
        for prepared in self.store.settled_prepared_decisions_needing_finalization():
            scanned += 1
            try:
                reservation = self._reservation_for_prepared(prepared.prepared_id)
                settlements = self.store.list_settlement_receipts(
                    prepared_id=prepared.prepared_id,
                    limit=2,
                )
                if reservation is None or len(settlements) != 1:
                    raise ConfigurationError("settled recovery evidence is incomplete")
                local_receipt = self._receipt_for_prepared_recovery(prepared, reservation)
                if local_receipt is None:
                    raise ConfigurationError("settled recovery has no exact bound local receipt")
                self._finalize_recovered_settlement(
                    prepared=prepared,
                    reservation=reservation,
                    settlement=settlements[0],
                    receipt=local_receipt,
                )
            except Exception:
                unresolved += 1
                items.append({"prepared_id": prepared.prepared_id, "result": "unresolved"})
                continue
            settled += 1
            items.append({"prepared_id": prepared.prepared_id, "result": "finalized"})
        for prepared in self.store.recoverable_prepared_decisions(
            as_of=self._economic_now()
        ):
            scanned += 1
            reservation = self._reservation_for_prepared(prepared.prepared_id)
            if prepared.state is PreparedDecisionState.PREPARED:
                # A claim without a state transition proves no invocation started.
                # It may still belong to a live worker between claim and reserve,
                # so recovery cannot cancel it until its immutable TTL expires.
                if self._economic_now() < prepared.expires_at:
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                    )
                    continue
                try:
                    action_binding = self.store.get_prepared_action_idempotency(
                        prepared.prepared_id
                    )
                    if action_binding is not None:
                        self.store.abandon_prepared_action_idempotency(
                            prepared.prepared_id,
                            action_digest=prepared.action_digest,
                            abandoned_at=self._economic_now(),
                        )
                    else:
                        self._transition_prepared(
                            prepared.prepared_id,
                            PreparedDecisionState.PREPARED,
                            PreparedDecisionState.CANCELLED,
                            "recovery cancelled an orphaned pre-invocation claim",
                        )
                except Exception:
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                    )
                    continue
                items.append({"prepared_id": prepared.prepared_id, "result": "cancelled"})
                continue
            if prepared.state is PreparedDecisionState.RESERVED and reservation is not None:
                intent: str | None = None
                if reservation.state in {
                    PaymentReservationState.INDETERMINATE,
                    PaymentReservationState.SETTLING,
                }:
                    intent = self.store.payment_reservation_operation_intent(
                        reservation.reservation_id
                    )
                    if intent is None or not intent.startswith("release:"):
                        # Keep RESERVED so an existing release intent can still be
                        # resumed. Moving the prepared state would strand the hold.
                        unresolved += 1
                        items.append(
                            {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                        )
                        continue
                if self.budget_manager is None:
                    unresolved += 1
                    items.append({"prepared_id": prepared.prepared_id, "result": "unresolved"})
                    continue
                release_key = (
                    (intent or "").removeprefix("release:")
                    if intent is not None
                    else f"{prepared.prepared_id}:recover-release"
                )
                if release_key.endswith(":cancel-release"):
                    release_reason = "cancelled by operator before invocation"
                elif release_key.endswith(":preinvoke-release"):
                    release_reason = "pre-invocation failure released the reservation"
                elif release_key.endswith(":recover-release"):
                    release_reason = "recovery released a never-invoked reservation"
                else:
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                    )
                    continue
                try:
                    await self.budget_manager.release_v2(
                        reservation.reservation_id,
                        reason=release_reason,
                        idempotency_key=release_key,
                    )
                except Exception:
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                    )
                    continue
                released += 1
                items.append({"prepared_id": prepared.prepared_id, "result": "released"})
                continue

            statements = self.store.list_usage_statements(prepared_id=prepared.prepared_id)
            statement = statements[0] if len(statements) == 1 else None
            local_receipt = (
                self._receipt_for_prepared_recovery(prepared, reservation)
                if reservation is not None
                else None
            )
            if (
                reservation is not None
                and local_receipt is not None
                and prepared.authorization_kind
                in {
                    AuthorizationKind.PUBLISHED_OFFER,
                    AuthorizationKind.PINNED_RATE_CARD,
                }
            ):
                try:
                    basis: CapabilityOffer | RateCardSnapshot | None
                    if prepared.authorization_kind is AuthorizationKind.PUBLISHED_OFFER:
                        basis = self._historical_prepared_offer(
                            prepared,
                            reservation,
                            local_receipt,
                        )
                        actual_amount = self._billable_amount_for_offer(
                            basis,
                            prepared,
                            local_receipt,
                        )
                        basis_level = EconomicEvidenceLevel.PUBLISHED_OFFER
                        basis_type = "capability_offer"
                        basis_id = basis.offer_id
                    else:
                        rate_card = self._prepared_rate_card(
                            prepared,
                            None,
                            historical=True,
                        )
                        basis = rate_card
                        result_accepted = (
                            local_receipt.status is ExecutionStatus.SUCCESS
                            and local_receipt.schema_valid is not False
                            and local_receipt.task_valid is not False
                        )
                        actual_amount = (
                            prepared.maximum_cash_authorization
                            if result_accepted
                            else None
                        )
                        basis_level = EconomicEvidenceLevel.STATIC_PRIOR
                        basis_type = "rate_card_snapshot"
                        basis_id = prepared.selected_rate_card_id or ""
                    if basis is None:
                        raise ConfigurationError("fixed authorization evidence is missing")
                    if actual_amount is None:
                        raise ConfigurationError("fixed authorization charge is indeterminate")
                    current = self.store.get_prepared_decision(prepared.prepared_id)
                    if current is None:
                        raise ConfigurationError("prepared recovery record disappeared")
                    if current.state is PreparedDecisionState.INVOKING:
                        self._transition_prepared(
                            prepared.prepared_id,
                            PreparedDecisionState.INVOKING,
                            PreparedDecisionState.AWAITING_USAGE,
                            "recovery found durable fixed-authorization execution evidence",
                        )
                        current = self.store.get_prepared_decision(prepared.prepared_id)
                    if current is not None and current.state in {
                        PreparedDecisionState.AWAITING_USAGE,
                        PreparedDecisionState.INDETERMINATE,
                    }:
                        self._transition_prepared(
                            prepared.prepared_id,
                            current.state,
                            PreparedDecisionState.SETTLING,
                            "recovery resumed fixed-authorization settlement",
                        )
                    elif current is None or current.state is not PreparedDecisionState.SETTLING:
                        raise ConfigurationError("fixed authorization is not recoverable")
                    if self.budget_manager is None:
                        raise ConfigurationError("economic recovery requires an agent budget")
                    self._save_economic_link(
                        charge_id=reservation.charge_id,
                        evidence_level=basis_level,
                        evidence_type=basis_type,
                        evidence_id=basis_id,
                        payload=basis,
                        authoritative=False,
                    )
                    settlement = await self.budget_manager.settle_v2(
                        reservation.reservation_id,
                        actual_amount=actual_amount,
                        evidence=SettlementEvidence(
                            charge_id=reservation.charge_id,
                            evidence_level=basis_level,
                            evidence_digest=canonical_digest(basis),
                        ),
                        idempotency_key=f"{prepared.prepared_id}:settle",
                    )
                    self._finalize_recovered_settlement(
                        prepared=prepared,
                        reservation=reservation,
                        settlement=settlement,
                        receipt=local_receipt,
                    )
                except Exception:
                    current = self.store.get_prepared_decision(prepared.prepared_id)
                    if (
                        current is not None
                        and current.state is not PreparedDecisionState.INDETERMINATE
                    ):
                        self._mark_economic_indeterminate(
                            prepared.prepared_id,
                            "fixed-authorization recovery remains unresolved",
                        )
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "unresolved"}
                    )
                    continue
                settled += 1
                items.append({"prepared_id": prepared.prepared_id, "result": "settled"})
                continue
            quote = (
                self.store.get_bounded_quote(prepared.selected_quote_id)
                if prepared.selected_quote_id is not None
                else None
            )
            if (
                reservation is None
                or statement is None
                or quote is None
                or local_receipt is None
                or not self._provider_status_consistent(
                    local_receipt.status, statement.execution_status
                )
            ):
                if prepared.state is not PreparedDecisionState.INDETERMINATE and prepared.state in {
                    PreparedDecisionState.INVOKING,
                    PreparedDecisionState.AWAITING_USAGE,
                    PreparedDecisionState.SETTLING,
                }:
                    self._mark_economic_indeterminate(
                        prepared.prepared_id, "recovery lacks determinate signed usage evidence"
                    )
                unresolved += 1
                items.append({"prepared_id": prepared.prepared_id, "result": "unresolved"})
                continue
            try:
                self._verify_usage_statement(
                    statement,
                    prepared=prepared,
                    spec=None,
                    attempt_id=reservation.attempt_id,
                    local_receipt=local_receipt,
                )
                claimed = statement.provider_calculated_amount
                if claimed is not None and claimed.amount > quote.maximum_amount.amount:
                    self.store.save_pricing_dispute(
                        PricingDispute(
                            dispute_id=new_id("dispute"),
                            prepared_id=prepared.prepared_id,
                            quote_id=quote.quote_id,
                            usage_statement_id=statement.usage_statement_id,
                            provider_id=quote.provider_id,
                            quoted_maximum=quote.maximum_amount,
                            provider_claimed_amount=claimed,
                            reason="provider usage amount exceeds the signed quote maximum",
                            created_at=self._economic_now(),
                        )
                    )
                    self._mark_economic_indeterminate(
                        prepared.prepared_id,
                        "provider claimed an amount above the signed maximum",
                    )
                    current = self.store.get_prepared_decision(prepared.prepared_id)
                    if (
                        current is not None
                        and current.state is PreparedDecisionState.INDETERMINATE
                    ):
                        self._transition_prepared(
                            prepared.prepared_id,
                            PreparedDecisionState.INDETERMINATE,
                            PreparedDecisionState.DISPUTED,
                            "provider amount exceeds signed maximum",
                        )
                    unresolved += 1
                    items.append(
                        {"prepared_id": prepared.prepared_id, "result": "disputed"}
                    )
                    continue
                provider_started = (
                    quote.billing_trigger is BillingTrigger.ON_ATTEMPT
                    or statement.started_at is not None
                    or statement.execution_status is ProviderExecutionStatus.SUCCESS
                )
                actual_amount = (
                    None
                    if quote.billing_trigger is BillingTrigger.ON_PROVIDER_START
                    and not provider_started
                    else billable_amount_for_execution(
                        quote,
                        execution_status=statement.execution_status,
                        provider_started=provider_started,
                        result_accepted=(
                            local_receipt.status is ExecutionStatus.SUCCESS
                            and local_receipt.schema_valid is not False
                            and local_receipt.task_valid is not False
                        ),
                        actual_usage_amount=claimed,
                    )
                )
                if actual_amount is None:
                    raise ConfigurationError("recovery cannot determine an actual charge")
                current = self.store.get_prepared_decision(prepared.prepared_id)
                if current is None:
                    raise ConfigurationError("prepared recovery record disappeared")
                if current.state is PreparedDecisionState.INDETERMINATE:
                    self._transition_prepared(
                        prepared.prepared_id,
                        PreparedDecisionState.INDETERMINATE,
                        PreparedDecisionState.SETTLING,
                        "recovery resumed idempotent settlement",
                    )
                elif current.state is PreparedDecisionState.AWAITING_USAGE:
                    self._transition_prepared(
                        prepared.prepared_id,
                        PreparedDecisionState.AWAITING_USAGE,
                        PreparedDecisionState.SETTLING,
                        "recovery resumed settlement after durable usage",
                    )
                elif current.state is not PreparedDecisionState.SETTLING:
                    raise ConfigurationError("prepared decision is not recoverable for settlement")
                if self.budget_manager is None:
                    raise ConfigurationError("economic recovery requires an agent budget")
                settlement = await self.budget_manager.settle_v2(
                    reservation.reservation_id,
                    actual_amount=actual_amount,
                    evidence=SettlementEvidence(
                        charge_id=reservation.charge_id,
                        evidence_level=EconomicEvidenceLevel.SIGNED_USAGE_STATEMENT,
                        usage_statement_id=statement.usage_statement_id,
                        evidence_digest=canonical_digest(statement),
                        provider_calculated_amount=(
                            claimed if claimed == actual_amount else None
                        ),
                    ),
                    idempotency_key=f"{prepared.prepared_id}:settle",
                )
                self._finalize_recovered_settlement(
                    prepared=prepared,
                    reservation=reservation,
                    settlement=settlement,
                    receipt=local_receipt,
                )
            except Exception:
                current = self.store.get_prepared_decision(prepared.prepared_id)
                if current is not None and current.state is not PreparedDecisionState.INDETERMINATE:
                    self._mark_economic_indeterminate(
                        prepared.prepared_id, "economic recovery remains unresolved"
                    )
                unresolved += 1
                items.append({"prepared_id": prepared.prepared_id, "result": "unresolved"})
                continue
            settled += 1
            items.append({"prepared_id": prepared.prepared_id, "result": "settled"})
        return {
            "scanned": scanned,
            "settled": settled,
            "released": released,
            "unresolved": unresolved,
            "items": items,
        }

    async def cancel_prepared(self, prepared_id: str) -> PreparedRouteDecision:
        """Cancel before invocation; release a reserved maximum idempotently."""

        prepared = self.get_prepared_decision(prepared_id)
        if prepared.state is PreparedDecisionState.RESERVED:
            reservation = self._reservation_for_prepared(prepared_id)
            if reservation is None or self.budget_manager is None:
                raise ConfigurationError("reserved prepared decision has no payment reservation")
            await self.budget_manager.release_v2(
                reservation.reservation_id,
                reason="cancelled by operator before invocation",
                idempotency_key=f"{prepared_id}:cancel-release",
            )
            self._prepared_contexts.pop(prepared_id, None)
            released = self.store.get_prepared_decision(prepared_id)
            if released is None:
                raise ConfigurationError("prepared decision disappeared after release")
            return released
        if prepared.state is not PreparedDecisionState.PREPARED:
            raise ConfigurationError(
                f"prepared decision cannot be casually cancelled from {prepared.state.value}"
            )
        self.store.save_prepared_transition(
            PreparedRouteTransition(
                prepared_id=prepared_id,
                from_state=PreparedDecisionState.PREPARED,
                to_state=PreparedDecisionState.CANCELLED,
                occurred_at=self._economic_now(),
                reason="cancelled by operator before reservation",
            )
        )
        self._prepared_contexts.pop(prepared_id, None)
        cancelled = self.store.get_prepared_decision(prepared_id)
        if cancelled is None:  # pragma: no cover - transition FK invariant
            raise ConfigurationError("prepared decision disappeared after cancellation")
        return cancelled

    async def discover(self, capability: str) -> list[ProviderDescriptor]:
        """Persist matching external routes as inert candidates."""

        self._ensure_open()
        providers = await self.provider_registry.discover(capability)
        for provider in providers:
            self.providers[provider.provider_id] = provider
            for spec in provider.executors:
                if spec.capability == capability:
                    self.ingest_candidate(spec, source_id=f"discovery:{provider.provider_id}")
        return providers

    async def ingest_provider_package(
        self,
        path: str | Path,
        *,
        source_id: str | None = None,
        allow_remote_artifacts: bool | None = None,
    ) -> tuple[RouteCandidate, ...]:
        """Verify one supported provider package and persist inert candidates."""

        self._ensure_open()
        config = self.manifest.provider_packages
        ingestor = self._provider_package_ingestor()
        return await ingestor.ingest(
            path,
            source_id=source_id,
            allow_remote_artifacts=(
                config.allow_remote_artifacts
                if allow_remote_artifacts is None
                else allow_remote_artifacts and config.allow_remote_artifacts
            ),
            allowed_artifact_hosts=config.allowed_artifact_hosts,
            allow_private_networks=config.allow_private_addresses,
            allow_self_asserted_priors=config.allow_self_asserted_priors,
            forbidden_executor_ids=frozenset(
                item.id for item in self.registry.all(include_disabled=True)
            ),
        )

    def _provider_package_ingestor(self) -> ProviderPackageIngestor:
        config = self.manifest.provider_packages
        artifact_root = _provider_artifact_root(
            config.artifact_root,
            self.manifest_path,
        )
        verifier = self._refresh_economic_verifier()
        trust = verifier.store if verifier is not None else TrustStore()
        return ProviderPackageIngestor(
            self.store,
            ContentArtifactStore(
                artifact_root,
                maximum_bytes=config.maximum_artifact_bytes,
            ),
            trust,
            clock=self._economic_now,
        )

    def inspect_candidate(self, executor_id: str) -> dict[str, Any]:
        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None:
            raise ConfigurationError(f"unknown candidate {executor_id!r}")
        snapshot = (
            self.store.get_candidate_verification_snapshot(
                candidate.verification_snapshot_id
            )
            if candidate.verification_snapshot_id is not None
            else None
        )
        package = (
            self.store.get_provider_package(candidate.package_digest)
            if candidate.package_digest is not None
            else None
        )
        evidence = self.store.list_evidence_records(executor_id)
        acceptances = self.store.list_evidence_acceptances(executor_id)
        smoke = self.store.latest_smoke_test_report(executor_id)
        next_command = (
            f"aeep candidate activate {executor_id}"
            if candidate.status is RouteLifecycle.QUALIFIED
            else f"aeep candidate smoke {executor_id}"
            if package is not None and (smoke is None or smoke.status is not SmokeStatus.PASSED)
            else f"aeep candidate qualify {executor_id} --reuse-evidence"
            if package is not None
            else f"aeep candidate qualify {executor_id} --cases @cases.yaml"
        )
        return {
            "candidate": candidate.model_dump(mode="json"),
            "package": (
                {
                    "package_id": package.metadata.package_id,
                    "version": package.metadata.version,
                    "digest": candidate.package_digest,
                }
                if package is not None
                else None
            ),
            "verification": snapshot.model_dump(mode="json") if snapshot else None,
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "acceptances": [item.model_dump(mode="json") for item in acceptances],
            "smoke": smoke.model_dump(mode="json") if smoke else None,
            "next": next_command,
        }

    async def refresh_candidate(self, executor_id: str) -> RouteCandidate:
        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None:
            raise ConfigurationError(f"unknown candidate {executor_id!r}")
        if not candidate.source_id.startswith("package-file:"):
            raise ConfigurationError("candidate refresh requires a local package-file source")
        path = candidate.source_id.removeprefix("package-file:")
        refreshed = await self.ingest_provider_package(path, source_id=candidate.source_id)
        return next(item for item in refreshed if item.executor_id == executor_id)

    async def smoke_candidate(self, executor_id: str) -> tuple[SmokeTestReport, ...]:
        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None or candidate.package_digest is None:
            raise ConfigurationError("smoke requires a provider-package candidate")
        if candidate.status not in {RouteLifecycle.CANDIDATE, RouteLifecycle.SUSPENDED}:
            raise ConfigurationError("smoke requires a non-active candidate")
        snapshot = self.store.get_candidate_verification_snapshot(
            candidate.verification_snapshot_id or ""
        )
        package = self.store.get_provider_package(candidate.package_digest)
        if snapshot is None or package is None:
            raise ConfigurationError("candidate package verification is unavailable")
        if (
            snapshot.integrity_status is not PackageIntegrityStatus.VERIFIED
            or snapshot.fingerprint_status is not FingerprintStatus.MATCHED
            or snapshot.artifact_status is not ArtifactStatus.VERIFIED
        ):
            raise ConfigurationError("candidate verification blocks smoke execution")
        definition = next(
            (item for item in package.spec.smoke_tests if item.route_id == executor_id),
            None,
        )
        if definition is None:
            raise ConfigurationError("candidate package does not define a smoke test")
        route = next(item for item in package.spec.routes if item.route_id == executor_id)
        if route.executor.side_effect.rank > SideEffect.READ.rank or not route.executor.idempotent:
            raise ConfigurationError("automatic smoke is restricted to read-only idempotent routes")
        if portable_route_fingerprint(route, package.spec.provider.provider_id) != (
            candidate.package_fingerprint
        ):
            self.suspend_candidate(executor_id, reason="package fingerprint drift before smoke")
            raise ConfigurationError("candidate package fingerprint changed before smoke")

        spec = route.executor_spec(package.spec.provider.provider_id)
        if not runtime_route_identity_matches(route, spec):
            self.suspend_candidate(executor_id, reason="runtime executable identity mismatch")
            raise ConfigurationError("candidate runtime executable identity does not match")
        spec.side_effect = route.executor.side_effect
        spec.idempotent = route.executor.idempotent
        spec.safe_to_auto_execute = True
        require_static_qualification(spec)
        modes: tuple[Literal["cold", "warm"], ...]
        if definition.mode == "cold_then_warm":
            modes = ("cold", "warm")
        elif definition.mode == "warm":
            modes = ("warm",)
        else:
            modes = ("cold",)
        modes = modes[: definition.max_executions]
        reports: list[SmokeTestReport] = []
        shared_executor: BaseExecutor | None = None
        all_passed = True
        try:
            for index, mode in enumerate(modes, start=1):
                started = self._economic_now()
                executor = (
                    _EXECUTOR_TYPES[spec.kind]()
                    if mode == "cold"
                    else shared_executor or _EXECUTOR_TYPES[spec.kind]()
                )
                if definition.mode == "cold_then_warm" and shared_executor is None:
                    shared_executor = executor
                request = ActionRequest(
                    action_id=f"smoke_{definition.smoke_id}_{index}",
                    capability=spec.capability,
                    input=dict(definition.input),
                )
                validate_json(request.input, spec.input_schema, label="smoke input")
                raw = await executor.execute(
                    ExecutionContext(
                        request=request,
                        spec=spec,
                        estimate=spec.estimate,
                        attempt=1,
                    )
                )
                output_valid: bool | None = None
                if raw.status is ExecutionStatus.SUCCESS and spec.output_schema is not None:
                    try:
                        validate_json(raw.output, spec.output_schema, label="smoke output")
                        output_valid = True
                    except Exception:
                        output_valid = False
                validation_results = await run_validators(
                    spec.validators,
                    ValidationContext(input=request.input, output=raw.output),
                    self.validator_callbacks,
                )
                task_valid = all(item.valid is True for item in validation_results)
                ended = self._economic_now()
                cash = raw.accounting.cash.actual_cash_cost(
                    self.manifest.economic_evidence.settlement_currency
                )
                tokens = raw.resources.input_tokens + raw.resources.output_tokens
                passed = (
                    raw.status is ExecutionStatus.SUCCESS
                    and output_valid is not False
                    and task_valid
                    and (ended - started).total_seconds() * 1000 <= definition.timeout_ms
                    and (definition.max_tokens is None or tokens <= definition.max_tokens)
                    and (
                        definition.max_cash is None
                        or (
                            cash is not None
                            and definition.max_cash.currency
                            == self.manifest.economic_evidence.settlement_currency
                            and cash <= definition.max_cash.amount
                        )
                    )
                )
                receipt = ExecutionReceipt(
                    decision_id=f"smoke:{definition.smoke_id}",
                    action_id=request.action_id,
                    capability=spec.capability,
                    executor_id=spec.id,
                    executor_kind=spec.kind,
                    status=raw.status,
                    attempt=index,
                    started_at=started,
                    ended_at=ended,
                    estimated=spec.estimate,
                    action_features=action_features(request.input),
                    actual_resources=raw.resources,
                    accounting=raw.accounting,
                    transport_success=raw.status is ExecutionStatus.SUCCESS,
                    execution_success=raw.status is ExecutionStatus.SUCCESS,
                    schema_valid=output_valid,
                    task_valid=task_valid,
                    validation_results=validation_results,
                    output_valid=output_valid,
                    metadata={"smoke_definition_id": definition.smoke_id},
                )
                self._save_receipt(receipt)
                report = SmokeTestReport(
                    smoke_report_id=new_id("smoke"),
                    candidate_id=executor_id,
                    route_fingerprint=candidate.package_fingerprint,
                    smoke_definition_id=definition.smoke_id,
                    environment_digest=deterministic_digest(
                        {
                            "os": os.name,
                            "executor_kind": spec.kind.value,
                            "runtime": spec.config.get("executable_identity"),
                        }
                    ),
                    mode=mode,
                    status=(SmokeStatus.PASSED if passed else SmokeStatus.FAILED),
                    started_at=started,
                    finished_at=ended,
                    execution_receipt_id=receipt.receipt_id,
                    failure_code=(None if passed else "smoke_failed"),
                )
                reports.append(report)
                all_passed &= passed
                if mode == "cold" and shared_executor is not executor:
                    await executor.close()
        finally:
            if shared_executor is not None:
                await shared_executor.close()

        updated_snapshot = snapshot.model_copy(
            update={
                "snapshot_id": new_id("verify"),
                "smoke_status": SmokeStatus.PASSED if all_passed else SmokeStatus.FAILED,
                "blocking_reasons": (
                    tuple(item for item in snapshot.blocking_reasons if item != "smoke_required")
                    if all_passed
                    else (*snapshot.blocking_reasons, "smoke_failed")
                ),
                "created_at": self._economic_now(),
            }
        )
        candidate.verification_snapshot_id = updated_snapshot.snapshot_id
        candidate.updated_at = self._economic_now()
        if not all_passed:
            candidate.status = RouteLifecycle.SUSPENDED
            candidate.reason = "smoke failed"
        self.store.save_smoke_candidate_result(tuple(reports), updated_snapshot, candidate)
        return tuple(reports)

    def qualify_candidate_from_evidence(self, executor_id: str) -> QualificationReport:
        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None or candidate.package_digest is None:
            raise ConfigurationError("evidence reuse requires a provider-package candidate")
        if candidate.status is RouteLifecycle.ACTIVE:
            raise ConfigurationError("suspend an active route before requalification")
        package = self.store.get_provider_package(candidate.package_digest)
        snapshot = self.store.get_candidate_verification_snapshot(
            candidate.verification_snapshot_id or ""
        )
        smoke = self.store.latest_smoke_test_report(executor_id)
        if package is None or snapshot is None or smoke is None:
            raise ConfigurationError("candidate package/smoke evidence is incomplete")
        correctness = [
            item
            for item in self.store.list_evidence_acceptances(executor_id)
            if item.metric == "correctness"
            and item.status is EvidenceAcceptanceStatus.ACCEPTED
            and item.effective_trust in {TrustLevel.VERIFIED, TrustLevel.ATTESTED}
        ]
        if (
            snapshot.integrity_status is not PackageIntegrityStatus.VERIFIED
            or snapshot.fingerprint_status is not FingerprintStatus.MATCHED
            or snapshot.artifact_status is not ArtifactStatus.VERIFIED
            or smoke.status is not SmokeStatus.PASSED
            or smoke.route_fingerprint != candidate.package_fingerprint
            or not correctness
        ):
            raise ConfigurationError("trusted exact evidence plus current smoke is required")
        route = next(item for item in package.spec.routes if item.route_id == executor_id)
        if route.executor.side_effect.rank > SideEffect.READ.rank or not route.executor.idempotent:
            raise ConfigurationError("evidence-assisted qualification is read-only/idempotent")
        spec = route.executor_spec(package.spec.provider.provider_id)
        spec.side_effect = route.executor.side_effect
        spec.idempotent = True
        spec.safe_to_auto_execute = True
        checks = require_static_qualification(spec)
        fingerprint = behavior_fingerprint(spec)
        report = QualificationReport(
            candidate_id=candidate.candidate_id,
            behavior_fingerprint=fingerprint,
            static_checks=checks,
            dynamic_cases=1,
            passed_cases=1,
            repetitions=1,
            dynamic_runs=1,
            passed_runs=1,
            passed=True,
            qualification_method="evidence_reuse",
            source_evidence_ids=sorted({item.evidence_id for item in correctness}),
            smoke_report_ids=[smoke.smoke_report_id],
            effective_trust=(
                TrustLevel.ATTESTED.value
                if any(item.effective_trust is TrustLevel.ATTESTED for item in correctness)
                else TrustLevel.VERIFIED.value
            ),
            environment_digest=smoke.environment_digest,
        )
        self.store.save_qualification_report(report)
        candidate.spec = spec
        candidate.behavior_fingerprint = fingerprint
        candidate.status = RouteLifecycle.QUALIFIED
        candidate.qualification_report_id = report.report_id
        candidate.reason = None
        candidate.updated_at = self._economic_now()
        self.store.save_route_candidate(candidate)
        return report

    def ingest_candidate(self, spec: ExecutorSpec, *, source_id: str) -> RouteCandidate:
        """Store an external claim without exposing it to routing or model tools."""

        self._ensure_open()
        if self.registry.contains(spec.id) and self.store.get_route_candidate(spec.id) is None:
            raise ConfigurationError(f"candidate {spec.id!r} collides with a trusted route")
        existing = self.store.get_route_candidate(spec.id)
        candidate_spec = spec.model_copy(deep=True)
        if existing is None:
            candidate_spec.enabled = False
            candidate_spec.safe_to_auto_execute = False
            candidate_spec.idempotent = False
            candidate_spec.side_effect = SideEffect.FINANCIAL
            candidate = RouteCandidate(
                executor_id=candidate_spec.id,
                source_id=source_id,
                provider_id=candidate_spec.provider_id,
                capability=candidate_spec.capability,
                behavior_fingerprint=behavior_fingerprint(candidate_spec),
                spec=candidate_spec,
            )
        else:
            if existing.source_id != source_id:
                raise ConfigurationError(
                    f"candidate {spec.id!r} collides with source {existing.source_id!r}"
                )
            candidate_spec.side_effect = existing.spec.side_effect
            candidate_spec.idempotent = existing.spec.idempotent
            candidate_spec.safe_to_auto_execute = existing.spec.safe_to_auto_execute
            candidate_spec.enabled = False
            fingerprint = behavior_fingerprint(candidate_spec)
            if fingerprint == existing.behavior_fingerprint:
                return existing
            existing.spec = candidate_spec
            existing.behavior_fingerprint = fingerprint
            existing.status = RouteLifecycle.SUSPENDED
            existing.qualification_report_id = None
            existing.reason = "behavior fingerprint drift"
            existing.updated_at = utc_now()
            candidate = existing
            if self.registry.contains(candidate.executor_id):
                self.registry.get(candidate.executor_id).enabled = False
        self.store.save_route_candidate(candidate)
        return candidate

    async def qualify_candidate(
        self,
        executor_id: str,
        *,
        side_effect: SideEffect,
        idempotent: bool,
        safe_to_auto_execute: bool,
        cases: list[QualificationCase] | None = None,
        repetitions: int = 1,
        conditions: list[QualificationCondition] | None = None,
    ) -> QualificationReport:
        """Qualify exactly one candidate/fingerprint, without routing or fallback."""

        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None:
            raise ConfigurationError(f"unknown candidate {executor_id!r}")
        if candidate.status == RouteLifecycle.ACTIVE:
            raise ConfigurationError("suspend an active route before requalification")
        if repetitions < 1 or repetitions > 1000:
            raise ConfigurationError("qualification repetitions must be between 1 and 1000")
        run_conditions = conditions or [QualificationCondition.PROCESS_COLD]
        if len(run_conditions) != len(set(run_conditions)):
            raise ConfigurationError("duplicate qualification condition")
        if not cases:
            raise ConfigurationError("qualification requires at least one canonical case")
        spec = candidate.spec.model_copy(deep=True)
        spec.side_effect = side_effect
        spec.idempotent = idempotent
        spec.safe_to_auto_execute = safe_to_auto_execute
        spec.enabled = False
        if spec.kind in {ExecutorKind.PYTHON, ExecutorKind.MANAGED_HOST}:
            raise ConfigurationError(
                "external Python or managed-host candidates cannot be qualified in-process "
                "from packages; "
                "use a reviewed command/container route or a trusted local manifest executor"
            )
        fingerprint = behavior_fingerprint(spec)
        checks = require_static_qualification(spec)
        dynamic_cases = cases
        case_passed = [True] * len(dynamic_cases)
        passed_runs = 0
        dynamic_runs = 0
        warm_executors: dict[ExecutorKind, BaseExecutor] = {}
        try:
            for condition in run_conditions:
                for _ in range(repetitions):
                    for case_index, case in enumerate(dynamic_cases):
                        validate_json(
                            case.input,
                            spec.input_schema,
                            label=f"qualification input for {spec.id}",
                        )
                        if condition == QualificationCondition.PROCESS_COLD:
                            executor = _EXECUTOR_TYPES[spec.kind]()
                        else:
                            warm_executor = warm_executors.get(spec.kind)
                            if warm_executor is None:
                                warm_executor = _EXECUTOR_TYPES[spec.kind]()
                                warm_executors[spec.kind] = warm_executor
                            executor = warm_executor
                        try:
                            request = ActionRequest(capability=spec.capability, input=case.input)
                            try:
                                raw = await executor.execute(
                                    ExecutionContext(
                                        request=request,
                                        spec=spec,
                                        estimate=spec.estimate,
                                        attempt=1,
                                    )
                                )
                            except Exception:
                                raw = None
                        finally:
                            if condition == QualificationCondition.PROCESS_COLD:
                                await executor.close()
                        dynamic_runs += 1
                        if raw is None:
                            case_passed[case_index] = False
                            continue
                        valid = raw.status == ExecutionStatus.SUCCESS
                        if valid and spec.output_schema is not None:
                            try:
                                validate_json(
                                    raw.output,
                                    spec.output_schema,
                                    label=f"qualification output for {spec.id}",
                                )
                            except Exception:
                                valid = False
                        if valid and case.expected_output is not None:
                            valid = raw.output == case.expected_output
                        if valid and spec.validators:
                            results = await run_validators(
                                spec.validators,
                                ValidationContext(input=case.input, output=raw.output),
                                self.validator_callbacks,
                            )
                            valid = all(result.valid is True for result in results)
                        case_passed[case_index] &= valid
                        if valid:
                            passed_runs += 1
        finally:
            for executor in warm_executors.values():
                await executor.close()
        report = QualificationReport(
            candidate_id=candidate.candidate_id,
            behavior_fingerprint=fingerprint,
            static_checks=checks,
            dynamic_cases=len(dynamic_cases),
            passed_cases=sum(case_passed),
            repetitions=repetitions,
            conditions=run_conditions,
            dynamic_runs=dynamic_runs,
            passed_runs=passed_runs,
            passed=passed_runs == dynamic_runs,
        )
        self.store.save_qualification_report(report)
        if report.passed:
            candidate.spec = spec
            candidate.behavior_fingerprint = fingerprint
            candidate.status = RouteLifecycle.QUALIFIED
            candidate.qualification_report_id = report.report_id
            candidate.reason = None
            candidate.updated_at = utc_now()
            self.store.save_route_candidate(candidate)
        else:
            candidate.status = (
                RouteLifecycle.CANDIDATE
                if candidate.status == RouteLifecycle.CANDIDATE
                else RouteLifecycle.SUSPENDED
            )
            candidate.spec.enabled = False
            candidate.qualification_report_id = None
            candidate.reason = "qualification failed"
            candidate.updated_at = utc_now()
            self.store.save_route_candidate(candidate)
        return report

    def activate_candidate(self, executor_id: str) -> RouteCandidate:
        with self._route_activation_lock:
            candidate = self.store.get_route_candidate(executor_id)
            if candidate is None or candidate.status != RouteLifecycle.QUALIFIED:
                raise ConfigurationError("candidate must be qualified before activation")
            report = self.store.get_qualification_report(
                candidate.qualification_report_id or ""
            )
            if (
                report is None
                or not report.passed
                or report.behavior_fingerprint != candidate.behavior_fingerprint
                or behavior_fingerprint(candidate.spec) != candidate.behavior_fingerprint
            ):
                raise ConfigurationError(
                    "qualification evidence does not match candidate fingerprint"
                )
            if candidate.package_digest is not None:
                package = self.store.get_provider_package(candidate.package_digest)
                snapshot = self.store.get_candidate_verification_snapshot(
                    candidate.verification_snapshot_id or ""
                )
                smoke = self.store.latest_smoke_test_report(executor_id)
                if package is None or snapshot is None:
                    raise ConfigurationError("provider-package verification is unavailable")
                current = self._provider_package_ingestor().verify_package(package)
                if (
                    current.integrity_status is not PackageIntegrityStatus.VERIFIED
                    or snapshot.integrity_status is not PackageIntegrityStatus.VERIFIED
                    or snapshot.fingerprint_status is not FingerprintStatus.MATCHED
                    or snapshot.artifact_status is not ArtifactStatus.VERIFIED
                    or (
                        self.manifest.provider_packages.require_local_smoke
                        and (smoke is None or smoke.status is not SmokeStatus.PASSED)
                    )
                ):
                    raise ConfigurationError(
                        "current package trust, artifacts, fingerprint, and smoke are required"
                    )
                if report.qualification_method == "evidence_reuse" and not any(
                    item.metric == "correctness"
                    and item.status is EvidenceAcceptanceStatus.ACCEPTED
                    and item.effective_trust in {TrustLevel.VERIFIED, TrustLevel.ATTESTED}
                    for item in self.store.list_evidence_acceptances(executor_id)
                ):
                    raise ConfigurationError(
                        "evidence-assisted activation requires current trusted correctness evidence"
                    )
            candidate.status = RouteLifecycle.ACTIVE
            candidate.spec.enabled = True
            candidate.updated_at = utc_now()
            self.store.save_route_candidate(candidate)
            self.registry.replace(candidate.spec)
            return candidate

    def suspend_candidate(self, executor_id: str, *, reason: str) -> RouteCandidate:
        with self._route_activation_lock:
            candidate = self.store.get_route_candidate(executor_id)
            if candidate is None:
                raise ConfigurationError(f"unknown candidate {executor_id!r}")
            candidate.status = RouteLifecycle.SUSPENDED
            candidate.spec.enabled = False
            candidate.reason = reason
            candidate.updated_at = utc_now()
            self.store.save_route_candidate(candidate)
            if self.registry.contains(executor_id):
                self.registry.get(executor_id).enabled = False
            return candidate

    def candidate_status(self) -> list[RouteCandidate]:
        return self.store.list_route_candidates()

    def _require_active_spec(self, spec: ExecutorSpec) -> None:
        if not spec.enabled:
            raise NoRouteError(f"route {spec.id!r} is not active; reroute")
        if not self.registry.contains(spec.id):
            raise NoRouteError(f"route {spec.id!r} is no longer registered; reroute")
        registered = self.registry.get(spec.id)
        if (
            not registered.enabled
            or behavior_fingerprint(registered) != behavior_fingerprint(spec)
        ):
            raise NoRouteError(
                f"route {spec.id!r} is not active for its exact fingerprint; reroute"
            )
        candidate = self.store.get_route_candidate(spec.id)
        if candidate is None:
            return
        if (
            candidate.status != RouteLifecycle.ACTIVE
            or not spec.enabled
            or candidate.behavior_fingerprint != behavior_fingerprint(spec)
        ):
            if candidate.status == RouteLifecycle.ACTIVE:
                self.suspend_candidate(spec.id, reason="execution-time fingerprint drift")
            raise NoRouteError(
                f"route {spec.id!r} is not active for its exact fingerprint; reroute"
            )
        if candidate.package_digest is not None:
            package = self.store.get_provider_package(candidate.package_digest)
            if package is None:
                self.suspend_candidate(spec.id, reason="provider package is unavailable")
                raise NoRouteError("provider package is unavailable; route suspended")
            route = next(
                (item for item in package.spec.routes if item.route_id == spec.id),
                None,
            )
            current = self._provider_package_ingestor().verify_package(package)
            if (
                route is None
                or current.integrity_status is not PackageIntegrityStatus.VERIFIED
                or portable_route_fingerprint(route, package.spec.provider.provider_id)
                != candidate.package_fingerprint
                or not runtime_route_identity_matches(route, spec)
            ):
                self.suspend_candidate(spec.id, reason="package trust/fingerprint drift")
                raise NoRouteError("provider package trust or fingerprint drift; route suspended")

    async def route_with_discovery(self, request: ActionRequest | dict[str, Any]) -> RouteDecision:
        request_model = (
            request if isinstance(request, ActionRequest) else ActionRequest.model_validate(request)
        )
        if not self.registry.find(request_model.capability):
            await self.discover(request_model.capability)
        await self._snapshot_managed_capacity(request_model.capability)
        return self.route(request_model)

    async def _snapshot_managed_capacity(
        self, capability: str, *, executor_id: str | None = None
    ) -> None:
        seen: set[tuple[str, str]] = set()
        for spec in sorted(self.registry.find(capability), key=lambda item: item.id):
            if spec.kind is not ExecutorKind.MANAGED_HOST or (
                executor_id is not None and spec.id != executor_id
            ):
                continue
            config = spec.managed_host_config()
            key = (config.adapter_id, spec.resource_pool or "")
            if key in seen:
                continue
            seen.add(key)
            try:
                observation = await asyncio.wait_for(
                    self.managed_hosts.get(config.adapter_id).snapshot_capacity(),
                    timeout=min(config.timeout_seconds, 30),
                )
                if observation.resource_id != spec.resource_pool:
                    raise ConfigurationError(
                        "managed-host capacity observation names the wrong resource"
                    )
            except Exception:
                observation = CapacityObservation(
                    resource_id=spec.resource_pool or "unknown",
                    source="managed_host_unavailable",
                    windows=(CapacityWindow(window_id="unknown", confidence=0),),
                )
            self.store.save_capacity_observation(observation)

    async def benchmark(
        self,
        request: ActionRequest | dict[str, Any],
        *,
        approved_side_effect: SideEffect = SideEffect.READ,
        allow_unsafe_executor: bool = False,
        allow_non_idempotent: bool = False,
        include_delegates: bool = False,
        max_routes: int | None = None,
    ) -> BenchmarkResult:
        """Sequentially execute feasible alternatives to collect comparable receipts.

        Benchmarking is intentionally sequential so resource contention does not
        distort measurements. Non-idempotent and delegated routes are skipped by
        default. Callers should still set explicit cost/latency/network constraints
        because read-only APIs can incur charges.
        """

        self._ensure_open()
        request_model = (
            request if isinstance(request, ActionRequest) else ActionRequest.model_validate(request)
        )
        route_decision = await self.route_with_discovery(request_model)
        candidates = self._candidate_order(route_decision)
        if not candidates:
            raise NoRouteError(route_decision.explanation)
        if max_routes is not None:
            candidates = candidates[: max(1, max_routes)]

        result = BenchmarkResult(
            action_id=route_decision.action.action_id,
            capability=route_decision.action.capability,
            policy=route_decision.policy.name,
            route_decision_id=route_decision.decision_id,
        )
        relaxed_policy = route_decision.policy.model_copy(deep=True)
        relaxed_policy.constraints = ActionConstraints(
            min_success_probability=0.0,
            min_quality_score=0.0,
            max_risk_score=1.0,
            max_side_effect=SideEffect.FINANCIAL,
        )

        for candidate in candidates:
            spec = self.registry.get(candidate.executor_id)
            self._require_active_spec(spec)
            entry = BenchmarkEntry(
                executor_id=spec.id,
                executor_kind=spec.kind,
                estimated=candidate.estimate,
            )
            if spec.kind in {ExecutorKind.DELEGATE, ExecutorKind.HOST} and not include_delegates:
                entry.skipped_reason = "delegated routes are excluded unless explicitly requested"
                result.entries.append(entry)
                continue
            if not spec.idempotent and not allow_non_idempotent:
                entry.skipped_reason = "non-idempotent route excluded from benchmark"
                result.entries.append(entry)
                continue
            if spec.side_effect.rank > approved_side_effect.rank and spec.kind not in {
                ExecutorKind.DELEGATE,
                ExecutorKind.HOST,
            }:
                entry.skipped_reason = (
                    f"requires {spec.side_effect.value} approval; ceiling is "
                    f"{approved_side_effect.value}"
                )
                result.entries.append(entry)
                continue
            if (
                not spec.safe_to_auto_execute
                and spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}
                and not allow_unsafe_executor
            ):
                entry.skipped_reason = "executor is not approved as safe_to_auto_execute"
                result.entries.append(entry)
                continue

            forced = route_decision.action.model_copy(deep=True)
            forced.constraints.allowed_executor_ids = [spec.id]
            try:
                forced_decision = self.route(forced)
                outcome = await self.execute(
                    forced_decision,
                    approved_side_effect=approved_side_effect,
                    allow_unsafe_executor=allow_unsafe_executor,
                )
                entry.decision_id = forced_decision.decision_id
                entry.ok = outcome.ok
                entry.status = outcome.status
                if outcome.receipts:
                    receipt = outcome.receipts[-1]
                    entry.receipt_id = receipt.receipt_id
                    entry.actual_resources = receipt.actual_resources
                    entry.output_valid = receipt.output_valid
                    entry.error_message = receipt.error_message
                    if receipt.status not in {
                        ExecutionStatus.DELEGATED,
                        ExecutionStatus.HOST_SELECTED,
                    }:
                        successful = outcome.ok and receipt.output_valid is not False
                        observed = RouteEstimate(
                            resources=receipt.actual_resources,
                            success_probability=1.0 if successful else 0.001,
                            quality_score=1.0 if successful else 0.0,
                            risk_score=0.0 if successful else 1.0,
                            confidence=0.25,
                            source=EstimateSource.OBSERVED,
                            sample_size=1,
                        )
                        actual_candidate = score_candidate(
                            spec,
                            observed,
                            relaxed_policy,
                            route_decision.action.context,
                            self._subscription_quota(spec, route_decision.action.context),
                        )
                        entry.actual_score = actual_candidate.score
            except Exception as exc:  # one bad integration must not abort calibration
                entry.ok = False
                entry.status = ExecutionStatus.FAILED
                entry.error_message = str(exc)
            result.entries.append(entry)

        ranked = [entry for entry in result.entries if entry.actual_score is not None]
        ranked.sort(
            key=lambda entry: (
                entry.actual_score.total if entry.actual_score is not None else float("inf"),
                entry.executor_id,
            )
        )
        for rank, entry in enumerate(ranked, start=1):
            entry.actual_rank = rank
        return result

    def _executor_for(self, kind: ExecutorKind) -> BaseExecutor:
        executor = self._executors.get(kind)
        if executor is None:
            try:
                executor = _EXECUTOR_TYPES[kind]()
            except KeyError as exc:  # pragma: no cover - enum constrains this
                raise ConfigurationError(f"unsupported executor kind {kind.value!r}") from exc
            self._executors[kind] = executor
        return executor

    @staticmethod
    def _candidate_order(decision: RouteDecision) -> list[CandidateScore]:
        return sorted(
            (item for item in decision.candidates if item.feasible and item.rank is not None),
            key=lambda item: item.rank or 10**9,
        )

    @staticmethod
    def _quota_materially_changed(
        before: SubscriptionQuota | None, after: SubscriptionQuota | None
    ) -> bool:
        if before is None or after is None:
            return before is not after
        fields = (
            "state",
            "confidence",
            "unit",
            "allowance_units",
            "remaining_units",
            "used_percent",
            "reset_at",
            "window_duration_seconds",
            "window_count",
        )
        return any(getattr(before, field) != getattr(after, field) for field in fields)

    @staticmethod
    def _can_fallback(
        *,
        status: ExecutionStatus,
        output_valid: bool | None,
        idempotent: bool,
        allow_non_idempotent: bool,
        retry_timeouts: bool,
        retry_validation_failures: bool,
    ) -> bool:
        if not idempotent and not allow_non_idempotent:
            # A failed write may have committed remotely even when the caller did
            # not receive a response. Never duplicate it automatically.
            return False
        if status == ExecutionStatus.TIMEOUT:
            return retry_timeouts
        if status == ExecutionStatus.SUCCESS and output_valid is False:
            return retry_validation_failures
        return status in {
            ExecutionStatus.FAILED,
            ExecutionStatus.REJECTED,
            ExecutionStatus.UNKNOWN,
        }

    async def execute(
        self,
        request_or_decision: ActionRequest | RouteDecision | dict[str, Any],
        *,
        approved_side_effect: SideEffect = SideEffect.READ,
        allow_unsafe_executor: bool = False,
        dry_run: bool = False,
        _idempotency_claimed: bool = False,
        _quota_rerouted: bool = False,
    ) -> ExecutionOutcome:
        """Route and execute, returning a full decision plus attempt receipts.

        `approved_side_effect` is an explicit runtime approval separate from the
        manifest's policy guardrail. Both must permit the action. Delegated routes
        return instructions to the host agent and do not execute the side effect.
        """

        self._ensure_open()
        if isinstance(request_or_decision, RouteDecision):
            decision = request_or_decision
        elif isinstance(request_or_decision, ActionRequest):
            decision = await self.route_with_discovery(request_or_decision)
        elif "decision_id" in request_or_decision and "action" in request_or_decision:
            decision = RouteDecision.model_validate(request_or_decision)
        else:
            decision = await self.route_with_discovery(
                ActionRequest.model_validate(request_or_decision)
            )

        expected_digest = self._validated_decisions.get(decision.decision_id)
        if expected_digest != self._decision_digest(decision):
            if decision.action.input.get("__aeep_redacted__") is True:
                raise ConfigurationError(
                    "persisted decisions have redacted inputs and cannot be executed; "
                    "reroute using the original ActionRequest"
                )
            decision = self.route(decision.action)

        if decision.action.input.get("__aeep_redacted__") is True:
            raise ConfigurationError(
                "persisted decisions have redacted inputs and cannot be executed; "
                "reroute using the original ActionRequest"
            )

        candidates = self._candidate_order(decision)
        if not candidates or decision.selected_executor_id is None:
            raise NoRouteError(decision.explanation)
        if dry_run:
            return ExecutionOutcome(
                ok=True,
                status=ExecutionStatus.UNKNOWN,
                output=None,
                decision=decision,
            )

        idempotency_key = decision.action.idempotency_key
        if idempotency_key is not None and not _idempotency_claimed:
            request_hash = hashlib.sha256(
                json.dumps(
                    {
                        "capability": decision.action.capability,
                        "input": decision.action.input,
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            existing = self.store.claim_idempotency(idempotency_key, request_hash)
            if existing is not None:
                if existing["state"] != "complete":
                    raise ConfigurationError(
                        f"idempotent action {idempotency_key!r} is already in progress"
                    )
                receipt_ids_value = existing.get("receipt_ids", [])
                receipt_ids = receipt_ids_value if isinstance(receipt_ids_value, list) else []
                receipts = [
                    receipt
                    for receipt_id in receipt_ids
                    if isinstance(receipt_id, str)
                    and (receipt := self.store.get_receipt(receipt_id)) is not None
                ]
                for receipt in receipts:
                    receipt.metadata["idempotency_replay"] = True
                status = ExecutionStatus(str(existing["status"]))
                return ExecutionOutcome(
                    ok=status
                    in {
                        ExecutionStatus.SUCCESS,
                        ExecutionStatus.DELEGATED,
                        ExecutionStatus.HOST_SELECTED,
                    },
                    status=status,
                    output=None,
                    decision=decision,
                    receipts=receipts,
                )
            try:
                outcome = await self.execute(
                    decision,
                    approved_side_effect=approved_side_effect,
                    allow_unsafe_executor=allow_unsafe_executor,
                    _idempotency_claimed=True,
                    _quota_rerouted=_quota_rerouted,
                )
            except Exception:
                self.store.mark_idempotency_indeterminate(idempotency_key)
                self.store.abandon_idempotency(idempotency_key)
                raise
            self.store.complete_idempotency(
                idempotency_key,
                decision_id=outcome.decision.decision_id,
                status=outcome.status.value,
                receipt_ids=[receipt.receipt_id for receipt in outcome.receipts],
            )
            return outcome

        fallback = decision.policy.fallback
        max_attempts = min(len(candidates), fallback.max_attempts if fallback.enabled else 1)
        attempts: list[ExecutionReceipt] = []
        last_output: Any = None

        for attempt_number, candidate in enumerate(candidates[:max_attempts], start=1):
            spec = self.registry.get(candidate.executor_id)
            self._require_active_spec(spec)
            if spec.kind is ExecutorKind.MANAGED_HOST:
                before_quota = candidate.subscription_quota
                await self._snapshot_managed_capacity(
                    decision.action.capability, executor_id=spec.id
                )
                after_quota = self._subscription_quota(spec, decision.action.context)
                if (
                    not _quota_rerouted
                    and self._quota_materially_changed(before_quota, after_quota)
                ):
                    rerouted = self.route(decision.action)
                    return await self.execute(
                        rerouted,
                        approved_side_effect=approved_side_effect,
                        allow_unsafe_executor=allow_unsafe_executor,
                        _idempotency_claimed=_idempotency_claimed,
                        _quota_rerouted=True,
                    )
            if not spec.enabled or spec.capability != decision.action.capability:
                raise NoRouteError(
                    f"route {spec.id!r} is no longer active for {decision.action.capability!r}; reroute"
                )
            validate_json(decision.action.input, spec.input_schema, label=f"input for {spec.id}")
            current_policy = self._policy_for(decision.action)
            current_estimate = self.estimator.estimate(
                spec, current_policy, decision.action_features
            )
            requires_prepared_economics = route_requires_live_quote(
                spec,
                current_estimate,
                require_binding_quote_for_paid_routes=(
                    self.manifest.economic_evidence.requirements.require_binding_quote_for_paid_routes
                ),
            ) and (
                self.manifest.economic_evidence.enabled or route_explicitly_requires_quote(spec)
            )
            paid_or_unknown_provider = (
                self.manifest.economic_evidence.enabled
                and spec.provider_id is not None
                and not route_is_operator_confirmed_free(spec, current_estimate)
            )
            if requires_prepared_economics or paid_or_unknown_provider:
                raise ConfigurationError(
                    f"executor {spec.id!r} requires prepared economic execution; "
                    "use prepare_route() followed by execute_prepared()"
                )
            current = score_candidate(
                spec,
                current_estimate,
                current_policy,
                decision.action.context,
                self._subscription_quota(spec, decision.action.context),
            )
            if not current.feasible:
                raise NoRouteError(
                    f"route {spec.id!r} no longer satisfies current policy: "
                    f"{'; '.join(current.rejection_reasons)}; reroute"
                )
            if spec.side_effect.rank > approved_side_effect.rank and spec.kind not in {
                ExecutorKind.DELEGATE,
                ExecutorKind.HOST,
            }:
                raise ApprovalRequired(
                    f"executor {spec.id!r} requires {spec.side_effect.value!r} approval; "
                    f"approved level is {approved_side_effect.value!r}",
                    executor_id=spec.id,
                    required_level=spec.side_effect.value,
                )
            if (
                not spec.safe_to_auto_execute
                and spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}
                and not allow_unsafe_executor
            ):
                raise ApprovalRequired(
                    f"executor {spec.id!r} is not marked safe_to_auto_execute; "
                    "pass explicit unsafe-executor approval after reviewing its configuration",
                    executor_id=spec.id,
                    required_level="unsafe_executor",
                )

            estimate = candidate.estimate
            approval_id: str | None = None
            if spec.side_effect.rank > SideEffect.READ.rank:
                approval = ActionApprovalRecord(
                    action_digest=deterministic_digest(
                        {
                            "capability": decision.action.capability,
                            "input": decision.action.input,
                        }
                    ),
                    policy_digest=self._effective_policy_digest(current_policy),
                    attempt_id=f"attempt-{attempt_number}",
                    granted_side_effect=approved_side_effect,
                    source=ApprovalSource.EMBEDDED_CALLER,
                    granted_at=self._economic_now(),
                )
                self.store.save_action_approval(approval)
                approval_id = approval.approval_id
            durable_attempt = self._create_claimed_attempt(
                decision_id=decision.decision_id,
                prepared_id=None,
                action_digest_value=deterministic_digest(
                    {
                        "capability": decision.action.capability,
                        "input": decision.action.input,
                        "constraints": decision.action.constraints,
                    }
                ),
                spec=spec,
            )
            durable_attempt = self._advance_attempt(
                durable_attempt,
                ExecutionAttemptState.RESERVED,
                reason="zero or locally managed reservation recorded",
            )
            durable_attempt = self._advance_attempt(
                durable_attempt,
                ExecutionAttemptState.INVOKING,
                reason="external invocation boundary entered",
                invocation_start_digest=deterministic_digest(
                    {
                        "attempt_id": durable_attempt.attempt_id,
                        "executor_fingerprint": durable_attempt.executor_fingerprint,
                    }
                ),
            )
            started_at = utc_now()
            with start_span(
                "aeep.execute",
                {
                    "aeep.decision_id": decision.decision_id,
                    "aeep.action_id": decision.action.action_id,
                    "aeep.capability": decision.action.capability,
                    "aeep.executor_id": spec.id,
                    "aeep.executor_kind": spec.kind.value,
                    "aeep.attempt": attempt_number,
                },
            ) as span:
                if _idempotency_claimed and idempotency_key and attempt_number == 1:
                    self.store.mark_idempotency_executing(idempotency_key)
                try:
                    raw = await self._executor_for(spec.kind).execute(
                        ExecutionContext(
                            request=decision.action,
                            spec=spec,
                            estimate=estimate,
                            attempt=attempt_number,
                            attempt_id=durable_attempt.attempt_id,
                            approved_side_effect=approved_side_effect,
                        )
                    )
                except Exception:
                    self._advance_attempt(
                        durable_attempt,
                        ExecutionAttemptState.INDETERMINATE,
                        reason="executor raised after invocation boundary",
                    )
                    raise
                durable_attempt = self._advance_attempt(
                    durable_attempt,
                    ExecutionAttemptState.VALIDATING,
                    reason="executor returned; validating locally",
                    external_thread_digest=raw.metadata.get("thread_identity_digest"),
                    external_turn_digest=raw.metadata.get("turn_identity_digest"),
                )
                output_valid: bool | None = None
                task_valid: bool | None = None
                validation_results: list[ValidationResult] = []
                error_type = raw.error_type
                error_message = raw.error_message
                if raw.status == ExecutionStatus.SUCCESS and spec.output_schema is not None:
                    try:
                        validate_json(
                            raw.output, spec.output_schema, label=f"output from {spec.id}"
                        )
                        output_valid = True
                        validation_results.append(
                            ValidationResult(
                                kind=ValidationKind.SCHEMA,
                                valid=True,
                                quality_score=1.0,
                                trust=TrustLevel.OBSERVED,
                            )
                        )
                    except Exception as exc:
                        output_valid = False
                        validation_results.append(
                            ValidationResult(
                                kind=ValidationKind.SCHEMA,
                                valid=False,
                                quality_score=0.0,
                                detail=str(exc),
                                trust=TrustLevel.OBSERVED,
                            )
                        )
                        error_type = type(exc).__name__
                        error_message = str(exc)
                elif raw.status == ExecutionStatus.SUCCESS:
                    output_valid = None
                if raw.status == ExecutionStatus.SUCCESS and output_valid is not False:
                    additional_results = await run_validators(
                        spec.validators,
                        ValidationContext(input=decision.action.input, output=raw.output),
                        self.validator_callbacks,
                    )
                    validation_results.extend(additional_results)
                    if spec.validators:
                        task_valid = all(
                            result.valid is True
                            for validator, result in zip(
                                spec.validators, additional_results, strict=True
                            )
                            if validator.required
                        )
                        if not task_valid:
                            error_type = "TaskValidationError"
                            error_message = "; ".join(
                                result.detail or f"{result.kind.value} validation failed"
                                for validator, result in zip(
                                    spec.validators, additional_results, strict=True
                                )
                                if validator.required and result.valid is not True
                            )
                    else:
                        task_valid = output_valid

                ended_at = utc_now()
                raw.resources.monetary_usd = mirror_actual_cash(raw.accounting)
                known_subscription = [
                    item.consumed
                    for item in raw.accounting.subscription_usage
                    if item.consumed is not None
                ]
                raw.resources.subscription_units = (
                    float(known_subscription[0]) if len(known_subscription) == 1 else 0.0
                )
                receipt = ExecutionReceipt(
                    decision_id=decision.decision_id,
                    action_id=decision.action.action_id,
                    capability=decision.action.capability,
                    executor_id=spec.id,
                    executor_kind=spec.kind,
                    status=raw.status,
                    attempt=attempt_number,
                    started_at=started_at,
                    ended_at=ended_at,
                    estimated=estimate,
                    action_features=decision.action_features,
                    actual_resources=raw.resources,
                    accounting=raw.accounting,
                    cache_affinity=self._cache_receipt(
                        candidate.cache_affinity,
                        decision.action.context,
                        raw.resources,
                    ),
                    transport_success=raw.status
                    in {
                        ExecutionStatus.SUCCESS,
                        ExecutionStatus.DELEGATED,
                        ExecutionStatus.HOST_SELECTED,
                    },
                    execution_success=(True if raw.status == ExecutionStatus.SUCCESS else None),
                    schema_valid=output_valid,
                    task_valid=task_valid,
                    quality_score=(
                        sum(
                            result.quality_score
                            for result in validation_results
                            if result.quality_score is not None
                        )
                        / len(
                            [
                                result
                                for result in validation_results
                                if result.quality_score is not None
                            ]
                        )
                        if any(result.quality_score is not None for result in validation_results)
                        else estimate.quality_score
                        if raw.status == ExecutionStatus.SUCCESS and task_valid is not False
                        else None
                    ),
                    validation_results=validation_results,
                    output_valid=output_valid,
                    error_type=error_type,
                    error_message=error_message,
                    trace_id=trace_id_from_span(span),
                    metadata={
                        **raw.metadata,
                        "exit_code": raw.exit_code,
                        "attempt_id": durable_attempt.attempt_id,
                    },
                    approval_id=approval_id,
                )
                durable_attempt = self._advance_attempt(
                    durable_attempt,
                    ExecutionAttemptState.SETTLING,
                    reason="validation completed; finalizing local accounting",
                )
                self._save_receipt(receipt)
                self._observe_receipt(spec, receipt)
                attempt_succeeded = raw.status in {
                    ExecutionStatus.SUCCESS,
                    ExecutionStatus.DELEGATED,
                    ExecutionStatus.HOST_SELECTED,
                } and output_valid is not False and task_valid is not False
                if attempt_succeeded:
                    terminal_attempt_state = ExecutionAttemptState.COMPLETED
                elif raw.status is ExecutionStatus.REJECTED:
                    terminal_attempt_state = ExecutionAttemptState.REJECTED
                elif raw.status in {ExecutionStatus.TIMEOUT, ExecutionStatus.UNKNOWN} and (
                    spec.kind is ExecutorKind.MANAGED_HOST
                    or not durable_attempt.retry_eligible
                ):
                    terminal_attempt_state = ExecutionAttemptState.INDETERMINATE
                else:
                    terminal_attempt_state = ExecutionAttemptState.FAILED
                durable_attempt = self._advance_attempt(
                    durable_attempt,
                    terminal_attempt_state,
                    reason="terminal receipt persisted",
                    terminal_receipt_ids=(receipt.receipt_id,),
                )
                attempts.append(receipt)
                last_output = raw.output

            if raw.error_type == "ProtocolError" and "schema drift" in (raw.error_message or ""):
                if self.store.get_route_candidate(spec.id) is not None:
                    self.suspend_candidate(spec.id, reason="MCP schema drift")
                return ExecutionOutcome(
                    ok=False,
                    status=ExecutionStatus.FAILED,
                    output=None,
                    decision=decision,
                    receipts=attempts,
                )

            if raw.status in {ExecutionStatus.DELEGATED, ExecutionStatus.HOST_SELECTED}:
                instructions = raw.metadata.get("instructions")
                if isinstance(raw.output, dict):
                    report = raw.output.get("report_outcome")
                    if isinstance(report, dict):
                        report["decision_id"] = decision.decision_id
                return ExecutionOutcome(
                    ok=True,
                    status=raw.status,
                    output=raw.output,
                    decision=decision,
                    receipts=attempts,
                    delegated_instructions=(
                        str(instructions) if instructions is not None else None
                    ),
                )

            success = (
                raw.status == ExecutionStatus.SUCCESS
                and output_valid is not False
                and task_valid is not False
            )
            if success:
                return ExecutionOutcome(
                    ok=True,
                    status=ExecutionStatus.SUCCESS,
                    output=raw.output,
                    decision=decision,
                    receipts=attempts,
                )

            if attempt_number >= max_attempts:
                break
            if durable_attempt.state is ExecutionAttemptState.INDETERMINATE:
                break
            if not self._can_fallback(
                status=raw.status,
                output_valid=(
                    False if output_valid is False or task_valid is False else task_valid
                ),
                idempotent=spec.idempotent,
                allow_non_idempotent=fallback.allow_non_idempotent,
                retry_timeouts=fallback.retry_timeouts,
                retry_validation_failures=fallback.retry_validation_failures,
            ):
                break

        if attempts:
            last_receipt = attempts[-1]
            final_status = (
                ExecutionStatus.FAILED
                if last_receipt.status == ExecutionStatus.SUCCESS
                and (last_receipt.task_valid is False or last_receipt.output_valid is False)
                else last_receipt.status
            )
        else:
            final_status = ExecutionStatus.FAILED
        return ExecutionOutcome(
            ok=False,
            status=final_status,
            output=last_output,
            decision=decision,
            receipts=attempts,
        )

    def record_external_outcome(
        self,
        report: ExternalOutcomeReport | dict[str, Any],
        *,
        _trusted_accounting: ResourceAccounting | None = None,
        _trusted_metadata: dict[str, Any] | None = None,
    ) -> ExecutionReceipt:
        """Record the selected host-executed delegate exactly once.

        This boundary is intentionally strict because untrusted agents can call
        it through MCP. Arbitrary observations for Python/CLI/HTTP/MCP routes
        belong in the trusted embedded :class:`ActionProfiler`, not this remote
        reporting endpoint.
        """

        self._ensure_open()
        report_model = (
            report
            if isinstance(report, ExternalOutcomeReport)
            else ExternalOutcomeReport.model_validate(report)
        )
        decision = self.store.get_decision(report_model.decision_id)
        if decision is None:
            raise ConfigurationError(f"unknown decision {report_model.decision_id!r}")
        spec = self.registry.get(report_model.executor_id)
        if spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}:
            raise ConfigurationError(
                "external outcome reports are only accepted for delegate or host executors"
            )
        if spec.id != decision.selected_executor_id:
            raise ConfigurationError(
                f"executor {spec.id!r} was not the selected route for decision "
                f"{decision.decision_id!r}"
            )
        if spec.capability != decision.action.capability:
            raise ConfigurationError(
                f"executor {spec.id!r} does not match decision capability "
                f"{decision.action.capability!r}"
            )
        candidate = next(
            (item for item in decision.candidates if item.executor_id == spec.id),
            None,
        )
        if candidate is None or not candidate.feasible:
            raise ConfigurationError(
                f"executor {spec.id!r} was not a feasible candidate in decision "
                f"{decision.decision_id!r}"
            )
        existing = self.store.list_receipts(decision_id=decision.decision_id, limit=1000)
        if any(
            receipt.executor_id == spec.id
            and bool(receipt.metadata.get("externally_reported", False))
            for receipt in existing
        ):
            raise ConfigurationError(
                f"an external outcome was already reported for decision "
                f"{decision.decision_id!r} and executor {spec.id!r}"
            )
        started = report_model.started_at or utc_now()
        ended = report_model.ended_at or utc_now()
        if ended < started:
            raise ConfigurationError("external outcome ended_at precedes started_at")
        receipt = ExecutionReceipt(
            decision_id=decision.decision_id,
            action_id=decision.action.action_id,
            capability=decision.action.capability,
            executor_id=spec.id,
            executor_kind=spec.kind,
            status=report_model.status,
            attempt=len(existing) + 1,
            started_at=started,
            ended_at=ended,
            estimated=candidate.estimate,
            action_features=decision.action_features,
            actual_resources=report_model.actual_resources,
            accounting=_trusted_accounting or ResourceAccounting(),
            cache_affinity=self._cache_receipt(
                candidate.cache_affinity,
                decision.action.context,
                report_model.actual_resources,
            ),
            transport_success=True,
            execution_success=report_model.status == ExecutionStatus.SUCCESS,
            schema_valid=report_model.output_valid,
            task_valid=(
                report_model.task_valid
                if report_model.task_valid is not None
                else report_model.output_valid
            ),
            quality_score=(
                report_model.quality_score
                if report_model.quality_score is not None
                else candidate.estimate.quality_score
                if report_model.status == ExecutionStatus.SUCCESS
                and report_model.task_valid is not False
                and report_model.output_valid is not False
                else None
            ),
            validation_results=report_model.validation_results,
            output_valid=report_model.output_valid,
            error_message=report_model.error_message,
            metadata={"externally_reported": True, **(_trusted_metadata or {})},
        )
        persisted = receipt.model_copy(deep=True)
        self._bind_receipt_evidence(spec, receipt)
        persisted.executor_fingerprint = receipt.executor_fingerprint
        persisted.cohort_digest = receipt.cohort_digest
        persisted.error_message = persisted.error_type or (
            "execution failed" if persisted.error_message else None
        )
        self.store.save_external_receipt_once(persisted)
        self._observe_receipt(spec, receipt)
        if spec.resource_pool and report_model.quota_observation is not None:
            self.observe_quota(
                spec.resource_pool,
                report_model.quota_observation,
                note=f"reported with external outcome {receipt.receipt_id}",
            )
        return receipt

    def _workflow_result(
        self,
        request: WorkflowRequest,
        *,
        status: WorkflowStatus,
        step_outputs: dict[str, Any],
        receipts: list[ExecutionReceipt],
        started: float,
        waiting_step_id: str | None = None,
        waiting_decision_id: str | None = None,
        step_durations: dict[str, float] | None = None,
        error: str | None = None,
    ) -> WorkflowExecutionOutcome:
        accounting = aggregate_accounting(receipts)
        outputs: dict[str, Any] = {}
        if status == WorkflowStatus.SUCCESS:
            for projection in request.outputs:
                outputs[projection.name] = pointer_get(
                    step_outputs[projection.step_id], projection.path
                )
        elapsed = (time.perf_counter() - started) * 1000.0
        result = WorkflowExecutionOutcome(
            workflow_id=request.workflow_id,
            workflow_hash=request.workflow_hash,
            status=status,
            outputs=outputs,
            step_outputs=step_outputs,
            receipts=receipts,
            accounting=accounting,
            known_cash_subtotal_usd=accounting.cash.known_subtotal("USD"),
            actual_cash_total_usd=accounting.cash.actual_cash_cost("USD"),
            policy_valuations=self._workflow_policy_valuations(receipts),
            wall_time_ms=elapsed,
            critical_path_ms=self._workflow_critical_path(
                request, step_durations or {}, default=elapsed
            ),
            peak_memory_mb=max(
                (receipt.actual_resources.peak_memory_mb for receipt in receipts), default=0.0
            ),
            waiting_step_id=waiting_step_id,
            waiting_decision_id=waiting_decision_id,
            error=error,
        )
        self.store.save_workflow_checkpoint(
            workflow_id=request.workflow_id,
            workflow_hash=request.workflow_hash,
            status=status.value,
            waiting_step_id=waiting_step_id,
            waiting_decision_id=waiting_decision_id,
        )
        return result

    def _workflow_policy_valuations(
        self, receipts: list[ExecutionReceipt]
    ) -> list[PolicyValuation]:
        values: list[PolicyValuation] = []
        for receipt in receipts:
            decision = self.store.get_decision(receipt.decision_id)
            if decision is None:
                continue
            amount = policy_valuation_amount(
                RouteEstimate(resources=receipt.actual_resources), decision.policy
            )
            if amount:
                values.append(
                    PolicyValuation(
                        amount=Decimal(str(amount)),
                        policy_id=decision.policy.name,
                        explanation=f"private resource valuation for {receipt.receipt_id}",
                    )
                )
            for usage in receipt.accounting.subscription_usage:
                if usage.consumed is None:
                    continue
                rule = next(
                    (
                        item
                        for item in decision.policy.subscription_rules
                        if item.resource_pool == usage.resource_pool
                        and item.unit == usage.unit
                        and item.policy_value_usd_per_unit is not None
                    ),
                    None,
                )
                if rule is not None and rule.policy_value_usd_per_unit is not None:
                    values.append(
                        PolicyValuation(
                            amount=usage.consumed * rule.policy_value_usd_per_unit,
                            policy_id=decision.policy.name,
                            resource_pool=usage.resource_pool,
                            unit=usage.unit,
                            explanation="operator-defined subscription opportunity value",
                        )
                    )
        return values

    @staticmethod
    def _workflow_critical_path(
        request: WorkflowRequest,
        durations: dict[str, float],
        *,
        default: float,
    ) -> float:
        if not durations:
            return default
        steps = {step.step_id: step for step in request.steps}
        totals: dict[str, float] = {}

        def total(step_id: str) -> float:
            if step_id not in totals:
                totals[step_id] = durations.get(step_id, 0.0) + max(
                    (total(dependency) for dependency in steps[step_id].depends_on),
                    default=0.0,
                )
            return totals[step_id]

        return max((total(step_id) for step_id in durations), default=default)

    async def execute_workflow(
        self,
        request: WorkflowRequest | dict[str, Any],
        *,
        approved_side_effect: SideEffect = SideEffect.READ,
        payment_approved: bool = False,
        human_approved: bool = False,
        allow_unsafe_executor: bool = False,
        _initial_outputs: dict[str, Any] | None = None,
        _initial_receipts: list[ExecutionReceipt] | None = None,
    ) -> WorkflowExecutionOutcome:
        """Execute a caller-authored DAG through the configured routing boundary.

        Economic networking uses request-bound preparation for only the current
        dependency-resolved wave.  Offline manifests retain the legacy
        deterministic ``route``/``execute`` path.
        """

        workflow = (
            request
            if isinstance(request, WorkflowRequest)
            else WorkflowRequest.model_validate(request)
        )
        started = time.perf_counter()
        step_outputs = dict(_initial_outputs or {})
        receipts = list(_initial_receipts or [])
        step_durations: dict[str, float] = {}
        steps_by_id = {step.step_id: step for step in workflow.steps}
        for step in workflow.steps:
            for binding in step.bindings:
                if binding.source_step_id is None:
                    continue
                source_step = steps_by_id[binding.source_step_id]
                schemas = [
                    spec.output_schema for spec in self.registry.find(source_step.action.capability)
                ]
                if schemas and any(
                    not schema_pointer_exists(schema, binding.source_path) for schema in schemas
                ):
                    raise ConfigurationError("workflow binding source path is not in route schema")
        for projection in workflow.outputs:
            source_step = steps_by_id[projection.step_id]
            schemas = [
                spec.output_schema for spec in self.registry.find(source_step.action.capability)
            ]
            if schemas and any(
                not schema_pointer_exists(schema, projection.path) for schema in schemas
            ):
                raise ConfigurationError("workflow output path is not in route schema")
        pending = {
            step.step_id: step for step in workflow.steps if step.step_id not in step_outputs
        }
        quota_start: dict[tuple[str, str], SubscriptionQuota] = {}
        quota_consumed: dict[tuple[str, str], float] = {}

        while pending:
            ready = sorted(
                (
                    step
                    for step in pending.values()
                    if all(dependency in step_outputs for dependency in step.depends_on)
                ),
                key=lambda step: step.step_id,
            )
            if not ready:  # The model validator catches cycles; this guards bad resume state.
                return self._workflow_result(
                    workflow,
                    status=WorkflowStatus.FAILED,
                    step_outputs=step_outputs,
                    receipts=receipts,
                    started=started,
                    error="workflow has no executable ready step",
                )

            if self.manifest.economic_evidence.enabled:
                currency = self.manifest.economic_evidence.settlement_currency
                if workflow.budget.max_cash_usd is not None and currency != "USD":
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error="USD workflow budget cannot authorize another currency",
                    )
                prior_cash = aggregate_accounting(receipts).cash.actual_cash_cost(currency)
                if workflow.budget.max_cash_usd is not None and receipts and prior_cash is None:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error="workflow cash is unavailable under a finite budget",
                    )
                accounted_cash = prior_cash or Decimal(0)
                remaining_cash = (
                    workflow.budget.max_cash_usd - accounted_cash
                    if workflow.budget.max_cash_usd is not None
                    else None
                )
                if remaining_cash is not None and remaining_cash < 0:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error="workflow cash budget is already exhausted",
                    )

                resolved_actions: dict[str, ActionRequest] = {}
                for step in ready:
                    action = step.action.model_copy(deep=True)
                    action.constraints = merge_constraints(
                        workflow.constraints, action.constraints
                    )
                    if remaining_cash is not None:
                        remaining = float(remaining_cash)
                        action.context.compute.monetary_budget_remaining_usd = remaining
                        action.constraints.max_cost_usd = (
                            remaining
                            if action.constraints.max_cost_usd is None
                            else min(action.constraints.max_cost_usd, remaining)
                        )
                    for binding in step.bindings:
                        source = (
                            workflow.input
                            if binding.source_step_id is None
                            else step_outputs[binding.source_step_id]
                        )
                        pointer_replace(
                            action.input,
                            binding.target_path,
                            pointer_get(source, binding.source_path),
                        )
                    resolved_actions[step.step_id] = action

                # Conservatively serialize a step when any exact-capability route
                # could be consequential, delegated, or resource-exclusive.  This
                # happens before quote acquisition and never guesses future inputs.
                exclusive_ready = []
                for step in ready:
                    compatible, _ = self.registry.compatible(
                        resolved_actions[step.step_id].capability,
                        resolved_actions[step.step_id].input,
                    )
                    if any(
                        spec.enabled
                        and (
                            spec.side_effect.rank > SideEffect.READ.rank
                            or spec.kind in {
                                ExecutorKind.DELEGATE,
                                ExecutorKind.HOST,
                                ExecutorKind.MANAGED_HOST,
                            }
                            or bool(spec.config.get("exclusive_resource"))
                        )
                        for spec in compatible
                    ):
                        exclusive_ready.append(step)
                wave = [exclusive_ready[0]] if exclusive_ready else ready[:8]

                preparation_results: dict[
                    str, PreparedRouteDecision | Exception
                ] = {}

                async def prepare_step(
                    step_id: str,
                    current_results: dict[
                        str, PreparedRouteDecision | Exception
                    ] = preparation_results,
                    current_actions: dict[str, ActionRequest] = resolved_actions,
                ) -> None:
                    try:
                        current_results[step_id] = await self.prepare_route(
                            current_actions[step_id]
                        )
                    except Exception as exc:
                        current_results[step_id] = exc

                async with asyncio.TaskGroup() as group:
                    for step in wave:
                        group.create_task(prepare_step(step.step_id))

                returned_prepared = [
                    prepared_result
                    for prepared_result in preparation_results.values()
                    if isinstance(prepared_result, PreparedRouteDecision)
                ]

                async def cancel_uninvoked(
                    current_prepared: list[
                        PreparedRouteDecision
                    ] = returned_prepared,
                ) -> None:
                    for prepared_item in current_prepared:
                        current = self.store.get_prepared_decision(
                            prepared_item.prepared_id
                        )
                        if current is not None and current.state in {
                            PreparedDecisionState.PREPARED,
                            PreparedDecisionState.RESERVED,
                        }:
                            await self.cancel_prepared(prepared_item.prepared_id)

                preparation_error = next(
                    (
                        (step.step_id, preparation_results[step.step_id])
                        for step in wave
                        if isinstance(preparation_results[step.step_id], Exception)
                    ),
                    None,
                )
                if preparation_error is not None:
                    await cancel_uninvoked()
                    preparation_step_id, preparation_exception = preparation_error
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=(
                            f"step {preparation_step_id} preparation failed: "
                            f"{type(preparation_exception).__name__}"
                        ),
                    )

                economic_prepared: dict[str, PreparedRouteDecision] = {}
                economic_decisions: dict[str, RouteDecision] = {}
                economic_specs: dict[str, ExecutorSpec] = {}
                invalid_step: tuple[str, str] | None = None
                wave_maximum = Decimal(0)
                for step in wave:
                    prepared_item = preparation_results[step.step_id]
                    assert isinstance(prepared_item, PreparedRouteDecision)
                    economic_prepared[step.step_id] = prepared_item
                    maximum = prepared_item.maximum_cash_authorization
                    if (
                        not prepared_item.feasible
                        or prepared_item.selected_executor_id is None
                    ):
                        invalid_step = (step.step_id, "no prepared route is feasible")
                        break
                    if maximum is None:
                        invalid_step = (step.step_id, "prepared cash maximum is unknown")
                        break
                    if maximum.currency != currency:
                        invalid_step = (step.step_id, "prepared cash currency is inconsistent")
                        break
                    if (
                        maximum.amount > 0
                        and (
                            prepared_item.authorization_kind is None
                            or prepared_item.authorization_id is None
                        )
                    ):
                        invalid_step = (
                            step.step_id,
                            "nonzero cash maximum lacks immutable authorization",
                        )
                        break
                    if (
                        maximum.amount == 0
                        and prepared_item.authorization_kind is None
                        and prepared_item.expected_accounting.cash.actual_cash_cost(currency)
                        != Decimal(0)
                    ):
                        invalid_step = (
                            step.step_id,
                            "unknown cash cannot be treated as confirmed free",
                        )
                        break
                    context = self._prepared_contexts.get(prepared_item.prepared_id)
                    if context is None:
                        invalid_step = (
                            step.step_id,
                            "prepared workflow context is unavailable",
                        )
                        break
                    economic_decisions[step.step_id] = context.route_decision
                    economic_specs[step.step_id] = self.registry.get(
                        prepared_item.selected_executor_id
                    )
                    wave_maximum += maximum.amount

                if invalid_step is not None:
                    await cancel_uninvoked()
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=f"step {invalid_step[0]} failed: {invalid_step[1]}",
                    )
                if (
                    workflow.budget.max_cash_usd is not None
                    and accounted_cash + wave_maximum > workflow.budget.max_cash_usd
                ):
                    await cancel_uninvoked()
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error="prepared workflow cash maxima exceed the workflow budget",
                    )

                economic_reservations: dict[tuple[str, str], float] = {}
                for step in wave:
                    spec = economic_specs[step.step_id]
                    if not spec.resource_pool:
                        continue
                    action = resolved_actions[step.step_id]
                    quota = self._subscription_quota(spec, action.context)
                    resource = self.resources.get(spec.resource_pool)
                    unit = (
                        quota.unit
                        if quota is not None
                        else resource.unit
                        if resource is not None
                        else "provider_unit"
                    )
                    key = (spec.resource_pool, unit)
                    candidate = next(
                        candidate_item
                        for candidate_item in economic_decisions[step.step_id].candidates
                        if candidate_item.executor_id == spec.id
                    )
                    estimated_usage = [
                        usage_item
                        for usage_item in candidate.estimate.subscription_usage
                        if usage_item.resource_pool == spec.resource_pool
                        and usage_item.consumed is not None
                    ]
                    if estimated_usage:
                        for usage_item in estimated_usage:
                            usage_key = (usage_item.resource_pool, usage_item.unit)
                            economic_reservations[usage_key] = economic_reservations.get(
                                usage_key, 0.0
                            ) + float(usage_item.consumed or 0)
                    else:
                        economic_reservations[key] = (
                            economic_reservations.get(key, 0.0)
                            + candidate.estimate.resources.subscription_units
                        )
                    if quota is not None:
                        quota_start.setdefault(key, quota.model_copy(deep=True))
                quota_error: tuple[str, str] | None = None
                for key, reserved in economic_reservations.items():
                    quota = quota_start.get(key)
                    if (
                        quota is not None
                        and quota.remaining_units is not None
                        and quota_consumed.get(key, 0.0) + reserved
                        > float(quota.remaining_units)
                    ):
                        quota_error = key
                        break
                if quota_error is not None:
                    await cancel_uninvoked()
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=f"parallel subscription reservation exceeds {quota_error[0]!r}",
                    )

                economic_outcomes: dict[str, ExecutionOutcome | Exception] = {}

                async def run_prepared_step(
                    step_id: str,
                    current_outcomes: dict[
                        str, ExecutionOutcome | Exception
                    ] = economic_outcomes,
                    current_prepared: dict[
                        str, PreparedRouteDecision
                    ] = economic_prepared,
                ) -> None:
                    try:
                        current_outcomes[step_id] = await self.execute_prepared(
                            current_prepared[step_id].prepared_id,
                            approved_side_effect=approved_side_effect,
                            payment_approved=payment_approved,
                            human_approved=human_approved,
                            allow_unsafe_executor=allow_unsafe_executor,
                        )
                    except Exception as exc:
                        current_outcomes[step_id] = exc

                async with asyncio.TaskGroup() as group:
                    for step in wave:
                        group.create_task(run_prepared_step(step.step_id))

                for step in wave:
                    economic_outcome = economic_outcomes[step.step_id]
                    if isinstance(economic_outcome, ExecutionOutcome):
                        receipts.extend(economic_outcome.receipts)
                        step_durations[step.step_id] = sum(
                            receipt.duration_ms for receipt in economic_outcome.receipts
                        )
                execution_error = next(
                    (
                        (step.step_id, economic_outcomes[step.step_id])
                        for step in wave
                        if isinstance(economic_outcomes[step.step_id], Exception)
                    ),
                    None,
                )
                if execution_error is not None:
                    await cancel_uninvoked()
                    execution_step_id, execution_exception = execution_error
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        step_durations=step_durations,
                        error=(
                            f"step {execution_step_id} failed: "
                            f"{type(execution_exception).__name__}"
                        ),
                    )

                waiting: tuple[str, ExecutionOutcome] | None = None
                invalid_outcome: str | None = None
                economic_wave_receipts: list[ExecutionReceipt] = []
                for step in wave:
                    economic_outcome = economic_outcomes[step.step_id]
                    assert isinstance(economic_outcome, ExecutionOutcome)
                    economic_wave_receipts.extend(economic_outcome.receipts)
                    if economic_outcome.status in {
                        ExecutionStatus.HOST_SELECTED,
                        ExecutionStatus.DELEGATED,
                    }:
                        waiting = (step.step_id, economic_outcome)
                    elif not economic_outcome.ok:
                        invalid_outcome = step.step_id
                    else:
                        step_outputs[step.step_id] = economic_outcome.output
                        pending.pop(step.step_id)

                actual_wave = aggregate_accounting(economic_wave_receipts)
                actual_by_key = {
                    (usage.resource_pool, usage.unit): float(usage.consumed)
                    for usage in actual_wave.subscription_usage
                    if usage.consumed is not None
                }
                for key, reserved in economic_reservations.items():
                    quota_consumed[key] = quota_consumed.get(
                        key, 0.0
                    ) + actual_by_key.get(key, reserved)

                if waiting is not None:
                    waiting_step_id, waiting_outcome = waiting
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.WAITING,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        waiting_step_id=waiting_step_id,
                        waiting_decision_id=waiting_outcome.decision.decision_id,
                        step_durations=step_durations,
                    )
                if invalid_outcome is not None:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        step_durations=step_durations,
                        error=f"step {invalid_outcome} did not produce a valid result",
                    )
                continue

            decisions: dict[str, RouteDecision] = {}
            prepared: dict[str, ActionRequest] = {}
            specs: dict[str, ExecutorSpec] = {}
            for step in ready:
                action = step.action.model_copy(deep=True)
                action.constraints = merge_constraints(workflow.constraints, action.constraints)
                if workflow.budget.max_cash_usd is not None:
                    current = aggregate_accounting(receipts).cash
                    spent = current.actual_cash_cost("USD")
                    if receipts and spent is None:
                        return self._workflow_result(
                            workflow,
                            status=WorkflowStatus.FAILED,
                            step_outputs=step_outputs,
                            receipts=receipts,
                            started=started,
                            error="workflow cash is unavailable under a finite budget",
                        )
                    accounted_spend = Decimal(0) if not receipts else spent
                    assert accounted_spend is not None
                    remaining = max(
                        0.0,
                        float(workflow.budget.max_cash_usd - accounted_spend),
                    )
                    action.context.compute.monetary_budget_remaining_usd = remaining
                    action.constraints.max_cost_usd = (
                        remaining
                        if action.constraints.max_cost_usd is None
                        else min(action.constraints.max_cost_usd, remaining)
                    )
                for binding in step.bindings:
                    source = (
                        workflow.input
                        if binding.source_step_id is None
                        else step_outputs[binding.source_step_id]
                    )
                    pointer_replace(
                        action.input,
                        binding.target_path,
                        pointer_get(source, binding.source_path),
                    )
                decision = await self.route_with_discovery(action)
                if decision.selected_executor_id is None:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=decision.explanation,
                    )
                decisions[step.step_id] = decision
                prepared[step.step_id] = action
                specs[step.step_id] = self.registry.get(decision.selected_executor_id)

            # Side effects and explicit exclusive resources serialize deterministically.
            exclusive = [
                step
                for step in ready
                if specs[step.step_id].side_effect.rank > SideEffect.READ.rank
                or specs[step.step_id].config.get("exclusive_resource")
            ]
            wave = [exclusive[0]] if exclusive else ready[:8]

            reservations: dict[tuple[str, str], float] = {}
            for step in wave:
                spec = specs[step.step_id]
                if not spec.resource_pool:
                    continue
                quota = self._subscription_quota(spec, prepared[step.step_id].context)
                resource = self.resources.get(spec.resource_pool)
                unit = (
                    quota.unit
                    if quota is not None
                    else resource.unit
                    if resource is not None
                    else "provider_unit"
                )
                key = (spec.resource_pool, unit)
                candidate = next(
                    item
                    for item in decisions[step.step_id].candidates
                    if item.executor_id == spec.id
                )
                estimated_usage = [
                    item
                    for item in candidate.estimate.subscription_usage
                    if item.resource_pool == spec.resource_pool and item.consumed is not None
                ]
                if estimated_usage:
                    for item in estimated_usage:
                        usage_key = (item.resource_pool, item.unit)
                        reservations[usage_key] = reservations.get(usage_key, 0.0) + float(
                            item.consumed or 0
                        )
                else:
                    reservations[key] = (
                        reservations.get(key, 0.0) + candidate.estimate.resources.subscription_units
                    )
                if quota is not None:
                    quota_start.setdefault(key, quota.model_copy(deep=True))
            for key, reserved in reservations.items():
                quota = quota_start.get(key)
                if (
                    quota is not None
                    and quota.remaining_units is not None
                    and quota_consumed.get(key, 0.0) + reserved > float(quota.remaining_units)
                ):
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=f"parallel subscription reservation exceeds {key[0]!r}",
                    )

            outcomes: dict[str, ExecutionOutcome | Exception] = {}

            async def run_step(
                step_id: str,
                current_outcomes: dict[str, ExecutionOutcome | Exception] = outcomes,
                current_decisions: dict[str, RouteDecision] = decisions,
            ) -> None:
                try:
                    current_outcomes[step_id] = await self.execute(
                        current_decisions[step_id],
                        approved_side_effect=approved_side_effect,
                        allow_unsafe_executor=allow_unsafe_executor,
                    )
                except Exception as exc:
                    current_outcomes[step_id] = exc

            async with asyncio.TaskGroup() as group:
                for step in wave:
                    group.create_task(run_step(step.step_id))

            for step in wave:
                outcome = outcomes[step.step_id]
                if isinstance(outcome, Exception):
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=f"step {step.step_id} failed: {type(outcome).__name__}",
                    )
                receipts.extend(outcome.receipts)
                step_durations[step.step_id] = sum(
                    receipt.duration_ms for receipt in outcome.receipts
                )
                if outcome.status in {ExecutionStatus.HOST_SELECTED, ExecutionStatus.DELEGATED}:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.WAITING,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        waiting_step_id=step.step_id,
                        waiting_decision_id=outcome.decision.decision_id,
                        step_durations=step_durations,
                    )
                if not outcome.ok:
                    return self._workflow_result(
                        workflow,
                        status=WorkflowStatus.FAILED,
                        step_outputs=step_outputs,
                        receipts=receipts,
                        started=started,
                        error=f"step {step.step_id} did not produce a valid result",
                    )
                step_outputs[step.step_id] = outcome.output
                pending.pop(step.step_id)

            wave_receipts: list[ExecutionReceipt] = []
            for step in wave:
                wave_outcome = outcomes[step.step_id]
                if isinstance(wave_outcome, ExecutionOutcome):
                    wave_receipts.extend(wave_outcome.receipts)
            actual_wave = aggregate_accounting(wave_receipts)
            actual_by_key = {
                (usage.resource_pool, usage.unit): float(usage.consumed)
                for usage in actual_wave.subscription_usage
                if usage.consumed is not None
            }
            for key, reserved in reservations.items():
                quota_consumed[key] = quota_consumed.get(key, 0.0) + actual_by_key.get(
                    key, reserved
                )

        return self._workflow_result(
            workflow,
            status=WorkflowStatus.SUCCESS,
            step_outputs=step_outputs,
            receipts=receipts,
            started=started,
            step_durations=step_durations,
        )

    async def resume_workflow(
        self,
        request: WorkflowRequest | dict[str, Any],
        waiting: WorkflowExecutionOutcome | dict[str, Any],
        *,
        step_id: str,
        output: Any,
        actual_resources: ResourceVector | None = None,
        actual_accounting: ResourceAccounting | None = None,
        approved_side_effect: SideEffect = SideEffect.READ,
        payment_approved: bool = False,
        human_approved: bool = False,
        allow_unsafe_executor: bool = False,
    ) -> WorkflowExecutionOutcome:
        workflow = (
            request
            if isinstance(request, WorkflowRequest)
            else WorkflowRequest.model_validate(request)
        )
        prior = (
            waiting
            if isinstance(waiting, WorkflowExecutionOutcome)
            else WorkflowExecutionOutcome.model_validate(waiting)
        )
        checkpoint = self.store.get_workflow_checkpoint(workflow.workflow_id)
        if (
            prior.status != WorkflowStatus.WAITING
            or prior.workflow_hash != workflow.workflow_hash
            or checkpoint is None
            or checkpoint["workflow_hash"] != workflow.workflow_hash
            or checkpoint["waiting_step_id"] != step_id
            or prior.waiting_step_id != step_id
        ):
            raise ConfigurationError("workflow continuation does not match the waiting checkpoint")
        decision = self.store.get_decision(prior.waiting_decision_id or "")
        if decision is None or decision.selected_executor_id is None:
            raise ConfigurationError("waiting workflow decision is unavailable")
        spec = self.registry.get(decision.selected_executor_id)
        if not spec.enabled:
            raise ConfigurationError("waiting workflow route is no longer active")
        self._require_active_spec(spec)
        step = next(item for item in workflow.steps if item.step_id == step_id)
        action = step.action.model_copy(deep=True)
        action.constraints = merge_constraints(workflow.constraints, action.constraints)
        for binding in step.bindings:
            source = (
                workflow.input
                if binding.source_step_id is None
                else prior.step_outputs[binding.source_step_id]
            )
            pointer_replace(
                action.input,
                binding.target_path,
                pointer_get(source, binding.source_path),
            )
        current = self.route(action)
        current_candidate = next(
            (item for item in current.candidates if item.executor_id == spec.id), None
        )
        if current_candidate is None or not current_candidate.feasible:
            raise ConfigurationError("waiting workflow route is no longer policy-feasible")
        if spec.output_schema is not None:
            validate_json(output, spec.output_schema, label=f"resumed output for {spec.id}")
        terminal = self.record_external_outcome(
            ExternalOutcomeReport(
                decision_id=decision.decision_id,
                executor_id=spec.id,
                status=ExecutionStatus.SUCCESS,
                actual_resources=actual_resources or ResourceVector(),
                output_valid=True,
                task_valid=True,
            ),
            _trusted_accounting=actual_accounting,
        )
        initial = dict(prior.step_outputs)
        initial[step_id] = output
        return await self.execute_workflow(
            workflow,
            approved_side_effect=approved_side_effect,
            payment_approved=payment_approved,
            human_approved=human_approved,
            allow_unsafe_executor=allow_unsafe_executor,
            _initial_outputs=initial,
            _initial_receipts=[*prior.receipts, terminal],
        )

    def register(self, spec: ExecutorSpec) -> None:
        """Register an executor dynamically for embedded-agent use."""

        self._ensure_open()
        self.registry.register(spec)

    def list_capabilities(self) -> list[dict[str, Any]]:
        self._ensure_open()
        return self.registry.describe()

    def search_capabilities(
        self,
        query: str = "",
        *,
        prefix: str | None = None,
        limit: int = 20,
        cursor: int = 0,
        include_executors: bool = False,
    ) -> dict[str, Any]:
        self._ensure_open()
        return self.registry.search(
            query,
            prefix=prefix,
            limit=limit,
            cursor=cursor,
            include_executors=include_executors,
        )

    def compact_decision(self, decision: RouteDecision) -> CompactRouteDecision:
        feasible = [
            candidate
            for candidate in decision.candidates
            if candidate.feasible and candidate.score is not None
        ]
        winner_score = (
            feasible[0].score.total if feasible and feasible[0].score is not None else 0.0
        )
        alternatives: list[CompactAlternative] = []
        for candidate in feasible[1:4]:
            if candidate.score is None:  # pragma: no cover - filtered above
                continue
            alternatives.append(
                CompactAlternative(
                    executor_id=candidate.executor_id,
                    kind=self.registry.get(candidate.executor_id).kind,
                    score=candidate.score.total,
                    delta=max(0.0, candidate.score.total - winner_score),
                )
            )
        selected = decision.selected_executor_id
        reason = (
            decision.bypass_reason.value.replace("_", " ")
            if decision.bypass_reason is not None
            else f"lowest feasible burden under {decision.policy.name}"
            if selected is not None
            else "no feasible route"
        )
        return CompactRouteDecision(
            decision_id=decision.decision_id,
            action_id=decision.action.action_id,
            capability=decision.action.capability,
            selected=selected,
            disposition=decision.disposition,
            bypass_reason=decision.bypass_reason,
            reason=reason,
            alternatives=alternatives,
            rejected=sum(not candidate.feasible for candidate in decision.candidates),
        )

    def compact_outcome(self, outcome: ExecutionOutcome) -> CompactExecutionOutcome:
        return CompactExecutionOutcome(
            ok=outcome.ok,
            status=outcome.status,
            output=outcome.output,
            decision=self.compact_decision(outcome.decision),
            receipts=[
                CompactReceipt(
                    receipt_id=receipt.receipt_id,
                    executor_id=receipt.executor_id,
                    status=receipt.status,
                    resources=receipt.actual_resources,
                    valid=(
                        False
                        if receipt.schema_valid is False or receipt.task_valid is False
                        else True
                        if receipt.status == ExecutionStatus.SUCCESS
                        else None
                    ),
                    error=receipt.error_message,
                )
                for receipt in outcome.receipts
            ],
            instructions=outcome.delegated_instructions,
        )

    def list_policies(self) -> list[dict[str, Any]]:
        self._ensure_open()
        return [
            {
                "name": name,
                "description": policy.description,
                "weights": policy.weights.model_dump(mode="json"),
                "constraints": policy.constraints.model_dump(mode="json"),
            }
            for name, policy in sorted(self.manifest.policies.items())
        ]

    def quotes(self, request: QuoteRequest | dict[str, Any]) -> list[Quote]:
        self._ensure_open()
        model = (
            request if isinstance(request, QuoteRequest) else QuoteRequest.model_validate(request)
        )
        compatible, _ = self.registry.compatible(model.action.capability, model.action.input)
        compatible_ids = {spec.id for spec in compatible}
        requested_ids = set(model.executor_ids or compatible_ids) & compatible_ids
        filtered = model.model_copy(update={"executor_ids": sorted(requested_ids)})
        quotes = self.quote_service.quote(filtered)
        for quote in quotes:
            self.store.save_quote(quote)
        return quotes

    def accept_quote(
        self,
        quote_id: str,
        *,
        action_id: str,
        max_amount_usd: float | None = None,
    ) -> QuoteAcceptance:
        self._ensure_open()
        quote = self.store.get_quote(quote_id)
        if quote is None:
            raise ConfigurationError(f"unknown quote {quote_id!r}")
        acceptance = self.quote_service.accept(
            quote,
            action_id=action_id,
            max_amount_usd=max_amount_usd,
        )
        self.store.save_quote_acceptance(acceptance)
        return acceptance

    def signed_receipt(self, receipt_id: str) -> SignedExecutionReceipt:
        self._ensure_open()
        if self.signer is None:
            raise ConfigurationError("receipt signing is not configured")
        receipt = self.store.get_receipt(receipt_id)
        if receipt is None:
            raise ConfigurationError(f"unknown receipt {receipt_id!r}")
        return self.signer.sign_receipt(receipt)

    def record_observation(self, observation: Observation | dict[str, Any]) -> Observation:
        self._ensure_open()
        model = (
            observation
            if isinstance(observation, Observation)
            else Observation.model_validate(observation)
        )
        if model.trust == TrustLevel.ATTESTED:
            if self.signer is None or model.attestation is None:
                raise ConfigurationError("attested observation requires a configured verifier")
            unsigned = model.model_copy(update={"attestation": None})
            if not self.signer.verify(unsigned, model.attestation):
                raise ConfigurationError("observation attestation is invalid")
        self.store.save_observation(model)
        return model

    def reputation(self, provider_id: str, capability: str) -> ProviderReputation:
        self._ensure_open()
        observations = [
            observation
            for observation in self.store.list_observations(
                provider_id=provider_id,
                capability=capability,
            )
            if observation.trust in {TrustLevel.OBSERVED, TrustLevel.VERIFIED, TrustLevel.ATTESTED}
        ]
        if not observations:
            return ProviderReputation(provider_id=provider_id, capability=capability)
        latencies = sorted(item.resources.latency_ms for item in observations)
        costs = [
            value
            for item in observations
            if (value := item.accounting.cash.actual_cash_cost("USD")) is not None
        ]
        successes = [
            item.execution_success for item in observations if item.execution_success is not None
        ]
        validity = [item.task_valid for item in observations if item.task_valid is not None]
        qualities = [item.quality_score for item in observations if item.quality_score is not None]
        return ProviderReputation(
            provider_id=provider_id,
            capability=capability,
            executions=len(observations),
            success_rate=(
                sum(bool(value) for value in successes) / len(successes) if successes else None
            ),
            task_valid_rate=(
                sum(bool(value) for value in validity) / len(validity) if validity else None
            ),
            quality_score=(sum(qualities) / len(qualities) if qualities else None),
            latency_p50_ms=latencies[(len(latencies) - 1) // 2],
            latency_p95_ms=latencies[max(0, math.ceil(len(latencies) * 0.95) - 1)],
            actual_cost_mean_usd=(
                float(sum(costs, Decimal(0)) / len(costs)) if costs else None
            ),
        )

    async def reserve_quote_payment(
        self,
        quote_id: str,
        *,
        action_id: str,
        approved_side_effect: SideEffect = SideEffect.READ,
        human_approved: bool = False,
    ) -> PaymentReservation:
        self._ensure_open()
        if self.budget_manager is None:
            raise ConfigurationError("agent budget is not configured")
        quote = self.store.get_quote(quote_id)
        if quote is None:
            raise ConfigurationError(f"unknown quote {quote_id!r}")
        return await self.budget_manager.reserve(
            quote,
            action_id=action_id,
            approved_side_effect=approved_side_effect,
            human_approved=human_approved,
        )

    async def capture_payment(self, reservation_id: str) -> PaymentCapture:
        self._ensure_open()
        if self.budget_manager is None:
            raise ConfigurationError("agent budget is not configured")
        return await self.budget_manager.capture(reservation_id)

    async def refund_payment(self, capture_id: str, amount_usd: float) -> PaymentRefund:
        self._ensure_open()
        if self.budget_manager is None:
            raise ConfigurationError("agent budget is not configured")
        return await self.budget_manager.refund(capture_id, amount_usd)

    def metrics(self, *, limit: int = 10_000) -> EconomicMetrics:
        """Aggregate private economic savings without pricing subscription quota."""

        self._ensure_open()
        decisions = self.store.list_decisions(limit=limit)
        receipts = self.store.list_receipts(limit=limit)
        operational_receipts = [
            self._receipt_with_current_payment_evidence(receipt)
            for receipt in receipts
            if receipt.status
            not in {
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
                ExecutionStatus.UNKNOWN,
            }
        ]
        accounting = aggregate_accounting(operational_receipts)
        final_receipts: dict[str, ExecutionReceipt] = {}
        for receipt in reversed(receipts):
            if receipt.status not in {
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
                ExecutionStatus.UNKNOWN,
            }:
                final_receipts[receipt.decision_id] = receipt

        actual_cash = accounting.cash.actual_cash_cost("USD")
        result = EconomicMetrics(
            decisions=len(decisions),
            actual_cash_known_subtotal_usd=accounting.cash.known_subtotal("USD"),
            actual_cash_total_usd=actual_cash,
            cash_status=accounting.cash.status,
            subscription_usage=accounting.subscription_usage,
            total_money_spent_usd=(float(actual_cash) if actual_cash is not None else None),
        )
        result.local_cpu_ms_consumed = sum(
            receipt.actual_resources.cpu_ms
            for receipt in operational_receipts
            if self.registry.get(receipt.executor_id).locality.value in {"in_process", "local"}
        )
        api_receipts = [
            receipt
            for receipt in operational_receipts
            if self.registry.get(receipt.executor_id).kind in {ExecutorKind.HTTP, ExecutorKind.MCP}
        ]
        api_cash = (
            aggregate_accounting(api_receipts).cash.actual_cash_cost("USD")
            if api_receipts
            else Decimal(0)
        )
        result.api_money_spent_usd = float(api_cash) if api_cash is not None else None
        for decision in decisions:
            selected_id = decision.selected_executor_id
            if selected_id is None:
                continue
            selected_spec = self.registry.get(selected_id)
            feasible = [candidate for candidate in decision.candidates if candidate.feasible]
            host_candidates = [
                candidate
                for candidate in feasible
                if self.registry.get(candidate.executor_id).kind == ExecutorKind.HOST
            ]
            if selected_spec.kind != ExecutorKind.HOST and host_candidates:
                result.model_actions_avoided += 1
                result.model_turns_avoided += 1
                result.context_tokens_avoided += max(
                    candidate.estimate.resources.context_tokens
                    + candidate.estimate.resources.input_tokens
                    + candidate.estimate.resources.output_tokens
                    for candidate in host_candidates
                )
                result.subscription_capacity_conserved += max(
                    candidate.estimate.resources.subscription_units for candidate in host_candidates
                )
            if selected_spec.kind == ExecutorKind.COMMAND and any(
                self.registry.get(candidate.executor_id).kind
                in {ExecutorKind.HOST, ExecutorKind.MCP}
                for candidate in feasible
            ):
                result.cli_substitutions += 1
            if selected_spec.kind != ExecutorKind.MCP and any(
                self.registry.get(candidate.executor_id).kind == ExecutorKind.MCP
                for candidate in feasible
            ):
                result.mcp_calls_avoided += 1
            if "browser" not in selected_spec.tags and any(
                "browser" in self.registry.get(candidate.executor_id).tags for candidate in feasible
            ):
                result.browser_actions_avoided += 1

            final_receipt = final_receipts.get(decision.decision_id)
            if final_receipt is None:
                continue
            if (
                final_receipt.status == ExecutionStatus.SUCCESS
                and final_receipt.task_valid is not False
            ):
                result.successful_actions += 1
            else:
                result.failed_actions += 1
            alternatives = [
                candidate.estimate.resources.latency_ms
                for candidate in feasible
                if candidate.executor_id != selected_id
            ]
            if alternatives:
                result.wall_clock_time_saved_ms += max(
                    0.0, min(alternatives) - final_receipt.actual_resources.latency_ms
                )
        if (
            result.successful_actions
            and actual_cash is not None
            and result.total_money_spent_usd is not None
        ):
            result.cost_per_successful_action_usd = (
                result.total_money_spent_usd / result.successful_actions
            )
        return result

    def _receipt_with_current_payment_evidence(
        self,
        receipt: ExecutionReceipt,
    ) -> ExecutionReceipt:
        """Return a reporting copy resolved from immutable economic records."""

        prepared_id = receipt.metadata.get("prepared_id")
        if not isinstance(prepared_id, str):
            return receipt
        settlement_id = receipt.metadata.get("settlement_id")
        authorization_id = receipt.metadata.get("authorization_id")
        paid = isinstance(settlement_id, str) or isinstance(authorization_id, str)
        settlements = self.store.list_settlement_receipts(
            prepared_id=prepared_id,
            limit=10_000,
        )
        if not settlements:
            # A prepared route with no payment authorization is the explicit
            # confirmed-free path. A paid route without durable settlement stays
            # unknown even if an older receipt carried an optimistic mirror.
            if not paid:
                return receipt
            accounting = receipt.accounting.model_copy(deep=True)
            accounting.cash = CashAccounting()
            return receipt.model_copy(update={"accounting": accounting})
        if len(settlements) != 1:
            accounting = receipt.accounting.model_copy(deep=True)
            accounting.cash = CashAccounting(status=EvidenceStatus.CONFLICT)
            return receipt.model_copy(update={"accounting": accounting})

        settlement = settlements[0]
        charge_id = receipt.metadata.get("charge_id")
        if (
            (isinstance(settlement_id, str) and settlement_id != settlement.settlement_id)
            or (isinstance(charge_id, str) and charge_id != settlement.charge_id)
        ):
            accounting = receipt.accounting.model_copy(deep=True)
            accounting.cash = CashAccounting(status=EvidenceStatus.CONFLICT)
            return receipt.model_copy(update={"accounting": accounting})
        resolved = cash_accounting_for_reporting(
            settlement,
            reconciliations=self.store.list_billing_reconciliations(
                settlement_id=settlement.settlement_id,
                limit=10_000,
            ),
            refunds=self.store.list_refund_receipts_v2(
                settlement_id=settlement.settlement_id,
                limit=10_000,
            ),
        )
        accounting = receipt.accounting.model_copy(deep=True)
        accounting.cash = resolved
        return receipt.model_copy(update={"accounting": accounting})

    def counterfactual(self, receipt_id: str) -> CounterfactualReport:
        """Compare an observed attempt with feasible alternatives from its decision."""

        self._ensure_open()
        receipt = self.store.get_receipt(receipt_id)
        if receipt is None:
            raise ConfigurationError(f"unknown receipt {receipt_id!r}")
        decision = self.store.get_decision(receipt.decision_id)
        if decision is None:
            raise ConfigurationError(f"decision {receipt.decision_id!r} is unavailable")
        selected = next(
            (
                candidate
                for candidate in decision.candidates
                if candidate.executor_id == receipt.executor_id
            ),
            None,
        )
        selected_units = (
            selected.estimate.resources.subscription_units if selected is not None else 0.0
        )
        alternatives: list[CounterfactualAlternative] = []
        for candidate in decision.candidates:
            if not candidate.feasible or candidate.executor_id == receipt.executor_id:
                continue
            spec = self.registry.get(candidate.executor_id)
            alternatives.append(
                CounterfactualAlternative(
                    executor_id=spec.id,
                    executor_kind=spec.kind,
                    estimated_resources=candidate.estimate.resources,
                    estimated_score=(candidate.score.total if candidate.score else None),
                    estimated_cash_saving_usd=None,
                    estimated_latency_saving_ms=max(
                        0.0,
                        receipt.actual_resources.latency_ms
                        - candidate.estimate.resources.latency_ms,
                    ),
                    conserves_subscription_units=(
                        selected_units if spec.kind != ExecutorKind.HOST else 0.0
                    ),
                )
            )
        alternatives.sort(
            key=lambda item: (
                item.estimated_score if item.estimated_score is not None else float("inf"),
                item.executor_id,
            )
        )
        best = alternatives[0] if alternatives else None
        saving = best.estimated_cash_saving_usd if best else None
        percent = None
        quota = selected.subscription_quota if selected is not None else None
        avoidable_units = best.conserves_subscription_units if best else 0.0
        explanation = (
            f"Alternative {best.executor_id!r} has a lower policy score; actual cash delta "
            f"is unavailable. It may conserve {avoidable_units:g} provider-local unit(s)."
            if best
            else "No other feasible route was present in the original decision."
        )
        return CounterfactualReport(
            receipt_id=receipt.receipt_id,
            decision_id=decision.decision_id,
            selected_executor_id=receipt.executor_id,
            actual_resources=receipt.actual_resources,
            alternatives=alternatives,
            best_alternative_executor_id=best.executor_id if best else None,
            potential_cash_saving_usd=saving,
            potential_cash_saving_percent=percent,
            avoidable_subscription_units=avoidable_units,
            subscription_pressure=quota.state if quota is not None else None,
            actual_cash_comparison=EvidenceStatus.UNAVAILABLE,
            actual_cash_saving_usd=None,
            explanation=explanation,
        )

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for executor in self._executors.values():
            await executor.close()
        self._executors.clear()
        for client in self._owned_quote_clients:
            await client.close()
        self._owned_quote_clients.clear()
        self.store.close()

    async def __aenter__(self) -> Router:
        self._ensure_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
