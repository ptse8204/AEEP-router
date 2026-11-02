"""Selected Cisco scanning through the existing container executor and ledger."""

from __future__ import annotations

import asyncio
import base64
import inspect as python_inspect
import json
import re
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentSubject,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.execution import ExecutionEvidence, persist_execution_events
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import (
    ActionRequest,
    ExecutionReceipt,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    RawExecution,
    ResourceVector,
    SideEffect,
    StrictModel,
    utc_now,
)

from .candidate import CandidatePayload, inspect
from .models import Digest
from .scanner_worker import SCANNER_ARTIFACT, SCANNER_VERSION, SOURCE_REVISION
from .workflow import StackWorkflow, _read
from .workflow_accounting import account_workflow


class ScannerRuntimeDefinition(StrictModel):
    schema_version: Literal["aeep.toolkit.scanner-runtime.v1"] = "aeep.toolkit.scanner-runtime.v1"
    source_revision: Literal["c3d7fd9fee50cf2ea45f0b381eb61f857360f825"] = (
        "c3d7fd9fee50cf2ea45f0b381eb61f857360f825"
    )
    environment: AssessmentEnvironment
    request: RecipeMaterializationRequest
    candidate_sha256: Digest
    worker_sha256: Digest
    executable_dependencies: dict[str, Digest] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(default=125, strict=True, ge=1, le=300)

    @model_validator(mode="after")
    def offline_existing_runtime(self) -> ScannerRuntimeDefinition:
        env = self.environment
        if (
            env.kind != "container"
            or env.network
            or env.read_only_roots
            or not re.fullmatch(r"sha256:[a-f0-9]{64}", env.container_image or "")
            or env.container_runtime is None
            or env.container_socket is None
            or content_digest(env) != self.request.environment_digest
        ):
            raise ValueError(
                "scanner requires an exact offline container and matching existing execution scope"
            )
        return self


class WorkflowScanRecord(StrictModel):
    schema_version: Literal["aeep.toolkit.workflow-scan.v1"] = "aeep.toolkit.workflow-scan.v1"
    definition_ref: Digest
    implementation_source: Digest
    candidate_sha256: Digest
    environment_digest: Digest
    wrapper_operation_id: str
    operation_id: str
    request_plan_id: str
    authorization_id: str
    receipt_ref: Digest
    execution_evidence_ref: Digest
    observations: dict[str, Any]
    cleanup_verified: bool


async def _docker(environment: AssessmentEnvironment, *args: str) -> tuple[int, bytes]:
    spec = ExecutorSpec(
        id="toolkit.container-ownership",
        capability="toolkit.container-ownership@1",
        kind=ExecutorKind.COMMAND,
        side_effect=SideEffect.READ,
        description="Inspect or stop only the identified owned scan container",
        config={
            "argv": [
                str(environment.container_runtime),
                "--host",
                f"unix://{environment.container_socket}",
                *args,
            ],
            "argv_literal": True,
            "inherit_env": False,
            "timeout_seconds": 10,
            "max_output_bytes": 500_000,
            "output": {"type": "text"},
        },
    )
    request = ActionRequest(capability=spec.capability)
    executor = CommandExecutor()
    try:
        raw = await executor.execute(
            ExecutionContext(
                request=request,
                spec=spec,
                estimate=spec.estimate,
                attempt=1,
                approved_side_effect=SideEffect.READ,
            )
        )
    finally:
        await executor.close()
    if raw.exit_code is None:
        raise ConfigurationError("container ownership check has no terminal exit status")
    return raw.exit_code, ((raw.stdout or "") + (raw.stderr or "")).encode()


