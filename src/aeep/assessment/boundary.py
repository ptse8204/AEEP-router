"""Evidence requirements for a reviewed execution boundary; catalogs are not permissions."""

from __future__ import annotations

from typing import Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

from ..errors import ConfigurationError
from ..execution import EventJournal, ExecutionEvidence, persist_execution_events
from ..models import ExecutorSpec, RawExecution, StrictModel
from .models import (
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlan,
    ConformanceProbeRequest,
    DifferentialEnvironment,
    Digest,
    ThreeWayAccessDefinition,
    content_digest,
)
from .repository import AssessmentRepository

REQUIRED_PROBES = frozenset({
    "allowed_tool", "denied_tool", "cross_worker", "answers", "configuration",
    "candidate_network", "credential_canary", "resource_limits", "cleanup", "events",
})


def require_managed_boundaries(repository: AssessmentRepository, environment: AssessmentEnvironment,
                               specs: list[ExecutorSpec], identities: dict[str, str]) -> None:
    """Recheck the reviewed worker boundary without starting host or model work."""
    from pathlib import Path

    from ..hosts.workers import binding_from_config
    from ..models import ExecutorKind
    from .verification import verification_source_digest

    for spec in specs:
        if spec.kind != ExecutorKind.MANAGED_HOST:
            continue
        config = spec.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        digest = (environment.conformance_digests or {}).get(spec.id)
        identity = identities.get(spec.id)
        if worker is None or digest is None or identity is None:
            raise ConfigurationError("managed-host admission requires verified worker boundary evidence")
        record = require_conformance(repository, digest,
            source_digest=verification_source_digest(Path(__file__).resolve().parents[3]),
            worker_digest=worker.digest(), identity_digest=identity)
        invocation = config.invocation
        dynamic_digest = invocation.dynamic_tools_digest if invocation is not None else None
        if dynamic_digest is not None:
            if (record.schema_version != 'assessment.boundary-conformance.v3'
                    or record.callback_binding_digest != dynamic_digest):
                raise ConfigurationError('dynamic profile requires exact composed boundary evidence')
        elif record.schema_version == 'assessment.boundary-conformance.v3':
            raise ConfigurationError('composed boundary differs from plain worker profile')
        if (record.adapter != config.adapter_id or record.adapter_version != "1"
                or record.image_digest != "sha256:" + worker.image.split("sha256:")[-1]
                or record.binary_digest != worker.binary_sha256
                or (record.configuration_digest or record.effective_policy_digest) != worker.configuration_digest):
            raise ConfigurationError("managed-host worker differs from its verified boundary")


class BoundaryProbeDefinition(StrictModel):
    name: str
    executor: ExecutorSpec
    expected: dict[str, str | int | bool]


class BoundaryProbe(StrictModel):
    schema_version: Literal["assessment.boundary-probe.v1", "assessment.boundary-probe.v2"] = "assessment.boundary-probe.v1"
    probe_id: str
    name: str
    implementation_digest: Digest
    worker_digest: Digest
    execution_evidence_digest: Digest
    observed: dict[str, str | int | bool]
    host_receipt_digest: Digest | None = None
    charged_operation_digest: Digest | None = None

    @model_validator(mode='after')
    def versioned_cost_binding(self) -> BoundaryProbe:
        if self.schema_version.endswith('.v2') != (self.charged_operation_digest is not None):
            raise ValueError('boundary probe v2 requires an exact charged operation digest')
        return self

    @model_serializer(mode='wrap')
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.host_receipt_digest is None:
            result.pop('host_receipt_digest', None)
        if self.charged_operation_digest is None:
            result.pop('charged_operation_digest', None)
        return result


COMPOSED_PROBES = frozenset({"callback_authority", "native_boundary", "callback_lifecycle", "protected_state"})


