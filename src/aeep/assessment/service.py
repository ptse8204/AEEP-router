"""Operator-reviewed assessments run through BenchmarkRunner, never ordinary routing."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import time
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from itertools import islice
from pathlib import Path
from typing import Any, cast

from ..benchmarking import (
    AssessmentBenchmarkCondition,
    BenchmarkCampaignReport,
    BenchmarkRoute,
    BenchmarkRunner,
    BenchmarkSplit,
    BenchmarkSuite,
    BenchmarkTrial,
)
from ..errors import ConfigurationError
from ..hosts.registry import ManagedHostRegistry
from ..models import ExecutorKind, ExecutorSpec, ResourceVector, StrictModel, new_id, utc_now
from ..qualification import (
    QualificationCondition,
    QualificationReport,
    RouteCandidate,
    activate_qualified_state,
    behavior_fingerprint,
)
from ..router import Router
from ..validators import ValidationContext, run_validators
from .identity import local_dependencies, runtime_dependencies, verify_dependencies, verify_subject
from .models import (
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentOperationLedger,
    AssessmentPlan,
    AssessmentProgress,
    AssessmentReport,
    AssessmentRunBinding,
    AssessmentSetupCost,
    AssessmentSubject,
    ComparisonStructure,
    DefinitionProposal,
    GraderValidationEvidence,
    IncrementalExperiment,
    PilotPolicy,
    RecipeCaseSet,
    RecipeDefinition,
    ReusableBaselineArtifact,
    ReviewedMapping,
    ScopedAdmission,
    content_digest,
    recipe_implementation_digest,
)
from .recipes import (
    generate_case,
    generate_reviewed_case,
    recipe_features,
    reference_csv,
    reference_search,
    reference_text,
    shipped_recipe,
)
from .reporting import apply_assessment_costs, fit_report
from .repository import AssessmentRepository


def benchmark_route(spec: ExecutorSpec) -> BenchmarkRoute:
    if "assessment_workflow" in spec.config:
        from .adapters import WorkflowAdapter
        adapter = WorkflowAdapter.model_validate(spec.config["assessment_workflow"])
        return BenchmarkRoute(route_id=spec.id, workflow=adapter.workflow, case_input_bindings=adapter.case_input_bindings, validation_output_path=spec.config.get("assessment_adapter", {}).get("output_pointer"))
    return BenchmarkRoute(route_id=spec.id, executor_id=spec.id)


class HostInventoryRecord(StrictModel):
    plan_id: str
    executor_id: str
    declarations: dict[str, Any]
    elapsed_seconds: float


class RuntimeBinding(StrictModel):
    plan_id: str
    executor_id: str
    digest: str


class AssessmentService:
    def __init__(self, router: Router, directory: Path) -> None:
        self.router = router
        self.repository = AssessmentRepository(router.store)
        self.directory = directory.resolve()

    def inspect_local(self, location: Path, *, kind: str = "plugin") -> AssessmentSubject:
        """Read bounded local metadata only; never start a plugin or resolve credentials."""
        started, cpu_started = time.perf_counter(), time.process_time()
        if location.is_symlink():
            raise ConfigurationError("select an explicit local path without symlinks")
        location = location.resolve(strict=True)
        codex_home = Path(os.environ.get("CODEX_HOME", str(Path.home() / ".codex"))).resolve()
        if location.is_relative_to(codex_home) and not location.is_relative_to(
            codex_home / "plugins"
        ):
            raise ConfigurationError(
                "select a plugin package; Codex state directories are excluded"
            )
        files = sorted(islice(location.rglob("*"), 2001)) if location.is_dir() else [location]
        if len(files) > 2000:
            raise ConfigurationError("plugin inventory exceeds the static inspection limit")
        digests: dict[str, str] = {}
        total = 0
        for file in files:
            if file.is_symlink():
                raise ConfigurationError("plugin dependencies may not contain symlinks")
            if not file.is_file():
                continue
            if file.name in {"auth.json", ".env", "credentials.json"}:
                raise ConfigurationError("select the plugin package, not a credential directory")
            total += file.stat().st_size
            if total > 10_000_000:
                raise ConfigurationError("plugin exceeds the static inspection byte limit")
            digests[str(file.relative_to(location)) if location.is_dir() else file.name] = (
                hashlib.sha256(file.read_bytes()).hexdigest()
            )
        subject = AssessmentSubject.model_validate(
            {
                "subject_id": "subject_"
                + content_digest(
                    {"kind": kind, "location": str(location), "dependencies": digests}
                ),
                "kind": kind,
                "location": str(location),
                "dependency_digests": digests,
                "description": "Locally selected package; declarations are not execution approval.",
            }
        )
        from .intake import declarations

        inspected = declarations(location, digests, kind)
        subject.description = inspected.description
        subject.declarations = inspected.model_dump(mode="json", exclude={"description"})
        if len(inspected.tools) == 1:
            subject.input_schema = inspected.tools[0].get("inputSchema")
            subject.output_schema = inspected.tools[0].get("outputSchema")
        self.repository.put("subject", subject.subject_id, subject)
        cost = AssessmentSetupCost(subject_digest=content_digest(subject), stage="static_inspection", elapsed_seconds=time.perf_counter() - started, cpu_ms=(time.process_time() - cpu_started) * 1000)
        self.repository.put("setup_cost", cost.cost_id, cost)
        return subject

    def propose(
        self,
        *,
        subject_id: str,
        family: str,
        candidate_id: str,
        baseline_id: str,
        authorization_id: str,
        environment: AssessmentEnvironment,
        seed: int = 0,
        structure: ComparisonStructure | None = None,
        _proposal_operation_id: str | None = None,
        case_set_id: str | None = None,
        experiment: IncrementalExperiment | None = None,
        pilot: PilotPolicy | None = None,
        pilot_report_id: str | None = None,
    ) -> AssessmentPlan:
        started, cpu_started = time.perf_counter(), time.process_time()
        subject = AssessmentSubject.model_validate(self.repository.get("subject", subject_id))
        recipe = (
            shipped_recipe(family)
            if family in {"csv", "text", "search"}
            else RecipeDefinition.model_validate(self.repository.get("recipe", family))
        )
        if recipe.implementation_digest != recipe_implementation_digest():
            raise ConfigurationError("recipe implementation changed; renewed review is required")
        candidate = self.router.store.get_route_candidate(candidate_id)
        spec = candidate.spec if candidate is not None else self.router.registry.get(candidate_id)
        baseline = self.router.registry.get(baseline_id)
        mapping = ReviewedMapping(candidate=spec, baseline=baseline)
        challengers = [self.router.registry.get(item.executor_id) for item in experiment.challengers] if experiment else []
        mapping.dependencies.extend(challengers)
        from .comparison import choices, define
        options = choices(subject, spec, baseline, experiment=experiment)
        if structure is None:
            structure = self.remembered_structure(content_digest(subject), content_digest(environment), recipe.capability)
        selected_structure = structure or options["recommended"]
        selection = next(item for item in options["choices"] if item["structure"] == selected_structure)
        reference = None
        reference_id = f"reference.{family}"
        if (experiment is None or experiment.stage != "aeep_value") and baseline.kind == ExecutorKind.MANAGED_HOST and self.router.registry.contains(reference_id) and reference_id not in {candidate_id, baseline_id}:
            reference = self.router.registry.get(reference_id)
            if reference.capability != recipe.capability:
                raise ConfigurationError("configured reference has an incompatible task contract")
            mapping.dependencies.append(reference)
        from .adapters import WorkflowAdapter
        for parent in (spec, baseline, *challengers):
            if "assessment_workflow" in parent.config:
                adapter = WorkflowAdapter.model_validate(parent.config["assessment_workflow"])
                for executor_id, fingerprint in adapter.executor_fingerprints.items():
                    dependency = self.router.registry.get(executor_id)
                    if behavior_fingerprint(dependency) != fingerprint or "assessment_workflow" in dependency.config:
                        raise ConfigurationError("workflow requires current, non-nested configured dependencies")
                    if dependency.id not in {item.id for item in mapping.subjects}:
                        mapping.dependencies.append(dependency)
        recipe_digest = self.repository.put("recipe", content_digest(recipe), recipe)
        if recipe.generator == "record_template:1" or recipe.extension is not None:
            with self.router.store._lock:
                review = self.router.store._connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (recipe_digest,)
                ).fetchone()
            if review is None or review[0]:
                raise ConfigurationError("review the generated recipe before its first execution")
        mapping.executable_dependencies = {**runtime_dependencies(), **({} if environment.kind == "container" else {name: digest for item in mapping.subjects for name, digest in local_dependencies(item).items()})}
        mapping_digest = self.repository.put("mapping", content_digest(mapping), mapping)
        environment_digest = self.repository.put(
            "environment", content_digest(environment), environment
        )
        comparison = define(selected_structure, spec, baseline, mapping.dependencies, reference, experiment=experiment)
        if pilot is not None and spec.kind == ExecutorKind.MANAGED_HOST and spec.managed_host_config().managed_worker is not None:
            comparison.primary_condition = "fresh-worker"
        comparison_digest = self.repository.put("comparison", content_digest(comparison), comparison)
        plan_id = new_id("plan")
        fixture_root = self.directory / plan_id / "fixtures"
        case_set = None
        if recipe.extension is not None:
            if case_set_id is None:
                raise ConfigurationError("materialize the reviewed executable recipe before proposing its campaign")
            case_set = RecipeCaseSet.model_validate(self.repository.get("recipe_case_set", case_set_id))
            if case_set.recipe_digest != recipe_digest or case_set.environment_digest != environment_digest or case_set.seed != seed:
                raise ConfigurationError("generated cases differ from the reviewed recipe, environment or seed")
        cases = case_set.cases if case_set is not None else [
            (
                generate_reviewed_case(recipe, index, seed, split)
                if recipe.generator == "record_template:1"
                else generate_case(family, index, seed, split, fixture_root=fixture_root)[0]
            )
            for split, count in (
                (BenchmarkSplit.QUALIFICATION, 8),
                (BenchmarkSplit.TRAINING, 28),
                (BenchmarkSplit.HOLDOUT, 105),
            )
            for index in range(count)
        ]
        if pilot is not None:
            cases = [case for case in cases if case.split == BenchmarkSplit.QUALIFICATION]
        blocked = list(selection["reasons"])
        if candidate_id == baseline_id:
            blocked.append("candidate and baseline must be different implementations")
        if any(item.capability != recipe.capability for item in (spec, baseline, *challengers)):
            blocked.append("a reviewed adapter mapping to the recipe task contract is required")
        if environment.kind == "codex_sandbox" and any(
            item.kind == ExecutorKind.MANAGED_HOST and item.managed_host_config().invocation is None
            for item in (spec, baseline)
        ):
            blocked.append(
                "Codex assessment requires an explicit isolated invocation configuration"
            )
        for item in mapping.subjects:
            if item.kind in {ExecutorKind.HOST, ExecutorKind.DELEGATE}:
                blocked.append(
                    "delegated placeholders cannot produce completed assessment evidence"
                )
            native_command = "assessment_workflow" not in item.config and (item.kind in {ExecutorKind.COMMAND, ExecutorKind.PYTHON} or (
                item.kind == ExecutorKind.MCP and item.config.get("transport") == "stdio"
            ))
            trusted_config = any(
                configured.id == item.id
                and behavior_fingerprint(configured) == behavior_fingerprint(item)
                for configured in self.router.manifest.executors
            )
            if native_command and not trusted_config and environment.kind != "container":
                blocked.append(
                    "untrusted command/Python trials require a configured container adapter"
                )
        scope: dict[str, list[str | int | bool]] = {}
        combinations: list[dict[str, str | int | bool]] = []
        for case in cases:
            if case.split != BenchmarkSplit.TRAINING:
                continue
            observed = recipe_features(recipe, case.action.input) or {}
            if family == "search" and observed:
                observed["root"] = environment.identity.get("approved_root", "")
            if observed and observed not in combinations:
                combinations.append(observed)
            for key, value in observed.items():
                if value not in scope.setdefault(key, []):
                    scope[key].append(value)
        if family == "search":
            scope["root"] = (
                [environment.identity["approved_root"]]
                if "approved_root" in environment.identity
                else []
            )
        from .pilot import timing_preview
        preceding_pilot = None
        pilot_report = None
        if pilot_report_id is not None:
            timing = timing_preview(self, pilot_report_id, mapping=mapping)
            if timing["proposed_normal_deadline_seconds"] is None:
                raise ConfigurationError("pilot measurements cannot establish a bounded deadline")
            pilot_report = AssessmentReport.model_validate(self.repository.get("report", pilot_report_id))
            preceding_pilot = AssessmentPlan.model_validate(self.repository.get("plan", pilot_report.plan_digest))
        pilot_digest = self.repository.put("pilot_policy", content_digest(pilot), pilot) if pilot else None
        plan = AssessmentPlan(
            schema_version="assessment.plan.v6" if pilot_report else "assessment.plan.v5" if pilot else "assessment.plan.v4" if experiment else "assessment.plan.v3" if case_set is not None else "assessment.plan.v2",
            pilot=pilot,
            pilot_report_digest=content_digest(pilot_report) if pilot_report else None,
            recipe_case_set_digest=content_digest(case_set) if case_set is not None else None,
            preparation_request_ids=([case_set.request_id] if case_set else []) + ([preceding_pilot.plan_id] if preceding_pilot else []) or None,
            comparison=comparison,
            feature_combinations=combinations,
            plan_id=plan_id,
            subject_digest=content_digest(subject),
            recipe_digest=recipe_digest,
            mapping_digest=mapping_digest,
            environment_digest=environment_digest,
            authorization_id=authorization_id,
            candidate_id=candidate_id,
            baseline_id=baseline_id,
            reference_id=reference.id if reference else None,
            definition_digests=[*([experiment.three_way_access_digest] if experiment and experiment.three_way_access_digest else []), recipe_digest, mapping_digest, environment_digest, comparison_digest, *([content_digest(case_set)] if case_set else []), *([pilot_digest] if pilot_digest else []), *([content_digest(pilot_report), content_digest(preceding_pilot)] if pilot_report and preceding_pilot else [])],
            route_fingerprints={item.id: behavior_fingerprint(item) for item in mapping.subjects},
            executable_dependencies=mapping.executable_dependencies,
            suite=BenchmarkSuite(
                suite_id=plan_id,
                domain=recipe.capability,
                seed=seed,
                repetitions=1,
                routes=[
                    benchmark_route(item)
                    for item in ((spec,) if experiment and experiment.stage == "qualification" else (spec, baseline, *challengers, *([reference] if reference else [])))
                ],
                cases=cases,
                conditions=[AssessmentBenchmarkCondition(comparison.primary_condition)],
                sequential_stages=True,
                paired_order=experiment is None or experiment.stage != "aeep_value",
                stop_on_screening_failure=pilot is None,
                baseline_route_id=None if experiment and experiment.stage == "qualification" else baseline_id,
                max_total_cash_usd=Decimal(0),
                deterministic_tools_available=True,
                allow_zero_subscription_weight=True,
            ),
            applicability=scope,
            blocked_reasons=blocked,
        )
        from .pilot import require_separation
        require_separation(self.repository, plan)
        from .pilot import require_linked_pilot
        require_linked_pilot(self.repository, plan)
        with self.router.store._lock:
            preparation = self.router.store._connection.execute(
                "SELECT id FROM assessment_records WHERE kind='setup_cost' "
                "AND json_extract(payload_json, '$.subject_digest')=? "
                "AND json_extract(payload_json, '$.stage')!='generation_and_proposal' ORDER BY rowid",
                (plan.subject_digest,),
            ).fetchall()
        cost = AssessmentSetupCost(cost_id=_proposal_operation_id or new_id("setup"), subject_digest=plan.subject_digest, stage="generation_and_proposal", elapsed_seconds=time.perf_counter() - started, cpu_ms=(time.process_time() - cpu_started) * 1000)
        self.repository.put("setup_cost", cost.cost_id, cost)
        # Freeze shared preparation now. Existing operation IDs prevent another
        # debit when later stages reuse these costs; prior proposals follow their
        # explicit parent-plan/report lineage rather than unrelated definitions.
        plan.setup_cost_ids = [*(str(row[0]) for row in preparation), cost.cost_id]
        if candidate is not None and candidate.source_id.startswith("reviewed-definition:"):
            proposal = DefinitionProposal.model_validate(self.repository.get("definition_proposal", candidate.source_id.removeprefix("reviewed-definition:")))
            if behavior_fingerprint(proposal.candidate) != behavior_fingerprint(spec):
                raise ConfigurationError("generated candidate differs from its reviewed proposal")
            if proposal.planning_request_id:
                plan.planning_request_ids = [proposal.planning_request_id]
        if case_set is not None:
            with self.router.store._immediate_transaction() as connection:
                if connection.execute("SELECT 1 FROM assessment_records WHERE kind='plan' AND json_extract(payload_json, '$.recipe_case_set_digest')=?", (content_digest(case_set),)).fetchone():
                    raise ConfigurationError("generate fresh cases for a changed executable-recipe plan")
                connection.execute("INSERT INTO assessment_records VALUES ('plan', ?, ?, ?)", (plan.plan_id, content_digest(plan), plan.model_dump_json()))
        else:
            self.repository.put("plan", plan.plan_id, plan)
        return plan

    def status(self, assessment_id: str) -> dict[str, Any]:
        from .recovery import mark_dead_worker
        mark_dead_worker(self.repository, assessment_id)
        with self.router.store._lock:
            row = self.router.store._connection.execute(
                "SELECT * FROM assessment_jobs WHERE id=?", (assessment_id,)
            ).fetchone()
        if row is None:
            raise ConfigurationError("unknown assessment")
        return AssessmentProgress.model_validate(dict(row)).model_dump(mode="json")

    def remembered_structure(self, subject_digest: str, environment_digest: str, capability: str) -> ComparisonStructure | None:
        with self.router.store._lock:
            previous = self.router.store._connection.execute("SELECT payload_json FROM assessment_records WHERE kind='plan' AND json_extract(payload_json, '$.subject_digest')=? AND json_extract(payload_json, '$.environment_digest')=? AND json_extract(payload_json, '$.suite.domain')=? ORDER BY rowid DESC LIMIT 1", (subject_digest, environment_digest, capability)).fetchone()
        remembered = AssessmentPlan.model_validate_json(previous[0]).comparison if previous else None
        return remembered.structure if remembered else None

    def comparison_choices(self, plan_id: str) -> dict[str, Any]:
        from .comparison import choices
        plan = AssessmentPlan.model_validate(self.repository.get("plan", plan_id))
        mapping = ReviewedMapping.model_validate(self.repository.get("mapping", plan.mapping_digest))
        subject = AssessmentSubject.model_validate(self.repository.get("subject", plan.subject_digest))
        return {**choices(subject, mapping.candidate, mapping.baseline, experiment=plan.comparison.experiment if plan.comparison else None), "selected": plan.comparison.structure if plan.comparison else None, "plan_id": plan_id}

    def select_structure(self, plan_id: str, structure: ComparisonStructure) -> AssessmentPlan:
        plan = AssessmentPlan.model_validate(self.repository.get("plan", plan_id))
        if plan.comparison is not None and plan.comparison.experiment is not None:
            raise ConfigurationError("changing an incremental structure requires a new explicit experiment and fresh cases")
        self.repository.authorize(plan)
        self._verify_dependencies(plan)
        recipe = RecipeDefinition.model_validate(self.repository.get("recipe", plan.recipe_digest))
        family = recipe.generator.split(":")[1] if recipe.generator.startswith("builtin:") else plan.recipe_digest
        operation_id = new_id("comparison_proposal")
        self.repository.reserve(plan, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="generation_and_proposal")
        started, cpu_started = time.perf_counter(), time.process_time()
        try:
            return self.propose(subject_id=plan.subject_digest, family=family, candidate_id=plan.candidate_id, baseline_id=plan.baseline_id, authorization_id=plan.authorization_id, environment=AssessmentEnvironment.model_validate(self.repository.get("environment", plan.environment_digest)), seed=plan.suite.seed + 1, structure=structure, _proposal_operation_id=operation_id, pilot=plan.pilot, pilot_report_id=plan.pilot_report_digest)
        finally:
            self.repository.finish_operation(operation_id, elapsed_seconds=time.perf_counter() - started, resources=ResourceVector(cpu_ms=(time.process_time() - cpu_started) * 1000))

    def budget_preview(self, plan_id: str) -> dict[str, Any]:
        plan = AssessmentPlan.model_validate(self.repository.get("plan", plan_id))
        mapping = ReviewedMapping.model_validate(self.repository.get("mapping", plan.mapping_digest))
        turns_per_case = 0
        operations_per_case = 0
        cash_per_case: Decimal | None = Decimal(0)
        trial_seconds_per_case = 0.0
        eligibility: list[dict[str, Any]] = []
        workers: list[dict[str, Any]] = []
        subjects = {item.id: item for item in mapping.subjects}
        for route in plan.suite.routes:
            arm = subjects[route.route_id]
            role = "candidate" if arm.id == plan.candidate_id else "baseline" if arm.id == plan.baseline_id else "comparison"
            members = [arm]
            if route.workflow is not None:
                members = []
                for step in route.workflow.steps:
                    allowed = step.action.constraints.allowed_executor_ids
                    if allowed is None or len(allowed) != 1:
                        raise ConfigurationError("workflow assessment requires exact step routes")
                    members.append(subjects[allowed[0]])
            operations_per_case += len(members)
            if cash_per_case is not None:
                if any(member.estimate.cash.upper_bound_usd is None for member in members):
                    cash_per_case = None
                else:
                    cash_per_case += sum((member.estimate.cash.upper_bound_usd or Decimal(0) for member in members), Decimal(0))
            worker_ids = set()
            trial_seconds_per_case += 5 + sum(float(member.config.get("timeout_seconds", 60)) for member in members)
            for member in members:
                if member.kind == ExecutorKind.MANAGED_HOST:
                    config = member.managed_host_config()
                    invocation = config.invocation
                    from ..execution import ExecutorCapabilities
                    capabilities = (self.router.managed_hosts.capabilities(config.adapter_id)
                                    if config.adapter_id in self.router.managed_hosts.ids()
                                    else ExecutorCapabilities(adapter=config.adapter_id))
                    required_capabilities = sorted({*member.required_capabilities, "identity", "usage"})
                    missing = [name for name in required_capabilities if capabilities.features.get(name) != "supported"]
                    eligibility.append({"executor_id": member.id, "adapter": config.adapter_id,
                                        "adapter_version": capabilities.version, "support_status": capabilities.support_status,
                                        "eligible": not missing, "missing_capabilities": missing,
                                        "permission_verification": "checked_separately_before_invocation",
                                        "managed_worker_configured": config.managed_worker is not None})
                    turns_per_case += int(invocation is None or invocation.mode != "mcp_tool")
                    if invocation is None or invocation.mode != "mcp_tool":
                        worker_ids.add(config.adapter_id)
            workers.append({"role": role, "executor_id": arm.id, "model_worker_profiles": sorted(worker_ids)})
        required = len(plan.suite.cases) * plan.suite.repetitions * len(plan.suite.conditions) * turns_per_case
        screening = sum(case.split == BenchmarkSplit.QUALIFICATION for case in plan.suite.cases) * plan.suite.repetitions * len(plan.suite.conditions) * turns_per_case
        with self.router.store._lock:
            state = self.router.store._connection.execute("SELECT model_turns, elapsed_seconds, operations, cash_usd FROM assessment_grants WHERE id=?", (plan.authorization_id,)).fetchone()
        remaining: dict[str, Any] | None = None
        if state is not None:
            grant = self.repository.effective_grant(plan.authorization_id)
            remaining = {"model_turns": max(0, grant.limits.max_model_turns - state[0]), "elapsed_seconds": max(0, grant.limits.max_elapsed_seconds - state[1]), "operations": max(0, grant.limits.max_operations - state[2]), "cash_usd": str(max(Decimal(0), grant.limits.max_cash_usd - Decimal(state[3])))}
        from .budget import campaign_allowances
        campaign = campaign_allowances(self, plan, operations_per_case=operations_per_case,
            turns_per_case=turns_per_case, seconds_per_case=trial_seconds_per_case,
            cash_per_case=cash_per_case, remaining=remaining)
        return {"campaign_allowance": campaign, "purpose": "timing_pilot" if plan.pilot else "assessment", "adapter_eligibility": eligibility, "minimum_trial_model_turns": required,
                "trial_elapsed_upper_seconds": len(plan.suite.cases) * plan.suite.repetitions * len(plan.suite.conditions) * trial_seconds_per_case,
                "evaluation_stage": plan.comparison.experiment.stage if plan.comparison and plan.comparison.experiment else None,
                "screening_trial_model_turns": screening, "workers": workers, "model_worker_profile_count": len({identity for worker in workers for identity in worker["model_worker_profiles"]}), "measurement_concurrency": 1, "remaining": remaining, "explanation": "Counts adapter model turns, not internal inference steps. Full planned trials exclude planning, warm-ups and retries. Profiles use fresh conversations per trial; timed trials run sequentially. Early rejection can use less; elapsed time is unknown until measured. Per-operation limits remain enforced."}

    async def inspect_host(self, plan_id: str, executor_id: str) -> HostInventoryRecord:
        plan = AssessmentPlan.model_validate(self.repository.get("plan", plan_id))
        if executor_id not in plan.route_fingerprints:
            raise ConfigurationError("host inventory must belong to a reviewed assessment route")
        mapping = self._verify_dependencies(plan)
        spec = next(
            item for item in (mapping.candidate, mapping.baseline) if item.id == executor_id
        )
        if spec.kind != ExecutorKind.MANAGED_HOST:
            raise ConfigurationError("host inventory requires a managed-host route")
        adapter_id = spec.managed_host_config().adapter_id
        owned_adapter = adapter_id not in self.router.managed_hosts.ids()
        registry = ManagedHostRegistry() if owned_adapter else self.router.managed_hosts
        if owned_adapter:
            registry.configure([spec], principal_salt=self.router.store.host_principal_key,
                               manifest_directory=self.router.manifest_path.parent if self.router.manifest_path else None)
        adapter = registry.get(adapter_id)
        inventory = getattr(adapter, "inventory", None)
        if inventory is None:
            raise ConfigurationError("configured host does not support inventory")
        operation_id = new_id("inventory")
        self.repository.reserve(
            plan, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="introspection"
        )
        started = time.perf_counter()
        # Inventory can start configured servers. Authorization and a durable debit precede it.
        import asyncio

        try:
            declarations = await asyncio.wait_for(inventory(), timeout=30)
        finally:
            if owned_adapter:
                await adapter.close()
            self.repository.finish_operation(operation_id, elapsed_seconds=time.perf_counter() - started)
        elapsed = time.perf_counter() - started
        record = HostInventoryRecord(
            plan_id=plan_id,
            executor_id=executor_id,
            declarations=declarations,
            elapsed_seconds=elapsed,
        )
        self.repository.put("host_inventory", operation_id, record)
        return record

    def enqueue(self, plan_id: str) -> str:
        plan = AssessmentPlan.model_validate(self.repository.get("plan", plan_id))
        self.repository.authorize(plan)
        if plan.blocked_reasons:
            raise ConfigurationError("; ".join(plan.blocked_reasons))
        with self.router.store._immediate_transaction() as connection:
            existing = connection.execute(
                "SELECT id FROM assessment_jobs WHERE plan_id=? ORDER BY rowid DESC LIMIT 1",
                (plan_id,),
            ).fetchone()
            if existing is not None:
                return str(existing[0])
            assessment_id = new_id("assessment")
            connection.execute(
                "INSERT INTO assessment_jobs(id, plan_id, state) VALUES (?, ?, 'queued')",
                (assessment_id, plan_id),
            )
        return assessment_id

    def cancel(self, assessment_id: str) -> None:
        self.status(assessment_id)
        with self.router.store._immediate_transaction() as connection:
            connection.execute(
                "UPDATE assessment_jobs SET state='cancelled' WHERE id=? AND state IN ('queued', 'running')",
                (assessment_id,),
            )

    async def admit_resolved(self, report_id: str) -> ScopedAdmission:
        """Refresh host identity for an operator admitting evidence in a new process."""
        report = AssessmentReport.model_validate(self.repository.get("report", report_id))
        plan = AssessmentPlan.model_validate(self.repository.get("plan", report.plan_digest))
        mapping = self._verify_dependencies(plan)
        for spec in mapping.subjects:
            if spec.kind == ExecutorKind.MANAGED_HOST:
                operation_id = new_id("admission_identity")
                self.repository.reserve(plan, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="admission_identity")
                started = time.perf_counter()
                try:
                    await self.router._resolve_host_identity(spec)
                finally:
                    self.repository.finish_operation(operation_id, elapsed_seconds=time.perf_counter() - started)
        return self.admit(report_id)

    def admit(self, report_id: str) -> ScopedAdmission:
        report = AssessmentReport.model_validate(self.repository.get("report", report_id))
        plan = AssessmentPlan.model_validate(self.repository.get("plan", report.plan_digest))
        recipe = RecipeDefinition.model_validate(self.repository.get("recipe", plan.recipe_digest))
        campaign = BenchmarkCampaignReport.model_validate(
            self.repository.get("campaign", report.campaign_digest)
        )
        ledger = AssessmentOperationLedger.model_validate(self.repository.get("operation_ledger", report.operation_ledger_digest)) if report.operation_ledger_digest else None
        verified = fit_report(plan, recipe, campaign, ledger=ledger)
        if (
            verified.outcome != "useful_within_scope"
            or not verified.qualification_passed
            or report.outcome != verified.outcome
        ):
            raise ConfigurationError(
                "admission requires passed qualification and a measured benefit"
            )
        if report.grader_validation_digest is None:
            raise ConfigurationError("admission requires independent grader-validation evidence")
        assert report.grader_validation_digest is not None
        validation = GraderValidationEvidence.model_validate(self.repository.get("grader_validation", report.grader_validation_digest))
        with self.router.store._lock:
            graded = self.router.store._connection.execute(
                "SELECT 1 FROM assessment_records r JOIN assessment_operations o ON o.id=r.id JOIN assessment_records s ON s.id=o.id AND s.kind='operation_start' WHERE r.kind='grader_validation' AND r.digest=? AND json_extract(s.payload_json, '$.plan_id')=? AND json_extract(s.payload_json, '$.stage')='grader_validation' AND o.state='complete'",
                (report.grader_validation_digest, plan.plan_id),
            ).fetchone()
        if (graded is None or content_digest(validation) != report.grader_validation_digest
                or validation.recipe_digest != plan.recipe_digest
                or len(set(validation.independent_fixture_digests)) < 2
                or validation.generator_fixture_digests != [content_digest(case) for case in plan.suite.cases[:8]]):
            raise ConfigurationError("admission grader-validation evidence does not match the plan")
        mapping = self._verify_dependencies(plan)
        for spec in mapping.subjects:
            if spec.kind == ExecutorKind.MANAGED_HOST:
                digest = verified.host_runtime_digests.get(spec.id)
                if not digest or self.router.store.host_runtime_digests.get(spec.id) != (behavior_fingerprint(spec), digest):
                    raise ConfigurationError("managed-host admission requires resolved runtime identity")
        from .boundary import require_managed_boundaries
        environment = AssessmentEnvironment.model_validate(self.repository.get("environment", plan.environment_digest))
        require_managed_boundaries(self.repository, environment, mapping.subjects, verified.host_runtime_digests)
        with (
            self.router._route_activation_lock,
            self.router.store._immediate_transaction() as connection,
        ):
            grant = self.repository.authorize(plan)
            if not grant.automatic_admission:
                raise ConfigurationError(
                    "standing authorization does not permit automatic admission"
                )
            existing = connection.execute(
                "SELECT admission_id, revoked, revoked_at FROM assessment_admissions WHERE executor_id=?",
                (plan.candidate_id,),
            ).fetchone()
            if existing is not None:
                previous = ScopedAdmission.model_validate(
                    self.repository.get("admission", existing[0])
                )
                previous_report = AssessmentReport.model_validate(
                    self.repository.get("report", previous.report_id)
                )
                if existing[1] and (
                    existing[2] is None
                    or report.created_at <= datetime.fromisoformat(existing[2])
                    or previous_report.campaign_digest == report.campaign_digest
                ):
                    raise ConfigurationError("revoked admission requires fresh assessment evidence")
                if previous.report_id == report_id:
                    return previous
            candidate = self.router.store.get_route_candidate(plan.candidate_id)
            if candidate is None:
                candidate = RouteCandidate(
                    executor_id=plan.candidate_id,
                    source_id="local-assessment",
                    capability=mapping.candidate.capability,
                    behavior_fingerprint=behavior_fingerprint(mapping.candidate),
                    spec=mapping.candidate.model_copy(deep=True),
                )
            qualification = QualificationReport(
                candidate_id=candidate.candidate_id,
                behavior_fingerprint=plan.route_fingerprints[plan.candidate_id],
                static_checks={"reviewed_mapping": True, "validated_grader": True},
                dynamic_cases=verified.distinct_holdout_cases,
                passed_cases=verified.distinct_holdout_cases,
                dynamic_runs=verified.distinct_holdout_cases
                * plan.suite.repetitions
                * len(plan.suite.conditions),
                passed_runs=verified.distinct_holdout_cases
                * plan.suite.repetitions
                * len(plan.suite.conditions),
                passed=True,
                source_evidence_ids=[report.report_id],
                valid_until=grant.expires_at,
                conditions=[condition.value if isinstance(condition, AssessmentBenchmarkCondition) else QualificationCondition(condition.value) for condition in plan.suite.conditions],
            )
            admission = ScopedAdmission(
                schema_version="assessment.admission.v3" if plan.comparison and plan.comparison.experiment else "assessment.admission.v2" if plan.comparison else "assessment.admission.v1",
                comparison=plan.comparison,
                feature_combinations=plan.feature_combinations,
                executor_id=plan.candidate_id,
                baseline_id=plan.baseline_id,
                capability=recipe.capability,
                candidate_fingerprint=plan.route_fingerprints[plan.candidate_id],
                executable_dependencies=plan.executable_dependencies,
                baseline_fingerprint=plan.route_fingerprints[plan.baseline_id],
                host_runtime_digests=verified.host_runtime_digests,
                subject_digest=plan.subject_digest,
                definition_digests=plan.definition_digests,
                recipe_digest=plan.recipe_digest,
                mapping_digest=plan.mapping_digest,
                environment_digest=plan.environment_digest,
                extractor=recipe.extractor,
                applicability=plan.applicability,
                qualification_report_id=qualification.report_id,
                report_id=report_id,
                authorization_id=plan.authorization_id,
                expires_at=grant.expires_at,
            )
            connection.execute(
                "INSERT INTO qualification_reports VALUES (?, ?, ?, ?)",
                (
                    qualification.report_id,
                    qualification.candidate_id,
                    qualification.behavior_fingerprint,
                    qualification.model_dump_json(),
                ),
            )
            connection.execute(
                "INSERT INTO assessment_records VALUES ('admission', ?, ?, ?)",
                (admission.admission_id, content_digest(admission), admission.model_dump_json()),
            )
            connection.execute(
                "INSERT INTO assessment_admissions (executor_id, admission_id, revoked) VALUES (?, ?, 0) ON CONFLICT(executor_id) DO UPDATE SET admission_id=excluded.admission_id, revoked=0, revoked_at=NULL",
                (admission.executor_id, admission.admission_id),
            )
            if candidate.behavior_fingerprint != qualification.behavior_fingerprint:
                raise ConfigurationError("candidate drifted before atomic admission")
            activate_qualified_state(candidate, qualification)
            connection.execute(
                "INSERT INTO route_candidates (executor_id, source_id, fingerprint, status, package_digest, package_fingerprint, verification_snapshot_id, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(executor_id) DO UPDATE SET status=excluded.status, payload_json=excluded.payload_json",
                (
                    candidate.executor_id,
                    candidate.source_id,
                    candidate.behavior_fingerprint,
                    candidate.status.value,
                    candidate.package_digest,
                    candidate.package_fingerprint,
                    candidate.verification_snapshot_id,
                    candidate.model_dump_json(),
                ),
            )
        spec = mapping.candidate.model_copy(update={"enabled": True})
        self.router.registry.replace(spec)
        return admission

    def _verify_dependencies(self, plan: AssessmentPlan) -> ReviewedMapping:
        verify_dependencies(plan.executable_dependencies)
        from .pilot import require_separation
        require_separation(self.repository, plan)
        from .pilot import require_linked_pilot
        preceding_pilot = require_linked_pilot(self.repository, plan)
        if plan.recipe_case_set_digest is not None:
            case_set = RecipeCaseSet.model_validate(self.repository.get("recipe_case_set", plan.recipe_case_set_digest))
            expected_cases = [case for case in case_set.cases if case.split == BenchmarkSplit.QUALIFICATION] if plan.pilot else case_set.cases
            if (expected_cases != plan.suite.cases or case_set.recipe_digest != plan.recipe_digest
                    or case_set.environment_digest != plan.environment_digest or case_set.seed != plan.suite.seed
                    or plan.preparation_request_ids != [case_set.request_id, *([preceding_pilot.plan_id] if preceding_pilot else [])]):
                raise ConfigurationError("executable recipe cases changed after materialization")
        subject = AssessmentSubject.model_validate(
            self.repository.get("subject", plan.subject_digest)
        )
        verify_subject(subject)
        mapping = ReviewedMapping.model_validate(
            self.repository.get("mapping", plan.mapping_digest)
        )
        if plan.comparison is not None:
            from .comparison import define
            reference = next((item for item in mapping.dependencies if item.id == plan.reference_id), None)
            expected = define(plan.comparison.structure, mapping.candidate, mapping.baseline, mapping.dependencies, reference, experiment=plan.comparison.experiment)
            expected.primary_condition = plan.comparison.primary_condition
            if expected != plan.comparison:
                raise ConfigurationError("comparison differs from the reviewed route mapping")
            experiment = plan.comparison.experiment
            if experiment is not None:
                self._verify_incremental_evidence(plan, experiment)
        for spec in mapping.subjects:
            candidate = self.router.store.get_route_candidate(spec.id)
            current = candidate.spec if candidate is not None else self.router.registry.get(spec.id)
            if behavior_fingerprint(current) != plan.route_fingerprints[spec.id]:
                raise ConfigurationError("assessment route changed; renewed review is required")
        return mapping

    def _verify_three_way_qualification(self, plan: AssessmentPlan,
                                        qualified_plan: AssessmentPlan, report: AssessmentReport) -> None:
        """Supplement existing canonical qualification checks, never replace refitting."""
        self.repository.authorize(qualified_plan)
        self._verify_dependencies(qualified_plan)
        if qualified_plan.candidate_id != plan.candidate_id or content_digest(qualified_plan) != report.plan_digest:
            raise ConfigurationError('three-way qualification candidate/plan differs')
        assert report.grader_validation_digest is not None
        validation = GraderValidationEvidence.model_validate(self.repository.get('grader_validation', report.grader_validation_digest))
        if (content_digest(validation) != report.grader_validation_digest
                or validation.recipe_digest != plan.recipe_digest or validation.rejected_fault_count < 1):
            raise ConfigurationError('three-way qualification grader binding differs')
        rows = self.router.store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='grader_validation' AND id IN (SELECT id || ':grader-validation' FROM assessment_jobs WHERE plan_id=? AND report_id=? AND state='complete' AND error_code IS NULL)",
            (qualified_plan.plan_id, report.report_id)).fetchall()
        if not any(row[0] == report.grader_validation_digest for row in rows):
            raise ConfigurationError('three-way requires canonical qualification grader validation')
        qualified_mapping = ReviewedMapping.model_validate(self.repository.get('mapping', qualified_plan.mapping_digest))
        current_mapping = ReviewedMapping.model_validate(self.repository.get('mapping', plan.mapping_digest))
        left = qualified_mapping.candidate.managed_host_config().model_dump(mode='json')
        right = current_mapping.candidate.managed_host_config().model_dump(mode='json')
        if left['invocation'].get('exposure') != 'required' or right['invocation'].get('exposure') != 'optional':
            raise ConfigurationError('three-way qualification exposure differs')
        for config in (left, right):
            config['invocation'].pop('exposure')
        if left != right:
            raise ConfigurationError('three-way qualification candidate backend differs')

    def _verify_incremental_evidence(self, plan: AssessmentPlan, experiment: IncrementalExperiment) -> None:
        from .boundary import require_differential
        environment = AssessmentEnvironment.model_validate(self.repository.get("environment", plan.environment_digest))
        require_differential(self.repository, environment, plan)
        if experiment.stage == "qualification":
            return
        assert experiment.qualification_report_digest is not None
        report = AssessmentReport.model_validate(self.repository.get("report", experiment.qualification_report_digest))
        qualified_plan = AssessmentPlan.model_validate(self.repository.get("plan", report.plan_digest))
        prior_experiment = qualified_plan.comparison.experiment if qualified_plan.comparison else None
        campaign = BenchmarkCampaignReport.model_validate(self.repository.get("campaign", report.campaign_digest))
        binding = AssessmentRunBinding.model_validate(self.repository.get("run_binding", qualified_plan.plan_id))
        from .verification import verification_source_digest
        recipe = RecipeDefinition.model_validate(self.repository.get("recipe", plan.recipe_digest))
        if (content_digest(report) != experiment.qualification_report_digest
                or prior_experiment is None or prior_experiment.stage != "qualification"
                or qualified_plan.authorization_id != plan.authorization_id
                or qualified_plan.subject_digest != plan.subject_digest or qualified_plan.recipe_digest != plan.recipe_digest
                or prior_experiment.environment != experiment.environment
                or binding.source_digest != verification_source_digest(Path(__file__).parents[3])
                or report.grader_validation_digest is None
                or not fit_report(qualified_plan, recipe, campaign).qualification_passed):
            raise ConfigurationError("incremental value requires current independent qualification evidence")
        allowed_training = {content_digest(case.action.input) for case in qualified_plan.suite.cases if case.split == BenchmarkSplit.TRAINING}
        prior_inputs = {content_digest(case.action.input) for case in qualified_plan.suite.cases if case.split == BenchmarkSplit.HOLDOUT}
        if experiment.stage == 'aeep_value':
            self.repository.authorize(qualified_plan)
            if (content_digest(qualified_plan) != report.plan_digest
                    or content_digest(campaign) != report.campaign_digest
                    or qualified_plan.candidate_id != plan.candidate_id
                    or len(qualified_plan.suite.routes) != 1
                    or prior_experiment.exposure != 'required'):
                raise ConfigurationError('three-way qualification canonical lineage differs')
        if experiment.stage == 'native_catalog':
            marginal = AssessmentReport.model_validate(self.repository.get('report', experiment.marginal_report_digest or ''))
            marginal_plan = AssessmentPlan.model_validate(self.repository.get('plan', marginal.plan_digest))
            marginal_experiment = marginal_plan.comparison.experiment if marginal_plan.comparison else None
            if (marginal_plan.pilot is not None or content_digest(marginal) != experiment.marginal_report_digest or marginal_experiment is None
                    or marginal_plan.authorization_id != plan.authorization_id
                    or marginal_experiment.stage != 'marginal_value' or marginal_plan.recipe_digest != plan.recipe_digest
                    or marginal_plan.subject_digest != plan.subject_digest
                    or marginal_experiment.environment.candidate_inventory != experiment.environment.candidate_inventory):
                raise ConfigurationError('native catalog requires matching preceding marginal evidence')
            marginal_binding = AssessmentRunBinding.model_validate(self.repository.get('run_binding', marginal_plan.plan_id))
            with self.router.store._lock:
                done = self.router.store._connection.execute(
                    "SELECT 1 FROM assessment_jobs WHERE plan_id=? AND report_id=? AND state='complete' AND error_code IS NULL",
                    (marginal_plan.plan_id, marginal.report_id)).fetchone()
            if done is None or marginal_binding.source_digest != binding.source_digest:
                raise ConfigurationError('native catalog requires a completed source-bound marginal campaign')
            prior_inputs |= {content_digest(case.action.input) for case in marginal_plan.suite.cases if case.split == BenchmarkSplit.HOLDOUT}
            allowed_training |= {content_digest(case.action.input) for case in marginal_plan.suite.cases if case.split == BenchmarkSplit.TRAINING}
        if prior_inputs & {content_digest(case.action.input) for case in plan.suite.cases if case.split == BenchmarkSplit.HOLDOUT}:
            raise ConfigurationError("evaluation stages must use disjoint holdout inputs")
        with self.router.store._lock:
            completed = self.router.store._connection.execute(
                "SELECT 1 FROM assessment_jobs WHERE plan_id=? AND report_id=? AND state='complete' AND error_code IS NULL",
                (qualified_plan.plan_id, report.report_id),
            ).fetchone()
            if completed is None:
                raise ConfigurationError("qualification requires a completed campaign, not a report alone")
            if experiment.stage == 'aeep_value':
                self._verify_three_way_qualification(plan, qualified_plan, report)
                return
            for identity in experiment.reusable_build_operation_ids:
                row = self.router.store._connection.execute(
                    "SELECT state, grant_id FROM assessment_operations WHERE id=?", (identity,)).fetchone()
                if row is None or row[0] != "complete" or row[1] != plan.authorization_id:
                    raise ConfigurationError("reusable baseline requires completed construction accounting on the same grant")
            artifact = self.router.store._connection.execute(
                "SELECT 1 FROM assessment_records r JOIN assessment_reviews v ON v.digest=r.digest WHERE r.digest=? AND v.revoked=0",
                (experiment.reusable_artifact_digest,),
            ).fetchone()
            if artifact is None:
                raise ConfigurationError("reusable baseline artifact requires exact operator review")
        artifact_record = ReusableBaselineArtifact.model_validate(self.repository.get("reusable_baseline", experiment.reusable_artifact_digest or ""))
        assert experiment.reusable_tool is not None
        if (artifact_record.executor_fingerprint != experiment.reusable_tool.fingerprint
                or artifact_record.build_operation_ids != experiment.reusable_build_operation_ids
                or not set(artifact_record.training_input_digests) <= (allowed_training | {
                    content_digest(case.action.input) for case in plan.suite.cases if case.split == BenchmarkSplit.TRAINING})
                or set(artifact_record.training_input_digests) & (prior_inputs | {
                    content_digest(case.action.input) for case in plan.suite.cases if case.split == BenchmarkSplit.HOLDOUT})):
            raise ConfigurationError("reusable artifact identity, construction or holdout separation differs")
        import hashlib

        from .planning import ReusableBuildOutput
        built_inputs: set[str] = set()
        for operation_id in artifact_record.build_operation_ids:
            built = ReusableBuildOutput.model_validate(self.repository.get("reusable_build_output", operation_id))
            source_hash = hashlib.sha256(built.source.encode()).hexdigest()
            if built.operation_id != operation_id or source_hash not in artifact_record.worker_files.values():
                raise ConfigurationError("reusable worker does not contain its measured construction output")
            built_inputs.update(built.training_input_digests)
        if built_inputs != set(artifact_record.training_input_digests):
            raise ConfigurationError("reusable construction inputs differ from the frozen artifact")
        reusable = self.router.registry.get(experiment.reusable_tool.executor_id)
        if reusable.kind == ExecutorKind.MANAGED_HOST:
            from ..hosts.workers import binding_from_config
            worker = binding_from_config(reusable.managed_host_config().managed_worker)
            if worker is None or any((worker.reviewed_files or {}).get(name) != digest for name, digest in artifact_record.worker_files.items()):
                raise ConfigurationError("reusable artifact is not bound into its immutable worker")

    def _probe_cost_source(self, probe: Any, evidence: Any, *, authorization_id: str) -> str:
        """Resolve a probe to its explicitly charged assessment operation.

        Legacy v1 probes retain their original attempt-id lookup. Version 2
        probes carry a canonical operation-start digest because adapter-owned
        child attempts are not assessment operation identifiers.
        """
        from .boundary import BoundaryProbe
        from .models import AssessmentOperation, ConformanceProbeRequest, content_digest

        if not isinstance(probe, BoundaryProbe):
            raise ConfigurationError('boundary probe is malformed')
        if probe.schema_version == 'assessment.boundary-probe.v1':
            # Preserve the historical direct lookup and its serialized meaning.
            operation = AssessmentOperation.model_validate(
                self.repository.get('operation_start', evidence.attempt_id)
            )
            return operation.plan_id

        charged_digest = probe.charged_operation_digest
        if charged_digest is None:
            raise ConfigurationError('boundary probe v2 has no charged operation binding')
        with self.router.store._lock:
            connection = self.router.store._connection
            start_row = connection.execute(
                "SELECT id, digest, payload_json FROM assessment_records "
                "WHERE kind='operation_start' AND digest=?", (charged_digest,)
            ).fetchone()
            if start_row is None:
                raise ConfigurationError('boundary probe charged operation is unavailable')
            operation_state = connection.execute(
                'SELECT grant_id, state FROM assessment_operations WHERE id=?', (start_row[0],)
            ).fetchone()
            measurement_row = connection.execute(
                "SELECT digest, payload_json FROM assessment_records "
                "WHERE kind='operation_measurement' AND id=?", (start_row[0],)
            ).fetchone()

        try:
            start_payload = json.loads(start_row[2])
            operation = AssessmentOperation.model_validate(start_payload)
            if (start_row[1] != charged_digest or content_digest(start_payload) != charged_digest
                    or operation.operation_id != start_row[0]
                    or operation_state is None or operation_state[1] != 'complete'
                    or operation_state[0] != authorization_id):
                raise ConfigurationError('boundary probe charged operation is not settled under this grant')
            if measurement_row is None:
                raise ConfigurationError('boundary probe charged operation has no valid measurement')
            measurement_payload = json.loads(measurement_row[1])
            measured = AssessmentOperation.model_validate(measurement_payload)
            if (content_digest(measurement_payload) != measurement_row[0]
                    or measured.operation_id != operation.operation_id
                    or measured.plan_id != operation.plan_id
                    or measured.stage != operation.stage
                    or measured.reserved != operation.reserved
                    or measured.elapsed_seconds is None):
                raise ConfigurationError('boundary probe charged operation has no valid measurement')
            with self.router.store._lock:
                request_row = self.router.store._connection.execute(
                    "SELECT digest, payload_json FROM assessment_records "
                    "WHERE kind='conformance_request' AND id=?", (operation.plan_id,)
                ).fetchone()
            if request_row is None:
                raise ConfigurationError('boundary probe charged operation request is unavailable')
            request_payload = json.loads(request_row[1])
            request = ConformanceProbeRequest.model_validate(request_payload)
            if (content_digest(request_payload) != request_row[0]
                    or request.plan_id != operation.plan_id
                    or request.authorization_id != authorization_id
                    or request.worker_digest != probe.worker_digest
                    or probe.implementation_digest not in request.definition_digests):
                raise ConfigurationError('boundary probe charged operation differs from its reviewed request')
        except ConfigurationError:
            raise
        except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            raise ConfigurationError('boundary probe charged operation records are malformed') from exc
        return operation.plan_id

    def _cost_sources(self, plan: AssessmentPlan, *, require_complete: bool = True) -> tuple[list[str], list[str]]:
        """Include measured preparation and preceding stages without another debit."""
        from ..execution import ExecutionEvidence
        from .boundary import BoundaryConformance, BoundaryProbe
        from .models import content_digest

        experiment = plan.comparison.experiment if plan.comparison else None
        identities = set(plan.setup_cost_ids)
        sources = set([*plan.planning_request_ids, *(plan.preparation_request_ids or [])])
        reports = [plan.pilot_report_digest]
        if experiment:
            identities.update(experiment.reusable_build_operation_ids)
            reports.extend([experiment.qualification_report_digest, experiment.marginal_report_digest])
        for digest in filter(None, reports):
            parent = AssessmentReport.model_validate(self.repository.get('report', digest))
            ledger = AssessmentOperationLedger.model_validate(self.repository.get('operation_ledger', parent.operation_ledger_digest or ''))
            if content_digest(parent) != digest or content_digest(ledger) != parent.operation_ledger_digest:
                raise ConfigurationError('preceding assessment cost evidence changed')
            identities.update(item.operation_id for item in ledger.operations)
        environment = AssessmentEnvironment.model_validate(self.repository.get('environment', plan.environment_digest))
        for digest in (environment.conformance_digests or {}).values():
            boundary = BoundaryConformance.model_validate(self.repository.get('boundary_conformance', digest))
            with self.router.store._lock:
                bootstrap = self.router.store._connection.execute(
                    "SELECT id FROM assessment_records WHERE kind='conformance_request' "
                    "AND json_extract(payload_json, '$.worker_digest')=? "
                    "AND json_extract(payload_json, '$.authorization_id')=?",
                    (boundary.worker_digest, plan.authorization_id)).fetchall()
            sources.update(row[0] for row in bootstrap)
            for probe_digest in boundary.probe_digests:
                probe_payload = self.repository.get('boundary_probe', probe_digest)
                probe = BoundaryProbe.model_validate(probe_payload)
                evidence_payload = self.repository.get('execution_evidence', probe.execution_evidence_digest)
                evidence = ExecutionEvidence.model_validate(evidence_payload)
                if probe.schema_version == 'assessment.boundary-probe.v2' and (
                    content_digest(probe_payload) != probe_digest
                    or content_digest(evidence) != probe.execution_evidence_digest
                    or not evidence.complete
                ):
                    raise ConfigurationError('boundary probe v2 execution evidence is incomplete or changed')
                source_plan_id = self._probe_cost_source(
                    probe, evidence, authorization_id=plan.authorization_id
                )
                # A bootstrap request also owns its protected sign-in operation.
                sources.add(source_plan_id)
        ledger = self.repository.operation_ledger(plan.plan_id, sorted(identities), sorted(sources))
        observed = {item.operation_id for item in ledger.operations}
        missing = identities - observed
        if missing and (require_complete or not missing <= set(plan.setup_cost_ids)):
            raise ConfigurationError('preceding assessment cost operations are missing')
        with self.router.store._lock:
            for identity in observed:
                grant = self.router.store._connection.execute('SELECT grant_id FROM assessment_operations WHERE id=?', (identity,)).fetchone()
                if grant is None or grant[0] != plan.authorization_id:
                    raise ConfigurationError('assessment costs belong to a different grant')
        return sorted(identities), sorted(sources)

    async def run(self, assessment_id: str) -> AssessmentReport:
        job = self.status(assessment_id)
        if job["state"] == "complete":
            return AssessmentReport.model_validate(self.repository.get("report", job["report_id"]))
        plan = AssessmentPlan.model_validate(self.repository.get("plan", job["plan_id"]))
        self.repository.authorize(plan)
        mapping = self._verify_dependencies(plan)
        recipe = RecipeDefinition.model_validate(self.repository.get("recipe", plan.recipe_digest))
        family = (
            recipe.generator.split(":")[1]
            if recipe.generator.startswith("builtin:")
            else "record_template"
        )
        if recipe.implementation_digest != recipe_implementation_digest() or (
            recipe.extension is None and recipe.generator != "record_template:1" and recipe != shipped_recipe(family)
        ):
            raise ConfigurationError("recipe implementation changed; renewed review is required")
        with self.router.store._immediate_transaction() as connection:
            if (
                connection.execute(
                    "UPDATE assessment_jobs SET state='running', started_at=? WHERE id=? AND state='queued'",
                    (utc_now().isoformat(), assessment_id),
                ).rowcount
                != 1
            ):
                raise ConfigurationError(
                    "assessment is cancelled or already claimed; inspect uncertain work"
                )
            from .recovery import record_worker_locked
            record_worker_locked(self.repository, assessment_id)

        async def before_trial(
            router: Router, route: BenchmarkRoute, trial: BenchmarkTrial
        ) -> None:
            self._verify_dependencies(plan)
            if self.status(assessment_id)["state"] != "running":
                raise ConfigurationError("assessment cancelled")
            if route.executor_id:
                specs = [router.registry.get(route.executor_id)]
            else:
                assert route.workflow is not None
                specs = []
                for step in route.workflow.steps:
                    allowed = step.action.constraints.allowed_executor_ids
                    if allowed is None or len(allowed) != 1:
                        raise ConfigurationError("workflow assessment requires exact step routes")
                    specs.append(router.registry.get(allowed[0]))
            from .destinations import require_destination
            grant = self.repository.authorize(plan)
            for spec in specs:
                require_destination(spec, environment, grant)
            if any(spec.estimate.cash.upper_bound_usd is None for spec in specs):
                raise ConfigurationError("assessment has no enforceable cash upper bound")
            upper = sum((spec.estimate.cash.upper_bound_usd or Decimal(0) for spec in specs), Decimal(0))
            turns = 0
            for spec in specs:
                if spec.kind == ExecutorKind.MANAGED_HOST:
                    invocation = spec.managed_host_config().invocation
                    turns += int(invocation is None or invocation.mode != "mcp_tool")
            trial_seconds = sum(float(spec.config.get("timeout_seconds", 60)) for spec in specs)
            self.repository.reserve(
                plan,
                trial.trial_id,
                AssessmentLimits(
                    max_operations=len(specs),
                    max_model_turns=turns,
                    max_elapsed_seconds=trial_seconds + 5,
                    max_cash_usd=upper,
                ),
                stage="trial",
            )
            router._trial_deadline = asyncio.get_running_loop().time() + trial_seconds
            router._callback_trial_identity = (assessment_id, trial.trial_id)
            started = time.perf_counter()
            try:
                async with asyncio.timeout_at(router._trial_deadline):
                    for spec in specs:
                        if spec.kind == ExecutorKind.MANAGED_HOST:
                            await router._resolve_host_identity(spec)
                            binding = router.store.host_runtime_digests.get(spec.id)
                            if binding is None:
                                raise ConfigurationError("host runtime identity could not be resolved")
                            self.repository.put("runtime_binding", f"{plan.plan_id}:{spec.id}", RuntimeBinding(plan_id=plan.plan_id, executor_id=spec.id, digest=binding[1]))
                            self.router.store.host_runtime_digests[spec.id] = binding
                            router.store.expected_host_runtime_digests[spec.id] = binding[1]
                    from .boundary import require_managed_boundaries
                    require_managed_boundaries(self.repository, environment, specs,
                        {key: value[1] for key, value in router.store.host_runtime_digests.items()})
            except Exception as exc:
                self.repository.finish_operation(trial.trial_id, elapsed_seconds=time.perf_counter() - started)
                raise ConfigurationError("assessment trial preflight failed") from exc

        def after_trial(trial: BenchmarkTrial) -> None:
            if trial.wall_time_ms is None:
                raise ConfigurationError("trial elapsed measurement unavailable; reservation retained")
            self.repository.finish_operation(
                trial.trial_id, elapsed_seconds=trial.wall_time_ms / 1000,
                accounting=trial.accounting, resources=trial.actual_resources,
            )
            if trial.error_type == "ValidationExecutionError":
                raise ConfigurationError("assessment grader failed; candidate correctness is not evaluated")
            if trial.failure_category == "environment_failure" or trial.error_type == "ConfigurationError":
                raise ConfigurationError("assessment environment failed; further trials stopped")

        environment = AssessmentEnvironment.model_validate(
            self.repository.get("environment", plan.environment_digest)
        )

        def campaign_router() -> Router:
            operation_id = new_id("router_setup")
            self.repository.reserve(plan, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="router_setup")
            started, cpu_started = time.perf_counter(), time.process_time()
            try:
                router = self.router._campaign_router(
                    mapping.subjects, plan_digest=content_digest(plan),
                    database=self.directory / plan.plan_id / "attempts" / f"{new_id('worker')}.sqlite3",
                    snapshot_bound_digests={
                        content_digest(plan), plan.subject_digest, plan.recipe_digest,
                        plan.mapping_digest, plan.environment_digest,
                        *plan.definition_digests, *plan.executable_dependencies.values(),
                        *([plan.recipe_case_set_digest] if plan.recipe_case_set_digest else []),
                    },
                )
                def check_current() -> None:
                    self.repository.authorize(plan)
                    self._verify_dependencies(plan)
                    if self.status(assessment_id)["state"] != "running":
                        raise ConfigurationError("assessment stopped before invocation")
                    from .boundary import require_managed_boundaries
                    identities = {key: value[1] for key, value in router.store.host_runtime_digests.items()}
                    require_managed_boundaries(self.repository, environment,
                        [item for item in mapping.subjects if item.id in identities], identities)
                router._trial_check = check_current
                router._trial_boundary_references = dict(environment.conformance_digests or {})
                if recipe.extension is not None:
                    from .extensions import callbacks
                    router.validator_callbacks.update(callbacks(self, plan, recipe))
                if environment.kind == "container":
                    from .containment import NATIVE_KINDS, ContainerExecutor

                    fixture_root = self.directory / plan.plan_id / "fixtures"
                    fixture_root.mkdir(parents=True, exist_ok=True)
                    for kind in NATIVE_KINDS:
                        router._executors[kind] = ContainerExecutor(environment, fixture_root=fixture_root)
                return router
            finally:
                self.repository.finish_operation(operation_id, elapsed_seconds=time.perf_counter() - started, resources=ResourceVector(cpu_ms=(time.process_time() - cpu_started) * 1000))

        runner = BenchmarkRunner(
            campaign_router,
            self.directory / plan.plan_id / "campaign.sqlite3",
            before_trial=before_trial,
            after_trial=after_trial,
            separate_grading=recipe.extension is not None,
        )
        from .verification import verification_source_digest
        source_digest = await asyncio.to_thread(verification_source_digest, Path(__file__).parents[3])
        self.repository.put("run_binding", plan.plan_id, AssessmentRunBinding(plan_id=plan.plan_id, source_digest=source_digest, campaign_path=runner.database))
        error_code: str | None = None
        report_operation = f"{assessment_id}:report"
        report_reserved = False
        try:
            self.repository.reserve(plan, report_operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="report_generation")
            report_reserved = True
            for cost_id in plan.setup_cost_ids:
                cost = AssessmentSetupCost.model_validate(self.repository.get("setup_cost", cost_id))
                with self.router.store._lock:
                    previous = self.router.store._connection.execute("SELECT state FROM assessment_operations WHERE id=?", (cost_id,)).fetchone()
                if previous is None:
                    self.repository.reserve(plan, cost_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=max(cost.elapsed_seconds, 0.000001)), stage=cost.stage)
                    self.repository.finish_operation(cost_id, elapsed_seconds=cost.elapsed_seconds, resources=ResourceVector(latency_ms=cost.elapsed_seconds * 1000, cpu_ms=cost.cpu_ms))
                elif previous[0] != "complete":
                    raise ConfigurationError("setup accounting is indeterminate")
            # Exercise the grader with independent known-good and deliberately wrong answers before any candidate call.
            operation_id = f"{assessment_id}:grader-validation"
            self.repository.reserve(
                plan, operation_id, AssessmentLimits(max_operations=1, max_elapsed_seconds=30), stage="grader_validation"
            )
            from .recipes import (
                faulty_outputs,
                independent_cases,
                reference_record_template,
                reviewed_record_fixtures,
            )
            started, cpu_started = time.perf_counter(), time.process_time()
            program_seconds: list[float] = []
            try:
                if recipe.extension is not None:
                    from .extensions import validate_grader
                    literals, faults_rejected = await validate_grader(self, plan, recipe, program_seconds)
                    builtin_cases: list[Any] = []
                else:
                    literals = reviewed_record_fixtures(recipe) if family == "record_template" else independent_cases(family, self.directory / plan.plan_id / "grader-fixtures")
                    faults_rejected = 0
                    builtin_cases = [*literals, *plan.suite.cases[:8]]
                for case in builtin_cases:
                    if family == "record_template":
                        correct = reference_record_template(recipe, case.action.input["text"])
                    else:
                        reference = cast(
                            Callable[..., dict[str, Any]],
                            {"csv": reference_csv, "text": reference_text, "search": reference_search}[
                                family
                            ],
                        )
                        correct = reference(**case.action.input)
                    good = await run_validators(
                        case.validators, ValidationContext(input=case.action.input, output=correct), {}
                    )
                    if not all(result.valid is True for result in good):
                        raise ConfigurationError("recipe grader validation failed")
                    for fault in faulty_outputs(correct):
                        bad = await run_validators(case.validators, ValidationContext(input=case.action.input, output=fault), {})
                        if any(result.valid is not False for result in bad):
                            raise ConfigurationError("recipe grader validation failed")
                        faults_rejected += 1
                validation = GraderValidationEvidence(recipe_digest=plan.recipe_digest,
                    independent_fixture_digests=[content_digest(case) for case in literals],
                    generator_fixture_digests=[content_digest(case) for case in plan.suite.cases[:8]],
                    rejected_fault_count=faults_rejected)
                self.repository.put("grader_validation", operation_id, validation)

            finally:
                self.repository.finish_operation(operation_id, elapsed_seconds=max(0, time.perf_counter() - started - sum(program_seconds)), resources=ResourceVector(cpu_ms=(time.process_time() - cpu_started) * 1000))
            campaign = await runner.run(plan.suite)
        except ConfigurationError:
            error_code = "assessment_blocked_or_budget_exhausted"
            trials = [
                BenchmarkTrial.model_validate_json(row[0])
                for row in runner.connection.execute(
                    "SELECT payload_json FROM trials WHERE suite_id=?", (plan.suite.suite_id,)
                )
            ]
            campaign = BenchmarkCampaignReport(
                run_id=assessment_id,
                suite_id=plan.suite.suite_id,
                domain=plan.suite.domain,
                trials=trials,
                deterministic_tools_available=True,
                pricing_snapshot_ids=[],
                frozen_holdout_decisions={},
                summaries=[],
                baseline_deltas=[],
                oracles=[],
                subscription_conservation=[],
            )
        except BaseException:
            with self.router.store._immediate_transaction() as connection:
                connection.execute(
                    "UPDATE assessment_jobs SET state='indeterminate', error_code='interrupted' WHERE id=?",
                    (assessment_id,),
                )
            raise
        finally:
            runner.connection.close()
        missing_cost_lineage = False
        try:
            cost_ids, cost_plans = self._cost_sources(plan)
        except ConfigurationError:
            # Already incurred usage remains in the ledger even if lineage is incomplete.
            missing_cost_lineage = True
            error_code = error_code or "assessment_cost_lineage_unavailable"
            cost_ids, cost_plans = plan.setup_cost_ids, plan.planning_request_ids
        ledger = self.repository.operation_ledger(plan.plan_id, cost_ids, cost_plans)
        started, cpu_started = time.perf_counter(), time.process_time()
        report = fit_report(plan, recipe, campaign, ledger=ledger)
        with self.router.store._lock:
            grader_record = self.router.store._connection.execute(
                "SELECT digest FROM assessment_records WHERE kind='grader_validation' AND id=?",
                (f"{assessment_id}:grader-validation",),
            ).fetchone()
        if grader_record is not None:
            report.grader_validation_digest = grader_record[0]
        if report_reserved:
            self.repository.finish_operation(report_operation, elapsed_seconds=time.perf_counter() - started, resources=ResourceVector(cpu_ms=(time.process_time() - cpu_started) * 1000))
            ledger = self.repository.operation_ledger(plan.plan_id, cost_ids, cost_plans)
            apply_assessment_costs(report, campaign, ledger)
        if missing_cost_lineage:
            report.measured_usage["assessment_wall_time_ms"] = None
            report.break_even_uses = {key: None for key in report.break_even_uses}
            report.explanations.append("Preparation cost lineage is incomplete; known incurred usage is retained.")
        self.repository.put("operation_ledger", content_digest(ledger), ledger)
        if error_code:
            report.outcome = "insufficient_evidence"
            report.qualification_passed = False
            report.explanations.append(error_code)
        self.repository.put("campaign", campaign.run_id, campaign)
        self.repository.put("report", report.report_id, report)
        with self.router.store._immediate_transaction() as connection:
            connection.execute(
                "UPDATE assessment_jobs SET state='complete', report_id=?, error_code=? WHERE id=?",
                (report.report_id, error_code, assessment_id),
            )
        if report.outcome == "useful_within_scope":
            try:
                if self.repository.authorize(plan).automatic_admission:
                    self.admit(report.report_id)
            except ConfigurationError:
                with self.router.store._immediate_transaction() as connection:
                    connection.execute(
                        "UPDATE assessment_jobs SET error_code='automatic_admission_unavailable' WHERE id=?",
                        (assessment_id,),
                    )
        return report
