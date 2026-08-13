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

import math
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from .config import load_manifest
from .discovery import CompositeProviderRegistry
from .economics import HMACSigner, QuoteService
from .errors import (
    ApprovalRequired,
    ConfigurationError,
    NoRouteError,
)
from .estimator import HistoricalEstimator
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
    CounterfactualAlternative,
    CounterfactualReport,
    EconomicMetrics,
    EstimateSource,
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
    ProviderDescriptor,
    ProviderReputation,
    Quote,
    QuoteAcceptance,
    QuoteRequest,
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
from .policy import builtin_policies, policy_with_constraints, resolve_policy
from .registry import Registry, validate_json
from .runtime import detect_compute_availability
from .scoring import score_candidate
from .store import ReceiptStore
from .telemetry import start_span, trace_id_from_span
from .validators import ValidationContext, ValidatorCallback, run_validators

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
            raise ConfigurationError(
                f"default policy {normalized.default_policy!r} is not defined"
            )
        self.manifest = normalized
        self.manifest_path = Path(manifest_path).resolve() if manifest_path else None
        self.registry = Registry(normalized.executors)
        self.resources = {resource.id: resource for resource in normalized.resources}
        self.provider_registry = CompositeProviderRegistry(normalized.registries)
        self.providers: dict[str, ProviderDescriptor] = {}
        self.store = store or ReceiptStore(normalized.database)
        self.estimator = HistoricalEstimator(self.store)
        self.validator_callbacks = dict(validator_callbacks or {})
        self.quote_service = QuoteService(self.registry, signer=signer)
        self.signer = signer
        self.budget_manager = (
            BudgetManager(
                normalized.budget,
                self.store,
                payment_adapter
                or PrepaidBalanceAdapter(normalized.budget.prepaid_balance_usd),
            )
            if normalized.budget is not None
            else None
        )
        self._executors: dict[ExecutorKind, BaseExecutor] = {}
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
        return resource.quota if resource is not None else None

    def route(self, request: ActionRequest | dict[str, Any]) -> RouteDecision:
        """Validate, filter, rank, explain, and persist an action decision."""

        self._ensure_open()
        request_model = (
            request if isinstance(request, ActionRequest) else ActionRequest.model_validate(request)
        )
        request_model = self._fill_runtime_context(request_model)
        policy = self._policy_for(request_model)
        compatible, schema_errors = self.registry.compatible(
            request_model.capability, request_model.input
        )

        candidates: list[CandidateScore] = []
        for spec in compatible:
            estimate = self.estimator.estimate(spec, policy)
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
            explanation = (
                f"No enabled executor advertises capability {request_model.capability!r}."
            )
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
            explanation=explanation,
        )
        self._persist_decision(decision)
        return decision

    async def discover(self, capability: str) -> list[ProviderDescriptor]:
        """Load only providers relevant to one requested capability."""

        self._ensure_open()
        providers = await self.provider_registry.discover(capability)
        for provider in providers:
            self.providers.setdefault(provider.provider_id, provider)
            for spec in provider.executors:
                if not self.registry.contains(spec.id):
                    self.registry.register(spec)
        return providers

    async def route_with_discovery(
        self, request: ActionRequest | dict[str, Any]
    ) -> RouteDecision:
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
            if (
                spec.side_effect.rank > approved_side_effect.rank
                and spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}
            ):
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
                entry.actual_score.total
                if entry.actual_score is not None
                else float("inf"),
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

        fallback = decision.policy.fallback
        max_attempts = min(len(candidates), fallback.max_attempts if fallback.enabled else 1)
        attempts: list[ExecutionReceipt] = []
        last_output: Any = None

        for attempt_number, candidate in enumerate(candidates[:max_attempts], start=1):
            spec = self.registry.get(candidate.executor_id)
            if (
                spec.side_effect.rank > approved_side_effect.rank
                and spec.kind not in {ExecutorKind.DELEGATE, ExecutorKind.HOST}
            ):
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
                        validate_json(raw.output, spec.output_schema, label=f"output from {spec.id}")
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
                    actual_resources=raw.resources,
                    transport_success=raw.status in {
                        ExecutionStatus.SUCCESS,
                        ExecutionStatus.DELEGATED,
                        ExecutionStatus.HOST_SELECTED,
                    },
                    execution_success=(
                        True if raw.status == ExecutionStatus.SUCCESS else None
                    ),
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
                        if any(
                            result.quality_score is not None
                            for result in validation_results
                        )
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
                        **(
                            {
                                "stdout_preview": (raw.stdout or "")[:4096],
                                "stderr_preview": (raw.stderr or "")[:4096],
                            }
                            if bool(spec.config.get("store_output_preview", False))
                            else {}
                        ),
                    },
                )
                self.store.save_receipt(receipt)
                self._observe_receipt(spec, receipt)
                attempts.append(receipt)
                last_output = raw.output

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
                    False
                    if output_valid is False or task_valid is False
                    else task_valid
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
                and (
                    last_receipt.task_valid is False
                    or last_receipt.output_valid is False
                )
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
            actual_resources=report_model.actual_resources,
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
            metadata={**report_model.metadata, "externally_reported": True},
        )
        self.store.save_external_receipt_once(receipt)
        self._observe_receipt(spec, receipt)
        return receipt

    def register(self, spec: ExecutorSpec) -> None:
        """Register an executor dynamically for embedded-agent use."""

        self._ensure_open()
        self.registry.register(spec)

    def list_capabilities(self) -> list[dict[str, Any]]:
        self._ensure_open()
        return self.registry.describe()

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
        model = request if isinstance(request, QuoteRequest) else QuoteRequest.model_validate(request)
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
            if observation.trust
            in {TrustLevel.OBSERVED, TrustLevel.VERIFIED, TrustLevel.ATTESTED}
        ]
        if not observations:
            return ProviderReputation(provider_id=provider_id, capability=capability)
        latencies = sorted(item.resources.latency_ms for item in observations)
        costs = [item.resources.monetary_usd for item in observations]
        successes = [item.execution_success for item in observations if item.execution_success is not None]
        validity = [item.task_valid for item in observations if item.task_valid is not None]
        qualities = [item.quality_score for item in observations if item.quality_score is not None]
        return ProviderReputation(
            provider_id=provider_id,
            capability=capability,
            executions=len(observations),
            success_rate=(sum(bool(value) for value in successes) / len(successes) if successes else None),
            task_valid_rate=(sum(bool(value) for value in validity) / len(validity) if validity else None),
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
        final_receipts: dict[str, ExecutionReceipt] = {}
        for receipt in reversed(receipts):
            if receipt.status not in {
                ExecutionStatus.DELEGATED,
                ExecutionStatus.HOST_SELECTED,
                ExecutionStatus.UNKNOWN,
            }:
                final_receipts[receipt.decision_id] = receipt

        result = EconomicMetrics(decisions=len(decisions))
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
                    candidate.estimate.resources.subscription_units
                    for candidate in host_candidates
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
                "browser" in self.registry.get(candidate.executor_id).tags
                for candidate in feasible
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
            result.total_money_spent_usd += final_receipt.actual_resources.monetary_usd
            if selected_spec.locality.value in {"in_process", "local"}:
                result.local_cpu_ms_consumed += final_receipt.actual_resources.cpu_ms
            if selected_spec.kind in {ExecutorKind.HTTP, ExecutorKind.MCP}:
                result.api_money_spent_usd += final_receipt.actual_resources.monetary_usd
            alternatives = [
                candidate.estimate.resources.latency_ms
                for candidate in feasible
                if candidate.executor_id != selected_id
            ]
            if alternatives:
                result.wall_clock_time_saved_ms += max(
                    0.0, min(alternatives) - final_receipt.actual_resources.latency_ms
                )
        if result.successful_actions:
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
                    estimated_cash_saving_usd=max(
                        0.0,
                        receipt.actual_resources.monetary_usd
                        - candidate.estimate.resources.monetary_usd,
                    ),
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
                item.estimated_score
                if item.estimated_score is not None
                else float("inf"),
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
            f"Alternative {best.executor_id!r} could save approximately "
            f"${saving:.6f} and {avoidable_units:g} provider-local subscription unit(s)."
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