class ScanContainerExecutor(ContainerExecutor):
    """Reuse containment; clean up only a proven owned container by immutable ID."""

    cleanup_verified = False

    def __init__(self, environment: AssessmentEnvironment, *, runtime_digest: str) -> None:
        super().__init__(environment)
        self.runtime_digest = runtime_digest

    async def checked_docker(self, *arguments: str) -> tuple[int, bytes]:
        if file_digest(Path(str(self.environment.container_runtime))) != self.runtime_digest:
            raise ConfigurationError("reviewed container runtime changed")
        return await _docker(self.environment, *arguments)

    def command(self, context: ExecutionContext) -> tuple[list[str], str]:
        argv, name = super().command(context)
        # Keep the established container protocol and narrow its automatic
        # runtime mount to the two AEEP packages, excluding adjacent host files.
        source_file = python_inspect.getsourcefile(ContainerExecutor)
        if source_file is None:
            raise ConfigurationError("container executor source is unavailable")
        source_root = Path(source_file).resolve().parents[2]
        original_mount = f"type=bind,src={source_root},dst={source_root},readonly"
        index = argv.index(original_mount)
        replacement = []
        for package in ("aeep", "aeep_toolkit"):
            path = source_root / package
            if not path.is_dir() or path.is_symlink() or path.resolve() != path:
                raise ConfigurationError(
                    "component source mounts must be exact package directories"
                )
            replacement.extend(["--mount", f"type=bind,src={path},dst={path},readonly"])
        argv[index - 1 : index + 1] = replacement
        # Reuse the already-reviewed scanner environment's Python dependencies.
        argv[argv.index("--entrypoint") + 1] = "/opt/aeep-scanner/bin/python"
        index = argv.index("run") + 1
        argv[index:index] = ["--label", "aeep.workflow-scan=" + str(context.attempt_id)]
        return argv, name

    async def execute(self, context: ExecutionContext) -> RawExecution:
        identity = context.attempt_id or context.request.action_id
        status, output = await self.checked_docker("container", "inspect", container_name(identity))
        if status == 0 or b"No such" not in output:
            raise ConfigurationError(
                "scan container name is not proven absent; preserve existing work"
            )
        return await super().execute(context)

    async def cleanup(self, attempt_id: str) -> bool:
        self.cleanup_verified = False
        try:
            status, output = await self.checked_docker(
                "container", "inspect", container_name(attempt_id)
            )
            if status != 0:
                self.cleanup_verified = b"No such" in output
                return self.cleanup_verified
            found = json.loads(output)[0]
            if (
                found["Image"] != self.environment.container_image
                or found["Config"].get("Labels", {}).get("aeep.workflow-scan") != attempt_id
            ):
                return False
            identity = found["Id"]
            if found["State"]["Running"]:
                status, _ = await self.checked_docker("stop", "--time", "1", identity)
                if status != 0:
                    return False
            status, output = await self.checked_docker("container", "inspect", identity)
            if status != 0:
                self.cleanup_verified = b"No such" in output
                return self.cleanup_verified
            current = json.loads(output)[0]
            if current["Id"] != identity or current["State"]["Running"]:
                return False
            status, _ = await self.checked_docker("rm", identity)
            self.cleanup_verified = status == 0
            return self.cleanup_verified
        except (OSError, ValueError, KeyError, TimeoutError, ConfigurationError):
            return False


def scan_spec(definition: ScannerRuntimeDefinition) -> ExecutorSpec:
    return ExecutorSpec(
        id="toolkit.static-scan",
        capability="toolkit.static-scan@1",
        kind=ExecutorKind.COMMAND,
        description="Selected candidate static scan in the reviewed existing offline image",
        side_effect=SideEffect.READ,
        idempotent=True,
        config={
            "argv": [
                "/opt/aeep-scanner/bin/python",
                "-I",
                "-B",
                str(Path(__file__).with_name("scanner_worker.py").resolve()),
                "--workspace",
                "/tmp",
            ],
            "argv_literal": True,
            "stdin_json": True,
            "max_stdin_bytes": 12_000_000,
            "max_output_bytes": 1_000_000,
            "timeout_seconds": definition.timeout_seconds,
            "output": {"type": "json"},
        },
    )


