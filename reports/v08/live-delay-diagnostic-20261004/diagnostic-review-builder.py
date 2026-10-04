"""Prepare proposed reviews only; no store, proxy, worker, model or directory creation."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import uuid
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
PINS = {
    "diagnostic-prepare.py": "81a9d1fa9c4feb06c18f58f95d684336a92fee5e7af5fbd0999e8a84e7557122",
    "diagnostic-run.py": "2c02948928087ae2de43a8c313b71f273a986c9dea797a387c11e56921bd1f4c",
    "diagnostic-persist.py": "dda52adddb66e162f7c5144aacbef8b335d8532c02b7771088c2c52dbb124cc4",
    "c-current-profile-v2.json": "ac096d106954d86433f4743333ac7004765a9dbc2db229c9fbecc5efa3db2eb8",
    "fresh-input.json": "0b1fe315b9fe2abea7715520b3eb7f21cf3b82b1ca07c7f48a876b25e77253d9",
    "input-provenance.json": "1661a9950a7fc7d1770fe0261cbee0e46a47c80e3c5cb60e158c02f030933850",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def sha(path: Path) -> str:
    require(path.is_file() and not path.is_symlink() and path.stat().st_size <= 2_000_000,
            "review input must be a bounded regular non-symlink file")
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path: Path) -> dict:
    sha(path)
    value = json.loads(path.read_bytes())
    require(isinstance(value, dict), "review input must be an object")
    return value


def build() -> tuple[dict, dict]:
    from aeep.assessment.identity import verify_dependencies
    from aeep.assessment.models import ConformanceProbeRequest, content_digest
    from aeep.assessment.verification import verification_source_digest

    require(verification_source_digest(ROOT) == SOURCE, "diagnostic source changed")
    for name, digest in PINS.items():
        require(sha(OUT / name) == digest, "frozen diagnostic helper, profile or input changed")
    # The pinned runner is inert on import. Reuse its read-only capacity and store
    # metadata checks, without constructing Router or opening any database.
    spec = importlib.util.spec_from_file_location("delay_diagnostic_reviewed_runner", OUT / "diagnostic-run.py")
    require(spec is not None and spec.loader is not None, "reviewed runner loader is unavailable")
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    bundle = read(runner.PREPARATION)
    request = ConformanceProbeRequest.model_validate(bundle["request"])
    require(bundle.get("source_digest") == SOURCE and content_digest(request) == bundle.get("request_digest")
            and request.authorization_id == "onboarding" and request.composed_model_turns == 1
            and bundle.get("diagnostic_only") is True and bundle.get("holdout") is False
            and bundle.get("execution_authorized") is False, "inert fresh diagnostic request changed")
    verify_dependencies(request.executable_dependencies)
    require(bundle.get("limits") == {"operations": 1, "model_turns": 1, "elapsed_seconds": 208.0,
            "cash_usd": 0, "task_calls": 1, "task_call_timeout_seconds": 10.0, "task_scope_attempts": 1},
            "finite diagnostic bounds changed")
    for path, field in ((runner.PROFILE, "profile_sha256"), (runner.COMPONENT_RESULT, "component_result_sha256"),
            (runner.COMPONENT_AUDIT, "component_terminal_audit_sha256"),
            (runner.PROXY_RESULT, "proxy_lifecycle_result_sha256"),
            (runner.SETUP_RESULT, "setup_result_sha256"), (runner.SETUP_REVIEW, "setup_review_sha256")):
        require(sha(path) == bundle.get(field), "a prepared prerequisite pin changed")
    component = read(runner.COMPONENT_RESULT)
    proxy = read(runner.PROXY_RESULT)
    native_result = read(runner.NATIVE_COMPONENT_RESULT)
    native_review = read(runner.NATIVE_COMPONENT_REVIEW)
    require(component.get("source_digest") == SOURCE and component.get("source_unchanged") is True
            and component.get("component_probes_match") is True and component.get("model_turns") == 0
            and component.get("full_conformance") is False, "worker component evidence is incomplete")
    require(proxy.get("status") == "passed" and proxy.get("source_digest") == SOURCE
            and proxy.get("source_unchanged") is True and proxy.get("proxy_restored_stopped") is True
            and proxy.get("cleanup_operation_settled") is True
            and proxy.get("inner_result_sha256") == sha(runner.COMPONENT_RESULT), "worker proxy lifecycle is incomplete")
    require(native_result.get("source_digest") == SOURCE and native_result.get("result_status") == "pass"
            and native_result.get("review_sha256") == sha(runner.NATIVE_COMPONENT_REVIEW)
            and native_result.get("cleanup_confirmed") is True and native_result.get("operation_settled") is True
            and native_result.get("source_unchanged") is True and native_result.get("model_turns") == 0
            and native_result.get("boundary_probes_complete") is True and native_result.get("full_conformance") is False,
            "native component evidence is incomplete")
    require(native_review.get("source_digest") == SOURCE and native_review.get("execution_authorized") is True
            and native_review.get("driver_sha256") == sha(runner.NATIVE_COMPONENT_RUNNER)
            and native_review.get("selected_worker_digest") == bundle["worker_digest"]
            and native_review.get("callback_document_digests", {}).get("treatment") == bundle["callback_binding_digest"],
            "native component review differs from the selected callback")
    canonical = runner._canonical_store(None)
    require((canonical["device"], canonical["inode"]) == (16777231, 166293865), "canonical database identity changed")
    # Only propose a new path. The root agent creates this parent at execution time.
    fresh_directory = Path("/private/tmp") / ("aeep-live-delay-20261004-" + uuid.uuid4().hex)
    fresh_database = fresh_directory / "outer.sqlite3"
    native_project = Path(bundle["task_scope_binding"]["project_root"]).resolve()
    require(not fresh_directory.exists() and not fresh_directory.is_symlink()
            and fresh_directory.resolve() == fresh_directory and ROOT not in fresh_database.parents
            and native_project not in fresh_database.parents, "proposed isolated database path is not fresh")
    execution = dict(
        schema_version="assessment.c-current-callback-execution-review.v1",
        status="proposed_not_authorized", execution_authorized=False, persistence_authorized=False,
        authority="Pending root exact review under docs/ASSESSMENT_TESTING.md standing finite delegation.",
        source_digest=SOURCE, builder_sha256=sha(Path(__file__)),
        preparation_sha256=sha(runner.PREPARATION), runner_sha256=sha(OUT / "diagnostic-run.py"),
        preparer_sha256=sha(OUT / "diagnostic-prepare.py"), profile_sha256=sha(runner.PROFILE),
        component_result_sha256=sha(runner.COMPONENT_RESULT), component_terminal_audit_sha256=sha(runner.COMPONENT_AUDIT),
        setup_result_sha256=sha(runner.SETUP_RESULT), setup_review_sha256=sha(runner.SETUP_REVIEW),
        proxy_lifecycle_result_sha256=sha(runner.PROXY_RESULT),
        request_id=request.plan_id, request_digest=content_digest(request),
        capacity_review_sha256=sha(runner.CAPACITY_REVIEW), capacity_result_sha256=sha(runner.CAPACITY_RESULT),
        capacity_request_sha256=sha(runner.CAPACITY_REQUEST),
        native_component_result_sha256=sha(runner.NATIVE_COMPONENT_RESULT), native_component_review_sha256=sha(runner.NATIVE_COMPONENT_REVIEW),
        max_operations=1, max_model_turns=1, max_elapsed_seconds=208.0, max_cash_usd=0,
        task_calls=1, task_scope_attempts=1, task_call_timeout_seconds=10.0, task_effect="read",
        model_id="gpt-6-luna", reasoning_effort="xhigh", worker_digest=bundle["worker_digest"],
        callback_binding_digest=bundle["callback_binding_digest"], task_scope_id=bundle["task_scope_id"],
        task_scope_binding_digest=bundle["task_scope_binding_digest"],
        fixture_input_digest=bundle["fixture_input_digest"], fixture_file_sha256=sha(runner.FIXTURE),
        proxy_name=runner.PROXY_NAME, proxy_id=runner.PROXY_ID, proxy_image=runner.PROXY_IMAGE,
        proxy_network=runner.PROXY_NETWORK, proxy_lifecycle_owned_here=False,
        fresh_database=str(fresh_database), fresh_directory=str(fresh_directory),
        fresh_directory_created=False, canonical_store=canonical,
        executable_dependencies=request.executable_dependencies, diagnostic_only=True, holdout=False,
        full_conformance=False, qualification=False, admission=False, value_trial=False,
        result_path=str(runner.RESULT), started_record_path=str(runner.STARTED),
    )
    capacity = runner._require_capacity(bundle, execution)
    execution["capacity_age_seconds_at_proposal"] = runner._age_seconds(capacity["capacity"]["observed_at"])
    execution["capacity_max_age_seconds"] = runner.MAX_CAPACITY_AGE_SECONDS
    persistence = dict(schema_version="assessment.live-delay-persistence-review.v1",
        status="proposed_not_authorized", persistence_authorized=False, execution_authorized=False,
        authority="Pending root exact review of inert persistence only; no allowance reservation.",
        source_digest=SOURCE, builder_sha256=sha(Path(__file__)), runner_sha256=sha(OUT / "diagnostic-persist.py"),
        manifest_sha256=canonical["manifest_sha256"], canonical_store=canonical,
        bundles={runner.PREPARATION.name: sha(runner.PREPARATION)}, request_id=request.plan_id,
        request_digest=content_digest(request), grant="onboarding", grant_counters_preserved=True,
        operations_reserved=0, model_turns=0, diagnostic_only=True)
    return persistence, execution


def main() -> None:
    targets = [OUT / "diagnostic-persistence-proposed-review.json", OUT / "diagnostic-execution-proposed-review.json"]
    require(not any(path.exists() or path.is_symlink() for path in targets), "preserve existing proposed reviews")
    records = build()
    for path, record in zip(targets, records, strict=True):
        with path.open("x") as stream:
            json.dump(record, stream, sort_keys=True, indent=2)
            stream.write("\n")
    print(json.dumps({"status": "proposed_only", "reviews": {str(path): sha(path) for path in targets},
                      "execution_authorized": False, "persistence_authorized": False,
                      "fresh_directory_created": False, "database_opened": False}))


if __name__ == "__main__":
    main()