class BoundaryConformance(StrictModel):
    schema_version: Literal["assessment.boundary-conformance.v1", "assessment.boundary-conformance.v2", "assessment.boundary-conformance.v3"] = "assessment.boundary-conformance.v1"
    conformance_id: str
    source_digest: Digest
    worker_digest: Digest
    image_digest: str = Field(pattern=r"^sha256:[a-f0-9]{64}$")
    binary_digest: Digest
    adapter: str
    adapter_version: str
    effective_policy_digest: Digest
    reviewed_inventory_digest: Digest
    identity_digest: Digest
    # Enforcement is independently reviewed implementation + effective runtime policy.
    # Probe success alone cannot establish a universal boundary.
    enforcement_definition_digest: Digest
    advertised_tools: list[str]
    permitted_tools: list[str]
    used_tools: list[str]
    probe_digests: list[Digest]
    configuration_digest: Digest | None = None
    effective_inventory: dict[str, Digest] | None = None
    callback_binding_digest: Digest | None = None
    native_backend_digest: Digest | None = None
    composed_definition_digest: Digest | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        for key in ("configuration_digest", "effective_inventory", "callback_binding_digest", "native_backend_digest", "composed_definition_digest"):
            if getattr(self, key) is None:
                result.pop(key, None)
        return result

    @model_validator(mode="after")
    def versioned_policy(self) -> BoundaryConformance:
        if self.schema_version.endswith('.v3'):
            if any(value is None for value in (self.configuration_digest, self.effective_inventory,
                    self.callback_binding_digest, self.native_backend_digest, self.composed_definition_digest)):
                raise ValueError('composed conformance requires exact callback/native/definition bindings')
        elif any(value is not None for value in (self.callback_binding_digest, self.native_backend_digest, self.composed_definition_digest)):
            raise ValueError('historical conformance cannot acquire composed semantics')
        elif self.schema_version.endswith('.v2'):
            if self.configuration_digest is None or self.effective_inventory is None:
                raise ValueError("v2 conformance requires configured and effective policy bindings")
        elif self.configuration_digest is not None or self.effective_inventory is not None:
            raise ValueError("historical conformance cannot acquire differential semantics")
        return self


class DifferentialConformance(StrictModel):
    schema_version: Literal["assessment.differential-conformance.v1"] = "assessment.differential-conformance.v1"
    definition: DifferentialEnvironment
    control_conformance_digest: Digest
    treatment_conformance_digest: Digest


def require_candidate_access(repository: AssessmentRepository, boundary: BoundaryConformance,
                             expected: DifferentialEnvironment, *, available: bool) -> None:
    """Bind access observations to the candidate representation and reviewed worker.

    Callers separately require execution-backed boundary conformance. Dynamic
    access additionally resolves the actual reviewed declaration; a claimed
    availability flag cannot stand in for the callback contract.
    """
    probes = [BoundaryProbe.model_validate(repository.get("boundary_probe", item))
              for item in boundary.probe_digests
              if repository.get("boundary_probe", item).get("name") == "candidate_access"]
    observation: dict[str, str | int | bool] = {
        "definition_digest": content_digest(expected), "candidate_available": available,
    }
    if len(probes) != 1:
        raise ConfigurationError("candidate availability probe must be present and unique")
    probe = probes[0]
    if expected.candidate_dynamic_tools:
        from ..hosts.codex_invocation import contract_digest

        binding_digest = boundary.callback_binding_digest
        if (boundary.schema_version not in {"assessment.boundary-conformance.v2", "assessment.boundary-conformance.v3"}
                or boundary.effective_inventory is None
                or probe.worker_digest != boundary.worker_digest
                or type(probe.observed.get("candidate_available")) is not bool):
            raise ConfigurationError("dynamic candidate access requires the exact worker")
        observed_inventory = {key: value for key, value in boundary.effective_inventory.items()
                              if key.startswith("dynamic:")}
        inventory: dict[str, str] = {}
        if binding_digest is None:
            if available or boundary.schema_version != "assessment.boundary-conformance.v2" or observed_inventory:
                raise ConfigurationError("plain worker cannot claim dynamic candidate access")
        else:
            if boundary.schema_version != "assessment.boundary-conformance.v3":
                raise ConfigurationError("dynamic declaration requires composed conformance")
            document = repository.get("codex_dynamic_tools", binding_digest)
            with repository.store._lock:
                review = repository.store._connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (binding_digest,)).fetchone()
            identity = document.get("identity")
            if (content_digest(document) != binding_digest or review is None or review[0]
                    or not isinstance(identity, dict) or identity.get("worker_digest") != boundary.worker_digest):
                raise ConfigurationError("dynamic candidate declaration is unreviewed or changed")
            namespace, tools = document.get("namespace"), document.get("tools")
            if (not isinstance(namespace, str) or not isinstance(tools, list) or not tools
                    or any(not isinstance(item, dict) or not isinstance(item.get("name"), str) for item in tools)):
                raise ConfigurationError("dynamic candidate declaration is malformed")
            inventory = {f"dynamic:{namespace}:{item['name']}": contract_digest(item) for item in tools}
            if len(inventory) != len(tools) or inventory != observed_inventory:
                raise ConfigurationError("dynamic declaration differs from the effective tool inventory")
        candidates = expected.candidate_dynamic_tools
        present = {key: inventory[key] for key in candidates if key in inventory}
        if present != (candidates if available else {}):
            raise ConfigurationError("dynamic candidate target or availability differs")
        observation.update(candidate_kind="dynamic_tool",
                           candidate_tools_digest=content_digest(candidates),
                           callback_binding_digest=binding_digest or "absent")
    if probe.observed != observation:
        raise ConfigurationError("candidate availability probe does not bind the reviewed candidate")