def scan_preview(
    workflow_file: Path, configuration: str
) -> tuple[dict[str, Any], ScannerRuntimeDefinition, CandidatePayload]:
    from .cli import read_json

    workflow = StackWorkflow.model_validate(read_json(workflow_file))
    selected = workflow.configurations[configuration]
    if selected.scanner is None or "skill-scanner" not in selected.components:
        raise ConfigurationError("explicit selected scanner and exact runtime binding are required")
    root = workflow_file.absolute().parent
    _, data = _read(selected.scanner, root)
    definition = ScannerRuntimeDefinition.model_validate_json(data)
    candidate_path = Path(selected.candidate.path)
    candidate = inspect(candidate_path if candidate_path.is_absolute() else root / candidate_path)
    if (
        candidate.sha256 != selected.candidate.sha256
        or candidate.sha256 != definition.candidate_sha256
    ):
        raise ConfigurationError(
            "scanner candidate bytes differ from the reviewed workflow/runtime"
        )
    worker = Path(__file__).with_name("scanner_worker.py").resolve()
    import hashlib

    if hashlib.sha256(worker.read_bytes()).hexdigest() != definition.worker_sha256:
        raise ConfigurationError("static scanner worker source changed")
    required = {str(worker), str(Path(str(definition.environment.container_runtime)).resolve())}
    if not required <= definition.executable_dependencies.keys() or Path(
        str(definition.environment.container_runtime)
    ).resolve() != Path(str(definition.environment.container_runtime)):
        raise ConfigurationError(
            "scanner requires canonical runtime and worker dependency fingerprints"
        )
    verify_dependencies(definition.executable_dependencies)
    from .installation import PreviewPolicy, preview
    from .models import ExtensionRegistry

    _, registry_data = _read(workflow.registry, root)
    _, policy_data = _read(workflow.policy, root)
    registry = ExtensionRegistry.model_validate_json(registry_data)
    policy = PreviewPolicy.model_validate_json(policy_data)
    component = registry.get("skill-scanner")
    if (
        component.source.revision != definition.source_revision
        or definition.source_revision != SOURCE_REVISION
    ):
        raise ConfigurationError("selected scanner source differs from the runtime")
    permissions = preview(registry, ("skill-scanner",), policy, profile="full")
    if permissions.blockers:
        raise ConfigurationError("selected scanner dependency or permission policy is unresolved")
    source = verification_source_digest(Path(__file__).resolve().parents[2])
    proposed = scan_spec(definition)
    action = ActionRequest(action_id="workflow-static-scan-preview", capability=proposed.capability)
    command, _ = ScanContainerExecutor(
        definition.environment,
        runtime_digest=definition.executable_dependencies[
            str(definition.environment.container_runtime)
        ],
    ).command(
        ExecutionContext(
            request=action,
            spec=proposed,
            estimate=proposed.estimate,
            attempt=1,
            attempt_id="workflow-static-scan-preview",
            approved_side_effect=SideEffect.READ,
        )
    )
    facts = {
        "definition": definition.model_dump(mode="json"),
        "definition_ref": content_digest(definition),
        "candidate": candidate.describe(),
        "implementation_source": source,
        "environment": definition.environment.model_dump(mode="json"),
        "executor": proposed.model_dump(mode="json"),
        "container_command_template": command,
        "installation": permissions.model_dump(mode="json"),
    }
    return (
        {
            **facts,
            "review_sha256": content_digest(facts),
            "execution_authorized": False,
            "functional_readiness": "NOT_VERIFIED_BY_PREVIEW",
            "safety_verdict": "NOT_ESTABLISHED",
        },
        definition,
        candidate,
    )


def _authorize(
    repository: AssessmentRepository,
    definition: ScannerRuntimeDefinition,
    candidate: CandidatePayload,
    *,
    execution: bool = True,
) -> RecipeMaterializationRequest:
    ref = content_digest(definition)
    stored = ScannerRuntimeDefinition.model_validate(repository.get("toolkit_scanner_runtime", ref))
    if stored != definition:
        raise ConfigurationError("scanner runtime differs from its stored exact definition")
    request = definition.request.model_copy(
        update={
            "definition_digests": list(dict.fromkeys([*definition.request.definition_digests, ref]))
        }
    )
    subject = AssessmentSubject.model_validate(repository.get("subject", request.subject_digest))
    environment = AssessmentEnvironment.model_validate(
        repository.get("environment", request.environment_digest)
    )
    if (
        subject.dependency_digests != candidate.describe()["files"]
        or environment != definition.environment
    ):
        raise ConfigurationError("scanner scope does not bind this actual subject and environment")
    if execution:
        repository.authorize(request)
    else:
        with repository.store._lock:
            row = repository.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (ref,)
            ).fetchone()
        if row is None or row[0]:
            raise ConfigurationError("selected scanner runtime review is absent or revoked")
    verify_dependencies(definition.executable_dependencies)
    return request


