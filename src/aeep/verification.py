"""Digest-bound executable completion verification for AEEP 0.7."""

from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Literal

from pydantic import ConfigDict, Field, model_validator

from .models import StrictModel


class CompletionStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    SKIP = "SKIP"
    DISABLED = "DISABLED"


class CompletionCheck(StrictModel):
    id: str = Field(min_length=1, max_length=200)
    profile: Literal["core", "openai", "marketplace_contract", "marketplace_live"]
    required: bool
    status: CompletionStatus
    test_ids: tuple[str, ...] = ()
    evidence_ids: tuple[str, ...] = ()
    artifact_digests: tuple[str, ...] = ()
    reason: str = Field(default="", max_length=4000)

    @model_validator(mode="after")
    def passing_checks_have_evidence(self) -> CompletionCheck:
        if self.status is CompletionStatus.PASS and (
            not self.test_ids or not self.evidence_ids or not self.artifact_digests
        ):
            raise ValueError("passing completion checks require tests and immutable evidence")
        return self


class RouterCompletionReport(StrictModel):
    model_config = ConfigDict(populate_by_name=True, serialize_by_alias=True)

    report_schema: Literal["aeep-router-completion-v1"] = Field(
        default="aeep-router-completion-v1", alias="schema"
    )
    version: Literal["0.7.0"] = "0.7.0"
    revision: str = Field(pattern=r"^(?:[a-f0-9]{40}|unknown)$")
    generated_at: datetime
    profiles: dict[str, CompletionStatus]
    checks: tuple[CompletionCheck, ...]
    router_core_ready: bool
    openai_adapter_ready: bool
    openai_live_verified: bool
    marketplace_contract_ready: bool
    marketplace_live_enabled: Literal[False] = False
    release_ready: bool

    @model_validator(mode="after")
    def readiness_is_derived(self) -> RouterCompletionReport:
        expected = {
            "router_core_ready": self.profiles.get("core") is CompletionStatus.PASS,
            "openai_adapter_ready": self.profiles.get("openai") is CompletionStatus.PASS,
            "marketplace_contract_ready": (
                self.profiles.get("marketplace_contract") is CompletionStatus.PASS
            ),
        }
        if any(getattr(self, field) is not value for field, value in expected.items()):
            raise ValueError("completion readiness must be derived from profile status")
        release = all(expected.values()) and not self.marketplace_live_enabled
        if self.release_ready is not release:
            raise ValueError("release_ready must be derived")
        return self


@dataclass(frozen=True)
class _CheckSpec:
    id: str
    profile: Literal["core", "openai", "marketplace_contract"]
    test_id: str
    artifact: str


