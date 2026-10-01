"""Keep implemented offline checks separate from the remaining product release gates."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from pydantic import Field

from ..errors import ConfigurationError
from ..models import StrictModel
from ..verification import _pytest

if TYPE_CHECKING:
    from ..benchmarking import BenchmarkCampaignReport
    from ..models import ExecutionReceipt


class AssessmentProductVerification(StrictModel):
    schema_version: Literal["assessment.verification.v1", "assessment.verification.v2"] = "assessment.verification.v2"
    offline_checks_passed: bool
    source_digest: str = ""
    host_protocol_checks_passed: bool = False
    live_codex_verified: bool = False
    complete_economic_accounting: bool = False
    untrusted_plugin_containment: bool = False
    host_inventory_and_invocation: bool = False
    release_ready: bool = False
    remaining_gates: list[str]
    failure_detail: str = ""
    live_evidence: dict[str, Any] = Field(default_factory=dict)
    compatibility_checks_passed: bool = False
    demonstrated_savings: bool = False
    controlled_fixture_verified: bool = False
    controlled_fixture_evidence: dict[str, Any] = Field(default_factory=dict)
    adapter_production_support: dict[str, str] = Field(default_factory=dict)
    production_support_verified: bool = False
    production_ready: bool = False
    adoption_gates: dict[str, str] = Field(default_factory=dict)


def verification_source_digest(repository: Path) -> str:
    digest = hashlib.sha256()
    paths = [repository / "pyproject.toml"]
    for directory in ("src", "tests", "integrations/aeep", "integrations/assessment-runtime", "integrations/managed-worker", "scripts"):
        paths.extend((repository / directory).rglob("*"))
    for path in sorted(paths):
        relative = path.relative_to(repository)
        if path.is_file() and not any(part == "__pycache__" or part.endswith(".egg-info") for part in relative.parts):
            digest.update(relative.as_posix().encode() + b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _candidate_discovery_verified(campaign: BenchmarkCampaignReport, candidate_id: str,
                                  receipts: dict[str, ExecutionReceipt]) -> bool:
    """Discovery concerns the treatment; bind its trial facts to actual receipts."""
    trials = [trial for trial in campaign.trials if trial.route_id == candidate_id]
    for trial in trials:
        if len(trial.receipt_ids) != 1 or trial.receipt_ids[0] not in receipts:
            return False
        observed = receipts[trial.receipt_ids[0]].metadata.get('capability_discovery')
        if (not isinstance(observed, dict) or trial.capability_discovery is None
                or any(type(observed.get(key)) is not bool
                       or observed[key] != trial.capability_discovery.get(key)
                       for key in ('exposed', 'retrieved', 'invoked'))):
            return False
    return bool(trials)


def verify_assessment_product(root: Path | None = None, *, real_container: bool = False, manifest: Path | None = None, assessment_ids: list[str] | None = None, receipt_ids: list[str] | None = None, release_checks: bool = False, controlled_fixture: Path | None = None) -> AssessmentProductVerification:
    repository = root or Path(__file__).resolve().parents[3]
    passed, detail = _pytest(
        repository,
        [
            "-m", "not real_container",
            "tests/test_v08_assessment.py",
            "tests/test_v08_campaign_foundations.py",
            "tests/test_v08_assessment_interfaces.py",
            "tests/test_v08_codex_invocation.py",
            "tests/test_v08_containment.py",
            "tests/test_v08_comparisons.py",
            "tests/test_v08_incremental.py",
            "tests/test_v08_pilot.py",
            "tests/test_v08_workbook.py",
            "tests/test_v08_identity.py",
            "tests/test_v08_planning.py",
            "tests/test_v08_accounting_faults.py",
            "tests/test_v08_workers.py",
            "tests/test_v08_execution_boundary.py",
            "tests/test_v08_scope_amendments.py",
            "tests/test_v08_conformance.py",
            "tests/test_v08_worker_inspection.py",
            "tests/test_v08_pair_inspection.py",
            "tests/test_v08_budget.py",
            "tests/test_v08_search_transport.py",
            "tests/test_v08_offline_pair.py",
            "tests/test_v08_managed_workers.py",
            "tests/test_v08_executable_recipes.py",
            "tests/test_v08_controlled_fixture.py",
            "tests/test_v08_task_profile.py",
            "tests/test_v08_native_process.py",
            "tests/test_v08_three_way.py",
            "tests/test_v08_composed_contract.py",
            "tests/test_codex_composed_inspection.py",
            "tests/test_fixed_helper.py",
            "tests/test_fixed_helper_recovery.py",
            "tests/test_fixed_callback_authority.py",
            "tests/test_codex_dynamic_tools.py",
            "tests/test_v08_task_lifecycle.py",
            "tests/test_v08_ard.py",
        ],
    )
    contained = False
    if real_container:
        if all(os.environ.get(key) for key in ("AEEP_CONTAINER_IMAGE", "AEEP_WORKBOOK_IMAGE", "AEEP_CONTAINER_RUNTIME", "AEEP_CONTAINER_SOCKET", "AEEP_CATALOG_METRICS_IMAGE", "AEEP_INSPECTION_FIXTURE_SPECS")):
            contained, container_detail = _pytest(repository, ["-m", "real_container", "tests/test_v08_real_container.py", "tests/test_v08_managed_workers.py", "tests/test_v08_executable_recipes.py", "tests/test_v08_workbook.py"])
            if not contained:
                detail += "\n" + container_detail
        else:
            detail += "\nReal-container verification requires an explicit runtime, socket, pinned execution/workbook/catalog images and offline inspection fixtures."
    remaining = [] if passed else ["offline assessment regression checks"]
    controlled: dict[str, object] = {}
    if controlled_fixture is not None:
        from .controlled_fixture import verify
        try:
            controlled = verify(controlled_fixture)
        except (ValueError, OSError, ConfigurationError) as exc:
            detail += f"\nControlled fixture validation failed: {exc}"
    if not contained:
        remaining.append("real-container isolation, cancellation and crash-recovery verification")
    live = verify_live_records(repository, manifest, assessment_ids or [], receipt_ids or []) if manifest is not None else {}
    host_verified = live.get("host_verified") is True
    live_verified = all(live.get(key) is True for key in ("campaigns_verified", "capability_calls_verified")) and (live.get("admitted_execution_observed") is True or live.get("demonstrated_savings") is False)
    support = live.get("adapter_production_support", {})
    adapter_support = support if isinstance(support, dict) else {}
    production_support = bool(adapter_support) and all(value == "supported" for value in adapter_support.values())
    compatibility, compatibility_detail = verify_compatibility(repository) if release_checks else (False, "")
    if not host_verified:
        remaining.append("live verification of Codex inventory and effective tool isolation")
    if not live_verified:
        remaining.append("authorized live Codex assessment-to-use campaigns and task calls for all four families")
    if not controlled:
        remaining.append("controlled-fixture admission, revocation and stale-decision rejection checks")
    if not compatibility:
        remaining.append("final compatibility, coverage, proof and package-build release checks")
    if live.get('accounting_verified') is not True:
        remaining.append('source-bound complete assessment operation accounting')
    for stage in ("qualification", "marginal_value", "native_catalog"):
        if live.get(f"{stage}_verified") is not True:
            remaining.append(f"source-bound {stage} evidence across all four families")
    detail += compatibility_detail
    # Offline tests cannot certify measured resources, people or live autonomy.
    # Keep these gates visible independently of the historical campaign gates.
    adoption = {
        'minimal_operation': 'offline-only' if passed else 'failed',
        'reversibility': 'offline-only' if passed else 'failed',
        'explanation_accuracy': 'offline-only' if passed else 'failed',
        'evidence_transfer': 'offline-only' if passed else 'failed',
        'resource_acceptance': 'not-yet-measured',
        'human_usability': 'not-yet-measured',
        'representative_unattended_operation': 'not-yet-measured',
    }
    remaining.extend([
        'native project journey and failure/recovery evidence for the declared support envelope',
        'whole-system resource evaluation against predeclared reviewed budgets',
        'human comprehension of consequences, permissions, pause and undo',
        'predeclared representative unattended task evaluation',
    ])
    return AssessmentProductVerification(
        offline_checks_passed=passed,
        source_digest=verification_source_digest(repository),
        host_protocol_checks_passed=passed,
        complete_economic_accounting=live.get('accounting_verified') is True,
        untrusted_plugin_containment=contained,
        live_codex_verified=live_verified,
        host_inventory_and_invocation=host_verified,
        compatibility_checks_passed=compatibility,
        demonstrated_savings=live.get("demonstrated_savings") is True,
        controlled_fixture_verified=bool(controlled),
        controlled_fixture_evidence=controlled,
        adapter_production_support=adapter_support,
        production_support_verified=production_support,
        production_ready=not remaining and production_support,
        live_evidence=live,
        release_ready=not remaining,
        failure_detail=detail.strip() if not passed or (real_container and not contained) or compatibility_detail else "",
        remaining_gates=remaining,
        adoption_gates=adoption,
    )


def verify_compatibility(root: Path) -> tuple[bool, str]:
    """Run release checks; callers cannot submit a precomputed success flag."""
    import subprocess
    import sys
    import tempfile

    before = verification_source_digest(root)
    with tempfile.TemporaryDirectory(prefix="aeep-release-") as temporary:
        coverage = str(Path(temporary) / "coverage.json")
        commands = [
            [sys.executable, "-m", "compileall", "-q", "src", "examples", "tests"],
            [sys.executable, "scripts/generate_schemas.py", "--check"],
            [sys.executable, "scripts/check_assessment_policy.py"],
            [sys.executable, "-m", "ruff", "check", "."],
            [sys.executable, "-m", "mypy", "src"],
            [sys.executable, "-m", "pytest", "-m", "not real_container"],
            [sys.executable, "-m", "coverage", "run", "--branch", "-m", "pytest", "-m", "not real_container"],
            [sys.executable, "-m", "coverage", "json", "-o", coverage],
            [sys.executable, "-m", "coverage", "report", "-m"],
            [sys.executable, "scripts/check_critical_coverage.py", coverage],
            [sys.executable, "scripts/check_assessment_coverage.py", coverage],
            [sys.executable, "examples/economic_evidence/campaign.py", "--repetitions", "30", "--check", "--require-gates"],
            [sys.executable, "examples/dsh_campaign/campaign.py", "--check"],
            [sys.executable, "examples/dsh_campaign/live_campaign.py", "--check-report", "reports/v05/dsh/live-safety.json"],
            [sys.executable, "examples/dsh_campaign/live_campaign.py", "--check-comparison", "reports/v05/dsh/live-comparison.json"],
            [sys.executable, "examples/dsh_campaign/live_campaign.py", "--check-native-plan"],
            [sys.executable, "examples/job_application/campaign.py", "--check"],
            [sys.executable, "-m", "aeep", "provider", "verify", "examples/provider_package/aeep-provider.yaml", "-m", "examples/provider_package/aeep.yaml", "--compact"],
            [sys.executable, "-m", "aeep", "verify", "router-complete", "--profile", "all", "--strict", "--json"],
            ["npm", "test", "--prefix", "integrations/dsh-aeep-router"],
            [sys.executable, "-m", "build"],
        ]
        for command in commands:
            try:
                result = subprocess.run(command, cwd=root, env={**os.environ, "PYTHONPATH": str(root / "src"), "COVERAGE_FILE": str(Path(temporary) / ".coverage")}, capture_output=True, text=True, timeout=900, check=False)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return False, f"Release command unavailable: {command}: {type(exc).__name__}"
            if result.returncode:
                return False, f"Release command failed: {command}\n{result.stdout[-4000:]}\n{result.stderr[-1000:]}"
    return (True, "") if verification_source_digest(root) == before else (False, "Source changed during release verification")


def verify_live_records(root: Path, manifest: Path, assessment_ids: list[str], receipt_ids: list[str]) -> dict[str, object]:
    """Read local authority records, never a caller-supplied readiness flag.

    Reports, campaign receipts and source bindings must agree. A valid negative
    comparison is product evidence, but cannot stand in for host conformance or
    an actual admitted execution.
    """
    import asyncio
    import sqlite3

    from ..benchmarking import BenchmarkCampaignReport
    from ..errors import ConfigurationError
    from ..models import ExecutionReceipt, ExecutorKind
    from ..router import Router
    from .models import (
        AssessmentPlan,
        AssessmentReport,
        AssessmentRunBinding,
        RecipeDefinition,
        content_digest,
    )
    from .reporting import fit_report
    from .service import AssessmentService

    router = Router.from_manifest(manifest)
    service = AssessmentService(router, manifest.parent / ".aeep" / "assessments")
    families: set[str] = set()
    stages: dict[str, set[str]] = {stage: set() for stage in ("qualification", "marginal_value", "native_catalog")}
    host_verified = bool(assessment_ids)
    accounting_verified = bool(assessment_ids)
    measured_benefit = False
    details: list[str] = []
    adapter_support: dict[str, str] = {}
    try:
        for assessment_id in assessment_ids:
            try:
                job = service.status(assessment_id)
                if job["state"] != "complete" or job["error_code"]:
                    raise ConfigurationError("assessment did not complete its reviewed campaign")
                report = AssessmentReport.model_validate(service.repository.get("report", job["report_id"]))
                plan = AssessmentPlan.model_validate(service.repository.get("plan", report.plan_digest))
                if plan.pilot is not None:
                    raise ConfigurationError("timing pilot cannot establish live product acceptance")
                binding = AssessmentRunBinding.model_validate(service.repository.get("run_binding", plan.plan_id))
                if binding.source_digest != verification_source_digest(root) or binding.plan_id != plan.plan_id:
                    raise ConfigurationError("live evidence belongs to a different source revision")
                mapping = service._verify_dependencies(plan)
                for spec in mapping.subjects:
                    if spec.kind == ExecutorKind.MANAGED_HOST:
                        adapter_id = spec.managed_host_config().adapter_id
                        adapter_support[adapter_id] = router.managed_hosts.capabilities(adapter_id).support_status if adapter_id in router.managed_hosts.ids() else "unknown"
                if plan.comparison is None or report.comparison != plan.comparison:
                    raise ConfigurationError("live evidence lacks the reviewed comparison structure")
                recipe = RecipeDefinition.model_validate(service.repository.get("recipe", plan.recipe_digest))
                campaign = BenchmarkCampaignReport.model_validate(service.repository.get("campaign", report.campaign_digest))
                if content_digest(campaign) != report.campaign_digest or content_digest(plan) != report.plan_digest:
                    raise ConfigurationError("live evidence digest mismatch")
                replay = fit_report(plan, recipe, campaign)
                if (replay.outcome, replay.qualification_passed) != (report.outcome, report.qualification_passed):
                    raise ConfigurationError("comparison outcome does not reproduce")
                from .models import AssessmentOperationLedger
                ledger = AssessmentOperationLedger.model_validate(service.repository.get('operation_ledger', report.operation_ledger_digest or ''))
                if content_digest(ledger) != report.operation_ledger_digest or ledger.plan_id != plan.plan_id:
                    raise ConfigurationError('campaign operation accounting differs from its report')
                accounted = fit_report(plan, recipe, campaign, ledger=ledger)
                accounting_verified &= (bool(ledger.operations) and all(item.elapsed_seconds is not None for item in ledger.operations)
                                        and accounted.measured_usage.get('assessment_wall_time_ms') is not None)
                # Read actual sanitized execution receipts, not provider claims or
                # declarations in a submitted release report.
                path = Path(binding.campaign_path).resolve(strict=True)
                expected_parent = service.directory / plan.plan_id
                if path.parent != expected_parent.resolve() or path.name != "campaign.sqlite3":
                    raise ConfigurationError("campaign receipt store is outside the assessment directory")
                with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
                    stored = {row[0]: ExecutionReceipt.model_validate_json(row[1]) for row in connection.execute("SELECT receipt_id, payload_json FROM trial_receipts")}
                ids = {identity for trial in campaign.trials for identity in trial.receipt_ids}
                if not ids or not ids.issubset(stored):
                    raise ConfigurationError("campaign receipts are incomplete")
                host = [stored[identity] for identity in ids if stored[identity].executor_kind == ExecutorKind.MANAGED_HOST]
                if not host or not any(item.metadata.get("model_turn_count", 0) for item in host):
                    raise ConfigurationError("campaign has no executed Codex model evidence")
                # Inventory is supporting evidence; actual worker enforcement is
                # bound separately regardless of the adapter's upstream label.
                from .boundary import require_conformance
                for item in host:
                    boundary = item.metadata.get("boundary_digest")
                    worker = item.metadata.get("worker_digest")
                    runtime = item.metadata.get("host_runtime_digest")
                    if not all(isinstance(value, str) and value for value in (boundary, worker, runtime)):
                        raise ConfigurationError("environment verification unavailable: canonical boundary references missing")
                    require_conformance(service.repository, str(boundary), source_digest=binding.source_digest,
                                        worker_digest=str(worker), identity_digest=str(runtime))
                family = recipe.generator.split(":")[1] if recipe.generator.startswith("builtin:") else "workbook" if recipe.capability == 'assessment.workbook@1' else "reviewed_new_recipe"
                families.add(family)
                if plan.comparison.experiment is not None:
                    stage = plan.comparison.experiment.stage
                    # Catalog retrieval cannot be inferred from tool invocation.
                    if stage != "native_catalog" or _candidate_discovery_verified(campaign, plan.candidate_id, stored):
                        stages[stage].add(family)
                measured_benefit |= report.outcome == "useful_within_scope"
            except (ConfigurationError, ValueError, OSError, sqlite3.Error) as exc:
                host_verified = False
                accounting_verified = False
                details.append(f"{assessment_id}: {exc}")
        called: set[str] = set()
        admitted_use = False
        for identity in receipt_ids:
            receipt = router.store.get_receipt(identity)
            if receipt is None or receipt.output_valid is False or receipt.task_valid is False or receipt.status.value != "success":
                details.append(f"{identity}: successful production receipt is missing")
                continue
            called.add(receipt.capability)
            with router.store._lock:
                admission = router.store._connection.execute("SELECT admission_id FROM assessment_admissions WHERE executor_id=?", (receipt.executor_id,)).fetchone()
            if admission:
                evidence = service.repository.get("admission", admission[0])
                report = AssessmentReport.model_validate(service.repository.get("report", evidence["report_id"]))
                from ..execution import ExecutionEvidence
                lineage = receipt.metadata.get("assessment_admission_id")
                canonical_ref = receipt.metadata.get("execution_evidence_digest")
                if lineage != admission[0] or not isinstance(canonical_ref, str):
                    details.append(f"{identity}: explicit admission-to-attempt lineage missing")
                    continue
                canonical = ExecutionEvidence.model_validate(service.repository.get("execution_evidence", canonical_ref))
                admitted_use |= (content_digest(canonical) == canonical_ref and canonical.complete
                                 and canonical.attempt_id == receipt.metadata.get("attempt_id")
                                 and receipt.started_at >= report.created_at and report.comparison is not None)
        required = {"csv", "text", "search", "workbook"}
        all_families = required.issubset(families)
        all_calls = {f"assessment.{family}@1" for family in required}.issubset(called)
        return {"families": sorted(families), "host_verified": host_verified, "campaigns_verified": all_families, "capability_calls_verified": all_calls, "admitted_execution_observed": admitted_use, "demonstrated_savings": measured_benefit, "adapter_production_support": adapter_support, "details": details, 'accounting_verified': accounting_verified,
                "stage_families": {stage: sorted(values) for stage, values in stages.items()},
                **{f"{stage}_verified": required.issubset(values) for stage, values in stages.items()}}
    finally:
        asyncio.run(router.close())