def _observations(
    value: Any, definition: ScannerRuntimeDefinition, candidate: CandidatePayload, source: str
) -> dict[str, Any]:
    if (
        not isinstance(value, dict)
        or value.get("component") != "skill-scanner"
        or value.get("source_revision") != definition.source_revision
        or value.get("implementation_source") != source
        or value.get("mode") != "upstream_functional"
        or value.get("scanner_version") != SCANNER_VERSION
        or value.get("scanner_artifact_sha256") != SCANNER_ARTIFACT
        or type(value.get("scanner_source_files_verified")) is not int
        or value["scanner_source_files_verified"] < 1
        or value.get("check") != "static_scan"
        or value.get("candidate_sha256") != candidate.sha256
        or value.get("candidate_bytes_bound") is not True
        or value.get("safety_verdict") != "NOT_ESTABLISHED"
        or type(value.get("analyzers_executed")) is not int
        or value["analyzers_executed"] < 1
        or not isinstance(value.get("findings"), list)
        or type(value.get("findings_count")) is not int
        or value.get("findings_count") != len(value["findings"])
        or not isinstance(value.get("analyzer_failures"), list)
        or type(value.get("failed_analyzers")) is not int
        or value.get("failed_analyzers") != len(value["analyzer_failures"])
        or not isinstance(value.get("analyzers_used"), list)
        or len(value["analyzers_used"]) != value["analyzers_executed"]
        or not all(
            isinstance(name, str) and re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", name)
            for name in value["analyzers_used"]
        )
        or not isinstance(value.get("upstream_report_sha256"), str)
        or not re.fullmatch(r"[a-f0-9]{64}", value["upstream_report_sha256"])
    ):
        raise ConfigurationError("scanner result has incomplete candidate/analyzer/source evidence")
    # The reviewed scanner worker already omits snippets and diagnostic text.
    # Validate the allowlist again before persisting any child-controlled fields.
    allowed = {"id", "rule_id", "category", "severity", "analyzer", "line_number"}
    for finding in value["findings"]:
        if (
            not isinstance(finding, dict)
            or not set(finding) <= allowed
            or finding.get("severity") not in {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO", "SAFE"}
            or any(
                value is not None
                and (
                    not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", value)
                )
                for key, value in finding.items()
                if key != "line_number"
            )
            or (
                finding.get("line_number") is not None
                and (type(finding["line_number"]) is not int or finding["line_number"] < 0)
            )
        ):
            raise ConfigurationError("scanner result contains unreviewed finding data")
    for failure in value["analyzer_failures"]:
        if (
            not isinstance(failure, dict)
            or set(failure) != {"analyzer", "diagnostic_sha256"}
            or not isinstance(failure.get("analyzer"), str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,200}", failure["analyzer"])
            or not isinstance(failure["diagnostic_sha256"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", failure["diagnostic_sha256"])
        ):
            raise ConfigurationError("scanner failure must retain a minimized diagnostic reference")
    return {
        name: value[name]
        for name in (
            "findings",
            "findings_count",
            "analyzer_failures",
            "failed_analyzers",
            "analyzers_executed",
            "analyzers_used",
            "upstream_report_sha256",
            "safety_verdict",
            "scanner_version",
            "scanner_artifact_sha256",
            "scanner_source_files_verified",
        )
    }


def scan(
    workflow_file: Path,
    configuration: str,
    *,
    accounting: Path | None,
    operation_key: str | None,
    reviewed_digest: str | None,
) -> dict[str, Any]:
    with account_workflow(
        accounting,
        workflow_file=workflow_file,
        configuration=configuration,
        stage="scan",
        operation_key=operation_key,
    ) as meter:
        details, definition, candidate = scan_preview(workflow_file, configuration)
        if reviewed_digest is None:
            return {
                **details,
                "workflow_accounting": meter.describe() if meter else {"coverage": "NOT_RECORDED"},
            }
        if details["review_sha256"] != reviewed_digest or meter is None or meter.scope is None:
            raise ConfigurationError(
                "scanner dispatch requires exact preview and accounting authority"
            )
        repository = meter.repository
        assert repository is not None
        meter.authorize()
        request = _authorize(repository, definition, candidate)
        with repository.store._lock:
            uncertain = repository.store._connection.execute(
                "SELECT 1 FROM assessment_records WHERE kind='toolkit_scan_cleanup_uncertain' AND id=?",
                (content_digest(definition),),
            ).fetchone()
        if uncertain is not None:
            raise ConfigurationError(
                "prior scanner cleanup is uncertain; inspect and reconcile before new dispatch"
            )
        operation = meter.operation_id + ":skill-scanner"
        repository.reserve(
            request,
            operation,
            AssessmentLimits(
                max_operations=1,
                max_model_turns=0,
                max_elapsed_seconds=definition.timeout_seconds + 40,
            ),
            stage="workflow_static_scan",
        )
        payload = {
            "candidate_sha256": candidate.sha256,
            "implementation_source": details["implementation_source"],
            "files": {
                name: base64.b64encode(raw).decode() for name, raw in candidate.files.items()
            },
            "check": "static_scan",
        }
        executor = ScanContainerExecutor(
            definition.environment,
            runtime_digest=definition.executable_dependencies[
                str(definition.environment.container_runtime)
            ],
        )
        spec = scan_spec(definition)
        action = ActionRequest(action_id=operation, capability=spec.capability, input=payload)

        def authorize() -> str:
            meter.authorize()
            current, latest, observed = scan_preview(workflow_file, configuration)
            if current["review_sha256"] != reviewed_digest:
                raise ConfigurationError("scanner workflow source changed")
            _authorize(repository, latest, observed)
            return content_digest(definition.environment)

        async def invoke() -> RawExecution:
            context = ExecutionContext(
                request=action,
                spec=spec,
                estimate=spec.estimate,
                attempt=1,
                attempt_id=operation,
                approved_side_effect=SideEffect.READ,
                invocation_check=authorize,
            )
            try:
                return await (await executor.start(context)).task
            finally:
                await executor.close()

        raw = None
        interrupted: BaseException | None = None
        began, started = time.perf_counter(), utc_now()
        with meter.exclude("canonical_static_scan"):
            try:
                with persist_execution_events(
                    lambda journal_id, event: repository.put(
                        "execution_event", journal_id + ":" + str(event.sequence), event
                    )
                ):
                    raw = asyncio.run(invoke())
            except BaseException as error:
                interrupted = error
                raw = RawExecution(status=ExecutionStatus.FAILED, error_type=type(error).__name__)
            finally:
                elapsed = time.perf_counter() - began
                resources = ResourceVector(latency_ms=elapsed * 1000)
                repository.finish_operation(
                    operation,
                    elapsed_seconds=elapsed,
                    accounting=raw.accounting if raw else None,
                    resources=resources,
                )
        assert raw is not None
        observations = None
        evidence_ref = None
        outcome_error = interrupted
        if raw.status == ExecutionStatus.SUCCESS and executor.cleanup_verified:
            try:
                evidence = ExecutionEvidence.model_validate(raw.metadata.get("execution_evidence"))
                if (
                    not evidence.complete
                    or evidence.attempt_id != operation
                    or not evidence.events
                    or evidence.events[-1].kind != "execution.completed"
                ):
                    raise ConfigurationError(
                        "scanner returned no complete canonical execution journal"
                    )
                evidence_ref = repository.put("execution_evidence", evidence.digest(), evidence)
                observations = _observations(
                    raw.output, definition, candidate, details["implementation_source"]
                )
                authorize()
            except (ValueError, ConfigurationError) as error:
                outcome_error = error
        okay = (
            raw.status == ExecutionStatus.SUCCESS
            and executor.cleanup_verified
            and outcome_error is None
        )
        receipt = ExecutionReceipt(
            decision_id=operation,
            action_id=action.action_id,
            capability=spec.capability,
            executor_id=spec.id,
            executor_kind=spec.kind,
            executor_fingerprint=executor_fingerprint(spec),
            status=ExecutionStatus.SUCCESS if okay else ExecutionStatus.FAILED,
            started_at=started,
            ended_at=utc_now(),
            estimated=spec.estimate,
            actual_resources=resources,
            accounting=raw.accounting,
            execution_success=okay,
            error_type=type(outcome_error).__name__
            if outcome_error
            else raw.error_type or (None if okay else "ScannerCleanupUncertain"),
            metadata={
                **raw.metadata,
                "component": "skill-scanner",
                "process_status": raw.status.value,
                "runtime_ref": content_digest(definition),
                "observed_resource_dimensions": ["latency_ms"],
                "scan_observation_sha256": content_digest(observations)
                if observations is not None
                else None,
                "container_resource_usage": "unavailable",
                "cleanup_verified": executor.cleanup_verified,
            },
        )
        repository.store.save_receipt(receipt)
        receipt_ref = repository.put("toolkit_component_receipt", operation, receipt)
        if not executor.cleanup_verified:
            repository.put("toolkit_scan_cleanup_uncertain", content_digest(definition), receipt)
        if interrupted is not None:
            raise interrupted
        if not okay or observations is None or evidence_ref is None:
            raise ConfigurationError(
                "scan failed or cleanup is uncertain; retain the attempt and inspect it"
            )
        record = WorkflowScanRecord(
            definition_ref=content_digest(definition),
            implementation_source=details["implementation_source"],
            candidate_sha256=candidate.sha256,
            environment_digest=content_digest(definition.environment),
            wrapper_operation_id=meter.operation_id,
            operation_id=operation,
            request_plan_id=request.plan_id,
            authorization_id=request.authorization_id,
            receipt_ref=receipt_ref,
            execution_evidence_ref=evidence_ref,
            observations=observations,
            cleanup_verified=True,
        )
        ref = repository.put("toolkit_workflow_scan", content_digest(record), record)
        return {
            "scan_ref": ref,
            **record.model_dump(mode="json"),
            "workflow_accounting": meter.describe(),
            "candidate_usefulness": "NOT_ASSESSED",
            "selection_usefulness": "NOT_ASSESSED",
        }


def require_scan(
    repository: AssessmentRepository, ref: str, workflow_file: Path, configuration: str
) -> WorkflowScanRecord:
    details, definition, candidate = scan_preview(workflow_file, configuration)
    record = WorkflowScanRecord.model_validate(repository.get("toolkit_workflow_scan", ref))
    _authorize(repository, definition, candidate, execution=False)
    receipt = ExecutionReceipt.model_validate(
        repository.get("toolkit_component_receipt", record.receipt_ref)
    )
    evidence = ExecutionEvidence.model_validate(
        repository.get("execution_evidence", record.execution_evidence_ref)
    )
    ledger = repository.operation_ledger(record.request_plan_id)
    operation = next(
        (item for item in ledger.operations if item.operation_id == record.operation_id), None
    )
    if (
        content_digest(record) != ref
        or content_digest(evidence) != record.execution_evidence_ref
        or not evidence.complete
        or evidence.attempt_id != record.operation_id
        or not evidence.events
        or evidence.events[-1].kind != "execution.completed"
        or record.definition_ref != content_digest(definition)
        or record.implementation_source != details["implementation_source"]
        or record.candidate_sha256 != candidate.sha256
        or not record.cleanup_verified
        or record.environment_digest != content_digest(definition.environment)
        or record.authorization_id != definition.request.authorization_id
        or record.request_plan_id != definition.request.plan_id
        or content_digest(receipt) != record.receipt_ref
        or receipt.metadata.get("runtime_ref") != content_digest(definition)
        or receipt.metadata.get("scan_observation_sha256") != content_digest(record.observations)
        or receipt.executor_fingerprint != executor_fingerprint(scan_spec(definition))
        or receipt.execution_success is not True
        or receipt.status != ExecutionStatus.SUCCESS
        or receipt.action_id != record.operation_id
        or receipt.metadata.get("cleanup_verified") is not True
        or operation is None
        or operation.elapsed_seconds is None
    ):
        raise ConfigurationError(
            "selected scanner observation is missing, stale, failed or unaccounted"
        )
    return record
