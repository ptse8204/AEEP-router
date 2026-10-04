"""Comparison choices describe experiments; they never grant execution authority."""

from __future__ import annotations

from typing import Any

from ..models import ExecutorKind, ExecutorSpec
from ..qualification import behavior_fingerprint
from .models import (
    AssessmentComparison,
    AssessmentSubject,
    ComparisonArm,
    ComparisonStructure,
    IncrementalExperiment,
)

DESCRIPTIONS = {
    "direct": "Test a callable implementation against the configured baseline and reference.",
    "controlled_agent": "Measure the effect of adding this plugin to the same model and supporting tools.",
    "workflow": "Measure the complete configured workflow, including its dependencies and setup.",
}


def arm(spec: ExecutorSpec, dependencies: list[ExecutorSpec]) -> ComparisonArm:
    required = spec.config.get("assessment_workflow", {}).get("executor_fingerprints", {})
    return ComparisonArm(
        executor_id=spec.id, fingerprint=behavior_fingerprint(spec),
        dependencies={item.id: behavior_fingerprint(item) for item in dependencies if item.id in required},
        host_config=spec.managed_host_config().model_dump(mode="json") if spec.kind == ExecutorKind.MANAGED_HOST else None,
    )


def choices(subject: AssessmentSubject, candidate: ExecutorSpec, baseline: ExecutorSpec, *, experiment: IncrementalExperiment | None = None) -> dict[str, Any]:
    workflow = "assessment_workflow" in candidate.config
    invocation = candidate.managed_host_config().invocation if candidate.kind == ExecutorKind.MANAGED_HOST else None
    skill = invocation is not None and invocation.mode == "skill"
    recommended: ComparisonStructure = "workflow" if workflow else "controlled_agent" if skill else "workflow" if candidate.kind == ExecutorKind.MANAGED_HOST and (invocation is None or invocation.mode != "mcp_tool") else "direct"
    reasons: dict[str, list[str]] = {key: [] for key in DESCRIPTIONS}
    if workflow or (candidate.kind == ExecutorKind.MANAGED_HOST and (invocation is None or invocation.mode != "mcp_tool")):
        reasons["direct"].append("Select a directly callable tool; this candidate is an agent or workflow.")
    if not skill or baseline.kind != ExecutorKind.MANAGED_HOST:
        reasons["controlled_agent"].append("Requires an explicit candidate skill and a managed-host baseline.")
    else:
        assert invocation is not None
        # Worker names select independent processes; they do not change the
        # experimental model, permissions, or supporting tools.
        excluded = {"invocation"}
        if experiment is not None:
            excluded.add("managed_worker")  # Exact reviewed differences are checked by define and conformance.
        if candidate.managed_host_config().adapter_id.split(":", 1)[0] == baseline.managed_host_config().adapter_id.split(":", 1)[0]:
            excluded.add("adapter_id")
        left = candidate.managed_host_config().model_dump(mode="json", exclude=excluded)
        right = baseline.managed_host_config().model_dump(mode="json", exclude=excluded)
        base_invocation = baseline.managed_host_config().invocation
        if left != right or base_invocation is None or base_invocation.mode != "turn" or invocation.supporting_tools != base_invocation.supporting_tools or invocation.supporting_skills != base_invocation.supporting_skills:
            reasons["controlled_agent"].append("Model settings, instructions, permissions and supporting tools must match; only the selected skill may differ.")
    if candidate.kind == baseline.kind == ExecutorKind.MANAGED_HOST:
        left_config, right_config = candidate.managed_host_config(), baseline.managed_host_config()
        if left_config.adapter_id.split(":", 1)[0] != right_config.adapter_id.split(":", 1)[0]:
            for key in ("controlled_agent", "workflow"):
                reasons[key].append("Both plugin-comparison arms must use the same adapter; changing adapters is a separate experiment.")
        if left_config.managed_worker is not None or right_config.managed_worker is not None:
            from ..errors import ConfigurationError
            from ..hosts.workers import binding_from_config, validate_worker_pair
            left_worker = binding_from_config(left_config.managed_worker)
            right_worker = binding_from_config(right_config.managed_worker)
            try:
                if left_worker is None or right_worker is None:
                    raise ConfigurationError("Both comparison arms require isolated worker bindings")
                validate_worker_pair(left_worker, right_worker)
            except ConfigurationError as exc:
                for key in ("controlled_agent", "workflow"):
                    reasons[key].append(str(exc))
    # Dependency metadata is a declaration, not a reviewed mapping. Unknown skill
    # requirements are deliberately visible even when front matter omits tools.
    requirements = [str(item) for item in subject.declarations.get("missing", [])]
    runtime_requirements = [item for item in requirements if item.startswith("Skill runtime dependency") ]
    if invocation is not None and skill and runtime_requirements and not invocation.supporting_tools:
        for key in ("controlled_agent", "workflow"):
            reasons[key].extend(runtime_requirements)
    return {
        "recommended": recommended,
        "choices": [{"structure": key, "description": description, "available": not reasons[key], "reasons": reasons[key]} for key, description in DESCRIPTIONS.items()],
        "dependency_review": requirements,
    }


