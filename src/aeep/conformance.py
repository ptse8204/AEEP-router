"""Deterministic provider-package conformance checks."""

from __future__ import annotations

from pydantic import Field

from .models import StrictModel
from .provider_package import (
    ProviderPackage,
    provider_package_digest,
    validate_declared_fingerprints,
    verify_embedded_package_signature,
)


class ProviderConformanceCheck(StrictModel):
    check_id: str
    passed: bool
    detail: str


class ProviderConformanceReport(StrictModel):
    profile: str = "aeep-provider-conformance-v1"
    package_digest: str
    passed: bool
    checks: tuple[ProviderConformanceCheck, ...] = Field(min_length=1)


def run_provider_conformance(package: ProviderPackage) -> ProviderConformanceReport:
    fingerprints = validate_declared_fingerprints(package)
    checks = (
        ProviderConformanceCheck(
            check_id="protocol_version",
            passed=package.api_version == "aeep.dev/v0.6",
            detail=package.api_version,
        ),
        ProviderConformanceCheck(
            check_id="canonical_digest",
            passed=provider_package_digest(package) == package.integrity.digest,
            detail="RFC 8785 package digest",
        ),
        ProviderConformanceCheck(
            check_id="embedded_signature",
            passed=any(
                verify_embedded_package_signature(package, signature)
                for signature in package.signatures
            ),
            detail="at least one embedded publisher signature",
        ),
        ProviderConformanceCheck(
            check_id="route_fingerprints",
            passed=bool(fingerprints) and all(fingerprints.values()),
            detail=f"{sum(fingerprints.values())}/{len(fingerprints)} exact routes",
        ),
        ProviderConformanceCheck(
            check_id="evidence_authority_and_cohort",
            passed=all(
                evidence.authority_class is not None and evidence.cohort is not None
                for evidence in package.spec.evidence
            ),
            detail=f"{len(package.spec.evidence)} evidence record(s)",
        ),
        ProviderConformanceCheck(
            check_id="python_isolation",
            passed=all(
                route.executor_spec(package.spec.provider.provider_id).config.get("isolation")
                == "subprocess"
                for route in package.spec.routes
                if route.executor.kind.value == "python"
            ),
            detail="published Python routes resolve to subprocess isolation",
        ),
    )
    return ProviderConformanceReport(
        package_digest=provider_package_digest(package),
        passed=all(check.passed for check in checks),
        checks=checks,
    )
