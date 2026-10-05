#!/usr/bin/env python3
"""Regenerate checked-in protocol schemas and provider tool declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aeep.assessment.boundary import BoundaryConformance, BoundaryProbe, DifferentialConformance
from aeep.assessment.controlled_fixture import ControlledFixtureRecord
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentComparison,
    AssessmentEnvironment,
    AssessmentPlan,
    AssessmentPlanningRequest,
    AssessmentProgress,
    AssessmentReport,
    AssessmentScopeAmendment,
    AssessmentSetupRequest,
    AssessmentSubject,
    ConformanceProbeRequest,
    DefinitionProposal,
    ExecutableRecipeExtension,
    GraderValidationEvidence,
    IncrementalExperiment,
    PilotPolicy,
    RecipeCaseSet,
    RecipeDefinition,
    RecipeMaterializationRequest,
    ReusableBaselineArtifact,
    ScopedAdmission,
    ThreeWayAccessDefinition,
)
from aeep.assessment.tools import declarations as assessment_tools
from aeep.attempts import ExecutionAttempt
from aeep.benchmarking import (
    BenchmarkCampaignReport,
    BenchmarkRevaluationReport,
    BenchmarkSuite,
    EconomicProofCampaignReport,
    ReleaseProofReport,
)
from aeep.capability_lifecycle import AdmissionDecision, AdmissionLookupRequest, CandidateIntake
from aeep.capacity import (
    CapacityAuthorizationEvidence,
    CapacityObservation,
    CapacityReservation,
    CapacityResource,
    CapacityWindow,
    EntitlementRedemptionReceipt,
    ExecutionEntitlement,
)
from aeep.configuration_profile import ConfigurationObservation
from aeep.conformance import ProviderConformanceReport
from aeep.discovery import (
    DiscoveryRequest,
    DiscoveryResult,
    DiscoverySourceRecord,
    ExternalResourceIdentity,
    RegistryCandidate,
)
from aeep.discovery_service import DiscoveryConfig, DiscoveryQueryRecord
from aeep.execution import ExecutionEvent, ExecutionEvidence, ExecutorCapabilities
from aeep.hosts.codex_inspection import WorkerInspectionResult
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition, WorkerPairInspection
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.hosts.workers import ManagedWorkerBinding
from aeep.integrations import export_tools
from aeep.models import (
    ActionApprovalRecord,
    ActionFeatures,
    ActionRequest,
    AuthorizationMeterQuantity,
    BenchmarkResult,
    BillingReconciliation,
    BoundedQuote,
    CacheAffinityEstimate,
    CacheAffinityObservation,
    CacheAffinityReceipt,
    CacheRoutingContext,
    CandidateRanking,
    CapabilityDefinition,
    CapabilityOffer,
    CashAccounting,
    CompactExecutionOutcome,
    CompactRouteDecision,
    CounterfactualReport,
    CurrencyAmount,
    EconomicEvidenceConfig,
    EconomicEvidenceLink,
    EconomicLiveQuotesConfig,
    EconomicMetrics,
    EconomicNetworkConfig,
    EconomicPaymentConfig,
    EconomicRequirementsConfig,
    EconomicTrustStoreConfig,
    EstimateUncertainty,
    EvidenceCohortKey,
    ExecutionReceipt,
    ExecutorSpec,
    ExternalOutcomeReport,
    ManagedHostExecutorConfig,
    Manifest,
    MarketAggregate,
    MarketAggregatesConfig,
    MeterQuantity,
    Observation,
    PaymentReservation,
    PaymentReservationV2,
    PinnedRateCardAuthorizationConfig,
    PolicyConfig,
    PreparedRouteDecision,
    PreparedRouteTransition,
    PricingDispute,
    PricingRule,
    ProviderDescriptor,
    ProviderPackageConfig,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    QuoteFailure,
    QuoteRequest,
    QuoteRequestV2,
    RateCardSnapshot,
    RefundReceiptV2,
    RejectedCandidate,
    ResourceAccounting,
    ResourceVector,
    RouteDecision,
    SettlementEvidence,
    SettlementReceipt,
    SignatureEnvelopeV2,
    SignedExecutionReceipt,
    SubscriptionResource,
    TaskExecutionOutcome,
    TaskScope,
    TraceProfileReport,
    UsageStatement,
)
from aeep.profiles import CapabilityProfile
from aeep.proofs import (
    DSHLiveComparisonReport,
    DSHLiveProofReport,
    DSHNativeCampaignReport,
    DSHPluginCampaignReport,
    DSHProofReport,
    HostNativeRoutingReport,
    JobProofReport,
    ResumePlan,
    RoutingValueReport,
)
from aeep.provider_package import (
    CandidateVerificationSnapshot,
    ComparativeMeasurement,
    EvidenceAcceptance,
    ProviderDiscoveryDocument,
    ProviderPackage,
    SmokeTestReport,
)
from aeep.provider_setup import ProviderSetupDefinition, ProviderSetupObservation
from aeep.qualification import QualificationReport, RouteCandidate
from aeep.stack_models import (
    ArtifactContract,
    GoalSpec,
    StackPreflight,
    StackProposal,
    StackRecovery,
)
from aeep.tasks import TaskActivation, TaskReconciliation
from aeep.verification import RouterCompletionReport
from aeep.workflow import WorkflowExecutionOutcome, WorkflowRequest
from aeep.x402 import X402BatchRecord, X402CapacityCommitment, X402ConformanceReport

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

MODEL_FILES = {
    "discovery-request.schema.json": DiscoveryRequest,
    "discovery-result.schema.json": DiscoveryResult,
    "discovery-source.schema.json": DiscoverySourceRecord,
    "discovery-query.schema.json": DiscoveryQueryRecord,
    "discovery-config.schema.json": DiscoveryConfig,
    "external-resource-identity.schema.json": ExternalResourceIdentity,
    "candidate-intake.schema.json": CandidateIntake,
    "admission-lookup.schema.json": AdmissionLookupRequest,
    "admission-decision.schema.json": AdmissionDecision,
    "goal.schema.json": GoalSpec,
    "artifact-contract.schema.json": ArtifactContract,
    "stack-proposal.schema.json": StackProposal,
    "stack-recovery.schema.json": StackRecovery,
    "stack-preflight.schema.json": StackPreflight,
    "provider-setup.schema.json": ProviderSetupDefinition,
    "provider-setup-observation.schema.json": ProviderSetupObservation,
    "capability-profile.schema.json": CapabilityProfile,
    "configuration-observation.schema.json": ConfigurationObservation,
    "codex-native-sandbox.schema.json": NativeSandboxConfig,
    "task-scope.schema.json": TaskScope,
    "task-activation.schema.json": TaskActivation,
    "task-reconciliation.schema.json": TaskReconciliation,
    "task-outcome.schema.json": TaskExecutionOutcome,
    "assessment-setup-request.schema.json": AssessmentSetupRequest,
    "assessment-controlled-fixture.schema.json": ControlledFixtureRecord,
    "assessment-recipe-extension.schema.json": ExecutableRecipeExtension,
    "assessment-recipe-materialization.schema.json": RecipeMaterializationRequest,
    "assessment-recipe-cases.schema.json": RecipeCaseSet,
    "execution-worker.schema.json": ManagedWorkerBinding,
    "assessment-boundary-conformance.schema.json": BoundaryConformance,
    "assessment-boundary-probe.schema.json": BoundaryProbe,
    "executor-capabilities.schema.json": ExecutorCapabilities,
    "execution-event.schema.json": ExecutionEvent,
    "execution-evidence.schema.json": ExecutionEvidence,
    "assessment-grader-validation.schema.json": GraderValidationEvidence,
    "assessment-scope-amendment.schema.json": AssessmentScopeAmendment,
    "assessment-budget-amendment.schema.json": AssessmentBudgetAmendment,
    "assessment-experiment.schema.json": IncrementalExperiment,
    "assessment-three-way-access.schema.json": ThreeWayAccessDefinition,
    "assessment-pilot.schema.json": PilotPolicy,
    "assessment-reusable-baseline.schema.json": ReusableBaselineArtifact,
    "assessment-differential-conformance.schema.json": DifferentialConformance,
    "action-features.schema.json": ActionFeatures,
    "evidence-cohort-key.schema.json": EvidenceCohortKey,
    "estimate-uncertainty.schema.json": EstimateUncertainty,
    "action-approval-record.schema.json": ActionApprovalRecord,
    "action-request.schema.json": ActionRequest,
    "authorization-meter-quantity.schema.json": AuthorizationMeterQuantity,
    "benchmark-result.schema.json": BenchmarkResult,
    "assessment-subject.schema.json": AssessmentSubject,
    "assessment-progress.schema.json": AssessmentProgress,
    "assessment-recipe.schema.json": RecipeDefinition,
    "assessment-plan.schema.json": AssessmentPlan,
    "assessment-comparison.schema.json": AssessmentComparison,
    "assessment-authorization.schema.json": AssessmentAuthorization,
    "assessment-report.schema.json": AssessmentReport,
    "assessment-admission.schema.json": ScopedAdmission,
    "assessment-environment.schema.json": AssessmentEnvironment,
    "assessment-planning-request.schema.json": AssessmentPlanningRequest,
    "assessment-conformance-request.schema.json": ConformanceProbeRequest,
    "assessment-worker-inspection.schema.json": WorkerInspectionResult,
    "assessment-worker-pair-inspection.schema.json": WorkerPairInspection,
    "assessment-composed-pair-inspection.schema.json": ComposedPairDefinition,
    "assessment-definition-proposal.schema.json": DefinitionProposal,
    "benchmark-suite.schema.json": BenchmarkSuite,
    "benchmark-campaign-report.schema.json": BenchmarkCampaignReport,
    "benchmark-revaluation-report.schema.json": BenchmarkRevaluationReport,
    "economic-proof-campaign-report.schema.json": EconomicProofCampaignReport,
    "release-proof-report.schema.json": ReleaseProofReport,
    "billing-reconciliation.schema.json": BillingReconciliation,
    "bounded-quote.schema.json": BoundedQuote,
    "cache-routing-context.schema.json": CacheRoutingContext,
    "cache-affinity-estimate.schema.json": CacheAffinityEstimate,
    "cache-affinity-receipt.schema.json": CacheAffinityReceipt,
    "cache-affinity-observation.schema.json": CacheAffinityObservation,
    "capacity-authorization-evidence.schema.json": CapacityAuthorizationEvidence,
    "capacity-observation.schema.json": CapacityObservation,
    "capacity-reservation.schema.json": CapacityReservation,
    "capacity-resource.schema.json": CapacityResource,
    "capacity-window.schema.json": CapacityWindow,
    "candidate-ranking.schema.json": CandidateRanking,
    "cash-accounting.schema.json": CashAccounting,
    "capability-definition.schema.json": CapabilityDefinition,
    "capability-offer.schema.json": CapabilityOffer,
    "compact-execution-outcome.schema.json": CompactExecutionOutcome,
    "compact-route-decision.schema.json": CompactRouteDecision,
    "counterfactual-report.schema.json": CounterfactualReport,
    "currency-amount.schema.json": CurrencyAmount,
    "economic-evidence-config.schema.json": EconomicEvidenceConfig,
    "economic-evidence-link.schema.json": EconomicEvidenceLink,
    "economic-live-quotes-config.schema.json": EconomicLiveQuotesConfig,
    "economic-metrics.schema.json": EconomicMetrics,
    "economic-network-config.schema.json": EconomicNetworkConfig,
    "economic-payment-config.schema.json": EconomicPaymentConfig,
    "economic-requirements-config.schema.json": EconomicRequirementsConfig,
    "economic-trust-store-config.schema.json": EconomicTrustStoreConfig,
    "entitlement-redemption-receipt.schema.json": EntitlementRedemptionReceipt,
    "execution-receipt.schema.json": ExecutionReceipt,
    "execution-attempt.schema.json": ExecutionAttempt,
    "execution-entitlement.schema.json": ExecutionEntitlement,
    "executor-spec.schema.json": ExecutorSpec,
    "external-outcome-report.schema.json": ExternalOutcomeReport,
    "manifest.schema.json": Manifest,
    "market-aggregate.schema.json": MarketAggregate,
    "market-aggregates-config.schema.json": MarketAggregatesConfig,
    "managed-host-executor-config.schema.json": ManagedHostExecutorConfig,
    "meter-quantity.schema.json": MeterQuantity,
    "observation.schema.json": Observation,
    "payment-reservation.schema.json": PaymentReservation,
    "payment-reservation-v2.schema.json": PaymentReservationV2,
    "pinned-rate-card-authorization-config.schema.json": PinnedRateCardAuthorizationConfig,
    "policy.schema.json": PolicyConfig,
    "prepared-route-decision.schema.json": PreparedRouteDecision,
    "prepared-route-transition.schema.json": PreparedRouteTransition,
    "pricing-dispute.schema.json": PricingDispute,
    "pricing-rule.schema.json": PricingRule,
    "provider-descriptor.schema.json": ProviderDescriptor,
    "provider-package-config.schema.json": ProviderPackageConfig,
    "aeep-provider.schema.json": ProviderPackage,
    "provider-discovery.schema.json": ProviderDiscoveryDocument,
    "provider-conformance-report.schema.json": ProviderConformanceReport,
    "evidence-acceptance.schema.json": EvidenceAcceptance,
    "candidate-verification-snapshot.schema.json": CandidateVerificationSnapshot,
    "smoke-test-report.schema.json": SmokeTestReport,
    "comparative-measurement.schema.json": ComparativeMeasurement,
    "registry-candidate.schema.json": RegistryCandidate,
    "dsh-proof-report.schema.json": DSHProofReport,
    "dsh-live-proof-report.schema.json": DSHLiveProofReport,
    "dsh-live-comparison-report.schema.json": DSHLiveComparisonReport,
    "dsh-native-campaign-report.schema.json": DSHNativeCampaignReport,
    "dsh-plugin-campaign-report.schema.json": DSHPluginCampaignReport,
    "routing-value-report.schema.json": RoutingValueReport,
    "job-proof-report.schema.json": JobProofReport,
    "host-native-routing-report.schema.json": HostNativeRoutingReport,
    "resume-plan.schema.json": ResumePlan,
    "quote.schema.json": Quote,
    "quote-acceptance.schema.json": QuoteAcceptance,
    "quote-failure.schema.json": QuoteFailure,
    "quote-request.schema.json": QuoteRequest,
    "quote-request-v2.schema.json": QuoteRequestV2,
    "quota-observation.schema.json": QuotaObservation,
    "refund-receipt-v2.schema.json": RefundReceiptV2,
    "rejected-candidate.schema.json": RejectedCandidate,
    "resource-vector.schema.json": ResourceVector,
    "resource-accounting.schema.json": ResourceAccounting,
    "rate-card-snapshot.schema.json": RateCardSnapshot,
    "route-candidate.schema.json": RouteCandidate,
    "qualification-report.schema.json": QualificationReport,
    "route-decision.schema.json": RouteDecision,
    "router-completion-report.schema.json": RouterCompletionReport,
    "settlement-evidence.schema.json": SettlementEvidence,
    "settlement-receipt.schema.json": SettlementReceipt,
    "signature-envelope-v2.schema.json": SignatureEnvelopeV2,
    "signed-execution-receipt.schema.json": SignedExecutionReceipt,
    "subscription-resource.schema.json": SubscriptionResource,
    "trace-profile-report.schema.json": TraceProfileReport,
    "usage-statement.schema.json": UsageStatement,
    "workflow-request.schema.json": WorkflowRequest,
    "workflow-execution-outcome.schema.json": WorkflowExecutionOutcome,
    "x402-batch-record.schema.json": X402BatchRecord,
    "x402-capacity-commitment.schema.json": X402CapacityCommitment,
    "x402-conformance-report.schema.json": X402ConformanceReport,
}

TOOL_FILES = {
    "tools.mcp.json": "mcp",
    "tools.openai-responses.json": "openai-responses",
    "tools.openai-chat.json": "openai-chat",
    "tools.anthropic.json": "anthropic",
    "tools.deepseek.json": "deepseek",
    "tools.zai.json": "zai",
}


def _encoded(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def generated() -> dict[Path, str]:
    values: dict[Path, str] = {}
    for filename, model in MODEL_FILES.items():
        values[SCHEMA_DIR / filename] = _encoded(model.model_json_schema())
    for filename, tool_format in TOOL_FILES.items():
        values[SCHEMA_DIR / filename] = _encoded({"tools": export_tools(tool_format)})
    values[SCHEMA_DIR / "tools.assessment.mcp.json"] = _encoded({"tools": assessment_tools()})
    values[SCHEMA_DIR / "tools.stack-task.mcp.json"] = _encoded({"tools": assessment_tools(tasks_only=True, include_stack=True)})
    values[SCHEMA_DIR / "tools.task.mcp.json"] = _encoded({"tools": assessment_tools(tasks_only=True)})
    return values


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="Fail when checked-in artifacts differ instead of writing them.",
    )
    args = parser.parse_args()
    stale: list[str] = []
    SCHEMA_DIR.mkdir(parents=True, exist_ok=True)
    for path, content in generated().items():
        if args.check:
            existing = path.read_text(encoding="utf-8") if path.exists() else None
            if existing != content:
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_text(content, encoding="utf-8")
    if stale:
        print("Generated artifacts are stale:")
        for item in stale:
            print(f"- {item}")
        print("Run: PYTHONPATH=src python scripts/generate_schemas.py")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
