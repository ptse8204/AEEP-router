"""Selected SkillRank queries reuse contained execution, exact reviews and receipts."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import time
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.verification import verification_source_digest
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
    ResourceAccounting,
    ResourceVector,
    RouteEstimate,
    SideEffect,
    StrictModel,
    utc_now,
)

from .catalog_worker import SOURCE_REVISION, VERSION, query
from .file_runtime import FileRuntimeInstallation
from .install_runtime import canonical, digest, parse_installation
from .models import Digest, Identifier, SourcePin
from .workflow import StackWorkflow, WorkflowFile, _read
from .workflow_accounting import account_workflow
from .workflow_runtime import lifecycle_preview, observe, runtime_target
from .workflow_security import ScanContainerExecutor


class CatalogRuntimeDefinition(StrictModel):
    schema_version: Literal["aeep.toolkit.catalog-runtime.v1"] = "aeep.toolkit.catalog-runtime.v1"
    source_revision: Literal["5216bae9149b4ff8a7f9e014b6889fb094cee8e1"] = (
        "5216bae9149b4ff8a7f9e014b6889fb094cee8e1"
    )
    runtime_id: Identifier
    environment: AssessmentEnvironment
    request: RecipeMaterializationRequest
    catalog: WorkflowFile
    catalog_source: SourcePin
    control_root: str
    worker_sha256: Digest
    executable_dependencies: dict[str, Digest] = Field(min_length=1, max_length=32)
    timeout_seconds: int = Field(default=45, strict=True, ge=10, le=300)

    @model_validator(mode="after")
    def bounded(self) -> CatalogRuntimeDefinition:
        env = self.environment
        import re

        if (
            env.kind != "container"
            or env.network
            or env.read_only_roots
            or re.fullmatch(r"sha256:[a-f0-9]{64}", env.container_image or "") is None
            or env.container_runtime is None
            or env.container_socket is None
            or content_digest(env) != self.request.environment_digest
            or self.catalog.sha256 != self.catalog_source.artifact_sha256
        ):
            raise ValueError(
                "catalog requires a pinned offline worker, exact data and matching scope"
            )
        runtime_target(self.control_root)
        return self


class WorkflowCatalogRecord(StrictModel):
    schema_version: Literal["aeep.toolkit.workflow-catalog.v1"] = "aeep.toolkit.workflow-catalog.v1"
    definition_ref: Digest
    implementation_source: Digest
    installation_ref: Digest
    binary_sha256: Digest
    catalog_sha256: Digest
    query_sha256: Digest
    mode: Literal["search", "show"]
    status: Literal["completed", "not_found"]
    result_sha256: Digest
    wrapper_operation_id: str
    operation_id: str
    request_plan_id: str
    authorization_id: str
    receipt_ref: Digest
    execution_evidence_ref: Digest
    cleanup_verified: bool


def valid_result(mode: str, status: object, result: Any) -> bool:
    """Validate upstream metadata without interpreting its ratings as evidence."""
    if status == "not_found":
        return mode == "show" and result is None
    if status != "completed" or not isinstance(result, dict):
        return False
    if mode == "search":
        return isinstance(result.get("items"), list) and len(result["items"]) <= 256
    return isinstance(result.get("slug"), str)


def catalog_preview(
    workflow_file: Path, configuration: str, mode: str, value: str
) -> tuple[
    dict[str, Any], CatalogRuntimeDefinition, FileRuntimeInstallation, Path, bytes, dict[str, str]
]:
    from .cli import read_json
    from .installation import PreviewPolicy, preview
    from .models import ExtensionRegistry

    selected_query = query(mode, value)
    workflow = StackWorkflow.model_validate(read_json(workflow_file))
    selected = workflow.configurations[configuration]
    if selected.catalog is None or "skillrank" not in selected.components:
        raise ConfigurationError("select SkillRank and its exact catalog binding explicitly")
    root = workflow_file.absolute().parent
    _, raw = _read(selected.catalog, root)
    definition = CatalogRuntimeDefinition.model_validate_json(raw)
    if definition.runtime_id not in selected.runtimes:
        raise ConfigurationError("catalog has no selected runtime installation")
    binding = selected.runtimes[definition.runtime_id]
    _, raw = _read(binding.installation, root)
    plan = parse_installation(json.loads(raw))
    if not isinstance(plan, FileRuntimeInstallation):
        raise ConfigurationError("catalog requires a hash-bound file runtime")
    component = binding.components.get("skillrank")
    primary = [f for f in plan.files if f.extension_id == component and f.primary and f.executable]
    if len(primary) != 1:
        raise ConfigurationError("catalog requires one selected executable artifact")
    binary = canonical(str(Path(plan.destination) / primary[0].destination))
    if any(c in str(binary) for c in ",\n\x00"):
        raise ConfigurationError("catalog executable path cannot be represented as a safe mount")
    _, data = _read(definition.catalog, root)
    entries = json.loads(data)
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256 or len(data) > 1024**2:
        raise ConfigurationError("selected catalog exceeds its metadata envelope")
    _, registry_raw = _read(workflow.registry, root)
    _, policy_raw = _read(workflow.policy, root)
    registry = ExtensionRegistry.model_validate_json(registry_raw)
    policy = PreviewPolicy.model_validate_json(policy_raw)
    manifest = registry.get("skillrank")
    if (
        manifest.source.revision != SOURCE_REVISION
        or manifest.source.artifact_sha256 != primary[0].sha256
        or definition.catalog_source.data_rights not in policy.allowed_data_rights
    ):
        raise ConfigurationError("catalog source or exact data rights differ from selected policy")
    permission = preview(registry, ("skillrank",), policy, profile="full")
    lifecycle, _ = lifecycle_preview(
        workflow_file, configuration, (definition.runtime_id,), operation="readiness"
    )
    worker = Path(__file__).with_name("catalog_worker.py").resolve()
    runtime = Path(str(definition.environment.container_runtime))
    if (
        file_digest(worker) != definition.worker_sha256
        or runtime.resolve() != runtime
        or not {str(worker), str(runtime)} <= definition.executable_dependencies.keys()
    ):
        raise ConfigurationError("catalog requires canonical controller/worker fingerprints")
    verify_dependencies(definition.executable_dependencies)
    observation = observe(plan)
    blockers = [*permission.blockers, *lifecycle["blockers"]]
    if not runtime_target(definition.control_root).is_dir():
        blockers.append("catalog control parent must already exist as an owned directory")
    if observation["installed"] is not True:
        blockers.append("selected catalog runtime is absent, changed or unowned")
    facts = {
        "definition": definition.model_dump(mode="json"),
        "definition_ref": content_digest(definition),
        "installation_ref": digest(plan),
        "binary_sha256": primary[0].sha256,
        "catalog_sha256": definition.catalog.sha256,
        "query_sha256": content_digest(selected_query),
        "mode": selected_query["mode"],
        "implementation_source": verification_source_digest(Path(__file__).resolve().parents[2]),
        "runtime_observation": observation,
        "blockers": sorted(set(blockers)),
        "execution_authorized": False,
        "functional_readiness": "NOT_VERIFIED_BY_PREVIEW",
        "usefulness": "NOT_ASSESSED",
    }
    return (
        {**facts, "review_sha256": content_digest(facts)},
        definition,
        plan,
        binary,
        data,
        selected_query,
    )


class CatalogContainerExecutor(ScanContainerExecutor):
    ownership_label = "aeep.workflow-catalog"

    def __init__(self, definition: CatalogRuntimeDefinition, binary: Path, config: Path):
        super().__init__(
            definition.environment,
            runtime_digest=definition.executable_dependencies[
                str(definition.environment.container_runtime)
            ],
        )
        self.binary, self.config = binary, config

    def command(self, context: ExecutionContext) -> tuple[list[str], str]:
        argv, name = super().command(context)
        argv[1:1] = ["--config", str(self.config)]
        index = argv.index("--entrypoint")
        argv[index:index] = [
            "--mount",
            f"type=bind,src={self.binary},dst=/opt/aeep-skillrank,readonly",
        ]
        return argv, name

    async def checked_docker(self, *arguments: str) -> tuple[int, bytes]:
        if file_digest(Path(str(self.environment.container_runtime))) != self.runtime_digest:
            raise ConfigurationError("reviewed container runtime changed")
        spec = ExecutorSpec(
            id="toolkit.catalog-ownership",
            capability="toolkit.container-ownership@1",
            description="Inspect/stop only the exact owned catalog worker",
            kind=ExecutorKind.COMMAND,
            side_effect=SideEffect.READ,
            config={
                "argv": [
                    str(self.environment.container_runtime),
                    "--config",
                    str(self.config),
                    "--host",
                    f"unix://{self.environment.container_socket}",
                    *arguments,
                ],
                "argv_literal": True,
                "inherit_env": False,
                "timeout_seconds": 10,
                "max_output_bytes": 500000,
                "output": {"type": "text"},
                "env": {"PATH": "/usr/bin:/bin", "HOME": str(self.config.parent)},
            },
        )
        executor = CommandExecutor()
        action = ActionRequest(capability=spec.capability)
        try:
            raw = await executor.execute(
                ExecutionContext(
                    request=action,
                    spec=spec,
                    estimate=spec.estimate,
                    attempt=1,
                    approved_side_effect=SideEffect.READ,
                )
            )
        finally:
            await executor.close()
        if raw.exit_code is None:
            raise ConfigurationError("catalog ownership inspection has no terminal status")
        return raw.exit_code, ((raw.stdout or "") + (raw.stderr or "")).encode()


def catalog(
    workflow_file: Path,
    configuration: str,
    mode: str,
    value: str,
    *,
    accounting: Path | None,
    operation_key: str | None,
    reviewed_digest: str | None,
) -> dict[str, Any]:
    with account_workflow(
        accounting,
        workflow_file=workflow_file,
        configuration=configuration,
        stage="catalog",
        operation_key=operation_key,
    ) as meter:
        details, definition, plan, binary, data, selected_query = catalog_preview(
            workflow_file, configuration, mode, value
        )
        if reviewed_digest is None:
            return details
        if (
            reviewed_digest != details["review_sha256"]
            or details["blockers"]
            or meter is None
            or meter.scope is None
            or meter.repository is None
            or not meter.scope.schema_version.endswith(".v4")
        ):
            raise ConfigurationError(
                "catalog needs exact preview, installed bytes and accounting v4 authority"
            )
        repository = meter.repository
        ref = content_digest(definition)
        stored = CatalogRuntimeDefinition.model_validate(
            repository.get("toolkit_catalog_runtime", ref)
        )
        if (
            stored != definition
            or definition.request.authorization_id != meter.scope.request.authorization_id
        ):
            raise ConfigurationError(
                "catalog definition or authority differs from the selected workflow"
            )
        request = definition.request.model_copy(
            update={
                "definition_digests": list(
                    dict.fromkeys([*definition.request.definition_digests, ref])
                )
            }
        )
        if (
            AssessmentEnvironment.model_validate(
                repository.get("environment", request.environment_digest)
            )
            != definition.environment
        ):
            raise ConfigurationError("catalog scope does not bind the actual environment")
        if repository.store._connection.execute(
            "SELECT 1 FROM assessment_records WHERE kind='toolkit_catalog_cleanup_uncertain' LIMIT 1"
        ).fetchone():
            raise ConfigurationError(
                "prior catalog cleanup is uncertain; reconcile before dispatch"
            )
        repository.authorize(request)
        meter.authorize()
        operation = meter.operation_id + ":skillrank-catalog"
        repository.reserve(
            request,
            operation,
            AssessmentLimits(
                max_operations=1,
                max_model_turns=0,
                max_elapsed_seconds=definition.timeout_seconds + 40,
            ),
            stage="workflow_catalog",
        )
        control = (
            runtime_target(definition.control_root) / hashlib.sha256(operation.encode()).hexdigest()
        )
        raw = None
        executor = None
        spec: ExecutorSpec | None = None
        interrupted: BaseException | None = None
        evidence_ref = None
        began, started = time.perf_counter(), utc_now()
        with meter.exclude("canonical_catalog_lookup"):
            try:
                control.mkdir(mode=0o700)
                config = control / "docker-config"
                config.mkdir(mode=0o700)
                (config / "config.json").write_text(
                    json.dumps(
                        {
                            "auths": {"https://index.docker.io/v1/": {}},
                            "credsStore": "",
                            "credHelpers": {},
                        }
                    )
                )
                executor = CatalogContainerExecutor(definition, binary, config)
                worker = str(Path(__file__).with_name("catalog_worker.py").resolve())
                spec = ExecutorSpec(
                    id="toolkit.skillrank-catalog",
                    capability="toolkit.catalog@1",
                    description="Selected upstream local SkillRank query in an offline worker",
                    kind=ExecutorKind.COMMAND,
                    side_effect=SideEffect.READ,
                    config={
                        "argv": ["python3", "-I", "-B", worker],
                        "argv_literal": True,
                        "stdin_json": True,
                        "max_stdin_bytes": 1800000,
                        "max_output_bytes": 600000,
                        "timeout_seconds": definition.timeout_seconds,
                        "output": {"type": "json"},
                    },
                )
                action = ActionRequest(
                    action_id=operation,
                    capability=spec.capability,
                    input={
                        "binary_sha256": details["binary_sha256"],
                        "catalog_sha256": definition.catalog.sha256,
                        "catalog_base64": base64.b64encode(data).decode(),
                        "query": selected_query,
                        "implementation_source": details["implementation_source"],
                    },
                )

                def authorize() -> str:
                    meter.authorize()
                    repository.authorize(request)
                    current = catalog_preview(workflow_file, configuration, mode, value)[0]
                    if current["review_sha256"] != reviewed_digest:
                        raise ConfigurationError("catalog workflow or runtime changed")
                    return content_digest(definition.environment)

                async def invoke() -> RawExecution:
                    assert executor is not None and spec is not None
                    try:
                        return await (
                            await executor.start(
                                ExecutionContext(
                                    request=action,
                                    spec=spec,
                                    estimate=spec.estimate,
                                    attempt=1,
                                    attempt_id=operation,
                                    approved_side_effect=SideEffect.READ,
                                    invocation_check=authorize,
                                )
                            )
                        ).task
                    finally:
                        try:
                            if not executor.cleanup_verified:
                                await executor.cleanup(operation)
                        finally:
                            await executor.close()

                with persist_execution_events(
                    lambda journal_id, event: repository.put(
                        "execution_event", journal_id + ":" + str(event.sequence), event
                    )
                ):
                    raw = asyncio.run(invoke())
                output = raw.output
                if (
                    raw.status != ExecutionStatus.SUCCESS
                    or not executor.cleanup_verified
                    or not isinstance(output, dict)
                    or output.get("component") != "skillrank"
                    or output.get("source_revision") != "5216bae9149b4ff8a7f9e014b6889fb094cee8e1"
                    or output.get("version") != VERSION
                    or output.get("binary_sha256") != details["binary_sha256"]
                    or output.get("catalog_sha256") != definition.catalog.sha256
                    or output.get("implementation_source") != details["implementation_source"]
                    or output.get("server_stopped") is not True
                    or output.get("status") not in {"completed", "not_found"}
                    or output.get("provider_claims_are_not_scan_or_usefulness_evidence") is not True
                    or not valid_result(mode, output.get("status"), output.get("result"))
                ):
                    raise ConfigurationError(
                        "catalog result has incomplete source/lifecycle evidence"
                    )
                evidence = ExecutionEvidence.model_validate(raw.metadata.get("execution_evidence"))
                if (
                    not evidence.complete
                    or evidence.attempt_id != operation
                    or not evidence.events
                    or evidence.events[-1].kind != "execution.completed"
                ):
                    raise ConfigurationError("catalog result has no complete canonical journal")
                evidence_ref = repository.put("execution_evidence", evidence.digest(), evidence)
                authorize()
            except BaseException as error:
                interrupted = error
            finally:
                elapsed = time.perf_counter() - began
                repository.finish_operation(
                    operation,
                    elapsed_seconds=elapsed,
                    accounting=raw.accounting if raw else None,
                    resources=ResourceVector(latency_ms=elapsed * 1000),
                )
        cleanup = executor.cleanup_verified if executor is not None else True
        okay = interrupted is None and raw is not None and cleanup and evidence_ref is not None
        receipt = ExecutionReceipt(
            decision_id=operation,
            action_id=operation,
            capability="toolkit.catalog@1",
            executor_id="toolkit.skillrank-catalog",
            executor_kind=ExecutorKind.COMMAND,
            status=ExecutionStatus.SUCCESS if okay else ExecutionStatus.FAILED,
            started_at=started,
            ended_at=utc_now(),
            estimated=spec.estimate if spec is not None else RouteEstimate(),
            actual_resources=ResourceVector(latency_ms=elapsed * 1000),
            accounting=raw.accounting if raw else ResourceAccounting(),
            execution_success=okay,
            error_type=type(interrupted).__name__ if interrupted else None,
            metadata={
                "component": "skillrank",
                "definition_ref": ref,
                "query_sha256": details["query_sha256"],
                "catalog_sha256": definition.catalog.sha256,
                "cleanup_verified": cleanup,
                "observed_resource_dimensions": ["latency_ms"],
                "container_resource_usage": "unavailable",
            },
        )
        repository.store.save_receipt(receipt)
        receipt_ref = repository.put("toolkit_component_receipt", operation, receipt)
        if not cleanup:
            repository.put("toolkit_catalog_cleanup_uncertain", operation, receipt)
        if interrupted is not None:
            raise interrupted
        assert raw is not None and evidence_ref is not None
        record = WorkflowCatalogRecord.model_validate(
            dict(
                definition_ref=ref,
                implementation_source=details["implementation_source"],
                installation_ref=digest(plan),
                binary_sha256=details["binary_sha256"],
                catalog_sha256=definition.catalog.sha256,
                query_sha256=details["query_sha256"],
                mode=selected_query["mode"],
                status=raw.output["status"],
                result_sha256=content_digest(raw.output["result"]),
                wrapper_operation_id=meter.operation_id,
                operation_id=operation,
                request_plan_id=request.plan_id,
                authorization_id=request.authorization_id,
                receipt_ref=receipt_ref,
                execution_evidence_ref=evidence_ref,
                cleanup_verified=True,
            )
        )
        record_ref = repository.put("toolkit_workflow_catalog", content_digest(record), record)
        return {
            "catalog_ref": record_ref,
            **record.model_dump(mode="json"),
            "result": raw.output["result"],
            "provider_claims_are_not_scan_or_usefulness_evidence": True,
            "candidate_usefulness": "NOT_ASSESSED",
            "selection_usefulness": "NOT_ASSESSED",
        }
