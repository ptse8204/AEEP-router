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

from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import load_manifest
from .errors import (
    ApprovalRequired,
    ConfigurationError,
    ExecutionFailed,
    NoRouteError,
)
from .estimator import HistoricalEstimator
from .executors import CommandExecutor, DelegateExecutor, HTTPExecutor, MCPExecutor, PythonExecutor
from .executors.base import BaseExecutor, ExecutionContext
from .models import (
    ActionConstraints,
    ActionContext,
    ActionRequest,
    BenchmarkEntry,
    BenchmarkResult,
    CandidateScore,
    ExecutionOutcome,
    ExecutionReceipt,
    ExecutionStatus,
    EstimateSource,
    ExecutorKind,
    ExternalOutcomeReport,
    Manifest,
    RouteDecision,
    RouteEstimate,
    SideEffect,
    utc_now,
)
from .policy import builtin_policies, policy_with_constraints, resolve_policy
from .registry import Registry, validate_json
from .runtime import detect_compute_availability
from .scoring import score_candidate
from .store import ReceiptStore
from .telemetry import start_span, trace_id_from_span


_EXECUTOR_TYPES: dict[ExecutorKind, type[BaseExecutor]] = {
    ExecutorKind.COMMAND: CommandExecutor,
    ExecutorKind.PYTHON: PythonExecutor,
    ExecutorKind.HTTP: HTTPExecutor,
    ExecutorKind.MCP: MCPExecutor,
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
        self.store = store or ReceiptStore(normalized.database)
        self.estimator = HistoricalEstimator(self.store)
        self._executors: dict[ExecutorKind, BaseExecutor] = {}
        self._closed = False

    @classmethod
    def from_manifest(cls, path: str | Path | None = None) -> "Router":
        manifest, manifest_path = load_manifest(path)
        return cls(manifest, manifest_path=manifest_path)

    def _ensure_open(self) -> None:
        if self._closed:
            raise ConfigurationError("router is closed")

    def _policy_for(self, request: ActionRequest):
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
            candidates.append(score_candidate(spec, estimate, policy, request_model.context))

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
        route_decision = self.route(request_model)
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
            if spec.kind == ExecutorKind.DELEGATE and not include_delegates:
                entry.skipped_reason = "delegated routes are excluded unless explicitly requested"
                result.entries.append(entry)
                continue
            if not spec.idempotent and not allow_non_idempotent:
                entry.skipped_reason = "non-idempotent route excluded from benchmark"
                result.entries.append(entry)
                continue
            if spec.side_effect.rank > approved_side_effect.rank and spec.kind != ExecutorKind.DELEGATE:
                entry.skipped_reason = (
                    f"requires {spec.side_effect.value} approval; ceiling is "
                    f"{approved_side_effect.value}"
                )
                result.entries.append(entry)
                continue
            if (
                not spec.safe_to_auto_execute
                and spec.kind != ExecutorKind.DELEGATE
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
                    if receipt.status != ExecutionStatus.DELEGATED:
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
                        )
                        entry.actual_score = actual_candidate.score
            except Exception as exc:  # one bad integration must not abort calibration
                entry.ok = False
                entry.status = ExecutionStatus.FAILED
                entry.error_message = str(exc)
            result.entries.append(entry)

        ranked = [entry for entry in result.entries if entry.actual_score is not None]
        ranked.sort(key=lambda entry: (entry.actual_score.total, entry.executor_id))
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
            decision = self.route(request_or_decision)
        elif "decision_id" in request_or_decision and "action" in request_or_decision:
            decision = RouteDecision.model_validate(request_or_decision)
        else:
            decision = self.route(ActionRequest.model_validate(request_or_decision))

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
            if spec.side_effect.rank > approved_side_effect.rank and spec.kind != ExecutorKind.DELEGATE:
                raise ApprovalRequired(
                    f"executor {spec.id!r} requires {spec.side_effect.value!r} approval; "
                    f"approved level is {approved_side_effect.value!r}",
                    executor_id=spec.id,
                    required_level=spec.side_effect.value,
                )
            if (
                not spec.safe_to_auto_execute
                and spec.kind != ExecutorKind.DELEGATE
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
                error_type = raw.error_type
                error_message = raw.error_message
                if raw.status == ExecutionStatus.SUCCESS and spec.output_schema is not None:
                    try:
                        validate_json(raw.output, spec.output_schema, label=f"output from {spec.id}")
                        output_valid = True
                    except Exception as exc:
                        output_valid = False
                        error_type = type(exc).__name__
                        error_message = str(exc)
                elif raw.status == ExecutionStatus.SUCCESS:
                    output_valid = None

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
                attempts.append(receipt)
                last_output = raw.output

            if raw.status == ExecutionStatus.DELEGATED:
                instructions = raw.metadata.get("instructions")
                if isinstance(raw.output, dict):
                    report = raw.output.get("report_outcome")
                    if isinstance(report, dict):
                        report["decision_id"] = decision.decision_id
                return ExecutionOutcome(
                    ok=True,
                    status=ExecutionStatus.DELEGATED,
                    output=raw.output,
                    decision=decision,
                    receipts=attempts,
                    delegated_instructions=(
                        str(instructions) if instructions is not None else None
                    ),
                )

            success = raw.status == ExecutionStatus.SUCCESS and output_valid is not False
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
                output_valid=output_valid,
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
                and last_receipt.output_valid is False
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
        if spec.kind != ExecutorKind.DELEGATE:
            raise ConfigurationError(
                "external outcome reports are only accepted for delegate executors"
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
            output_valid=report_model.output_valid,
            error_message=report_model.error_message,
            metadata={**report_model.metadata, "externally_reported": True},
        )
        self.store.save_external_receipt_once(receipt)
        return receipt

    def register(self, spec) -> None:
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

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for executor in self._executors.values():
            await executor.close()
        self._executors.clear()
        self.store.close()

    async def __aenter__(self) -> "Router":
        self._ensure_open()
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.close()
