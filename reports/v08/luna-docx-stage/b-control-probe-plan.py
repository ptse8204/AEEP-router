"""Build a read-only, report-local plan for the next B control probe.

This helper never imports AEEP, opens a database, persists definitions, reserves
allowance, starts a worker, or calls a model. Its JSON is a proposal only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PROFILE = OUT / "b-current-profile-v2.json"
PROFILE_SHA256 = "28ed2a514083beda4ef3fc1fbcfa6320f5fabe2b8dcde74dddac7d7bb489c79a"
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
NATIVE_MANIFEST = Path("/private/var/folders/_g/bvzl9cms7cx1d0wdpc981n9w0000gn/T/aeep-b-native-final-20261003/aeep.json")
NATIVE_MANIFEST_SHA256 = "11707d498ce6a285c85c0e7c90314e9f24ff355e1be987021898896e9e920d60"
NATIVE_REVIEW = OUT / "b-native-components-v4-review.json"
NATIVE_REVIEW_SHA256 = "2a8823bfa8fff767a73e791f0e27277290e82ce5ed4b56d583f19f1c204a4c31"
NATIVE_RESULT = OUT / "b-native-components-v4-result.json"
NATIVE_RESULT_SHA256 = "2cafc12642b19d0dddb158f614da19bed96d2dc39ea8657375ccc55965230ad4"
PAIR_RESULT = OUT / "b-worker-components-v2-result.json"
PAIR_RESULT_SHA256 = "0552cf86620985194c5bd9d1252e88819667730ff9004efc1b82510b98696379"
PAIR_AUDIT = OUT / "b-worker-components-terminal-audit.json"
PAIR_AUDIT_SHA256 = "81ca6e006016204a07977bd137066a2352311839664cf500f9859ac27b49e60a"
TREATMENT_CALLBACK_RESULT = OUT / "b-current-callback-result-v2.json"
TREATMENT_CALLBACK_RESULT_SHA256 = "deea583086869129974e63f81bc0e3875fb8666e1f92a921aec338a24d6d8c20"
TREATMENT_PROXY_RESULT = OUT / "b-worker-proxy-lifecycle-v3-result.json"
TREATMENT_PROXY_RESULT_SHA256 = "1153138d250c32d7720852561936bc0a6d3d5a06293203fe4de444a739cdc5e5"
FIXTURE = ROOT / "integrations/assessment-runtime/workbook-grader-fixtures.json"
FIXTURE_SHA256 = "e1342eb43a3daac7ef1dd59ab121d4b1e4f77d07ab8595e4639fc5b8b7c7e5be"
FIXTURE_INPUT_DIGEST = "f7ef188dad768538b171d56cdf655801a45489c6fed6d88b8257284a54520beb"
CONTROL_WORKER = "e15b7ee0ecabb077cc64ba80f724c739bc51bda8dc71d4038efc92f7678df345"
CONTROL_CALLBACK = "c2e2f8d21a5c791f707da9d1ae83257c4feb99a3e94559d6bca7bfcd127a1c16"
PAIR_COMPONENT = "5438e3aae178909d6d7c765b1590c05308a343d26e8c467097435ba1b1149e8d"
NATIVE_BACKEND = "5c3f016cdf6ee992218e15ebb262a447e7c8ec4353c320e25e58b7617cbebd6d"
NATIVE_BACKEND_COMPONENT = "7be9c342d3d026bee66e7ce1317aa53a85082faf9cad0b10d5fd4c9d79a878a5"
EXECUTOR_FINGERPRINT = "sha256:658eb48482ecca3a53a7099b85a307f377f07061c186918334bc321343a653e4"
OLD_SCOPE_ID = "current-composed-workbook"
NEW_SCOPE_ID = "b-control-callback-20261003"
PLAN_PATH = OUT / "b-control-probe-plan.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pins() -> dict[str, str]:
    return {
        str(path): expected for path, expected in (
            (PROFILE, PROFILE_SHA256), (SETUP_RESULT, SETUP_RESULT_SHA256),
            (NATIVE_REVIEW, NATIVE_REVIEW_SHA256), (NATIVE_RESULT, NATIVE_RESULT_SHA256),
            (PAIR_RESULT, PAIR_RESULT_SHA256), (PAIR_AUDIT, PAIR_AUDIT_SHA256),
            (TREATMENT_PROXY_RESULT, TREATMENT_PROXY_RESULT_SHA256), (FIXTURE, FIXTURE_SHA256),
        )
    }


def build_plan() -> dict[str, Any]:
    for path_text, expected in _pins().items():
        path = Path(path_text)
        if path.is_symlink() or not path.is_file() or _sha(path) != expected:
            raise RuntimeError(f"pinned read-only input changed: {path.name}")
    profile = json.loads(PROFILE.read_text())
    setup = json.loads(SETUP_RESULT.read_text())
    native_review = json.loads(NATIVE_REVIEW.read_text())
    native_result = json.loads(NATIVE_RESULT.read_text())
    pair_result = json.loads(PAIR_RESULT.read_text())
    pair_audit = json.loads(PAIR_AUDIT.read_text())
    treatment_result = json.loads(TREATMENT_CALLBACK_RESULT.read_text())
    proxy_result = json.loads(TREATMENT_PROXY_RESULT.read_text())
    profile_sha = _sha(PROFILE)
    if profile.get("source_digest") != SOURCE or profile.get("component_digest") != PAIR_COMPONENT:
        raise RuntimeError("current profile/source/component binding differs")
    if (profile.get("task_instructions", "").count("fixed_workbook") != 0
            or "may use available local tools" not in profile.get("task_instructions", "")):
        raise RuntimeError("frozen control instruction changed; review the exposure premise")
    control = profile["component"]["composed"]["control"]
    callback = profile["callback_documents_by_role"]["control"]
    if (control["id"] != "b.luna.discovery"
            or callback["identity"]["worker_digest"] != CONTROL_WORKER
            or callback["identity"]["native_backend_digest"] != NATIVE_BACKEND
            or callback.get("max_calls") != 1 or callback.get("timeout_seconds") != 10.0
            or [tool.get("name") for tool in callback.get("tools", [])] != ["fixed_workbook"]
            or control["config"]["invocation"]["mode"] != "turn"
            or control["config"]["invocation"].get("dynamic_tools_digest") != CONTROL_CALLBACK):
        raise RuntimeError("exact control worker/callback binding differs")
    if (setup.get("project") != str(NATIVE_MANIFEST.parent)
            or setup.get("scope_id") != OLD_SCOPE_ID
            or setup.get("scope_digest") != "01182a6f178c9cd33b7b90e7eb4d1d068dd7c397bc47641acc982c3937909177"
            or _sha(NATIVE_MANIFEST) != NATIVE_MANIFEST_SHA256):
        raise RuntimeError("existing native project or consumed scope binding differs")
    if NEW_SCOPE_ID == OLD_SCOPE_ID:
        raise RuntimeError("fresh control scope must not reuse the consumed scope id")
    if (native_review.get("selected_worker_digest") != "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
            or native_result.get("result_status") != "pass"
            or native_result.get("operation_settled") is not True
            or native_result.get("native_attempts") != 2
            or native_result.get("full_conformance") is not False):
        raise RuntimeError("existing native probes are not valid; treatment evidence cannot stand in for control")
    if (pair_result.get("source_unchanged") is not True
            or pair_result.get("component_probes_match") is not True
            or pair_result.get("component_evidence_only") is not True
            or pair_result.get("full_conformance") is not False
            or any(pair_result.get("workers", {}).get(role, {}).get("cleanup_confirmed") is not True
                   for role in ("control", "treatment"))
            or pair_audit.get("source_digest") != SOURCE
            or pair_audit.get("actual_worker_cleanup_confirmed") is not True):
        raise RuntimeError("existing pair inspection evidence is not source-stable and clean")
    if (treatment_result.get("worker_digest") != "19027f56cdc99fc9b728dc2bf7af597f33c6a0d8f4b5d71d19739aa512a56df0"
            or treatment_result.get("cleanup_confirmed") is not True
            or treatment_result.get("source_unchanged") is not True
            or treatment_result.get("full_conformance") is not False):
        raise RuntimeError("existing treatment callback evidence is not the expected non-conformance pilot")
    if (proxy_result.get("proxy_restored_stopped") is not True
            or proxy_result.get("cleanup_operation_settled") is not True):
        raise RuntimeError("prior proxy lifecycle did not settle stopped")

    return {
        "schema_version": "assessment.b-control-probe-plan.v1",
        "status": "inert_proposal",
        "source_digest": SOURCE,
        "profile_path": str(PROFILE),
        "profile_sha256": profile_sha,
        "plan_helper_sha256": _sha(Path(__file__).resolve()),
        "input_pins": _pins(),
        "component_digest": PAIR_COMPONENT,
        "control": {
            "executor_id": control["id"],
            "worker_digest": CONTROL_WORKER,
            "callback_digest": CONTROL_CALLBACK,
            "native_backend_digest": NATIVE_BACKEND,
            "executor_fingerprint": EXECUTOR_FINGERPRINT,
            "invocation_mode": "turn",
            "callback_exposure": "optional; instruction remains unchanged",
            "callback_tool_names": ["fixed_workbook"],
            "task_instruction": profile["task_instructions"],
            "model_id": "gpt-6-luna",
            "reasoning_effort": "xhigh",
            "worker_image_digest": control["config"]["managed_worker"]["image"],
            "credential_volume": control["config"]["managed_worker"]["credential_volume"],
        },
        "native_project": {
            "manifest_path": str(NATIVE_MANIFEST),
            "manifest_sha256": NATIVE_MANIFEST_SHA256,
            "project_root": str(NATIVE_MANIFEST.parent),
            "database_path": setup.get("database_path") or str(NATIVE_MANIFEST.parent / ".aeep/state.db"),
            "preserve_consumed_scope": {"scope_id": OLD_SCOPE_ID, "scope_digest": setup["scope_digest"]},
            "proposed_new_scope": {
                "scope_id": NEW_SCOPE_ID,
                "executor_fingerprints": {"native.composed.workbook": EXECUTOR_FINGERPRINT},
                "approval_ceiling": "read",
                "max_attempts": 1,
                "max_attempt_seconds": 10.0,
                "expiry": "generated once at reviewed setup; 15 minute horizon",
                "reuse_or_reset": False,
            },
        },
            "native_probe_set": {
            "template_review_sha256": NATIVE_REVIEW_SHA256,
            "template_result_sha256": NATIVE_RESULT_SHA256,
            "selected_worker_digest": CONTROL_WORKER,
            "native_backend_component_digest": NATIVE_BACKEND_COMPONENT,
            "required_probe_names": ["native_boundary", "protected_state", "callback_lifecycle"],
            "definitions_must_be_fresh": True,
            "old_treatment_probes_satisfy_control": False,
            "max_native_attempts": 2,
            "max_native_attempt_seconds": 10.0,
            "max_assessment_operations": 1,
            "max_model_turns": 0,
            "max_elapsed_seconds": 40.0,
            "cash_ceiling_usd": 0,
        },
        "callback_probe": {
            "public_fixture_path": str(FIXTURE),
            "public_fixture_sha256": FIXTURE_SHA256,
            "record_index": 0,
            "input_digest": FIXTURE_INPUT_DIGEST,
            "expected_output_or_later_rows_read": False,
            "callback_tool": "fixed_workbook",
            "model_id": "gpt-6-luna",
            "reasoning_effort": "xhigh",
            "max_model_turns": 1,
            "max_assessment_operations": 1,
            "max_elapsed_seconds": 208.0,
            "worker_timeout_seconds": 203.0,
            "cleanup_allowance_seconds": 5.0,
            "max_callback_calls": 1,
            "callback_timeout_seconds": 10.0,
            "cash_ceiling_usd": 0,
            "no_invocation_outcome": "inconclusive; preserve result and do not replay",
        },
        "prerequisites": {
            "fresh_control_worker_capacity": "required immediately before the model attempt; not present in this plan",
            "proxy": "exact proxy must be started under its separately reviewed lifecycle and stopped afterward",
            "new_scope_and_probe_records": "must be prepared/reviewed in a separate approved setup step; not persisted here",
            "full_conformance": False,
            "qualification": False,
            "value_trial": False,
            "admission": False,
        },
        "prior_costs": "retain all existing same-grant operations; no reset or refund",
        "canonical_definitions_persisted": False,
        "allowance_reserved": False,
        "execution_authorized": False,
    }


def write_exclusive(path: Path, value: dict[str, Any]) -> None:
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, sort_keys=True, indent=2) + "\n")
        stream.flush()
        os.fsync(stream.fileno())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-plan", action="store_true")
    args = parser.parse_args()
    plan = build_plan()
    if args.write_plan:
        write_exclusive(PLAN_PATH, plan)
        print(json.dumps({"status": plan["status"], "path": str(PLAN_PATH),
                          "plan_sha256": _sha(PLAN_PATH)}, sort_keys=True))
    else:
        print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
