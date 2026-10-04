"""Local discovery lineage and point-in-time advice over existing admission authority.

Inspection is operator-only. Lookup neither installs artifacts nor qualifies routes,
starts assessments, changes approval ceilings, or makes a saved decision executable.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field, model_validator

from .assessment.applicability import require_applicable
from .assessment.models import (
    AssessmentPlan,
    AssessmentReport,
    AssessmentSubject,
    Digest,
    ReviewedMapping,
    ScopedAdmission,
    content_digest,
)
from .assessment.service import AssessmentService
from .discovery import ExternalResourceIdentity, RegistryCandidate, external_resource_identity
from .errors import ConfigurationError, InputValidationError, NoRouteError
from .estimator import action_features
from .models import ActionRequest, StrictModel, UtcDateTime, new_id, utc_now
from .registry import validate_json
from .scoring import rejection_reasons

if TYPE_CHECKING:
    from .router import Router

Disposition = Literal["admit", "reject", "restrict", "assess", "inconclusive", "expired"]


def _candidate_digest(candidate: RegistryCandidate) -> str:
    # A repeated observation of identical metadata is not an artifact change.
    return content_digest(candidate.model_dump(mode="json", exclude={"retrieved_at"}))


def _contributor_provenance(candidate: RegistryCandidate) -> dict[str, Any]:
    """Retain bounded attribution claims, including disagreements, without resolving links."""
    names = {
        "publisher": ("publisher", "provider"),
        "maintainer": ("maintainer", "maintainers", "author", "authors", "contributors"),
        "project": ("project", "projectUrl", "homepage", "homePage"),
        "source": ("source_repository", "sourceRepository", "repository", "source"),
        "upstream_dependencies": ("dependencies", "upstreamDependencies", "upstream_dependencies"),
        "support": ("support", "supportUrl", "support_url", "supportLinks"),
        "sponsorship": ("sponsorship", "sponsors", "sponsor", "funding", "fundingUrl"),
        "license": ("license", "licenses", "licenseUrl"),
    }
    sources: dict[str, Any] = {
        "candidate": {"source_repository": candidate.source_repository},
        "provenance": candidate.provenance,
        "provenance.entry": candidate.provenance.get("entry"),
    }
    claims: dict[str, list[dict[str, Any]]] = {}
    omitted = []
    remaining_bytes = 32_768
    for category, keys in names.items():
        for source, metadata in sources.items():
            if not isinstance(metadata, dict):
                continue
            for key in keys:
                value = metadata.get(key)
                if value is None:
                    continue
                size = len(json.dumps(value, ensure_ascii=True, allow_nan=False).encode())
                path = f"{source}.{key}"
                if size > min(4096, remaining_bytes):
                    omitted.append(path)
                    continue
                remaining_bytes -= size
                claims.setdefault(category, []).append({"source_field": path, "value": value})
    return {
        "verification": "unverified_provider_claims", "claims": claims,
        "unknown_categories": sorted(set(names) - set(claims)), "omitted_fields": omitted,
        "links_followed": False, "beneficiary_relationship": "unknown",
    }


class CandidateIntake(StrictModel):
    schema_version: Literal["aeep.candidate-intake.v1"] = "aeep.candidate-intake.v1"
    intake_id: str = Field(default_factory=lambda: new_id("intake"))
    candidate: RegistryCandidate
    candidate_snapshot_digest: Digest
    external_identity: ExternalResourceIdentity | None = None
    subject_id: str
    subject_digest: Digest
    mapping_digest: Digest | None = None
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def exact_snapshot(self) -> CandidateIntake:
        if self.candidate_snapshot_digest != _candidate_digest(self.candidate):
            raise ValueError("intake candidate snapshot differs")
        if self.external_identity != external_resource_identity(self.candidate):
            raise ValueError("intake external identity differs from its candidate")
        return self


class AdmissionLookupRequest(StrictModel):
    candidate_id: str = Field(min_length=1, max_length=300)
    intake_id: str | None = Field(default=None, min_length=1, max_length=300)
    request: ActionRequest | None = None


class AdmissionDecision(StrictModel):
    schema_version: Literal["aeep.admission-decision.v1"] = "aeep.admission-decision.v1"
    candidate_id: str
    disposition: Disposition
    next_action: Literal["use_admitted_capability", "assess_candidate", "keep_current_environment"]
    reason_codes: list[str]
    explanation: str
    intake_id: str | None = None
    executor_id: str | None = None
    admission_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)
    evidence_cohort: dict[str, Any] = Field(default_factory=dict)
    contributor_provenance: dict[str, Any] = Field(default_factory=dict)
    historical_comparisons: list[dict[str, Any]] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    observed_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def advice_is_not_authority(self) -> AdmissionDecision:
        if (self.next_action == "use_admitted_capability") != (self.disposition == "admit"):
            raise ValueError("only currently applicable admissions can suggest use")
        if self.disposition == "admit" and not (self.intake_id and self.executor_id and self.admission_id):
            raise ValueError("admitted advice requires exact intake and admission references")
        return self


class CapabilityLifecycle:
    def __init__(self, assessment: AssessmentService) -> None:
        self.assessment = assessment
        self.router = assessment.router
        self.repository = assessment.repository
        self.store = self.router.store

    @classmethod
    def from_router(cls, router: Router) -> CapabilityLifecycle:
        directory = router.manifest_path.parent if router.manifest_path else Path.cwd()
        return cls(AssessmentService(router, directory / ".aeep" / "assessments"))

    def inspect_candidate(
        self, candidate_id: str, location: Path, *, kind: str = "plugin",
        mapping: ReviewedMapping | None = None,
    ) -> CandidateIntake:
        """Bind an operator-selected LOCAL artifact; locator URLs are never followed.

        Review the returned exact intake definition through AssessmentRepository.review.
        A proposed mapping still needs the assessment service's separate exact review.
        """
        candidate = self.store.get_registry_candidate(candidate_id)
        if candidate is None:
            raise ConfigurationError("unknown discovery candidate")
        # Reject a symlink in any ancestor before the existing bounded inspection.
        selected = location.expanduser().absolute()
        if selected != selected.resolve(strict=True):
            raise ConfigurationError("candidate intake requires an explicit local path without symlinks")
        subject = self.assessment.inspect_local(selected, kind=kind)
        identity = external_resource_identity(candidate)
        mapping_digest = None
        if mapping is not None:
            mapping_digest = content_digest(mapping)
            self.repository.put("mapping", mapping_digest, mapping)
        intake = CandidateIntake(
            candidate=candidate, candidate_snapshot_digest=_candidate_digest(candidate),
            external_identity=identity,
            subject_id=subject.subject_id, subject_digest=content_digest(subject),
            mapping_digest=mapping_digest,
        )
        self.repository.put("candidate_intake", intake.intake_id, intake)
        return intake

    def lookup(
        self, candidate_id: str, request: ActionRequest | None = None, *,
        intake_id: str | None = None,
    ) -> AdmissionDecision:
        """Bounded offline lookup. Execution must still revalidate normal routing authority."""
        candidate = self.store.get_registry_candidate(candidate_id)
        if candidate is None:
            return self._decision(candidate_id, "inconclusive", "candidate_unknown")
        if intake_id is None:
            with self.store._lock:
                row = self.store._connection.execute(
                    "SELECT payload_json FROM assessment_records WHERE kind='candidate_intake' "
                    "AND json_extract(payload_json, '$.candidate.registry_candidate_id')=? "
                    "ORDER BY rowid DESC LIMIT 1", (candidate_id,),
                ).fetchone()
            if row is None:
                return self._decision(candidate_id, "assess", "local_intake_required", candidate=candidate)
            intake = CandidateIntake.model_validate_json(row[0])
        else:
            intake = CandidateIntake.model_validate(self.repository.get("candidate_intake", intake_id))
        if (intake.candidate.registry_candidate_id != candidate_id
                or intake.candidate_snapshot_digest != _candidate_digest(candidate)):
            return self._decision(candidate_id, "restrict", "discovery_snapshot_changed", intake)
        with self.store._lock:
            review = self.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (content_digest(intake),),
            ).fetchone()
            # Only current admission markers count. Historical records cannot restore revocation.
            rows = self.store._connection.execute(
                "SELECT r.payload_json, a.revoked FROM assessment_admissions a "
                "JOIN assessment_records r ON r.kind='admission' AND r.id=a.admission_id "
                "WHERE json_extract(r.payload_json, '$.subject_digest')=? ORDER BY a.executor_id LIMIT 101",
                (intake.subject_digest,),
            ).fetchall()
        if review is None or review[0]:
            return self._decision(candidate_id, "restrict", "intake_requires_current_review", intake)
        if len(rows) > 100:
            return self._decision(candidate_id, "inconclusive", "admission_lookup_limit", intake)
        decisions = []
        for row in rows:
            admission = ScopedAdmission.model_validate_json(row[0])
            if intake.mapping_digest is not None and admission.mapping_digest != intake.mapping_digest:
                continue
            decision = self._admission_decision(candidate_id, intake, admission, bool(row[1]), request)
            if decision.disposition == "admit":
                return decision
            decisions.append(decision)
        if decisions:
            # Keep the first deterministic explanation; expose all matched evidence references.
            decision = decisions[0]
            decision.evidence_refs = sorted({ref for item in decisions for ref in item.evidence_refs})
            return decision
        decision = self._decision(candidate_id, "assess", "applicable_admission_missing", intake)
        # Completed reports are useful context, never a shortcut around admission/refitting.
        with self.store._lock:
            reports = self.store._connection.execute(
                "SELECT r.payload_json, p.payload_json FROM assessment_jobs j "
                "JOIN assessment_records r ON r.kind='report' AND r.id=j.report_id "
                "JOIN assessment_records p ON p.kind='plan' AND p.id=j.plan_id "
                "WHERE j.state='complete' AND j.error_code IS NULL "
                "AND json_extract(p.payload_json, '$.subject_digest')=? "
                "ORDER BY j.rowid DESC LIMIT 10", (intake.subject_digest,),
            ).fetchall()
        for report_json, plan_json in reports:
            report = AssessmentReport.model_validate_json(report_json)
            plan = AssessmentPlan.model_validate_json(plan_json)
            if report.plan_digest != content_digest(plan) or plan.pilot is not None:
                continue
            if intake.mapping_digest is not None and intake.mapping_digest != plan.mapping_digest:
                continue
            decision.evidence_refs.append(report.report_id)
            decision.historical_comparisons.append({
                "report_id": report.report_id, "outcome": report.outcome,
                "scope_status": "historical_not_revalidated",
                "created_at": report.created_at.isoformat(),
                "plan_digest": report.plan_digest, "mapping_digest": plan.mapping_digest,
                "environment_digest": plan.environment_digest, "recipe_digest": plan.recipe_digest,
                "distinct_paired_cases": report.distinct_paired_cases,
                "measured_usage": report.measured_usage,
                "measurement_coverage": report.measurement_coverage,
                "paired_savings": report.paired_savings,
                "savings_interval": report.savings_interval,
            })
        if decision.evidence_refs:
            decision.disposition = "inconclusive"
            decision.next_action = "keep_current_environment"
            decision.reason_codes = ["comparison_exists_without_applicable_admission"]
            decision.explanation = "Completed comparisons exist, but none establishes current scoped admission. Keep the current environment."
            decision.unknowns.append("comparison_applicability_to_current_request")
        return decision

    def _admission_decision(
        self, candidate_id: str, intake: CandidateIntake, admission: ScopedAdmission,
        revoked: bool, request: ActionRequest | None,
    ) -> AdmissionDecision:
        def result(disposition: Disposition, reason: str) -> AdmissionDecision:
            decision = self._decision(candidate_id, disposition, reason, intake)
            decision.executor_id = admission.executor_id
            decision.admission_id = admission.admission_id
            decision.evidence_refs = [admission.admission_id, admission.report_id, admission.qualification_report_id]
            decision.evidence_cohort = {
                **decision.evidence_cohort,
                "subject_digest": admission.subject_digest,
                "candidate_fingerprint": admission.candidate_fingerprint,
                "baseline_fingerprint": admission.baseline_fingerprint,
                "mapping_digest": admission.mapping_digest,
                "recipe_digest": admission.recipe_digest,
                "environment_digest": admission.environment_digest,
                "host_runtime_digests": admission.host_runtime_digests,
                "executable_dependencies_digest": content_digest(admission.executable_dependencies),
                "definition_digests": admission.definition_digests,
                "applicability": admission.applicability,
                "feature_combinations": admission.feature_combinations,
                "comparison": admission.comparison.model_dump(mode="json") if admission.comparison else None,
                "expires_at": admission.expires_at.isoformat(),
                "request_capability": request.capability if request else None,
                "request_constraints_digest": content_digest(request.constraints) if request else None,
            }
            return decision

        if revoked:
            return result("restrict", "admission_revoked")
        if admission.expires_at <= utc_now():
            return result("expired", "admission_expired")
        if request is None:
            return result("restrict", "request_scope_required")
        if request.capability != admission.capability:
            return result("restrict", "capability_mismatch")
        if not self.router.registry.contains(admission.executor_id):
            return result("restrict", "executor_unavailable")
        try:
            with self.store._lock:
                current = self.store._connection.execute(
                    "SELECT admission_id, revoked FROM assessment_admissions WHERE executor_id=?",
                    (admission.executor_id,),
                ).fetchone()
            if current is None or current[0] != admission.admission_id or current[1]:
                return result("restrict", "admission_changed_during_lookup")
            spec = self.router.registry.get(admission.executor_id)
            baseline = self.router.registry.get(admission.baseline_id) if self.router.registry.contains(admission.baseline_id) else None
            # Explicitly invoke applicability even on a trial router, where ordinary
            # active checks may bypass admissions for a reviewed benchmark worker.
            require_applicable(self.store, spec, request, baseline)
            self.router._require_active_spec(spec, request)
            validate_json(request.input, spec.input_schema, label="candidate input")
            effective_request = self.router._fill_runtime_context(request)
            policy = self.router._policy_for(effective_request)
            estimate = self.router.estimator.estimate(spec, policy, action_features(request.input))
            reasons = rejection_reasons(
                spec, estimate, policy,
                effective_request.context, self.router._subscription_quota(spec, effective_request.context),
            )
            if reasons:
                return result("reject", "current_hard_constraints_reject")
        except (ConfigurationError, InputValidationError, NoRouteError, ValueError, OSError):
            return result("restrict", "evidence_or_execution_scope_not_applicable")
        decision = result("restrict", "current_scoped_admission")
        return AdmissionDecision.model_validate({
            **decision.model_dump(mode="python"),
            "disposition": "admit", "next_action": "use_admitted_capability",
            "explanation": "Existing evidence admits this capability for this request and bound environment. Normal execution must recheck authority and approval.",
        })

    def _decision(
        self, candidate_id: str, disposition: Disposition, reason: str,
        intake: CandidateIntake | None = None, *, candidate: RegistryCandidate | None = None,
    ) -> AdmissionDecision:
        candidate = intake.candidate if intake else candidate
        identity = external_resource_identity(candidate) if candidate else None
        cohort: dict[str, Any] = {
            "external_identity": identity.model_dump(mode="json") if identity else None,
            "external_identity_verified": False,
            "discovered_version": candidate.version if candidate else None,
            "discovery_metadata_digest": candidate.raw_metadata_digest if candidate else None,
            "candidate_snapshot_digest": _candidate_digest(candidate) if candidate else None,
        }
        unknowns = ["future_task_outcome", "subscription_cash_equivalence"]
        if identity is None:
            unknowns.append("external_resource_identity")
        if intake:
            cohort.update(subject_digest=intake.subject_digest, mapping_digest=intake.mapping_digest)
            try:
                subject = AssessmentSubject.model_validate(self.repository.get("subject", intake.subject_digest))
                if content_digest(subject) != intake.subject_digest:
                    raise ConfigurationError("intake subject digest differs")
                cohort["artifact_dependencies_digest"] = content_digest(subject.dependency_digests)
                cohort["artifact_dependency_count"] = len(subject.dependency_digests)
                cohort["artifact_identity_status"] = "inspected_snapshot"
            except (ConfigurationError, ValueError):
                unknowns.append("artifact_dependencies")
        return AdmissionDecision(
            candidate_id=candidate_id, disposition=disposition,
            next_action="assess_candidate" if disposition == "assess" else "keep_current_environment",
            reason_codes=[reason], intake_id=intake.intake_id if intake else None,
            explanation="Keep the current environment until the missing scope, review, or evidence is resolved. No assessment has started.",
            evidence_cohort=cohort,
            contributor_provenance=_contributor_provenance(candidate) if candidate else {},
            unknowns=unknowns,
        )


def _self_check() -> None:
    """Small, offline invariant check; no database, artifact, or execution is opened."""
    from pydantic import ValidationError

    decision = AdmissionDecision(candidate_id="unknown", disposition="inconclusive", next_action="keep_current_environment", reason_codes=["candidate_unknown"], explanation="Unknown candidate.")
    assert decision.next_action == "keep_current_environment"
    try:
        AdmissionDecision(candidate_id="unknown", disposition="admit", next_action="use_admitted_capability", reason_codes=[], explanation="")
    except ValidationError:
        pass
    else:
        raise AssertionError("an unbound recommendation must not suggest use")


if __name__ == "__main__":
    _self_check()
