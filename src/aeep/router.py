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
import time
from collections.abc import Mapping
from decimal import Decimal
from pathlib import Path
from typing import Any

from .accounting import aggregate_accounting, mirror_actual_cash
from .config import load_manifest
from .discovery import CompositeProviderRegistry
from .economics import HMACSigner, QuoteService
from .errors import (
    ApprovalRequired,
    ConfigurationError,
    NoRouteError,
)
from .estimator import HistoricalEstimator, action_features
from .executors import (
    CommandExecutor,
    DelegateExecutor,
    HostExecutor,
    HTTPExecutor,
    MCPExecutor,
    PythonExecutor,
)
from .executors.base import BaseExecutor, ExecutionContext
from .models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    BenchmarkEntry,
    BenchmarkResult,
    CandidateScore,
    CompactAlternative,
    CompactExecutionOutcome,
    CompactReceipt,
    CompactRouteDecision,
    CounterfactualAlternative,
    CounterfactualReport,
    EconomicMetrics,
    EstimateSource,
    EvidenceStatus,
    ExecutionOutcome,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    ExternalOutcomeReport,
    Manifest,
    Observation,
    PaymentCapture,
    PaymentRefund,
    PaymentReservation,
    PolicyConfig,
    PolicyValuation,
    ProviderDescriptor,
    ProviderReputation,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    QuoteRequest,
    ResourceAccounting,
    ResourceVector,
    RouteDecision,
    RouteEstimate,
    SideEffect,
    SignedExecutionReceipt,
    SubscriptionQuota,
    TrustLevel,
    ValidationKind,
    ValidationResult,
    utc_now,
)
from .payments import BudgetManager, PaymentAdapter, PrepaidBalanceAdapter
from .policy import builtin_policies, merge_constraints, policy_with_constraints, resolve_policy
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
    ) -> None:
        normalized = manifest.model_copy(deep=True)
        policies = builtin_policies()
        policies.update(normalized.policies)
        normalized.policies = policies
        if normalized.default_policy not in normalized.policies:
            raise ConfigurationError(f"default policy {normalized.default_policy!r} is not defined")
        self.manifest = normalized
        self.manifest_path = Path(manifest_path).resolve() if manifest_path else None
        self.registry = Registry(normalized.executors)
        self.resources = {resource.id: resource for resource in normalized.resources}
        self.provider_registry = CompositeProviderRegistry(normalized.registries)
        self.providers: dict[str, ProviderDescriptor] = {}
        self.store = store or ReceiptStore(normalized.database)
        for candidate in self.store.list_route_candidates():
            if candidate.status == RouteLifecycle.ACTIVE:
                if candidate.behavior_fingerprint != behavior_fingerprint(candidate.spec):
                    candidate.status = RouteLifecycle.SUSPENDED
                    candidate.reason = "stored active fingerprint does not match spec"
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
        self.signer = signer
        self.budget_manager = (
            BudgetManager(
                normalized.budget,
                self.store,
                payment_adapter or PrepaidBalanceAdapter(normalized.budget.prepaid_balance_usd),
            )
            if normalized.budget is not None
            else None
        )
        self._executors: dict[ExecutorKind, BaseExecutor] = {}
        self._validated_decisions: dict[str, str] = {}
        self._closed = False

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
            "argument_mode",
            "callable",
            "executable",
            "exit_code",
            "host",
            "ipc_bytes",
            "method",
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
            "tool_schema_tokens_estimate",
        }
        return {
            key: value
            for key, value in metadata.items()
            if key in allowed and isinstance(value, (str, int, float, bool, type(None)))
        }

    def _save_receipt(self, receipt: ExecutionReceipt) -> None:
        persisted = receipt.model_copy(deep=True)
        persisted.metadata = self._safe_receipt_metadata(persisted.metadata)
        if persisted.error_message:
            persisted.error_message = persisted.error_type or "execution failed"
        self.store.save_receipt(persisted)

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
        override = context.subscription_quotas.get(spec.resource_pool)
        if override is not None:
            return override
        resource = self.resources.get(spec.resource_pool)
        if resource is None:
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

    def route(self, request: ActionRequest | dict[str, Any]) -> RouteDecision:
        """Validate, filter, rank, explain, and persist an action decision."""

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
            estimate = self.estimator.estimate(spec, policy, features)
            candidates.append(
                score_candidate(
                    spec,
                    estimate,
                    policy,
                    request_model.context,
                    self._subscription_quota(spec, request_model.context),
                )
            )

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

        if not candidates and not self.registry.find(request_model.capability):
            explanation = f"No enabled executor advertises capability {request_model.capability!r}."
        elif selected is None:
            reason_count = sum(len(item.rejection_reasons) for item in rejected)
            explanation = (
                f"No executor is feasible for {request_model.capability!r}; "
                f"{len(rejected)} candidate(s) produced {reason_count} rejection reason(s)."
            )
        else:
            winner = feasible[0]
            score = winner.score.total if winner.score is not None else 0.0
            explanation = (
                f"Selected {selected!r} from {len(feasible)} feasible route(s) under "
                f"policy {policy.name!r}; lower score is better (winner {score:.6f})."
            )

        decision = RouteDecision(
            action=request_model,
            policy=policy,
            selected_executor_id=selected,
            candidates=ordered,
            action_features=features,
            explanation=explanation,
        )
        self._persist_decision(decision)
        self._validated_decisions[decision.decision_id] = self._decision_digest(decision)
        return decision

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
        if spec.kind == ExecutorKind.PYTHON:
            raise ConfigurationError(
                "external Python candidates cannot be qualified in-process; "
                "use a reviewed command/container route or a trusted manifest executor"
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
        candidate = self.store.get_route_candidate(executor_id)
        if candidate is None or candidate.status != RouteLifecycle.QUALIFIED:
            raise ConfigurationError("candidate must be qualified before activation")
        report = self.store.get_qualification_report(candidate.qualification_report_id or "")
        if (
            report is None
            or not report.passed
            or report.behavior_fingerprint != candidate.behavior_fingerprint
            or behavior_fingerprint(candidate.spec) != candidate.behavior_fingerprint
        ):
            raise ConfigurationError("qualification evidence does not match candidate fingerprint")
        candidate.status = RouteLifecycle.ACTIVE
        candidate.spec.enabled = True
        candidate.updated_at = utc_now()
        self.store.save_route_candidate(candidate)
        self.registry.replace(candidate.spec)
        return candidate

    def suspend_candidate(self, executor_id: str, *, reason: str) -> RouteCandidate:
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

    async def route_with_discovery(self, request: ActionRequest | dict[str, Any]) -> RouteDecision:
        request_model = (
            request if isinstance(request, ActionRequest) else ActionRequest.model_validate(request)
        )
        if not self.registry.find(request_model.capability):
            await self.discover(request_model.capability)
        return self.route(request_model)

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
            if not spec.enabled or spec.capability != decision.action.capability:
                raise NoRouteError(
                    f"route {spec.id!r} is no longer active for {decision.action.capability!r}; reroute"
                )
            validate_json(decision.action.input, spec.input_schema, label=f"input for {spec.id}")
            current_policy = self._policy_for(decision.action)
            current = score_candidate(
                spec,
                self.estimator.estimate(spec, current_policy, decision.action_features),
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
                raw = await self._executor_for(spec.kind).execute(
                    ExecutionContext(
                        request=decision.action,
                        spec=spec,
                        estimate=estimate,
                        attempt=attempt_number,
                    )
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
                    metadata={**raw.metadata, "exit_code": raw.exit_code},
                )
                self._save_receipt(receipt)
                self._observe_receipt(spec, receipt)
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
            metadata={"externally_reported": True},
        )
        persisted = receipt.model_copy(deep=True)
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
        allow_unsafe_executor: bool = False,
        _initial_outputs: dict[str, Any] | None = None,
        _initial_receipts: list[ExecutionReceipt] | None = None,
    ) -> WorkflowExecutionOutcome:
        """Execute a caller-authored DAG through the ordinary route/execute boundary."""

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
                    remaining = max(0.0, float(workflow.budget.max_cash_usd - (spent or 0)))
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
            f"lowest feasible burden under {decision.policy.name}"
            if selected is not None
            else "no feasible route"
        )
        return CompactRouteDecision(
            decision_id=decision.decision_id,
            action_id=decision.action.action_id,
            capability=decision.action.capability,
            selected=selected,
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
        costs = [item.resources.monetary_usd for item in observations]
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
            actual_cost_mean_usd=sum(costs) / len(costs),
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
            receipt
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
            total_money_spent_usd=float(actual_cash or 0),
        )
        result.local_cpu_ms_consumed = sum(
            receipt.actual_resources.cpu_ms
            for receipt in operational_receipts
            if self.registry.get(receipt.executor_id).locality.value in {"in_process", "local"}
        )
        result.api_money_spent_usd = sum(
            float(value)
            for receipt in operational_receipts
            if self.registry.get(receipt.executor_id).kind in {ExecutorKind.HTTP, ExecutorKind.MCP}
            and (value := receipt.accounting.cash.actual_cash_cost("USD")) is not None
        )
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
        if result.successful_actions and actual_cash is not None:
            result.cost_per_successful_action_usd = (
                result.total_money_spent_usd / result.successful_actions
            )
        return result

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
                    estimated_cash_saving_usd=0.0,
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
        saving = best.estimated_cash_saving_usd if best else 0.0
        percent = (
            saving / receipt.actual_resources.monetary_usd * 100.0
            if receipt.actual_resources.monetary_usd > 0
            else None
        )
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
        self.store.close()

    async def __aenter__(self) -> Router:
        self._ensure_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