def require_dynamic_candidate_target(spec: ExecutorSpec, boundary: BoundaryConformance,
                                     expected: DifferentialEnvironment, *, available: bool) -> None:
    """Join the candidate definition to the actual invocation, including absence."""
    if not expected.candidate_dynamic_tools:
        return
    target = spec.managed_host_config().invocation
    if target is None or target.dynamic_tools_digest != boundary.callback_binding_digest:
        raise ConfigurationError("dynamic candidate invocation binding differs")
    if available:
        key = f"dynamic:{target.server}:{target.tool}"
        if (target.mode != "dynamic_tool"
                or expected.candidate_dynamic_tools.get(key) != target.tool_sha256):
            raise ConfigurationError("invocation does not target the reviewed dynamic candidate")
    elif target.mode != "turn":
        raise ConfigurationError("control invocation must leave dynamic candidate unavailable")


def require_differential(repository: AssessmentRepository, environment: AssessmentEnvironment,
                         plan: AssessmentPlan) -> None:
    """Differential evidence supplements each worker's enforcement evidence."""
    if plan.comparison is None or plan.comparison.experiment is None:
        return
    digest = environment.differential_conformance_digest
    if digest is None:
        raise ConfigurationError("environment verification unavailable: differential conformance missing")
    record = DifferentialConformance.model_validate(repository.get("differential_conformance", digest))
    expected = plan.comparison.experiment.environment
    with repository.store._lock:
        shared = repository.store._connection.execute(
            "SELECT 1 FROM assessment_records r JOIN assessment_reviews v ON v.digest=r.digest WHERE r.digest=? AND v.revoked=0",
            (expected.shared_definition_digest,),
        ).fetchone()
    if shared is None:
        raise ConfigurationError("shared environment definition requires exact operator review")
    if (content_digest(record) != digest or record.definition != expected
            or record.control_conformance_digest != (environment.conformance_digests or {}).get(plan.baseline_id)
            or record.treatment_conformance_digest != (environment.conformance_digests or {}).get(plan.candidate_id)):
        raise ConfigurationError("differential conformance differs from the reviewed experiment")
    specs = {}
    if expected.candidate_dynamic_tools:
        from .models import ReviewedMapping

        mapping = ReviewedMapping.model_validate(repository.get("mapping", plan.mapping_digest))
        specs = {spec.id: spec for spec in mapping.subjects}
    for identity, expected_inventory in ((record.control_conformance_digest, expected.control_inventory),
                                         (record.treatment_conformance_digest, expected.treatment_inventory)):
        boundary = BoundaryConformance.model_validate(repository.get("boundary_conformance", identity))
        if (boundary.schema_version not in {"assessment.boundary-conformance.v2", "assessment.boundary-conformance.v3"} or boundary.effective_inventory != expected_inventory
                or boundary.reviewed_inventory_digest != content_digest(expected_inventory)):
            raise ConfigurationError("effective inventory differs from the differential definition")
        require_conformance(repository, identity, source_digest=boundary.source_digest,
                            worker_digest=boundary.worker_digest, identity_digest=boundary.identity_digest)
        require_candidate_access(repository, boundary, expected,
                                 available=identity == record.treatment_conformance_digest)
        if expected.candidate_dynamic_tools:
            available = identity == record.treatment_conformance_digest
            role = plan.candidate_id if available else plan.baseline_id
            if role not in specs:
                raise ConfigurationError("dynamic candidate executor mapping is missing")
            require_dynamic_candidate_target(specs[role], boundary, expected, available=available)


    if plan.comparison.experiment.stage == 'aeep_value':
        require_three_way_access(repository, environment, plan)


