"""Optional bridge to the existing reviewed AEEP assessment service.

No grants, workers, scheduling or inference are implemented here. Canonical
assessment records retain all costs, including trials that cannot be normalized.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import suppress
from pathlib import Path
from typing import Any

from pydantic import TypeAdapter, ValidationError

from aeep.assessment import verification
from aeep.assessment.boundary import require_conformance
from aeep.assessment.models import (
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    AssessmentSubject,
    RecipeDefinition,
    ReviewedMapping,
    content_digest,
)
from aeep.assessment.reporting import fit_report
from aeep.assessment.scheduling import TrialCoordinator
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.benchmarking import BenchmarkCampaignReport, BenchmarkPhase, BenchmarkTrial
from aeep.errors import ConfigurationError
from aeep.estimator import evidence_cohort_digest
from aeep.hosts.codex_accounting import TOKEN_FIELDS
from aeep.models import ExecutionReceipt, ExecutionStatus, ExecutorKind
from aeep_toolkit.models import (
    AdapterCapabilities,
    EvaluationRun,
    EvidenceBundle,
    Identifier,
    SourcePin,
    TokenObservation,
)
from aeep_toolkit.stack_readiness import require_engineering_run, require_stack_complete
from aeep_toolkit.telemetry import bound_journal, candidate_loading, capture_summary, token_capture


def _report_family_keys(labels: set[str]) -> dict[str, str]:
    """Preserve legacy identifiers and encode other labels without merging families."""
    identifier = TypeAdapter(Identifier)
    result = {}
    for label in sorted(labels):
        with suppress(ValidationError):
            result[label] = identifier.validate_python(label)
    reserved = set(result.values())
    for label in sorted(labels - result.keys()):
        # Reserve all original identifiers first, including any hash-shaped names.
        # At most len(labels) keys can collide; a finite extra slot always remains.
        for salt in range(len(labels) + 1):
            raw = label if salt == 0 else f"aeep.toolkit.family.v1:{salt}:{label}"
            key = "source-family:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if key not in reserved:
                result[label] = key
                reserved.add(key)
                break
        else:
            raise ConfigurationError("task-family labels cannot be encoded uniquely")
    return result


def plan_preview(plan: AssessmentPlan, source: SourcePin) -> dict[str, Any]:
    """Pure file-based review; no Router, database, recovery or host initialization."""
    capabilities = AdapterCapabilities(
        adapter_id="aeep.benchmark-runner.codex:external-scheduler" if plan.scheduler_digest else "aeep.benchmark-runner.codex",
        implementation_sha256=verification_source_digest(
            Path(verification.__file__).resolve().parents[3]
        ),
        hosts=("codex",),
        candidate_types=("skill",),
        optional_invocation=plan.scheduler_digest is None,
        telemetry=("tokens", "agent_wall_seconds", "verification_wall_seconds"),
        containment="unverified",
    )
    binding = {
        "plan_sha256": content_digest(plan),
        "source": source.model_dump(mode="json"),
        "adapter": capabilities.model_dump(mode="json"),
    }
    return {
        **binding,
        "review_sha256": content_digest(binding),
        "plan_id": plan.plan_id,
        "authorization_id": plan.authorization_id,
        "blocked_reasons": plan.blocked_reasons,
        "notice": "File-based review only. Source association, current grant, worker conformance and available budget are checked by the existing service before execution.",
    }


class AEEPAssessmentAdapter:
    """Bind one existing plan; a source pin is attribution, never authorization."""

    def __init__(self, service: AssessmentService, plan_id: str, source: SourcePin, *, coordinator: Any = None):
        self.service, self.source = service, source.model_copy(deep=True)
        self.coordinator = coordinator
        self.root = Path(verification.__file__).resolve().parents[3]
        self.plan = AssessmentPlan.model_validate(service.repository.get("plan", plan_id))
        if not self.plan.plan_id or Path(self.plan.plan_id).name != self.plan.plan_id or self.plan.plan_id in {'.', '..'}:
            raise ConfigurationError('assessment identity is not a bounded directory name')
        self.mapping = ReviewedMapping.model_validate(
            service.repository.get("mapping", self.plan.mapping_digest)
        )
        self.recipe = RecipeDefinition.model_validate(
            service.repository.get("recipe", self.plan.recipe_digest)
        )
        subject = AssessmentSubject.model_validate(
            service.repository.get("subject", self.plan.subject_digest)
        )
        for value, expected in (
            (self.mapping, self.plan.mapping_digest),
            (self.recipe, self.plan.recipe_digest),
            (subject, self.plan.subject_digest),
        ):
            if content_digest(value) != expected:
                raise ConfigurationError("canonical assessment definition digest mismatch")
        comparison = self.plan.comparison
        if (
            comparison is None
            or comparison.structure != "controlled_agent"
            or comparison.experiment is None
        ):
            raise ConfigurationError(
                "toolkit managed adapter requires a reviewed controlled-agent experiment"
            )
        if any(
            spec.kind != ExecutorKind.MANAGED_HOST
            for spec in (self.mapping.candidate, self.mapping.baseline)
        ):
            raise ConfigurationError("primary arms must be managed hosts")
        invocation = self.mapping.candidate.managed_host_config().invocation
        if (
            subject.kind not in {"skill", "plugin"}
            or invocation is None
            or invocation.mode != "skill"
            or invocation.skill_sha256 not in subject.dependency_digests.values()
            or source.artifact_sha256 != content_digest(subject.dependency_digests)
        ):
            raise ConfigurationError(
                "source artifact must match the reviewed skill and inspected subject"
            )
        self.capabilities = AdapterCapabilities.model_validate(
            plan_preview(self.plan, self.source)["adapter"]
        )
        self.details: dict[str, Any] = {}
        self.accounting_records: dict[str, Any] = {}
        self._family_keys = _report_family_keys({
            case.template_family or self.recipe.recipe_id for case in self.plan.suite.cases
        })

    @property
    def review_digest(self) -> str:
        return content_digest(
            {
                "plan_sha256": content_digest(self.plan),
                "source": self.source.model_dump(mode="json"),
                "adapter": self.capabilities.model_dump(mode="json"),
            }
        )

    def preview(self) -> dict[str, Any]:
        """Read already-open local records; never enqueue, recover or start a host."""
        with self.service.router.store._lock:
            row = self.service.router.store._connection.execute(
                "SELECT id, state, report_id, error_code FROM assessment_jobs WHERE plan_id=? ORDER BY rowid DESC LIMIT 1",
                (self.plan.plan_id,),
            ).fetchone()
        return {
            "review_sha256": self.review_digest,
            "plan_id": self.plan.plan_id,
            "plan_sha256": content_digest(self.plan),
            "source": self.source.model_dump(mode="json"),
            "backend": self.capabilities.model_dump(mode="json"),
            "job": dict(row) if row else None,
            "notice": "Existing reviews, grant and worker conformance still apply. Preview grants no execution authority.",
        }

    async def evaluate(self, reviewed_plan_id: str, *, stack_readiness_ref: str | None = None,
                       engineering_review_ref: str | None = None) -> EvidenceBundle:
        from .workflow_accounting import bind_workflow_plan

        bind_workflow_plan(self.plan)
        if reviewed_plan_id != self.review_digest:
            raise ConfigurationError("exact source, plan and adapter review required")
        if verification_source_digest(self.root) != self.capabilities.implementation_sha256:
            raise ConfigurationError("adapter implementation changed after preview")
        current = AssessmentPlan.model_validate(
            self.service.repository.get("plan", self.plan.plan_id)
        )
        if current != self.plan:
            raise ConfigurationError("reviewed plan changed")
        if engineering_review_ref is not None:
            if stack_readiness_ref is not None:
                raise ConfigurationError('select engineering or comparison authority, never both')
            require_engineering_run(self.service.repository, engineering_review_ref,
                                    plan=self.plan, source_digest=self.capabilities.implementation_sha256)
        else:
            if self.plan.schema_version == "assessment.plan.v9":
                raise ConfigurationError("SkillRank diagnostic requires exact engineering authority")
            require_stack_complete(self.service.repository, stack_readiness_ref,
                                   source_digest=self.capabilities.implementation_sha256)
        # The service owns all authorization, reservation, execution and recovery.
        if self.plan.scheduler_digest != (self.coordinator.definition_digest if self.coordinator else None):
            raise ConfigurationError("selected evaluator is missing or changed; no fallback is inferred")
        from .workflow_accounting import exclude_canonical_execution

        with exclude_canonical_execution():
            report = await self.service.run(self.service.enqueue(self.plan.plan_id), coordinator=self.coordinator) if self.coordinator else await self.service.run(self.service.enqueue(self.plan.plan_id))
        bundle = self.normalize(report.report_id)
        if engineering_review_ref is not None:
            if report.qualification_passed:
                raise ConfigurationError('finite engineering check unexpectedly claims qualification')
            self.details['engineering_scope'] = {'review_ref': engineering_review_ref,
                                                 'purpose': 'stack_integration_only',
                                                 'candidate_usefulness': 'NOT_ASSESSED',
                                                 'selection_usefulness': 'NOT_ASSESSED'}
        return bundle

    def normalize(self, report_id: str) -> EvidenceBundle:
        from .workflow_accounting import bind_workflow_plan

        bind_workflow_plan(self.plan)
        repository = self.service.repository
        report = AssessmentReport.model_validate(repository.get("report", report_id))
        if report.plan_digest != content_digest(self.plan):
            raise ConfigurationError("report belongs to a different reviewed plan")
        binding = AssessmentRunBinding.model_validate(
            repository.get("run_binding", self.plan.plan_id)
        )
        if (
            binding.plan_id != self.plan.plan_id
            or binding.source_digest != self.capabilities.implementation_sha256
            or verification_source_digest(self.root) != binding.source_digest
        ):
            raise ConfigurationError("report belongs to another source revision")
        campaign = BenchmarkCampaignReport.model_validate(
            repository.get("campaign", report.campaign_digest)
        )
        ledger = AssessmentOperationLedger.model_validate(
            repository.get("operation_ledger", report.operation_ledger_digest or "")
        )
        if (
            content_digest(campaign) != report.campaign_digest
            or content_digest(ledger) != report.operation_ledger_digest
            or ledger.plan_id != self.plan.plan_id
            or campaign.suite_id != self.plan.suite.suite_id
        ):
            raise ConfigurationError("campaign or accounting digest mismatch")
        reproduced = fit_report(self.plan, self.recipe, campaign, ledger=ledger)
        if report.outcome != "insufficient_evidence" and (
            reproduced.outcome,
            reproduced.qualification_passed,
        ) != (report.outcome, report.qualification_passed):
            raise ConfigurationError("canonical comparison does not reproduce")
        # Service failure may downgrade the verdict, never rewrite measured statistics.
        for field in (
            "distinct_holdout_cases", "distinct_paired_cases", "correctness_failures",
            "execution_failures", "tested_variations", "paired_measurement_cases",
            "paired_savings", "savings_interval", "utility_evidence",
            "host_runtime_digests", "deterministic_reference_comparison", "measurement_coverage",
        ):
            if getattr(report, field) != getattr(reproduced, field):
                raise ConfigurationError("canonical comparison statistics do not reproduce")
        saved_conditions = report.condition_comparisons or {}
        fresh_conditions = reproduced.condition_comparisons or {}
        if saved_conditions.keys() != fresh_conditions.keys():
            raise ConfigurationError("canonical comparison statistics do not reproduce")
        for condition, expected_condition in fresh_conditions.items():
            saved = saved_conditions[condition]
            if not isinstance(saved, dict) or saved.keys() != expected_condition.keys():
                raise ConfigurationError("canonical comparison statistics do not reproduce")
            for field, expected_value in expected_condition.items():
                if field != 'break_even_uses':
                    if saved[field] != expected_value:
                        raise ConfigurationError("canonical comparison statistics do not reproduce")
                    continue
                # Condition costs precede completion of the report's own charged operation.
                costs = saved[field]
                if (not isinstance(costs, dict) or costs.keys() != expected_value.keys()
                        or any(value is not None and value != expected_value[key] for key, value in costs.items())):
                    raise ConfigurationError("canonical condition costs do not reproduce")
        incomplete_costs = "Preparation cost lineage is incomplete; known incurred usage is retained." in report.explanations
        expected_usage = dict(reproduced.measured_usage)
        expected_break_even = dict(reproduced.break_even_uses)
        if incomplete_costs:
            expected_usage["assessment_wall_time_ms"] = None
            expected_break_even = {key: None for key in expected_break_even}
        if report.measured_usage != expected_usage or report.break_even_uses != expected_break_even:
            raise ConfigurationError("canonical comparison costs do not reproduce")
        expected = {
            (case.case_id, route.route_id, condition.value, repetition)
            for case in self.plan.suite.cases
            for route in self.plan.suite.routes
            for condition in self.plan.suite.conditions
            for repetition in range(self.plan.suite.repetitions)
        }
        observed = [(trial.case_id, trial.route_id, trial.condition.value, trial.repetition)
                    for trial in campaign.trials if trial.phase != BenchmarkPhase.SETUP]
        positions = set(observed)
        path = Path(binding.campaign_path).resolve(strict=True)
        if path != self.service.directory / self.plan.plan_id / "campaign.sqlite3":
            raise ConfigurationError("campaign receipt store is outside its plan directory")
        with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
            receipts = {
                row[0]: (row[1], ExecutionReceipt.model_validate_json(row[2]))
                for row in connection.execute(
                    "SELECT receipt_id, trial_id, payload_json FROM trial_receipts"
                )
            }
            trial_stores = dict(connection.execute('SELECT trial_id, database_path FROM trial_stores'))
        runs, gaps, auxiliary = [], [], []
        self.accounting_records = {}
        captures = {}
        journals = {}
        for trial in campaign.trials:
            if trial.route_id not in {self.plan.candidate_id, self.plan.baseline_id}:
                auxiliary.append(trial.trial_id)
                continue
            try:
                if len(trial.receipt_ids) != 1:
                    raise ConfigurationError("requires one canonical primary receipt")
                bound_trial, receipt = receipts[trial.receipt_ids[0]]
                if (
                    bound_trial != trial.trial_id
                    or receipt.receipt_id != trial.receipt_ids[0]
                    or receipt.executor_id != trial.route_id
                ):
                    raise ConfigurationError("receipt is bound to another trial or route")
                original_path = Path(trial_stores[trial.trial_id]).resolve(strict=True)
                if original_path.parent != self.service.directory / self.plan.plan_id / 'attempts':
                    raise ConfigurationError('original receipt store is outside the plan attempts directory')
                with sqlite3.connect(original_path.as_uri() + '?mode=ro', uri=True) as original:
                    row = original.execute('SELECT payload_json FROM receipts WHERE receipt_id=?', (receipt.receipt_id,)).fetchone()
                    journal_row = (original.execute(
                        "SELECT payload_json FROM assessment_records WHERE kind='execution_evidence' AND digest=?",
                        (receipt.metadata["execution_evidence_digest"],)).fetchone()
                        if receipt.metadata.get("execution_evidence_digest") else None)
                if row is None or content_digest(ExecutionReceipt.model_validate_json(row[0])) != content_digest(receipt):
                    raise ConfigurationError('campaign receipt differs from the original retained receipt')
                self.accounting_records[content_digest(receipt)] = receipt.model_dump(mode='json')
                journal = bound_journal(receipt, json.loads(journal_row[0]) if journal_row else None)
                invocation = (self.mapping.candidate if trial.route_id == self.plan.candidate_id
                              else self.mapping.baseline).managed_host_config().invocation
                capture = {"tokens": token_capture(receipt, journal),
                           "candidate": candidate_loading(receipt, journal,
                               skill_sha256=invocation.skill_sha256 if invocation else None)}
                runs.append(self._run(trial, receipt))
                captures[trial.trial_id] = capture
                if journal is not None:
                    journals[receipt.metadata["execution_evidence_digest"]] = journal.model_dump(mode="json")
            except (ConfigurationError, ValueError, TypeError, KeyError, OSError, sqlite3.Error) as exc:
                gaps.append(
                    {
                        "trial_id": trial.trial_id,
                        "reason": str(exc)
                        if isinstance(exc, ConfigurationError)
                        else "canonical receipt or normalization contract unavailable",
                    }
                )
        self.details = {
            "plan_sha256": content_digest(self.plan),
            "report_sha256": content_digest(report),
            "campaign_sha256": report.campaign_digest,
            "operation_ledger_sha256": report.operation_ledger_digest,
            "canonical_trials": len(campaign.trials),
            "expected_trial_positions": len(expected),
            "missing_trial_positions": len(expected - positions),
            "unexpected_trial_positions": len(positions - expected),
            "duplicate_trial_positions": len(observed) - len(positions),
            "unresolved_operations": sum(item.elapsed_seconds is None for item in ledger.operations),
            "normalized_primary_trials": len(runs),
            "normalization_gaps": gaps,
            "task_family_labels": {
                key: label for label, key in self._family_keys.items() if key != label
            },
            "telemetry_capture": captures,
            "telemetry_capture_summary": capture_summary(captures),
            "execution_journals": journals,
            "auxiliary_trial_ids": auxiliary,
            "assessment_analysis": report.model_dump(mode="json"),
            "timing_scope": "Trial wall time includes routing and preflight; separately measured grading is excluded by BenchmarkRunner.",
            "notice": "All primary and auxiliary costs remain in the canonical ledger. Normalization alone is not efficacy or release qualification.",
        }
        if self.plan.scheduler_digest is not None:
            from .ase_scheduler import SchedulerObservation

            try:
                scheduling_payload = repository.get("scheduler_observation", self.plan.plan_id)
            except ConfigurationError:
                self.details['external_scheduler'] = {'definition_ref':self.plan.scheduler_digest,
                                                       'completion':'UNKNOWN'}
            else:
                observation = SchedulerObservation.model_validate(scheduling_payload)
                process = ExecutionReceipt.model_validate(repository.get(
                    'scheduler_receipt', self.plan.plan_id + ':external-scheduler'))
                if (observation.definition_ref != self.plan.scheduler_digest
                        or content_digest(process) != observation.process_receipt_ref
                        or process.execution_success is not True
                        or not set(observation.trial_refs.values()) <= {content_digest(t) for t in campaign.trials}):
                    raise ConfigurationError('upstream scheduling evidence differs from the canonical campaign')
                self.details['external_scheduler'] = observation.model_dump(mode='json')
        from .workflow_accounting import active_accounting, active_component_observations

        components = active_component_observations()
        if components:
            self.details['workflow_component_checks'] = components
        self.details['workflow_accounting'] = active_accounting() or {
            'coverage': 'NOT_RECORDED',
            'notice': 'No workflow overhead scope was selected; execution ledger alone is incomplete composed cost coverage.',
        }
        return EvidenceBundle(candidate=self.source, adapter=self.capabilities, runs=tuple(runs))

    def _run(self, trial: BenchmarkTrial, receipt: ExecutionReceipt) -> EvaluationRun:
        comparison = self.plan.comparison
        assert comparison is not None and comparison.experiment is not None
        metadata = receipt.metadata
        keys = (
            "protocol_version",
            "actual_model",
            "worker_digest",
            "host_runtime_digest",
            "boundary_digest",
            "task_instruction_sha256",
        )
        if receipt.executor_kind != ExecutorKind.MANAGED_HOST or any(
            not isinstance(metadata.get(key), str) or not metadata[key] for key in keys
        ):
            raise ConfigurationError(
                "observed host, model, worker, boundary or task-prompt binding unavailable"
            )
        if type(metadata.get("model_turn_count")) is not int or metadata["model_turn_count"] != 1:
            raise ConfigurationError("no single observed managed model turn")
        require_conformance(
            self.service.repository,
            metadata["boundary_digest"],
            source_digest=self.capabilities.implementation_sha256,
            worker_digest=metadata["worker_digest"],
            identity_digest=metadata["host_runtime_digest"],
        )
        spec = (
            self.mapping.candidate
            if trial.route_id == self.plan.candidate_id
            else self.mapping.baseline
        )
        config = spec.managed_host_config()
        expected_binding = evidence_cohort_digest(spec, receipt.action_features, metadata['host_runtime_digest'])
        if (receipt.executor_fingerprint, receipt.cohort_digest) != expected_binding:
            raise ConfigurationError('receipt executor or runtime cohort differs from the frozen route')
        if (
            config.adapter_id.split(":")[0] != "codex-app-server"
            or len(config.reasoning_efforts) != 1
        ):
            raise ConfigurationError("requires one pinned Codex effort")
        case = next((case for case in self.plan.suite.cases if case.case_id == trial.case_id), None)
        if case is None or trial.route_fingerprint != self.plan.route_fingerprints.get(
            trial.route_id
        ):
            raise ConfigurationError("trial is outside the frozen case or route binding")
        receipt_ref = content_digest(receipt)
        if any(
            getattr(receipt.actual_resources, field) != getattr(trial.actual_resources, field)
            for field in TOKEN_FIELDS.values()
        ):
            raise ConfigurationError("receipt usage differs from canonical trial measurements")
        if (
            trial.status != receipt.status
            or trial.host_models is None
            or trial.host_models.get(trial.route_id) != metadata["actual_model"]
            or trial.host_runtime_digests.get(trial.route_id) != metadata["host_runtime_digest"]
        ):
            raise ConfigurationError(
                "receipt status or observed identity differs from canonical trial"
            )
        observed = json.loads(metadata.get("codex_token_fields", "[]"))
        if not isinstance(observed, list) or any(
            not isinstance(key, str) or key not in {*TOKEN_FIELDS, "totalTokens"}
            for key in observed
        ):
            raise ConfigurationError("invalid token observation mask")
        tokens = None
        if observed and receipt.status == ExecutionStatus.SUCCESS:
            counts = {
                field: getattr(receipt.actual_resources, field) if wire in observed else None
                for wire, field in TOKEN_FIELDS.items()
                if field != "cache_write_input_tokens"
            }
            tokens = TokenObservation(
                source_ref=receipt_ref,
                cached_semantics="included_in_input",
                reasoning_semantics="included_in_output",
                **counts,
            )
        discovery = trial.capability_discovery or {}
        if discovery != (metadata.get("capability_discovery") or {}):
            raise ConfigurationError("candidate discovery differs from its canonical receipt")
        status = (
            "completed"
            if receipt.status == ExecutionStatus.SUCCESS
            else "timeout"
            if receipt.status == ExecutionStatus.TIMEOUT
            else "indeterminate"
            if receipt.status
            in {ExecutionStatus.UNKNOWN, ExecutionStatus.HOST_SELECTED, ExecutionStatus.DELEGATED}
            else "failed"
        )
        verification = "unknown"
        graded = (
            bool(case.validators)
            and len(trial.case_validation) == len(case.validators)
            and all(
                result.kind == validator.kind and type(result.valid) is bool
                for result, validator in zip(trial.case_validation, case.validators, strict=True)
            )
        )
        if graded:
            passed = all(result.valid is True for result in trial.case_validation)
            if passed != trial.valid:
                raise ConfigurationError(
                    "trial verification disagrees with its independent grader results"
                )
            verification = (
                "pass" if passed and status == "completed" else "fail" if not passed else "unknown"
            )
        return EvaluationRun.model_validate(
            dict(
                run_id=trial.trial_id,
                plan_ref=content_digest(self.plan),
                candidate_sha256=self.source.artifact_sha256,
                adapter_sha256=self.capabilities.implementation_sha256,
                host="codex",
                host_version=metadata["protocol_version"],
                model=metadata["actual_model"],
                effort=config.reasoning_efforts[0],
                shared_environment_sha256=comparison.experiment.environment.shared_definition_digest,
                worker_sha256=metadata["worker_digest"],
                task_sha256=content_digest(case),
                task_family=self._family_keys[case.template_family or self.recipe.recipe_id],
                verifier_sha256=self.plan.recipe_digest,
                prompt_sha256=metadata["task_instruction_sha256"],
                arm="treatment" if trial.route_id == self.plan.candidate_id else "control",
                mode="optional"
                if comparison.experiment.exposure == "optional"
                else "forced_diagnostic",
                candidate_exposed=discovery.get("exposed"),
                candidate_invoked=discovery.get("invoked"),
                verification=verification,
                verification_ref=content_digest(trial) if verification != "unknown" else None,
                status=status,
                retries=trial.retry_fallback_count,
                evidence_kind="live",
                receipt_refs=(receipt_ref,),
                tokens=tokens,
                agent_wall_seconds=trial.wall_time_ms / 1000
                if trial.wall_time_ms is not None
                else None,
                verification_wall_seconds=trial.grading_wall_time_ms / 1000
                if trial.grading_wall_time_ms is not None
                else None,
                timing_source_ref=content_digest(trial),
                cash_accounting_ref=receipt_ref,
            )
        )



def comparison_summary(adapter: AEEPAssessmentAdapter, bundle: EvidenceBundle) -> dict[str, Any]:
    """Present the reused analysis separately from unauthenticated descriptive input."""
    from .reporting import summarize

    summary = summarize(bundle, accounting_records=adapter.accounting_records)
    details = adapter.details
    analysis = AssessmentReport.model_validate(details["assessment_analysis"])
    summary["managed_analysis"] = {
        "analysis_ref": details["report_sha256"],
        "plan_ref": details["plan_sha256"],
        "campaign_ref": details["campaign_sha256"],
        "operation_ledger_ref": details["operation_ledger_sha256"],
        "outcome": analysis.outcome,
        "qualification_passed": analysis.qualification_passed,
        "distinct_holdout_cases": analysis.distinct_holdout_cases,
        "distinct_paired_cases": analysis.distinct_paired_cases,
        "correctness_failures": analysis.correctness_failures,
        "execution_failures": analysis.execution_failures,
        **{key: details[key] for key in (
            "expected_trial_positions", "missing_trial_positions", "unexpected_trial_positions",
            "duplicate_trial_positions", "unresolved_operations")},
        "paired_measurement_cases": analysis.paired_measurement_cases,
        "paired_savings": analysis.paired_savings,
        "savings_interval": analysis.savings_interval,
        "condition_comparisons": analysis.condition_comparisons,
        "utility_evidence": analysis.utility_evidence,
        "measured_usage": analysis.measured_usage,
        "measurement_coverage": analysis.measurement_coverage,
        "break_even_uses": analysis.break_even_uses,
        "timing_scope": details["timing_scope"],
        "telemetry_capture": details["telemetry_capture_summary"],
        "workflow_accounting": details.get("workflow_accounting", {"coverage": "NOT_RECORDED"}),
        **({"workflow_component_checks": details["workflow_component_checks"]} if details.get("workflow_component_checks") else {}),
    }
    if 'external_scheduler' in details:
        summary['external_scheduler'] = details['external_scheduler']
        summary['limitations'].append('Upstream scheduler timing/token defaults are compatibility artifacts. Only canonical AEEP receipts supply measured usage; the upstream verdict checks the existing protected grade certificate.')
    if details.get('task_family_labels'):
        summary['task_family_labels'] = details['task_family_labels']
    summary["limitations"].extend([
        f"Canonical campaign: {details['canonical_trials']} trials; {len(bundle.runs)} normalized primary trials; "
        f"{len(details['normalization_gaps'])} normalization gaps; {len(details['auxiliary_trial_ids'])} auxiliary trials.",
        "Canonical analysis includes its frozen conditions, repetitions and auxiliary arms. Descriptive tables below cover only normalized primary trials; they cannot replace the complete campaign or cost ledger.",
        "The canonical verdict is the assessment service's recorded conclusion, not a new toolkit qualification, independent attestation or release approval.",
        *[f"Unnormalized trial {item['trial_id']}: {item['reason']}" for item in details['normalization_gaps']],
    ])
    return summary


def main(argv: list[str] | None = None) -> None:
    import argparse
    import asyncio

    from aeep.router import Router
    from aeep_toolkit.cli import read_json, read_plan_bytes
    from aeep_toolkit.reporting import render

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("plan", "run", "report"):
        command = commands.add_parser(name)
        command.add_argument("--plan", type=Path, required=True)
        command.add_argument("--source", type=Path, required=True)
        command.add_argument("--scheduler", type=Path, help="Exact reviewed external scheduling definition")
        if name != "plan":
            command.add_argument("--manifest", type=Path, required=True)
            command.add_argument("--directory", type=Path)
            command.add_argument("--output", type=Path, required=True)
        if name == "run":
            command.add_argument("--reviewed-digest", required=True)
            command.add_argument("--stack-readiness", help="Reviewed current-source canonical complete-stack record")
            command.add_argument("--engineering-review", help="Exact finite required-use integration check; never value evidence")
        if name == "report":
            command.add_argument("--report-id", required=True)
    args = parser.parse_args(argv)
    try:
        plan = AssessmentPlan.model_validate_json(read_plan_bytes(args.plan))
        source = SourcePin.model_validate(read_json(args.source))
        scheduler = None
        if args.scheduler is not None:
            from aeep.assessment.scheduling import SKILLRANK_DIAGNOSTIC, SchedulerDefinition

            scheduler = SchedulerDefinition.model_validate(read_json(args.scheduler))
            if content_digest(scheduler) != plan.scheduler_digest:
                raise ConfigurationError("scheduler file differs from the frozen plan")
        if args.operation == "run" and bool(plan.scheduler_digest) != (scheduler is not None):
            raise ConfigurationError("selected evaluator requires its bound scheduler file")
        preview = plan_preview(plan, source)
        if args.operation == "plan":
            print(json.dumps(preview, indent=2))
            return
        if args.operation == "run" and args.reviewed_digest != preview["review_sha256"]:
            raise ConfigurationError("exact review differs")
        if args.operation == "run" and not (args.stack_readiness or args.engineering_review):
            raise ConfigurationError("complete upstream stack evidence is required before new comparisons")

        async def execute() -> None:
            router = Router.from_manifest(args.manifest)
            try:
                service = AssessmentService(
                    router,
                    args.directory or args.manifest.resolve().parent / ".aeep" / "assessments",
                )
                coordinator: TrialCoordinator | None = None
                if scheduler is not None and args.operation == "run":
                    from .ase_scheduler import AgentSkillEvalCoordinator
                    from .skillrank_scheduler import SkillRankCoordinator

                    if scheduler.adapter_id == SKILLRANK_DIAGNOSTIC:
                        coordinator = SkillRankCoordinator(service.repository, plan)
                    else:
                        coordinator = AgentSkillEvalCoordinator(service.repository, plan)
                adapter = AEEPAssessmentAdapter(service, plan.plan_id, source, coordinator=coordinator)
                if content_digest(adapter.plan) != content_digest(plan):
                    raise ConfigurationError("supplied plan differs from canonical record")
                args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
                state = args.output / "operation.json"
                state.write_text(
                    json.dumps(
                        {"state": "started", "plan_id": plan.plan_id, "operation": args.operation}
                    )
                    + "\n"
                )
                try:
                    bundle = (
                        await adapter.evaluate(args.reviewed_digest, stack_readiness_ref=args.stack_readiness,
                                               engineering_review_ref=args.engineering_review)
                        if args.operation == "run"
                        else adapter.normalize(args.report_id)
                    )
                    summary = comparison_summary(adapter, bundle)
                    for name, document in (
                        ("toolkit-evidence", bundle.model_dump(mode="json")),
                        ("managed-evidence", adapter.details),
                        ("accounting-records", adapter.accounting_records),
                        ("summary", summary),
                    ):
                        with (args.output / (name + ".json")).open("x") as handle:
                            json.dump(document, handle, indent=2, allow_nan=False)
                            handle.write("\n")
                    for format, suffix in (("markdown", "md"), ("html", "html")):
                        with (args.output / ("report." + suffix)).open("x") as handle:
                            handle.write(render(summary, format))
                    state.write_text(
                        json.dumps(
                            {
                                "state": "exported",
                                "plan_id": plan.plan_id,
                                "normalization_gaps": len(adapter.details["normalization_gaps"]),
                            }
                        )
                        + "\n"
                    )
                    print(
                        json.dumps(
                            {
                                "output": str(args.output),
                                "report_id": adapter.details["assessment_analysis"]["report_id"],
                                "normalized_trials": len(bundle.runs),
                                "normalization_gaps": len(adapter.details["normalization_gaps"]),
                                "release_ready": False,
                            }
                        )
                    )
                except BaseException:
                    state.write_text(
                        json.dumps(
                            {
                                "state": "incomplete",
                                "plan_id": plan.plan_id,
                                "notice": "Inspect canonical assessment state and retained costs before further execution. No automatic retry.",
                            }
                        )
                        + "\n"
                    )
                    raise
            finally:
                await router.close()

        asyncio.run(execute())
    except (ConfigurationError, ValueError, OSError, sqlite3.Error):
        parser.exit(
            2,
            "Managed evaluation could not complete; inspect the canonical assessment and supplied metadata. No automatic retry.\n",
        )


if __name__ == "__main__":
    main()
