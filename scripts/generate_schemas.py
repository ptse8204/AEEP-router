#!/usr/bin/env python3
"""Regenerate checked-in protocol schemas and provider tool declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aeep.benchmarking import (
    BenchmarkCampaignReport,
    BenchmarkRevaluationReport,
    BenchmarkSuite,
    EconomicProofCampaignReport,
    ReleaseProofReport,
)
from aeep.conformance import ProviderConformanceReport
from aeep.discovery import RegistryCandidate
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
    TraceProfileReport,
    UsageStatement,
)
from aeep.proofs import (
    DSHLiveComparisonReport,
    DSHLiveProofReport,
    DSHNativeCampaignReport,
    DSHPluginCampaignReport,
    DSHProofReport,
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
from aeep.qualification import QualificationReport, RouteCandidate
from aeep.workflow import WorkflowExecutionOutcome, WorkflowRequest

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

MODEL_FILES = {
    "action-features.schema.json": ActionFeatures,
    "evidence-cohort-key.schema.json": EvidenceCohortKey,
    "estimate-uncertainty.schema.json": EstimateUncertainty,
    "action-approval-record.schema.json": ActionApprovalRecord,
    "action-request.schema.json": ActionRequest,
    "authorization-meter-quantity.schema.json": AuthorizationMeterQuantity,
    "benchmark-result.schema.json": BenchmarkResult,
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
    "execution-receipt.schema.json": ExecutionReceipt,
    "executor-spec.schema.json": ExecutorSpec,
    "external-outcome-report.schema.json": ExternalOutcomeReport,
    "manifest.schema.json": Manifest,
    "market-aggregate.schema.json": MarketAggregate,
    "market-aggregates-config.schema.json": MarketAggregatesConfig,
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
    "settlement-evidence.schema.json": SettlementEvidence,
    "settlement-receipt.schema.json": SettlementReceipt,
    "signature-envelope-v2.schema.json": SignatureEnvelopeV2,
    "signed-execution-receipt.schema.json": SignedExecutionReceipt,
    "subscription-resource.schema.json": SubscriptionResource,
    "trace-profile-report.schema.json": TraceProfileReport,
    "usage-statement.schema.json": UsageStatement,
    "workflow-request.schema.json": WorkflowRequest,
    "workflow-execution-outcome.schema.json": WorkflowExecutionOutcome,
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
