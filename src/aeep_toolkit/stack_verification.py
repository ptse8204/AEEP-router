"""Operator CLI for existing assessment definitions, probes and readiness evidence."""

from __future__ import annotations

import argparse
import asyncio
import json
import sqlite3
from pathlib import Path
from typing import Any

from pydantic import Field, ValidationError

from aeep.assessment.boundary import BoundaryProbeDefinition, run_boundary_probe
from aeep.assessment.destinations import require_destination
from aeep.assessment.models import (
    AssessmentEnvironment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import ExecutorKind, StrictModel
from aeep.store import ReceiptStore

from .cli import read_json
from .install_runtime import canonical
from .models import Identifier
from .stack_readiness import (
    REQUIRED_CHECKS,
    IntegrationDefinition,
    IntegrationEvidence,
    StackCompletion,
    _resolve,
    check_contract,
    checklist,
    require_check,
    require_definition,
    require_integration,
    require_stack_complete,
    source_revisions,
    verify_integration,
)

ROOT = Path(__file__).resolve().parents[2]
DEFINITION = "toolkit_integration_definition"
EVIDENCE = "toolkit_integration_evidence"
COMPLETION = "toolkit_stack_completion"
REQUEST = "recipe_materialization_request"
CHECK = "boundary_probe_definition"


class VerificationDefinitions(StrictModel):
    integration: IntegrationDefinition
    checks: dict[Identifier, BoundaryProbeDefinition]
    requests: dict[Identifier, RecipeMaterializationRequest] = Field(default_factory=dict)
    environment: AssessmentEnvironment | None = None


def _require_request(
    request: RecipeMaterializationRequest, definition: IntegrationDefinition, check_ref: str
) -> None:
    if (
        request.mapping_digest != check_ref
        or request.environment_digest != definition.runtime_digest
        or not {check_ref, content_digest(definition)} <= set(request.definition_digests)
    ):
        raise ConfigurationError(
            "probe request must bind its exact integration, check and environment"
        )


def define(
    repository: AssessmentRepository, bundle: VerificationDefinitions, source: str
) -> dict[str, Any]:
    definition = bundle.integration
    if (
        definition.implementation_source != source
        or definition.source_revision != source_revisions(source)[definition.component]
        or bundle.checks.keys() != definition.probe_definitions.keys()
        or not bundle.requests.keys() <= bundle.checks.keys()
        or (
            bundle.environment is not None
            and content_digest(bundle.environment) != definition.runtime_digest
        )
    ):
        raise ConfigurationError(
            "definition bundle differs from the current source or check inventory"
        )
    for name, check in bundle.checks.items():
        check_contract(definition, name, check)
        if name in bundle.requests:
            _require_request(bundle.requests[name], definition, content_digest(check))
    # One transaction so a conflicting request cannot leave a partial definition.
    with repository.store._immediate_transaction() as connection:
        ref = repository._put(connection, DEFINITION, content_digest(definition), definition)
        for check in bundle.checks.values():
            repository._put(connection, CHECK, content_digest(check), check)
        if bundle.environment is not None:
            repository._put(
                connection, "environment", definition.runtime_digest, bundle.environment
            )
        for request in bundle.requests.values():
            repository._put(connection, REQUEST, request.plan_id, request)
    return {
        "definition_ref": ref,
        "checks": definition.probe_definitions,
        "requests": {name: request.plan_id for name, request in bundle.requests.items()},
        "grants_changed": False,
    }


async def probe(
    repository: AssessmentRepository,
    component: str,
    name: str,
    definition_ref: str,
    request_id: str,
    source: str,
) -> dict[str, Any]:
    from .workflow_security import ScanContainerExecutor

    definition = require_definition(
        repository, definition_ref, component=component, source_digest=source
    )
    check_ref = definition.probe_definitions[name]
    check = _resolve(repository, CHECK, check_ref, BoundaryProbeDefinition, reviewed=True)
    check_contract(definition, name, check)
    request = RecipeMaterializationRequest.model_validate(repository.get(REQUEST, request_id))
    if request.plan_id != request_id:
        raise ConfigurationError("probe requires the stored request ID")
    _require_request(request, definition, check_ref)
    env = _resolve(repository, "environment", request.environment_digest, AssessmentEnvironment)
    spec = check.executor
    runtime = env.container_runtime
    config = spec.config
    argv = config.get("argv")
    timeout = config.get("timeout_seconds", 60)
    if (
        env.kind != "container"
        or env.network
        or env.read_only_roots
        or not env.container_image
        or not env.container_image.startswith("sha256:")
        or runtime is None
        or runtime not in definition.executable_dependencies
        or spec.kind != ExecutorKind.COMMAND
        or spec.requires_network
        or not spec.enabled
        or not spec.idempotent
        or spec.side_effect.rank > 1
        or spec.estimate.cash.upper_bound_usd not in (None, 0)
        or config.keys() - {"argv", "argv_literal", "timeout_seconds", "output", "max_output_bytes"}
        or not isinstance(argv, list)
        or not argv
        or not all(isinstance(arg, str) for arg in argv)
        or not Path(argv[0]).is_absolute()
        or config.get("argv_literal") is not True
        or config.get("output") != {"type": "json"}
        or type(timeout) is not int
        or not 0 < timeout <= 900
    ):
        raise ConfigurationError(
            "stack probe requires a reviewed offline command in a pinned local image"
        )

    def recheck() -> None:
        if verification_source_digest(ROOT) != source:
            raise ConfigurationError("stack probe implementation source changed")
        require_definition(repository, definition_ref, component=component, source_digest=source)
        require_destination(spec, env, repository.authorize(request))

    recheck()
    executor = ScanContainerExecutor(
        env, runtime_digest=definition.executable_dependencies[runtime]
    )
    try:
        observation = await run_boundary_probe(
            repository,
            check_ref,
            worker_digest=definition.runtime_digest,
            executor=executor,
            plan=request,
            invocation_check=recheck,
            cleanup_check=lambda: executor.cleanup_verified,
        )
    finally:
        await executor.close()
    ref = content_digest(observation)
    recheck()
    _, journal = require_check(repository, definition, name, ref)
    return {"check": name, "probe_ref": ref, "operation_id": journal.attempt_id}


def _find_records(repository: AssessmentRepository, kind: str, key: str, value: str) -> list[str]:
    with repository.store._lock:
        return [
            row[0]
            for row in repository.store._connection.execute(
                "SELECT digest FROM assessment_records WHERE kind=? AND json_extract(payload_json, ?) = ? "
                "ORDER BY rowid DESC",
                (kind, f"$.{key}", value),
            )
        ]


def _observe_component(
    repository: AssessmentRepository, component: str, source: str
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for definition_ref in _find_records(repository, DEFINITION, "component", component):
        entry: dict[str, Any] = {"definition_ref": definition_ref}
        try:
            raw = _resolve(repository, DEFINITION, definition_ref, IntegrationDefinition)
            entry.update(
                source_revision=raw.source_revision,
                implementation_source=raw.implementation_source,
                runtime_digest=raw.runtime_digest,
            )
            definition = require_definition(
                repository, definition_ref, component=component, source_digest=source
            )
        except (ConfigurationError, OSError, ValidationError) as exc:
            entry["gap"] = (
                str(exc)
                if isinstance(exc, ConfigurationError)
                else "canonical definition or runtime unavailable"
            )
            rows.append(entry)
            continue
        entry["checks"] = {}
        for name, check_ref in definition.probe_definitions.items():
            detail: dict[str, Any] = {
                "definition_ref": check_ref,
                "status": "BLOCKED",
                "gap": "no canonical observation",
            }
            for ref in _find_records(
                repository, "boundary_probe", "implementation_digest", check_ref
            ):
                try:
                    record, journal = require_check(repository, definition, name, ref)
                except (ConfigurationError, ValidationError):
                    detail["gap"] = "canonical observation failed validation"
                    continue
                detail = {
                    "definition_ref": check_ref,
                    "status": "VERIFIED",
                    "probe_ref": ref,
                    "journal_ref": record.execution_evidence_digest,
                    "operation_id": journal.attempt_id,
                    "receipt_ref": record.host_receipt_digest,
                    "observed": record.observed,
                }
                break
            entry["checks"][name] = detail
        evidence = IntegrationEvidence(
            definition_ref=definition_ref,
            probe_refs={
                name: detail["probe_ref"]
                for name, detail in entry["checks"].items()
                if detail["status"] == "VERIFIED"
            },
        )
        entry["verified_checks"] = len(evidence.probe_refs)
        if evidence.probe_refs.keys() == definition.probe_definitions.keys():
            ref = content_digest(evidence)
            entry["available_evidence_ref"] = ref
            for candidate in _find_records(repository, EVIDENCE, "definition_ref", definition_ref):
                try:
                    require_integration(
                        repository, candidate, component=component, source_digest=source
                    )
                except (ConfigurationError, ValidationError, OSError):
                    continue
                entry["integration_evidence_ref"] = candidate
                break
            else:
                entry["gap"] = "verified checks have not been recorded as component evidence"
        rows.append(entry)
    if not rows:
        return {
            "component": component,
            "functional_status": "BLOCKED",
            "checks": {
                name: {"status": "BLOCKED", "gap": "no canonical integration definition"}
                for name in REQUIRED_CHECKS[component]
            },
            "source_revision": source_revisions(source)[component],
        }
    best = max(
        rows, key=lambda row: ("integration_evidence_ref" in row, row.get("verified_checks", -1))
    )
    return {
        "component": component,
        **best,
        "functional_status": "VERIFIED" if "integration_evidence_ref" in best else "BLOCKED",
        "checks": best.get(
            "checks",
            {
                name: {"status": "BLOCKED", "gap": best.get("gap")}
                for name in REQUIRED_CHECKS[component]
            },
        ),
    }


def status(repository: AssessmentRepository, source: str) -> dict[str, Any]:
    result = checklist()
    result.update(
        implementation_source=source,
        components=[_observe_component(repository, name, source) for name in REQUIRED_CHECKS],
        notice="Canonical functional evidence only. No runtime, service or model was started.",
    )
    for ref in _find_records(repository, COMPLETION, "implementation_source", source):
        try:
            require_stack_complete(repository, ref, source_digest=source)
        except (ConfigurationError, ValidationError, OSError):
            continue
        result.update(
            comparison_dispatch="STACK_GATE_VERIFIED_SEPARATE_EXECUTION_AUTHORITY_REQUIRED",
            stack_completion_ref=ref,
        )
        break
    return result


def main(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="aeep-toolkit stack-verify")
    commands = parser.add_subparsers(dest="operation", required=True)
    for name in ("status", "define", "probe", "record", "assemble"):
        command = commands.add_parser(name)
        command.add_argument(
            "--store", type=Path, required=True, help="Existing canonical AEEP database"
        )
        if name in {"define", "record", "assemble"}:
            command.add_argument("--file", type=Path, required=True)
        if name in {"record", "probe"}:
            command.add_argument("--component", choices=REQUIRED_CHECKS, required=True)
        if name == "probe":
            command.add_argument("--check", required=True)
            command.add_argument("--definition-ref", required=True)
            command.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    try:
        path = canonical(str(args.store.absolute()))
        if not path.is_file() or path.stat().st_nlink != 1:
            raise ConfigurationError(
                "stack verification requires an existing unlinked AEEP database"
            )
        source = verification_source_digest(ROOT)
        with ReceiptStore(path, read_only=args.operation == "status") as store:
            repository = AssessmentRepository(store)
            if args.operation == "status":
                result = status(repository, source)
            elif args.operation == "define":
                result = define(
                    repository, VerificationDefinitions.model_validate(read_json(args.file)), source
                )
            elif args.operation == "probe":
                result = asyncio.run(
                    probe(
                        repository,
                        args.component,
                        args.check,
                        args.definition_ref,
                        args.request_id,
                        source,
                    )
                )
            elif args.operation == "record":
                evidence = IntegrationEvidence.model_validate(read_json(args.file))
                verify_integration(
                    repository, evidence, component=args.component, source_digest=source
                )
                ref = repository.put(EVIDENCE, content_digest(evidence), evidence)
                result = {"integration_evidence_ref": ref, "component": args.component}
            else:
                completion = StackCompletion.model_validate(read_json(args.file))
                if completion.implementation_source != source:
                    raise ConfigurationError("stack record is for another implementation source")
                for component, ref in completion.components.items():
                    require_integration(repository, ref, component=component, source_digest=source)
                ref = repository.put(COMPLETION, content_digest(completion), completion)
                result = {"stack_completion_ref": ref, "comparisons_authorized": False}
        print(json.dumps(result, indent=2, allow_nan=False))
    except ConfigurationError as error:
        parser.exit(2, f"Stack verification blocked. {error}\n")
    except (OSError, KeyError, ValueError, sqlite3.Error):
        parser.exit(2, "Cannot read the selected stack verification files or canonical store.\n")
