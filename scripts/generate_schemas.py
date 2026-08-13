#!/usr/bin/env python3
"""Regenerate checked-in protocol schemas and provider tool declarations."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aeep.integrations import export_tools
from aeep.models import (
    ActionFeatures,
    ActionRequest,
    BenchmarkResult,
    CapabilityDefinition,
    CompactExecutionOutcome,
    CompactRouteDecision,
    CounterfactualReport,
    EconomicMetrics,
    ExecutionReceipt,
    ExecutorSpec,
    ExternalOutcomeReport,
    Manifest,
    Observation,
    PaymentReservation,
    PolicyConfig,
    ProviderDescriptor,
    QuotaObservation,
    Quote,
    QuoteAcceptance,
    QuoteRequest,
    ResourceVector,
    RouteDecision,
    SignedExecutionReceipt,
    SubscriptionResource,
    TraceProfileReport,
)

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_DIR = ROOT / "schemas"

MODEL_FILES = {
    "action-features.schema.json": ActionFeatures,
    "action-request.schema.json": ActionRequest,
    "benchmark-result.schema.json": BenchmarkResult,
    "capability-definition.schema.json": CapabilityDefinition,
    "compact-execution-outcome.schema.json": CompactExecutionOutcome,
    "compact-route-decision.schema.json": CompactRouteDecision,
    "counterfactual-report.schema.json": CounterfactualReport,
    "economic-metrics.schema.json": EconomicMetrics,
    "execution-receipt.schema.json": ExecutionReceipt,
    "executor-spec.schema.json": ExecutorSpec,
    "external-outcome-report.schema.json": ExternalOutcomeReport,
    "manifest.schema.json": Manifest,
    "observation.schema.json": Observation,
    "payment-reservation.schema.json": PaymentReservation,
    "policy.schema.json": PolicyConfig,
    "provider-descriptor.schema.json": ProviderDescriptor,
    "quote.schema.json": Quote,
    "quote-acceptance.schema.json": QuoteAcceptance,
    "quote-request.schema.json": QuoteRequest,
    "quota-observation.schema.json": QuotaObservation,
    "resource-vector.schema.json": ResourceVector,
    "route-decision.schema.json": RouteDecision,
    "signed-execution-receipt.schema.json": SignedExecutionReceipt,
    "subscription-resource.schema.json": SubscriptionResource,
    "trace-profile-report.schema.json": TraceProfileReport,
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
