"""Prepare or run the bounded C treatment native-only component inspection."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import os
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
HISTORY = OUT.parent / "luna-docx-stage"
PROFILE = OUT / "c-current-profile-v2.json"
PROFILE_SHA256 = "ac096d106954d86433f4743333ac7004765a9dbc2db229c9fbecc5efa3db2eb8"
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"
B_SETUP_SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PRODUCER = OUT / "native-component-definitions-treatment.py"
PRODUCER_SHA256 = "b75eb9fe5d3bc0fac8c314e8b8fff231e46c81bd6e8a7d4d0ca7bf92b9f4c0a3"
SETUP_RESULT = HISTORY / "b-native-setup-v3-result.json"
SETUP_REVIEW = HISTORY / "b-native-setup-v3-review.json"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
MAIN_MANIFEST = ROOT / ".aeep" / "live-review-v3" / "aeep.json"
MAIN_MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
MAIN_DATABASE = ROOT / ".aeep" / "live-review-v3" / "aeep.sqlite3"
MAIN_DATABASE_DEVICE = 16777231
MAIN_DATABASE_INODE = 166293865
REVIEW_PATH = OUT / "native-components-treatment-review.json"
RESULT_PATH = OUT / "native-components-treatment-result.json"
NATIVE_MANIFEST_SHA256 = "11707d498ce6a285c85c0e7c90314e9f24ff355e1be987021898896e9e920d60"
DEFINITION_ID = "delay-native-treatment-20261004-e6b71acb"
REQUEST_ID = "conformance_delay_native_treatment_20261004_e6b71acb"
CANCELLATION_SEMANTICS_RATIONALE = (
    "The native cancellation contract returns a TIMEOUT after terminating/EOF-closing the owned native command, "
    "rather than propagating CancelledError. The pinned test asserts execute_single_process returns timed_out "
    "after task.cancel() (tests/test_v08_native_process.py:85-96); the native host adapter handles cancellation "
    "as timed_out (src/aeep/hosts/codex_native_process.py:159-180), and CommandExecutor returns TIMEOUT "
    "(src/aeep/executors/command.py:413-424). For an idempotent READ, the router marks TIMEOUT FAILED; it "
    "reserves INDETERMINATE for writes or non-retry-eligible/managed-host timeouts "
    "(src/aeep/router.py:798-800, 901-911). This probe claims neither write recovery nor host EOF."
)
MAX_SECONDS = 40.0
MAX_ATTEMPTS = 2
ATTEMPT_SECONDS = 10.0


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json_exclusive(path: Path, value: dict) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, sort_keys=True) + "\n")


def source_pin() -> str:
    from aeep.assessment.verification import verification_source_digest
    return verification_source_digest(ROOT)


def load_components() -> dict:
    require(PROFILE.is_file() and not PROFILE.is_symlink() and sha256(PROFILE) == PROFILE_SHA256,
            "renewed component profile changed")
    require(sha256(PRODUCER) == PRODUCER_SHA256, "native component producer changed")
    module_spec = importlib.util.spec_from_file_location("c_native_components_treatment", PRODUCER)
    require(module_spec is not None and module_spec.loader is not None, "producer loader unavailable")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    return module.definitions()


def boundary_probe_definitions(components: dict) -> dict:
    from aeep.assessment.boundary import BoundaryProbeDefinition
    from aeep.models import ExecutorSpec

    native = components["native_boundary_expected"]
    expectations = {
        "native_boundary": {
            key: native[key] for key in (
                "hard_nproc", "session_leader", "marker", "fork_errno", "spawn_errno",
                "raise_denied", "network_denied",
            )
        },
        "protected_state": {
            "private_denied": native["private_denied"],
            "database_denied": native["database_denied"],
            "witness_unchanged": True,
        },
        "callback_lifecycle": {
            "cancel_requested": True,
            "fixed_helper_returned_timeout": True,
            "timeout_receipt_persisted": True,
            "read_attempt_failed_retry_eligible": True,
            "single_cancel_attempt": True,
            "ready_line_observed": True,
            "owned_non_zombie_processes_gone": True,
            "host_eof_observed": False,
        },
    }
    result = {}
    for name, expected in expectations.items():
        component = "cancel" if name == "callback_lifecycle" else "guard"
        executor = ExecutorSpec.model_validate(components["components"][component]["spec"])
        result[name] = BoundaryProbeDefinition(name=name, executor=executor, expected=expected)
    return result


def open_main():
    from aeep.router import Router
    from aeep.assessment.repository import AssessmentRepository
    setup_review = json.loads(SETUP_REVIEW.read_text())
    canonical = setup_review["canonical_store"]
    require(canonical == {
        "manifest": str(MAIN_MANIFEST),
        "manifest_sha256": MAIN_MANIFEST_SHA256,
        "database": str(MAIN_DATABASE),
        "device": MAIN_DATABASE_DEVICE,
        "inode": MAIN_DATABASE_INODE,
    }, "canonical setup-store identity differs from the reviewed setup")
    require(MAIN_MANIFEST.is_file() and not MAIN_MANIFEST.is_symlink()
            and sha256(MAIN_MANIFEST) == MAIN_MANIFEST_SHA256, "canonical manifest changed")
    manifest_payload = json.loads(MAIN_MANIFEST.read_text())
    require(manifest_payload.get("database") == str(MAIN_DATABASE), "canonical manifest database target changed")
    stat = MAIN_DATABASE.stat()
    require((stat.st_dev, stat.st_ino) == (MAIN_DATABASE_DEVICE, MAIN_DATABASE_INODE),
            "canonical database identity changed")
    router = Router.from_manifest(MAIN_MANIFEST)
    return router, AssessmentRepository(router.store)


def setup_anchor(repository):
    from aeep.assessment.models import ConformanceProbeRequest
    setup_review = json.loads(SETUP_REVIEW.read_text())
    anchor_id = setup_review["request"]["plan_id"]
    anchor = ConformanceProbeRequest.model_validate(repository.get("conformance_request", anchor_id))
    require(anchor.model_dump(mode="json") == setup_review["request"], "canonical setup request differs")
    require(anchor.schema_version == "assessment.conformance-request.v2"
            and anchor.operation == "worker_inspection" and anchor.composed_model_turns == 0,
            "expected reviewed zero-turn setup anchor")
    return anchor


def prepare() -> dict:
    from aeep.assessment.identity import file_digest, runtime_dependencies
    from aeep.assessment.models import content_digest
    from aeep.assessment.verification import verification_source_digest
    from aeep.hosts.workers import ManagedWorkerBinding
    from aeep.models import StrictModel

    require(not RESULT_PATH.exists() and not RESULT_PATH.is_symlink(),
            "native component result already exists or is unsafe; blind retry denied")
    require(sha256(SETUP_RESULT) == SETUP_RESULT_SHA256, "settled setup result changed")
    require(sha256(SETUP_REVIEW) == SETUP_REVIEW_SHA256, "settled setup review changed")
    require(verification_source_digest(ROOT) == SOURCE, "source pin changed")
    components = load_components()
    require(components.get("source_digest") == SOURCE
            and components.get("historical_setup_source_digest") == B_SETUP_SOURCE,
            "C native definitions are not bound to C source plus historical B setup")
    router, repository = open_main()
    try:
        anchor = setup_anchor(repository)
        workers = {role: ManagedWorkerBinding.model_validate(value)
                   for role, value in components["worker_documents"].items()}
        require(set(workers) == {"control", "treatment"}, "exact B worker pair unavailable")
        worker_records = {}
        for role, worker in workers.items():
            worker_records[role] = repository.put("worker_binding", worker.digest(), worker)
            repository.review(worker_records[role])

        class NativeComponentDefinition(StrictModel):
            source_digest: str
            profile_sha256: str
            component_profile_digest: str
            setup_request_id: str
            setup_result_digest: str
            setup_review_digest: str
            manifest_digest: str
            native_backend_digest: str
            selected_worker_role: str
            selected_worker_digest: str
            worker_record_digests: dict[str, str]
            callback_document_digests: dict[str, str]
            components: dict
            expected_native_boundary: dict
            expected_callback_lifecycle_partial: dict
            cancellation_semantics_rationale: str
            limits: dict
            callback_requirement: dict
            full_conformance: bool

        definition = NativeComponentDefinition(
            source_digest=SOURCE,
            profile_sha256=PROFILE_SHA256,
            component_profile_digest=components["component_profile_digest"],
            setup_request_id=components["setup_request_id"],
            setup_result_digest=components["setup_result_digest"],
            setup_review_digest=components["setup_review_digest"],
            manifest_digest=components["manifest_digest"],
            native_backend_digest=components["native_backend_digest"],
            selected_worker_role="treatment",
            selected_worker_digest=components["selected_worker_digest"],
            worker_record_digests=worker_records,
            callback_document_digests=components["callback_document_digests"],
            components=components["components"],
            expected_native_boundary=components["native_boundary_expected"],
            expected_callback_lifecycle_partial={
                "cancel_requested": True,
                "fixed_helper_returned_timeout": True,
                "timeout_receipt_persisted": True,
                "read_attempt_failed_retry_eligible": True,
                "single_cancel_attempt": True,
                "ready_line_observed": True,
                "owned_non_zombie_processes_gone": True,
                "host_eof_observed": False,
            },
            cancellation_semantics_rationale=CANCELLATION_SEMANTICS_RATIONALE,
            limits={"max_operations": 1, "max_model_turns": 0, "max_elapsed_seconds": MAX_SECONDS,
                    "max_cash_usd": 0, "native_attempts": MAX_ATTEMPTS,
                    "native_attempt_seconds": ATTEMPT_SECONDS},
            callback_requirement=components["callback_requirement"],
            full_conformance=False,
        )
        definition_digest = repository.put("native_component_definition", DEFINITION_ID, definition)
        repository.review(definition_digest)
        probe_definition_digests = {}
        for name, probe_definition in boundary_probe_definitions(components).items():
            probe_digest = content_digest(probe_definition)
            stored_probe_digest = repository.put("boundary_probe_definition", probe_digest, probe_definition)
            require(stored_probe_digest == probe_digest, "boundary probe definition identity changed")
            repository.review(probe_digest)
            probe_definition_digests[name] = probe_digest

        dependencies = dict(anchor.executable_dependencies)
        dependencies.update(runtime_dependencies())
        for path in (Path(__file__).resolve(), PRODUCER.resolve(), PROFILE.resolve(), SETUP_RESULT.resolve(),
                     SETUP_REVIEW.resolve(), Path(components["manifest_path"]).resolve()):
            dependencies[str(path)] = file_digest(path)
        request = anchor.model_copy(update={
            "plan_id": REQUEST_ID,
            "worker_digest": components["selected_worker_digest"],
            "definition_digests": [*anchor.definition_digests, *worker_records.values(), definition_digest,
                                   *probe_definition_digests.values()],
            "executable_dependencies": dependencies,
            "composed_model_turns": 0,
        })
        request_digest = repository.put("conformance_request", request.plan_id, request)
        repository.review(request_digest)
        repository.authorize(request)
        review = {
            "schema_version": "c-native-components-review.treatment.v1",
            "stage": "native_component_inspection",
            "source_digest": SOURCE,
            "driver_sha256": sha256(Path(__file__).resolve()),
            "producer_sha256": PRODUCER_SHA256,
            "profile_sha256": PROFILE_SHA256,
            "component_profile_digest": components["component_profile_digest"],
            "setup_result_sha256": SETUP_RESULT_SHA256,
            "setup_review_sha256": SETUP_REVIEW_SHA256,
            "manifest_sha256": components["manifest_digest"],
            "canonical_manifest_sha256": MAIN_MANIFEST_SHA256,
            "request_id": request.plan_id,
            "request_digest": request_digest,
            "definition_digest": definition_digest,
            "definition_id": DEFINITION_ID,
            "probe_definition_digests": probe_definition_digests,
            "expected_native_boundary": components["native_boundary_expected"],
            "expected_callback_lifecycle_partial": definition.expected_callback_lifecycle_partial,
            "cancellation_semantics_rationale": CANCELLATION_SEMANTICS_RATIONALE,
            "worker_digests": components["worker_digests"],
            "selected_worker_digest": components["selected_worker_digest"],
            "native_backend_digest": components["native_backend_digest"],
            "callback_document_digests": components["callback_document_digests"],
            "limits": {"max_operations": 1, "max_model_turns": 0, "max_elapsed_seconds": MAX_SECONDS,
                       "max_cash_usd": 0, "native_attempts": MAX_ATTEMPTS,
                       "native_attempt_seconds": ATTEMPT_SECONDS},
            "project": components["project"],
            "database_path": components["database_path"],
            "canary_path": components["canary_path"],
            "local_database_path": components["local_database_path"],
            "callback_requirement": components["callback_requirement"],
            "full_conformance": False,
            "execution_authorized": False,
            "result_path": str(RESULT_PATH),
        }
        if REVIEW_PATH.exists() or REVIEW_PATH.is_symlink():
            raise RuntimeError("native component review already exists; overwrite denied")
        write_json_exclusive(REVIEW_PATH, review)
        return {"review_path": str(REVIEW_PATH), "review_sha256": sha256(REVIEW_PATH),
                "request_id": request.plan_id, "request_digest": request_digest,
                "definition_digest": definition_digest, "execution_started": False}
    finally:
        asyncio.run(router.close())


def load_review(review_sha: str) -> dict:
    require(REVIEW_PATH.is_file() and not REVIEW_PATH.is_symlink(), "exact prepared review is absent or unsafe")
    review_bytes = REVIEW_PATH.read_bytes()
    require(hashlib.sha256(review_bytes).hexdigest() == review_sha,
            "prepared review SHA does not match supplied approval")
    review = json.loads(review_bytes)
    require(review.get("execution_authorized") is True, "exact review has not been authorized for execution")
    require(review.get("schema_version") == "c-native-components-review.treatment.v1"
            and review.get("request_id") == REQUEST_ID
            and review.get("definition_id") == DEFINITION_ID
            and review.get("cancellation_semantics_rationale") == CANCELLATION_SEMANTICS_RATIONALE
            and set(review.get("probe_definition_digests", {})) == {
                "native_boundary", "protected_state", "callback_lifecycle"},
            "review does not bind the fresh v2 request, definition and exact probe identifiers")
    require(review.get("source_digest") == SOURCE and review.get("driver_sha256") == sha256(Path(__file__).resolve()),
            "review does not bind the current frozen runner")
    require(review.get("profile_sha256") == PROFILE_SHA256 and sha256(PROFILE) == PROFILE_SHA256,
            "review does not bind the renewed component profile")
    require(review.get("producer_sha256") == PRODUCER_SHA256 and sha256(PRODUCER) == PRODUCER_SHA256,
            "review does not bind the current producer")
    require(review.get("setup_result_sha256") == SETUP_RESULT_SHA256 and sha256(SETUP_RESULT) == SETUP_RESULT_SHA256,
            "review does not bind the settled setup result")
    require(review.get("setup_review_sha256") == SETUP_REVIEW_SHA256 and sha256(SETUP_REVIEW) == SETUP_REVIEW_SHA256,
            "review does not bind the settled setup review")
    require(review.get("canonical_manifest_sha256") == MAIN_MANIFEST_SHA256
            and review.get("manifest_sha256") == NATIVE_MANIFEST_SHA256,
            "review does not bind the exact canonical and project manifests")
    require(review.get("limits") == {"max_operations": 1, "max_model_turns": 0,
                                     "max_elapsed_seconds": MAX_SECONDS, "max_cash_usd": 0,
                                     "native_attempts": MAX_ATTEMPTS,
                                     "native_attempt_seconds": ATTEMPT_SECONDS}
            and review.get("full_conformance") is False
            and review.get("result_path") == str(RESULT_PATH),
            "reviewed limits, result path or conformance claim changed")
    require(source_pin() == SOURCE, "frozen source pin changed")
    require(not RESULT_PATH.exists() and not RESULT_PATH.is_symlink(),
            "native component result already exists or is unsafe; blind retry denied")
    return review


async def execute(review_sha: str) -> dict:
    import psutil
    from datetime import timedelta

    from aeep.assessment.identity import file_digest, verify_dependencies
    from aeep.assessment.models import AssessmentLimits, ConformanceProbeRequest, content_digest
    from aeep.assessment.boundary import BoundaryProbe, BoundaryProbeDefinition
    from aeep.assessment.repository import AssessmentRepository
    from aeep.assessment.verification import verification_source_digest
    from aeep.assessment.fixed_helper import FixedHelperService
    from aeep.attempts import ExecutionAttempt
    from aeep.execution import EventJournal, persist_execution_events, start_execution
    from aeep.economic.prepared import executor_fingerprint
    from aeep.executors.command import CommandExecutor
    from aeep.models import (
        ExecutionReceipt, ExecutionStatus, ExecutorKind, ExecutorSpec, Manifest, RawExecution,
        PolicyConfig, FallbackConfig, SideEffect, TaskScope, utc_now,
    )
    from aeep.router import Router

    review = load_review(review_sha)
    components = load_components()
    require(verification_source_digest(ROOT) == SOURCE, "source changed before reservation")
    main_router, repository = open_main()
    local_router = None
    operation_id = "c-native-components:" + review["request_id"]
    request = ConformanceProbeRequest.model_validate(repository.get("conformance_request", review["request_id"]))
    require(content_digest(request) == review["request_digest"], "canonical request differs from reviewed request")
    require(review["definition_digest"] in request.definition_digests,
            "request omits its reviewed native component definition")
    expected_probe_definitions = boundary_probe_definitions(components)
    probe_definition_digests = review["probe_definition_digests"]
    require(set(probe_definition_digests) == set(expected_probe_definitions)
            and all(digest in request.definition_digests for digest in probe_definition_digests.values()),
            "request omits an exact reviewed native component probe definition")
    for name, expected_definition in expected_probe_definitions.items():
        actual_definition = BoundaryProbeDefinition.model_validate(
            repository.get("boundary_probe_definition", probe_definition_digests[name]))
        require(content_digest(actual_definition) == probe_definition_digests[name]
                and actual_definition.model_dump(mode="json") == expected_definition.model_dump(mode="json"),
                "reviewed boundary probe definition differs from the exact component observations")
    repository.authorize(request)
    verify_dependencies(request.executable_dependencies)
    started = time.perf_counter()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + MAX_SECONDS
    limits = AssessmentLimits(max_operations=1, max_model_turns=0,
                              max_elapsed_seconds=MAX_SECONDS, max_cash_usd=0)
    repository.reserve(request, operation_id, limits, stage="native_component_inspection")
    operation_start = repository.get("operation_start", operation_id)
    require(operation_start.get("operation_id") == operation_id,
            "native component request lacks its exact reserved parent operation")
    charged_operation_digest = content_digest(operation_start)
    record = {
        "schema_version": "c-native-components-result.treatment.v1",
        "request_id": request.plan_id,
        "operation_id": operation_id,
        "review_sha256": review_sha,
        "source_digest": SOURCE,
        "model_turns": 0,
        "native_attempts": 0,
        "observations": {},
        "attempt_digests": [],
        "receipt_digests": [],
        "receipt_resources": [],
        "execution_evidence_digests": [],
        "execution_evidence_receipt_ids": [],
        "cleanup_confirmed": False,
        "host_callback_observed": False,
        "full_conformance": False,
        "boundary_probes_complete": False,
        "whole_system_cost_complete": False,
        "resource_totals_complete": False,
        "accounting_status": "raw child receipts retained separately; no aggregate accounting inferred",
        "resource_claim": "receipt values are retained as serialized; default zero fields do not establish zero consumption",
        "accounting_scope": "operation start through local native router close; canonical settlement/report writing excluded",
    }
    owned: list[psutil.Process] = []
    pending: asyncio.Task | None = None
    local_repository = None
    cancel_stdout = bytearray()
    action_deadline = deadline - 5.0

    def retain_local_records() -> None:
        if local_router is None or local_repository is None:
            return
        with local_router.store._lock:
            attempt_rows = [json.loads(row[0]) for row in local_router.store._connection.execute(
                "SELECT payload_json FROM execution_attempts ORDER BY rowid LIMIT 3")]
            receipt_rows = [json.loads(row[0]) for row in local_router.store._connection.execute(
                "SELECT payload_json FROM receipts ORDER BY rowid LIMIT 3")]
        require(len(attempt_rows) <= MAX_ATTEMPTS and len(receipt_rows) <= MAX_ATTEMPTS,
                "native child records exceed the reviewed attempt cap")
        attempts = [ExecutionAttempt.model_validate(value) for value in attempt_rows]
        receipts = [ExecutionReceipt.model_validate(value) for value in receipt_rows]
        record["native_attempts"] = len(attempts)
        for attempt in attempts:
            digest = content_digest(attempt)
            if digest not in record["attempt_digests"]:
                record["attempt_digests"].append(repository.put("native_component_attempt", digest, attempt))
        recorded_receipts = {item["receipt_id"] for item in record.get("receipt_resources", [])}
        for receipt in receipts:
            if receipt.receipt_id not in recorded_receipts:
                digest = content_digest(receipt)
                retained_receipt_digest = repository.put("native_component_receipt", digest, receipt)
                record["receipt_digests"].append(retained_receipt_digest)
                record.setdefault("receipt_by_executor", {})[receipt.executor_id] = retained_receipt_digest
                record.setdefault("receipt_resources", []).append({
                    "receipt_id": receipt.receipt_id,
                    "executor_id": receipt.executor_id,
                    "status": receipt.status.value,
                    "resources": receipt.actual_resources.model_dump(mode="json"),
                    "accounting": receipt.accounting.model_dump(mode="json"),
                })
                evidence_digest = receipt.metadata.get("execution_evidence_digest")
                if isinstance(evidence_digest, str):
                    evidence = local_repository.get("execution_evidence", evidence_digest)
                    from aeep.execution import ExecutionEvidence
                    evidence_model = ExecutionEvidence.model_validate(evidence)
                    stored = repository.put("execution_evidence", evidence_model.digest(), evidence_model)
                    record["execution_evidence_digests"].append(stored)
                    record.setdefault("execution_evidence_by_executor", {})[receipt.executor_id] = stored
                    record["execution_evidence_receipt_ids"].append(receipt.receipt_id)
                elif receipt.executor_id == components["components"]["guard"]["spec"]["id"]:
                    record["guard_execution_evidence_missing"] = True
            if receipt.metadata.get("enforcement_backend_digest") == components["native_backend_digest"]:
                record.setdefault("native_backend_receipt_executor_ids", []).append(receipt.executor_id)

    def observe(chunk: bytes) -> None:
        buffer = cancel_stdout
        if len(buffer) < 512:
            buffer.extend(chunk[:512 - len(buffer)])
        if record.get("ready_observation") is not None or b"\n" not in buffer:
            return
        stage = "decode_readiness"
        chain_summary = []
        candidate_summary = []
        try:
            first = bytes(buffer).split(b"\n", 1)[0]
            value = json.loads(first)
            pid = value.get("pid")
            require(value.get("native_component_ready") is True and type(pid) is int and pid > 1,
                    "cancel readiness line is not the pinned literal observation")
            stage = "inspect_owned_process_chain"
            target = psutil.Process(pid)
            chain = target.parents()
            for item in [target, *chain][:8]:
                try:
                    chain_summary.append({"pid": item.pid, "ppid": item.ppid()})
                except psutil.Error as exc:
                    chain_summary.append({"pid": item.pid, "identity_error_type": type(exc).__name__})
            record["observer_process_chain"] = chain_summary
            binary = Path(components["native_config"]["binary"]).resolve()
            servers = []
            for item in chain:
                parent_pid = item.ppid()
                if parent_pid != os.getpid():
                    continue
                candidate = {"pid": item.pid, "ppid": parent_pid}
                candidate_summary.append(candidate)
                # Only inspect executable identity after proving the process is
                # the direct child of this supervisor. Ancestors may be protected.
                executable = item.exe()
                candidate["executable_name"] = Path(executable).name[:96]
                candidate["matches_native_binary"] = Path(executable).resolve() == binary
                if candidate["matches_native_binary"]:
                    servers.append(item)
            record["observer_direct_child_candidates"] = candidate_summary[:2]
            stage = "verify_owned_session"
            require(pid == os.getpgid(pid) == os.getsid(pid) and len(servers) == 1,
                    "cancel readiness process is not the owned native session")
            owned.append(target)
            for item in chain:
                owned.append(item)
                if item == servers[0]:
                    break
            record["ready_observation"] = {
                "line_digest": hashlib.sha256(first).hexdigest(),
                "pid": pid,
                "processes": [{"pid": item.pid, "created_at": item.create_time(), "name": item.name()}
                              for item in owned],
            }
        except Exception as exc:
            message = " ".join(str(exc).split())[:200]
            record["observer_error"] = {
                "stage": stage,
                "type": type(exc).__name__,
                "message": message,
                "message_sha256": hashlib.sha256(message.encode()).hexdigest(),
                "process_chain": chain_summary[:8],
                "direct_child_candidates": candidate_summary[:2],
            }
            raise

    try:
        async with asyncio.timeout_at(action_deadline):
            scopes = {}
            specs = {name: ExecutorSpec.model_validate(components["components"][name]["spec"])
                     for name in ("guard", "cancel")}
            database = Path(components["local_database_path"])
            canary = Path(components["canary_path"])
            require(not database.exists() and not database.is_symlink(), "fresh local component store already exists")
            require(not canary.exists() and not canary.is_symlink(), "private canary already exists")
            from aeep.assessment.models import content_digest as local_digest

            class ObservedNativeExecutor(CommandExecutor):
                async def start(self, context):
                    async def run(journal):
                        raw = await self.execute(context)
                        if raw.status == ExecutionStatus.SUCCESS and isinstance(raw.output, dict):
                            journal.append("artifact.created", "native-component-output",
                                            evidence_ref=content_digest(raw.output))
                        journal.append(
                            "execution.completed" if raw.status == ExecutionStatus.SUCCESS else "execution.failed",
                            "terminal",
                        )
                        evidence = journal.evidence(self.capabilities().adapter, raw)
                        raw.metadata["execution_evidence"] = evidence.model_dump(mode="json")
                        return raw

                    return start_execution(context.attempt_id or context.request.action_id,
                                           self.capabilities().adapter, run)

            def new_local_router(observer=None):
                child = Router(
                    Manifest(database=str(database), executors=list(specs.values()), policies={
                        "balanced": PolicyConfig(fallback=FallbackConfig(enabled=False, max_attempts=1))}),
                    manifest_path=Path(components["project"]) / "aeep.json",
                    executor_overrides={ExecutorKind.COMMAND: ObservedNativeExecutor(stdout_observer=observer)},
                )
                child._trial_check = check_reserved
                child._trial_deadline = action_deadline
                return child

            def check_reserved() -> None:
                repository.authorize(request)
                verify_dependencies(request.executable_dependencies)
                with repository.store._lock:
                    row = repository.store._connection.execute(
                        "SELECT state FROM assessment_operations WHERE id=?", (operation_id,)).fetchone()
                require(row is not None and row[0] == "reserved" and loop.time() < deadline,
                        "outer native component reservation/deadline unavailable")

            def bind_service(router, local_repository, name, spec):
                scope = TaskScope(
                    scope_id=f"c-native-component-{request.plan_id}-{name}",
                    project_root=str(Path(components["project"]).resolve()),
                    executor_fingerprints={spec.id: executor_fingerprint(spec)},
                    approval_ceiling=SideEffect.READ,
                    max_attempts=1,
                    max_attempt_seconds=ATTEMPT_SECONDS,
                    expires_at=utc_now() + timedelta(minutes=5),
                )
                scope_digest = local_repository.put("task_scope", scope.scope_id, scope)
                local_repository.review(scope_digest)
                router.bind_task_scope(scope.scope_id)

                def check_scope(expected_scope_digest: str = scope_digest, expected_scope: TaskScope = scope,
                                selected=spec) -> str:
                    check_reserved()
                    actual = TaskScope.model_validate(local_repository.get("task_scope", expected_scope.scope_id))
                    require(local_digest(actual) == expected_scope_digest, "native task scope changed")
                    router._require_active_spec(selected)
                    return expected_scope_digest

                return FixedHelperService(
                    router, spec.id, task_scope=scope.scope_id,
                    declaration={"name": f"fixed_{name}", "description": "Fixed reviewed native component",
                                 "inputSchema": spec.input_schema},
                    check=check_scope,
                )

            local_router = new_local_router()
            local_repository = AssessmentRepository(local_router.store)
            scopes["guard"] = bind_service(local_router, local_repository, "guard", specs["guard"])
            canary.write_text("c-native-component-private-canary\n")
            canary_digest = file_digest(canary)
            database_path = Path(components["database_path"])
            database_digest = file_digest(database_path)
            guard_service = scopes["guard"]
            guard_result = await guard_service.call("fixed_guard", components["components"]["guard"]["input"])
            guard_payload = guard_result.get("structuredContent")
            require(isinstance(guard_payload, dict) and guard_payload.get("status") == "success",
                    "guard native fixed-helper call failed")
            observed = guard_payload.get("output")
            require(observed == components["native_boundary_expected"],
                    "actual native guard observations differ from the reviewed boundary")
            require(file_digest(canary) == canary_digest and file_digest(database_path) == database_digest,
                    "protected native canary or database changed")
            record["observations"]["native_boundary"] = observed
            record["protected_state"] = {
                "canary_sha256_before_after": [canary_digest, file_digest(canary)],
                "project_database_sha256_before_after": [database_digest, file_digest(database_path)],
            }
            record["protected_state_unchanged"] = True
            record["observations"]["protected_state"] = {
                "private_denied": observed["private_denied"],
                "database_denied": observed["database_denied"],
                "witness_unchanged": True,
            }
            retain_local_records()

            await local_router.close()
            local_router = None
            local_router = new_local_router(observer=observe)
            local_repository = AssessmentRepository(local_router.store)
            scopes["cancel"] = bind_service(local_router, local_repository, "cancel", specs["cancel"])
            cancel_task = asyncio.create_task(
                scopes["cancel"].call("fixed_cancel", components["components"]["cancel"]["input"]))
            pending = cancel_task
            while record.get("ready_observation") is None and not cancel_task.done():
                await asyncio.sleep(0.01)
            require(record.get("ready_observation") is not None and not cancel_task.done(),
                    "independent native cancellation readiness was not observed")
            cancel_task.cancel()
            try:
                cancel_result = await cancel_task
            except asyncio.CancelledError:
                record["cancel_task_cancelled_exception_propagated"] = True
                raise RuntimeError("fixed helper propagated cancellation instead of returning the native timeout")
            pending = None
            cancel_payload = cancel_result.get("structuredContent") if isinstance(cancel_result, dict) else None
            require(cancel_result.get("isError") is True if isinstance(cancel_result, dict) else False,
                    "fixed helper did not report its timeout outcome as an error")
            require(isinstance(cancel_payload, dict)
                    and cancel_payload.get("ok") is False
                    and cancel_payload.get("status") == ExecutionStatus.TIMEOUT.value,
                    "fixed helper did not return the pinned TIMEOUT contract")
            record["cancel_helper_response"] = {
                "is_error": cancel_result.get("isError") is True,
                "status": cancel_payload["status"],
                "ok": cancel_payload["ok"],
            }
            end = min(deadline, loop.time() + 2.0)
            def process_alive(item):
                try:
                    return item.is_running() and item.status() != psutil.STATUS_ZOMBIE
                except psutil.NoSuchProcess:
                    return False
                except psutil.Error:
                    return True

            while any(process_alive(item) for item in owned) and loop.time() < end:
                await asyncio.sleep(0.02)
            processes_gone = not any(process_alive(item) for item in owned)
            retain_local_records()
            attempts = [ExecutionAttempt.model_validate(repository.get("native_component_attempt", digest))
                        for digest in record["attempt_digests"]]
            cancel_attempts = [attempt for attempt in attempts if attempt.executor_id == specs["cancel"].id]
            cancel_receipts = [entry for entry in record.get("receipt_resources", [])
                               if entry["executor_id"] == specs["cancel"].id]
            require(len(cancel_attempts) == 1 and cancel_attempts[0].state.value == "FAILED"
                    and cancel_attempts[0].retry_eligible is True
                    and cancel_attempts[0].idempotent is True
                    and cancel_attempts[0].side_effect is SideEffect.READ,
                    "native cancellation did not produce the expected idempotent READ failure state")
            require(len(cancel_receipts) == 1 and cancel_receipts[0]["status"] == ExecutionStatus.TIMEOUT.value,
                    "native cancellation timeout receipt is absent or differs")
            require(specs["cancel"].idempotent is True and specs["cancel"].side_effect is SideEffect.READ,
                    "native cancellation probe is no longer an idempotent READ")
            require(len(record["attempt_digests"]) == MAX_ATTEMPTS
                    and len(record["receipt_digests"]) == MAX_ATTEMPTS,
                    "native component attempts/receipts are not the exact bounded pair")
            record["observations"]["callback_lifecycle"] = {
                "cancel_requested": True,
                "fixed_helper_returned_timeout": True,
                "timeout_receipt_persisted": True,
                "read_attempt_failed_retry_eligible": True,
                "single_cancel_attempt": len(cancel_attempts) == 1,
                "ready_line_observed": True,
                "owned_non_zombie_processes_gone": processes_gone,
                "host_eof_observed": False,
            }
            record["cleanup_confirmed"] = processes_gone
            require(processes_gone, "owned native process remains after cancellation")
            record["supervisor_probe_digests"] = {}
            child_receipts = record.get("receipt_by_executor", {})
            child_evidence = record.get("execution_evidence_by_executor", {})
            supervisor_sources = {
                "native_boundary": (specs["guard"].id,),
                "protected_state": (specs["guard"].id,),
                "callback_lifecycle": (specs["cancel"].id,),
            }
            for probe_name, probe_definition_digest in probe_definition_digests.items():
                expected_probe = expected_probe_definitions[probe_name]
                if probe_name == "native_boundary":
                    probe_observed = {key: observed[key] for key in expected_probe.expected}
                elif probe_name == "protected_state":
                    probe_observed = record["observations"]["protected_state"]
                else:
                    probe_observed = record["observations"]["callback_lifecycle"]
                require(probe_observed == expected_probe.expected,
                        "actual observation differs from its predeclared boundary probe")
                child_executor_ids = supervisor_sources[probe_name]
                child_receipt_refs = [child_receipts[executor_id] for executor_id in child_executor_ids]
                child_evidence_refs = [child_evidence[executor_id] for executor_id in child_executor_ids
                                       if executor_id in child_evidence]
                require(len(child_receipt_refs) == len(child_executor_ids),
                        "supervisor probe lacks retained actual child receipt linkage")
                if probe_name != "callback_lifecycle":
                    require(child_evidence_refs,
                            "successful native probe lacks retained child execution evidence")
                attempt_id = f"c-native-supervisor-{request.plan_id}-{probe_name}"
                with persist_execution_events(lambda journal_id, event: repository.put(
                        "execution_event", journal_id + ":" + str(event.sequence), event)):
                    journal = EventJournal(attempt_id)
                    journal.append("execution.started", "supervisor.started")
                    for index, child_ref in enumerate(child_receipt_refs):
                        journal.append("artifact.created", f"child-receipt-{index}", evidence_ref=child_ref)
                    for index, child_ref in enumerate(child_evidence_refs):
                        journal.append("artifact.created", f"child-evidence-{index}", evidence_ref=child_ref)
                    journal.append("artifact.created", "observed-probe", evidence_ref=content_digest(probe_observed))
                    journal.append("execution.completed", "supervisor.terminal")
                    supervisor_raw = RawExecution(
                        status=ExecutionStatus.SUCCESS,
                        output=probe_observed,
                        metadata={"boundary_digest": request.worker_digest,
                                  "supervised_child_receipt_digests": child_receipt_refs,
                                  "supervised_child_evidence_digests": child_evidence_refs},
                    )
                    supervisor_evidence = journal.evidence("c_native_component_supervisor", supervisor_raw)
                require(supervisor_evidence.complete and supervisor_evidence.boundary_digest == request.worker_digest,
                        "supervisor evidence does not bind a complete successful observation to the selected worker")
                supervisor_evidence_digest = repository.put(
                    "execution_evidence", supervisor_evidence.digest(), supervisor_evidence)
                probe = BoundaryProbe(
                    schema_version="assessment.boundary-probe.v2",
                    probe_id=f"probe_{request.plan_id}_{probe_name}",
                    name=probe_name,
                    implementation_digest=probe_definition_digest,
                    worker_digest=request.worker_digest,
                    execution_evidence_digest=supervisor_evidence_digest,
                    observed=probe_observed,
                    charged_operation_digest=charged_operation_digest,
                )
                stored_probe_digest = repository.put("boundary_probe", probe.probe_id, probe)
                require(stored_probe_digest == content_digest(probe), "stored supervisor probe digest differs")
                record["supervisor_probe_digests"][probe_name] = stored_probe_digest
                record.setdefault("probe_child_receipt_digests", {})[probe_name] = child_receipt_refs
                record.setdefault("probe_child_evidence_digests", {})[probe_name] = child_evidence_refs
            record["boundary_probes_complete"] = len(record["supervisor_probe_digests"]) == 3
    except BaseException as exc:
        record["error_type"] = type(exc).__name__
        record["error_sha256"] = hashlib.sha256(str(exc).encode()).hexdigest()
    finally:
        if pending is not None and not pending.done():
            pending.cancel()
            try:
                async with asyncio.timeout_at(deadline):
                    await asyncio.gather(pending, return_exceptions=True)
            except BaseException:
                record["cancel_cleanup_unresolved"] = True
        if local_router is not None:
            try:
                retain_local_records()
            except BaseException as exc:
                record["retention_error_type"] = type(exc).__name__
            try:
                async with asyncio.timeout_at(deadline):
                    await local_router.close()
            except BaseException as exc:
                record["cleanup_confirmed"] = False
                record["local_close_error_type"] = type(exc).__name__
        record["elapsed_seconds"] = time.perf_counter() - started
        try:
            record["source_unchanged"] = verification_source_digest(ROOT) == SOURCE
        except BaseException as exc:
            record["source_unchanged"] = False
            record["source_check_error_type"] = type(exc).__name__
        record["operation_settled"] = False
        try:
            repository.finish_operation(operation_id, elapsed_seconds=record["elapsed_seconds"])
            record["operation_settled"] = True
        except BaseException as exc:
            record["settlement_error_type"] = type(exc).__name__
        record["result_status"] = "pass" if (
            record.get("cleanup_confirmed") is True and record.get("operation_settled") is True
            and record.get("source_unchanged") is True and not record.get("error_type")
            and record.get("native_attempts") == MAX_ATTEMPTS
            and components["components"]["guard"]["spec"]["id"]
            in record.get("native_backend_receipt_executor_ids", [])
            and record.get("guard_execution_evidence_missing") is not True
            and not record.get("retention_error_type")
            and len(record.get("execution_evidence_receipt_ids", [])) >= 1
            and len(record.get("attempt_digests", [])) == MAX_ATTEMPTS
            and len(record.get("receipt_digests", [])) == MAX_ATTEMPTS
            and record.get("observations", {}).get("native_boundary") == components["native_boundary_expected"]
            and record.get("observations", {}).get("callback_lifecycle", {}).get(
                "read_attempt_failed_retry_eligible") is True
            and record.get("boundary_probes_complete") is True
            and set(record.get("supervisor_probe_digests", {})) == {
                "native_boundary", "protected_state", "callback_lifecycle"}
        ) else "fail"
        record["main_close_confirmed"] = False
        try:
            async with asyncio.timeout_at(deadline):
                await main_router.close()
            record["main_close_confirmed"] = True
        except BaseException as exc:
            record["main_close_error_type"] = type(exc).__name__
            record["result_status"] = "fail"
        if RESULT_PATH.exists() or RESULT_PATH.is_symlink():
            record["result_status"] = "fail"
            raise RuntimeError("result appeared during one-shot operation; preserved")
        write_json_exclusive(RESULT_PATH, record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "execute"))
    parser.add_argument("--review-sha")
    args = parser.parse_args()
    if args.mode == "prepare":
        result = prepare()
    else:
        require(isinstance(args.review_sha, str) and len(args.review_sha) == 64,
                "execute requires the exact prepared review SHA")
        result = asyncio.run(execute(args.review_sha))
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