_CHECKS = (
    _CheckSpec("exact-versioned-capability", "core", "tests/test_version_consistency.py::test_legacy_manifest_versions_remain_supported", "tests/test_version_consistency.py"),
    _CheckSpec("input-output-schema-validation", "core", "tests/test_router_execution.py::test_invalid_output_without_fallback_has_failed_outcome", "tests/test_router_execution.py"),
    _CheckSpec("hard-policy-before-scoring", "core", "tests/test_models_policy_scoring.py::test_hard_constraints_reject_before_scoring", "tests/test_models_policy_scoring.py"),
    _CheckSpec("request-cannot-weaken-policy", "core", "tests/test_models_policy_scoring.py::test_merge_constraints_never_weakens_policy", "tests/test_models_policy_scoring.py"),
    _CheckSpec("route-qualification-activation-drift", "core", "tests/test_v03_qualification_workflow.py::test_candidate_requires_qualification_activation_and_suspends_on_drift", "tests/test_v03_qualification_workflow.py"),
    _CheckSpec("deterministic-ranking-tie-breaking", "core", "tests/test_v07_completion_verifier.py::test_router_tie_breaks_by_executor_id", "tests/test_v07_completion_verifier.py"),
    _CheckSpec("baseline-abstention", "core", "tests/test_router_execution.py::test_router_abstains_when_gain_is_below_configured_overhead", "tests/test_router_execution.py"),
    _CheckSpec("idempotency", "core", "tests/test_p0_usefulness.py::test_idempotency_replays_receipt_without_reexecuting_output", "tests/test_p0_usefulness.py"),
    _CheckSpec("unified-attempt-transitions", "core", "tests/test_v07_execution_attempts.py::test_fault_at_every_state_is_durable", "tests/test_v07_execution_attempts.py"),
    _CheckSpec("crash-recovery-no-blind-duplicate", "core", "tests/test_v07_execution_attempts.py::test_managed_crash_is_indeterminate_and_same_decision_cannot_duplicate", "tests/test_v07_execution_attempts.py"),
    _CheckSpec("receipt-accounting-integrity", "core", "tests/test_v04_accounting.py::test_subscription_usage_stays_separate_from_cash", "tests/test_v04_accounting.py"),
    _CheckSpec("privacy-defaults", "core", "tests/test_router_execution.py::test_persisted_decision_redacts_sensitive_input_and_context", "tests/test_router_execution.py"),
    _CheckSpec("managed-prompt-output-privacy", "core", "tests/test_v07_security.py::test_default_database_omits_managed_prompt_and_output", "tests/test_v07_security.py"),
    _CheckSpec("old-manifest-database-compatibility", "core", "tests/test_v04_store_migrations.py::test_unversioned_legacy_database_migrates_without_data_loss", "tests/test_v04_store_migrations.py"),
    _CheckSpec("database-migration-rollback", "core", "tests/test_v04_store_migrations.py::test_failed_migration_rolls_back_as_one_transaction", "tests/test_v04_store_migrations.py"),
    _CheckSpec("offline-operation", "core", "tests/test_v07_host_native_routing.py::test_exact_local_bypass_makes_no_model_call", "tests/test_v07_host_native_routing.py"),
    _CheckSpec("offline-verifier-network-guard", "core", "tests/test_v07_security.py::test_verifier_subprocess_enables_offline_guard", "tests/conftest.py"),
    _CheckSpec("committed-secret-scan", "core", "tests/test_v07_security.py::test_committed_fixture_reports_contain_no_secret_patterns", "tests/test_v07_security.py"),
    _CheckSpec("generated-schema-consistency", "core", "tests/test_generated_artifacts.py::test_checked_in_schemas_are_current", "tests/test_generated_artifacts.py"),
    _CheckSpec("app-server-handshake-features", "openai", "tests/test_codex_app_server_transport.py::test_transport_handshake_requests_and_clean_shutdown", "tests/fixtures/fake_codex_app_server.py"),
    _CheckSpec("app-server-executable-identity", "openai", "tests/test_codex_app_server_transport.py::test_executable_path_and_optional_digest_are_validated", "tests/test_codex_app_server_transport.py"),
    _CheckSpec("codex-auth-boundary", "openai", "tests/test_codex_subscription_adapter.py::test_auth_required_is_explicit_and_does_not_fallback", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("account-identity-redaction", "openai", "tests/test_codex_subscription_adapter.py::test_runtime_models_and_multi_window_quota_are_preserved", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("account-switch-hmac-invalidation", "openai", "tests/test_codex_subscription_adapter.py::test_account_switch_invalidates_cached_probe_and_hmac_identity", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("bounded-environment-allowlist", "openai", "tests/test_codex_subscription_adapter.py::test_environment_is_exactly_allowlisted", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("runtime-model-discovery", "openai", "tests/test_v07_operator_cli.py::test_codex_operator_commands_use_fake_without_model_turn", "tests/test_v07_operator_cli.py"),
    _CheckSpec("multi-window-quota", "openai", "tests/test_codex_subscription_adapter.py::test_runtime_models_and_multi_window_quota_are_preserved", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("per-turn-token-accounting", "openai", "tests/test_codex_subscription_adapter.py::test_managed_action_records_one_turn_reroute_and_token_accounting", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("model-reroute-recording", "openai", "tests/test_codex_subscription_adapter.py::test_managed_action_records_one_turn_reroute_and_token_accounting", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("approval-intersection", "openai", "tests/test_codex_subscription_adapter.py::test_approval_requires_both_host_decision_and_aeep_ceiling", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("approval-replay", "openai", "tests/test_codex_subscription_adapter.py::test_approval_request_replay_fails_closed", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("one-turn-managed-execution", "openai", "tests/test_codex_subscription_adapter.py::test_managed_action_records_one_turn_reroute_and_token_accounting", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("no-credential-file-reads", "openai", "tests/test_codex_subscription_adapter.py::test_adapter_never_reads_codex_auth_files", "tests/test_codex_subscription_adapter.py"),
    _CheckSpec("fake-server-conformance", "openai", "tests/test_codex_app_server_transport.py::test_transport_fails_closed_on_invalid_frames", "tests/fixtures/fake_codex_app_server.py"),
    _CheckSpec("capacity-resource-contract", "marketplace_contract", "tests/test_v07_capacity.py::test_old_subscription_resources_keep_safe_defaults", "tests/test_v07_capacity.py"),
    _CheckSpec("transferability-enforcement", "marketplace_contract", "tests/test_v07_capacity.py::test_self_only_openai_capacity_cannot_issue_external_entitlement", "tests/test_v07_capacity.py"),
    _CheckSpec("capacity-reservation-release", "marketplace_contract", "tests/test_v07_capacity.py::test_capacity_reservation_release_and_replay_are_atomic", "tests/test_v07_capacity.py"),
    _CheckSpec("entitlement-binding", "marketplace_contract", "tests/test_x402_capacity_binding.py::test_local_batch_conformance_is_complete_and_offline", "tests/test_x402_capacity_binding.py"),
    _CheckSpec("openai-self-only-rejection", "marketplace_contract", "tests/test_x402_capacity_binding.py::test_openai_self_only_fails_before_x402_serialization", "tests/test_x402_capacity_binding.py"),
    _CheckSpec("provider-authorized-mock-transfer", "marketplace_contract", "tests/test_v07_capacity.py::test_provider_authorized_entitlement_redeems_once_without_double_spend", "tests/test_v07_capacity.py"),
    _CheckSpec("x402-local-batch-conformance", "marketplace_contract", "tests/test_x402_capacity_binding.py::test_x402_cli_emits_valid_json_report", "reports/v07/x402-conformance.json"),
    _CheckSpec("replay-expiry-double-spend", "marketplace_contract", "tests/test_x402_capacity_binding.py::test_local_batch_conformance_is_complete_and_offline", "tests/test_x402_capacity_binding.py"),
)


def _digest(path: Path) -> str:
    return f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}"


def _revision(root: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip().lower()
    return value if result.returncode == 0 and len(value) == 40 else "unknown"


def _pytest(root: Path, node_ids: list[str]) -> tuple[bool, str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *node_ids],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=300,
        env={**os.environ, "AEEP_VERIFY_OFFLINE": "1"},
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output[-2000:]


def verify_router_complete(
    *,
    profile: Literal["core", "openai", "marketplace-contract", "all"] = "all",
    root: Path | None = None,
) -> RouterCompletionReport:
    repository = (root or Path(__file__).resolve().parents[2]).resolve()
    lock_path = repository / "reports" / "v07" / "verification-lock.json"
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    expected_digests: dict[str, str] = lock["artifacts"]
    selected_profiles = (
        {"core", "openai", "marketplace_contract"}
        if profile == "all"
        else {profile.replace("-", "_")}
    )
    selected = [item for item in _CHECKS if item.profile in selected_profiles]
    all_tests_passed, test_output = _pytest(
        repository, sorted({item.test_id for item in selected})
    )
    individual: dict[str, bool] = {}
    if not all_tests_passed:
        for test_id in sorted({item.test_id for item in selected}):
            individual[test_id] = _pytest(repository, [test_id])[0]

    checks: list[CompletionCheck] = []
    for spec in selected:
        artifact = repository / spec.artifact
        actual_digest = _digest(artifact) if artifact.is_file() else "sha256:" + "0" * 64
        digest_ok = expected_digests.get(spec.artifact) == actual_digest
        test_ok = all_tests_passed or individual.get(spec.test_id, False)
        reasons: list[str] = []
        if not digest_ok:
            reasons.append(f"artifact digest mismatch: {spec.artifact}")
        if not test_ok:
            reasons.append(f"executable test failed: {spec.test_id}")
        checks.append(
            CompletionCheck(
                id=spec.id,
                profile=spec.profile,
                required=True,
                status=(CompletionStatus.PASS if digest_ok and test_ok else CompletionStatus.FAIL),
                test_ids=(spec.test_id,),
                evidence_ids=(spec.artifact,),
                artifact_digests=(actual_digest,),
                reason="; ".join(reasons) or "",
            )
        )

    if "openai" in selected_profiles:
        checks.append(
            CompletionCheck(
                id="openai-live-account-proof",
                profile="openai",
                required=False,
                status=CompletionStatus.SKIP,
                reason=(
                    "requires explicit operator approval, an interactive Codex login, "
                    "and permission to consume one live subscription turn"
                ),
            )
        )
    if "marketplace_contract" in selected_profiles:
        checks.append(
            CompletionCheck(
                id="live-marketplace-networking",
                profile="marketplace_live",
                required=False,
                status=CompletionStatus.DISABLED,
                reason="AEEP 0.7 ships local contracts only; live networking is disabled",
            )
        )

    statuses: dict[str, CompletionStatus] = {}
    for name in ("core", "openai", "marketplace_contract"):
        if name not in selected_profiles:
            statuses[name] = CompletionStatus.SKIP
            continue
        required = [item for item in checks if item.profile == name and item.required]
        statuses[name] = (
            CompletionStatus.PASS
            if required and all(item.status is CompletionStatus.PASS for item in required)
            else CompletionStatus.FAIL
        )
    statuses["marketplace_live"] = CompletionStatus.DISABLED
    core = statuses["core"] is CompletionStatus.PASS
    openai = statuses["openai"] is CompletionStatus.PASS
    marketplace = statuses["marketplace_contract"] is CompletionStatus.PASS
    report = RouterCompletionReport(
        revision=_revision(repository),
        generated_at=datetime.now(UTC),
        profiles=statuses,
        checks=tuple(checks),
        router_core_ready=core,
        openai_adapter_ready=openai,
        openai_live_verified=False,
        marketplace_contract_ready=marketplace,
        release_ready=core and openai and marketplace,
    )
    if not all_tests_passed and test_output:
        failing = [item for item in report.checks if item.status is CompletionStatus.FAIL]
        if failing:
            failing[0].reason = f"{failing[0].reason}; pytest: {test_output}"[-4000:]
    return report


def write_completion_report(report: RouterCompletionReport, *, root: Path | None = None) -> None:
    repository = (root or Path(__file__).resolve().parents[2]).resolve()
    report_dir = repository / "reports" / "v07"
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "router-complete.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        "# AEEP 0.7 router completion",
        "",
        f"Revision: `{report.revision}`",
        f"Release ready: `{str(report.release_ready).lower()}`",
        "",
        "| Check | Profile | Status |",
        "|---|---|---|",
        *(
            f"| `{item.id}` | `{item.profile}` | `{item.status.value}` |"
            for item in report.checks
        ),
        "",
    ]
    (report_dir / "router-complete.md").write_text("\n".join(lines), encoding="utf-8")


def strict_failure(report: RouterCompletionReport) -> bool:
    return any(
        item.required and item.status is not CompletionStatus.PASS
        for item in report.checks
    )