def define(structure: ComparisonStructure, candidate: ExecutorSpec, baseline: ExecutorSpec, dependencies: list[ExecutorSpec], reference: ExecutorSpec | None, *, experiment: IncrementalExperiment | None = None) -> AssessmentComparison:
    if experiment is not None:
        from ..errors import ConfigurationError
        by_id = {spec.id: spec for spec in dependencies}
        for challenger in experiment.challengers:
            if challenger.executor_id not in by_id or arm(by_id[challenger.executor_id], dependencies) != challenger:
                raise ConfigurationError("challenger differs from its reviewed route mapping")
        if experiment.stage == 'aeep_value' and (candidate.kind != ExecutorKind.MANAGED_HOST or baseline.kind != ExecutorKind.MANAGED_HOST):
            raise ConfigurationError('three-way value requires managed hosts')
        if candidate.kind == ExecutorKind.MANAGED_HOST or baseline.kind == ExecutorKind.MANAGED_HOST:
            validate_incremental_hosts(candidate, baseline, by_id, experiment)
    return AssessmentComparison(schema_version="assessment.comparison.v2" if experiment else "assessment.comparison.v1", structure=structure, candidate=arm(candidate, dependencies), baseline=arm(baseline, dependencies), reference=arm(reference, []) if reference else None, experiment=experiment,
                                primary_condition="fresh-worker" if experiment and candidate.kind == ExecutorKind.MANAGED_HOST else "router-fresh")


def validate_incremental_hosts(candidate: ExecutorSpec, baseline: ExecutorSpec,
                               dependencies: dict[str, ExecutorSpec], experiment: IncrementalExperiment) -> None:
    from ..errors import ConfigurationError
    from ..hosts.workers import binding_from_config, validate_worker_pair

    members = [candidate, baseline, *(dependencies[item.executor_id] for item in experiment.challengers)]
    if any(item.kind != ExecutorKind.MANAGED_HOST for item in members):
        raise ConfigurationError("incremental agent arms require the same managed adapter")
    base = baseline.managed_host_config()
    base_worker = binding_from_config(base.managed_worker)
    excluded = {"adapter_id", "managed_worker", "invocation"}
    if base_worker is None or base.invocation is None or base.invocation.mode != "turn":
        raise ConfigurationError("incremental control requires an isolated candidate-free turn environment")
    if experiment.stage == "aeep_value":
        three_way_workers = [binding_from_config(item.managed_host_config().managed_worker) for item in members]
        if any(worker is None for worker in three_way_workers):
            raise ConfigurationError("three-way arms require isolated worker bindings")
        for index, worker in enumerate(three_way_workers):
            assert worker is not None
            for other in three_way_workers[index + 1:]:
                assert other is not None
                validate_worker_pair(worker, other)
    for member in members:
        config = member.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        if worker is None or config.invocation is None or config.adapter_id.split(':', 1)[0] != base.adapter_id.split(':', 1)[0]:
            raise ConfigurationError("incremental arms require pinned workers on the same adapter")
        if member.id != baseline.id:
            validate_worker_pair(worker, base_worker)
        high = experiment.higher_compute is not None and member.id == experiment.higher_compute.executor_id
        ignored = excluded | ({"reasoning_efforts", "timeout_seconds"} if high else set())
        if config.model_dump(exclude=ignored) != base.model_dump(exclude=ignored):
            raise ConfigurationError("incremental arms differ in shared instructions, model or resource policy")
        if high and (config.timeout_seconds != base.timeout_seconds * 2 or len(config.reasoning_efforts) != 1
                     or config.reasoning_efforts == base.reasoning_efforts):
            raise ConfigurationError("higher-compute arm requires distinct pinned effort and twice the deadline")
        invocation = config.invocation
        if experiment.stage == 'aeep_value' and invocation.supporting_tools != base.invocation.supporting_tools:
            raise ConfigurationError('three-way ordinary supporting tools differ')
        normal = experiment.normal_host is not None and member.id == experiment.normal_host.executor_id
        if not normal and (invocation.local_profile != base.invocation.local_profile
                or invocation.native_catalog != base.invocation.native_catalog):
            raise ConfigurationError("incremental arms differ in shared local/catalog profiles")
        if normal and experiment.stage == "aeep_value":
            reviewed_skills = {skill.path: skill for skill in base.invocation.supporting_skills}
            if any(reviewed_skills.get(skill.path) != skill for skill in invocation.supporting_skills):
                raise ConfigurationError("three-way normal supporting skills must be an exact subset of discovery skills")
        elif invocation.supporting_skills != base.invocation.supporting_skills:
            raise ConfigurationError("incremental arms differ in reviewed background skills")
        if member.id == candidate.id:
            dynamic_candidate = (invocation.mode == "dynamic_tool"
                and invocation.dynamic_tools_digest is not None
                and experiment.stage in {"qualification", "aeep_value"})
            if (invocation.mode != "skill" and not dynamic_candidate) or (invocation.exposure or "required") != experiment.exposure:
                raise ConfigurationError("candidate invocation does not match the frozen exposure mode")
        elif invocation.mode != "turn":
            raise ConfigurationError("control arms cannot target the candidate")