def require_three_way_access(repository: AssessmentRepository, environment: AssessmentEnvironment,
                             plan: AssessmentPlan) -> None:
    from .models import ReviewedMapping

    assert plan.comparison is not None and plan.comparison.experiment is not None
    experiment = plan.comparison.experiment
    digest = experiment.three_way_access_digest
    if digest is None or digest not in plan.definition_digests or experiment.normal_host is None:
        raise ConfigurationError('three-way access definition is unbound')
    access = ThreeWayAccessDefinition.model_validate(repository.get('three_way_access', digest))
    with repository.store._lock:
        reviewed = repository.store._connection.execute(
            'SELECT revoked FROM assessment_reviews WHERE digest=?', (digest,)).fetchone()
    if content_digest(access) != digest or reviewed is None or reviewed[0]:
        raise ConfigurationError('three-way access requires current exact review')
    expected = experiment.environment
    if (set(access.normal_inventory) & set(access.discovery_inventory)
            or expected.control_inventory != access.normal_inventory | access.discovery_inventory
            or any(access.discovery_inventory.get(key) != value for key, value in access.external_candidate_inventory.items())
            or set(access.external_candidate_inventory) & set(expected.candidate_inventory)):
        raise ConfigurationError('three-way discovery or external candidate access differs')
    roles = [experiment.normal_host.executor_id, plan.baseline_id, plan.candidate_id]
    if set(access.worker_digests) != set(roles) or set(access.configuration_digests) != set(roles):
        raise ConfigurationError('three-way worker roles differ')
    mapping = ReviewedMapping.model_validate(repository.get('mapping', plan.mapping_digest))
    specs = {spec.id: spec for spec in mapping.subjects}
    inventories = [access.normal_inventory, expected.control_inventory, expected.treatment_inventory]
    identities = {}
    selected = []
    supporting_skills = {}
    for role, inventory in zip(roles, inventories, strict=True):
        conformance = (environment.conformance_digests or {}).get(role)
        if role not in specs or conformance is None:
            raise ConfigurationError('three-way worker conformance missing')
        boundary = BoundaryConformance.model_validate(repository.get('boundary_conformance', conformance))
        if (boundary.worker_digest != access.worker_digests[role]
                or boundary.configuration_digest != access.configuration_digests[role]
                or boundary.schema_version not in {'assessment.boundary-conformance.v2', 'assessment.boundary-conformance.v3'}
                or boundary.effective_inventory != inventory
                or boundary.reviewed_inventory_digest != content_digest(inventory)):
            raise ConfigurationError('three-way effective worker/access binding differs')
        if role == experiment.normal_host.executor_id:
            require_candidate_access(repository, boundary, expected, available=False)
        require_dynamic_candidate_target(specs[role], boundary, expected,
                                         available=role == plan.candidate_id)
        target = specs[role].managed_host_config().invocation
        if target is None:
            raise ConfigurationError('three-way supporting skill profile is missing')
        supporting_skills[role] = target.supporting_skills
        identities[role] = boundary.identity_digest
        selected.append(specs[role])
    shared = {skill.path: skill for skill in supporting_skills[plan.baseline_id]}
    normal = {skill.path: skill for skill in supporting_skills[experiment.normal_host.executor_id]}
    if (supporting_skills[plan.candidate_id] != supporting_skills[plan.baseline_id]
            or any(shared.get(path) != skill for path, skill in normal.items())
            or any(access.external_candidate_inventory.get('skill:' + skill.name) != skill.sha256
                   for path, skill in shared.items() if path not in normal)):
        raise ConfigurationError('three-way omitted supports require exact external discovery skill bindings')
    # Validates current source, actual configured immutable worker, binary, config,
    # reviewed enforcement and every execution-backed probe for all three roles.
    require_managed_boundaries(repository, environment, selected, identities)


def require_conformance(repository: AssessmentRepository, digest: str, *, source_digest: str,
                        worker_digest: str, identity_digest: str) -> BoundaryConformance:
    record = BoundaryConformance.model_validate(repository.get("boundary_conformance", digest))
    if content_digest(record) != digest or (record.source_digest, record.worker_digest, record.identity_digest) != (source_digest, worker_digest, identity_digest):
        raise ConfigurationError("environment verification unavailable: boundary identity drift")
    with repository.store._lock:
        # Worker execution identities retain their original JSON hash. Reviews
        # address canonical assessment documents, which use a different hash.
        worker_review_digest = record.worker_digest
        worker_document = repository.store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='worker_binding' AND id=?", (record.worker_digest,)
        ).fetchone()
        if worker_document is not None:
            from ..hosts.workers import ManagedWorkerBinding
            worker = ManagedWorkerBinding.model_validate(repository.get("worker_binding", record.worker_digest))
            if worker.digest() != record.worker_digest or content_digest(worker) != worker_document[0]:
                raise ConfigurationError("environment verification unavailable: reviewed worker binding differs")
            worker_review_digest = worker_document[0]
        for reviewed_definition in (record.enforcement_definition_digest, record.effective_policy_digest,
                           record.reviewed_inventory_digest, worker_review_digest):
            reviewed = repository.store._connection.execute(
                "SELECT revoked FROM assessment_reviews WHERE digest=?", (reviewed_definition,)
            ).fetchone()
            if reviewed is None or reviewed[0]:
                raise ConfigurationError("environment verification unavailable: enforcement review missing")
    if not set(record.used_tools).issubset(record.permitted_tools):
        raise ConfigurationError("environment verification unavailable: unpermitted tool used")
    composed = record.schema_version.endswith('.v3')
    if composed:
        from ..hosts.codex_pair_inspection import verify_composed_binding
        selected_spec = verify_composed_binding(repository, record, worker_digest)
    checked: set[str] = set()
    for probe_digest in record.probe_digests:
        probe = BoundaryProbe.model_validate(repository.get("boundary_probe", probe_digest))
        definition = BoundaryProbeDefinition.model_validate(repository.get("boundary_probe_definition", probe.implementation_digest))
        with repository.store._lock:
            review = repository.store._connection.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (probe.implementation_digest,)).fetchone()
        if (content_digest(probe) != probe_digest or probe.worker_digest != worker_digest
                or content_digest(definition) != probe.implementation_digest
                or definition.name != probe.name or probe.observed != definition.expected
                or review is None or review[0] or probe.name in checked):
            raise ConfigurationError("environment verification unavailable: incomplete or conflicting probes")
        evidence = ExecutionEvidence.model_validate(repository.get("execution_evidence", probe.execution_evidence_digest))
        if (content_digest(evidence) != probe.execution_evidence_digest or not evidence.complete
                or evidence.boundary_digest != worker_digest or not evidence.events
                or (definition.executor.kind.value == 'host_managed' and evidence.identity_digest != identity_digest)
                or evidence.events[-1].kind != "execution.completed"
                or not any(event.kind == "artifact.created" and event.evidence_ref == content_digest(probe.observed)
                           for event in evidence.events)):
            raise ConfigurationError("environment verification unavailable: probe execution evidence missing")
        if composed and probe.name == 'callback_authority':
            from ..hosts.codex_pair_inspection import verify_composed_callback
            verify_composed_callback(repository, record, probe, definition, evidence, selected_spec)
        checked.add(probe.name)
    required = REQUIRED_PROBES | {"candidate_access"} if record.schema_version.endswith(('.v2', '.v3')) else REQUIRED_PROBES
    if composed:
        required |= COMPOSED_PROBES
    if checked != required:
        raise ConfigurationError("environment verification unavailable: required probes missing")
    return record


async def run_boundary_probe(repository: AssessmentRepository, definition_digest: str, *,
                             worker_digest: str, executor: object, plan: AssessmentPlan | ConformanceProbeRequest) -> BoundaryProbe:
    """Run a reviewed harmless probe and bind its actual result, never a success flag."""
    import time

    from ..execution import start_execution
    from ..executors.base import BaseExecutor, ExecutionContext
    from ..models import ActionRequest, ExecutionStatus, ExecutorKind, new_id

    if not isinstance(executor, BaseExecutor):
        raise ConfigurationError("boundary probe requires a controlled executor")
    definition = BoundaryProbeDefinition.model_validate(repository.get("boundary_probe_definition", definition_digest))
    with repository.store._lock:
        review = repository.store._connection.execute("SELECT revoked FROM assessment_reviews WHERE digest=?", (definition_digest,)).fetchone()
    if content_digest(definition) != definition_digest or review is None or review[0]:
        raise ConfigurationError("boundary probe implementation requires operator review")
    managed = definition.executor.kind == ExecutorKind.MANAGED_HOST
    if managed != isinstance(plan, ConformanceProbeRequest):
        raise ConfigurationError("model bootstrap requires a separate reviewed conformance request")
    if managed:
        assert isinstance(plan, ConformanceProbeRequest)
        if plan.operation is not None:
            raise ConfigurationError("worker inspection cannot start a model connectivity turn")
        from .identity import verify_dependencies
        verify_dependencies(plan.executable_dependencies)
        if not plan.executable_dependencies or worker_digest != plan.worker_digest:
            raise ConfigurationError("model bootstrap dependencies differ from the request")
        config = definition.executor.managed_host_config()
        invocation = config.invocation
        if (definition.name != "model_connectivity" or definition.executor.capability != "aeep.conformance.connectivity@1"
                or config.managed_worker is None or invocation is None or invocation.mode != "turn"
                or invocation.supporting_tools or invocation.supporting_skills or invocation.local_profile is not None
                or invocation.dynamic_tools_digest is not None
                or config.artifact is not None or config.input_tree is not None or config.store_prompt or config.store_output
                or config.timeout_seconds > 60 or config.approval_ceiling.rank > 1
                or definition.executor.estimate.cash.upper_bound_usd != 0):
            raise ConfigurationError("model bootstrap is limited to a reviewed isolated connectivity probe")
        from ..hosts.workers import binding_from_config
        worker = binding_from_config(config.managed_worker)
        if worker is None or worker.digest() != worker_digest:
            raise ConfigurationError("model bootstrap worker differs from the reviewed binding")
        from .destinations import require_destination
        require_destination(definition.executor,
            AssessmentEnvironment.model_validate(repository.get("environment", plan.environment_digest)), repository.authorize(plan))
    if (definition.executor.kind.value not in {"command", "python", "mcp", "host_managed"}
            or not definition.executor.idempotent or definition.executor.side_effect.rank > 1):
        raise ConfigurationError("boundary probes must be harmless local tools")
    if definition_digest not in plan.definition_digests or content_digest(repository.get("conformance_request" if managed else "plan", plan.plan_id)) != content_digest(plan):
        raise ConfigurationError("boundary probe is not in the frozen assessment plan")
    attempt = "probe:" + plan.plan_id if managed else new_id("probe-attempt")
    timeout = float(definition.executor.config.get("timeout_seconds", 60))
    repository.reserve(plan, attempt, AssessmentLimits(max_operations=1, max_model_turns=1 if managed else 0, max_elapsed_seconds=timeout + 5), stage="conformance_bootstrap" if managed else "boundary_probe")
    started = time.perf_counter()
    context = ExecutionContext(request=ActionRequest(capability=definition.executor.capability),
                               spec=definition.executor, estimate=definition.executor.estimate,
                               attempt=1, attempt_id=attempt,
                               invocation_check=lambda: (repository.authorize(plan), worker_digest)[1])

    async def invoke(journal: EventJournal) -> RawExecution:
        raw = await executor.execute(context)
        nested = raw.metadata.get("execution_evidence")
        if nested is not None:
            adapter_evidence = ExecutionEvidence.model_validate(nested)
            digest = repository.put("execution_evidence", adapter_evidence.digest(), adapter_evidence)
            journal.append("artifact.created", "adapter-evidence", evidence_ref=digest)
        raw.metadata["boundary_digest"] = worker_digest
        if raw.status == ExecutionStatus.SUCCESS and isinstance(raw.output, dict):
            journal.append("artifact.created", "probe-result", evidence_ref=content_digest(raw.output))
        return raw

    raw = None
    with persist_execution_events(lambda journal_id, event: repository.put(
            "execution_event", journal_id + ":" + str(event.sequence), event)):
        handle = start_execution(attempt, executor.capabilities().adapter, invoke)
        try:
            raw = await handle.task
        finally:
            repository.finish_operation(attempt, elapsed_seconds=time.perf_counter() - started,
                                        accounting=raw.accounting if raw else None,
                                        resources=raw.resources if raw else None)
    evidence = ExecutionEvidence.model_validate(raw.metadata["execution_evidence"])
    evidence_digest = repository.put("execution_evidence", evidence.digest(), evidence)
    if not evidence.complete or raw.status != ExecutionStatus.SUCCESS or not isinstance(raw.output, dict):
        raise ConfigurationError("boundary probe returned no complete observation")
    probe = BoundaryProbe(probe_id=new_id("probe"), name=definition.name,
                          implementation_digest=definition_digest, worker_digest=worker_digest,
                          execution_evidence_digest=evidence_digest, observed=raw.output)
    repository.put("boundary_probe", probe.probe_id, probe)
    return probe


def prepare_model_probe(service: object, *, source_plan_id: str, definition: BoundaryProbeDefinition) -> ConformanceProbeRequest:
    """Store an inert, one-turn request. Only an operator review can authorize it."""
    from .identity import runtime_dependencies
    from .service import AssessmentService

    if not isinstance(service, AssessmentService):
        raise TypeError('assessment service required')
    from ..hosts.workers import binding_from_config
    prior = AssessmentPlan.model_validate(service.repository.get('plan',source_plan_id))
    worker = binding_from_config(definition.executor.managed_host_config().managed_worker)
    if worker is None:
        raise ConfigurationError('model bootstrap requires an isolated worker')
    definition_digest = service.repository.put('boundary_probe_definition', content_digest(definition), definition)
    environment = AssessmentEnvironment(environment_id='bootstrap-'+worker.worker_id,kind='codex_sandbox',
        identity={'purpose':'connectivity conformance only','worker_digest':worker.digest()})
    environment_digest = service.repository.put('environment',content_digest(environment),environment)
    dependencies = runtime_dependencies()
    from .models import RecipeRuntimeBinding
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = service.repository.put('probe_runtime',content_digest(runtime),runtime)
    request = ConformanceProbeRequest(subject_digest=prior.subject_digest,recipe_digest=prior.recipe_digest,
        mapping_digest=definition_digest,environment_digest=environment_digest,authorization_id=prior.authorization_id,
        definition_digests=[definition_digest,environment_digest,runtime_digest,prior.recipe_digest],
        worker_digest=worker.digest(),executable_dependencies=dependencies)
    service.repository.put('conformance_request',request.plan_id,request)
    return request


async def execute_model_probe(service: object, request_id: str) -> BoundaryProbe:
    from .service import AssessmentService

    if not isinstance(service, AssessmentService):
        raise TypeError('assessment service required')
    request = ConformanceProbeRequest.model_validate(service.repository.get('conformance_request',request_id))
    service.repository.authorize(request)
    definition = BoundaryProbeDefinition.model_validate(service.repository.get('boundary_probe_definition',request.mapping_digest))
    router = service.router._campaign_router([definition.executor],plan_digest=content_digest(request),
        database=service.directory / request.plan_id / 'bootstrap.sqlite3')
    try:
        return await run_boundary_probe(service.repository, request.mapping_digest,worker_digest=request.worker_digest,
            executor=router._executor_for(definition.executor.kind),plan=request)
    finally:
        await router.close()
