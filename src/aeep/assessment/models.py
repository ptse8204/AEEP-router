"""Versioned, inert assessment definitions. None of these records grants execution alone."""

from __future__ import annotations

import hashlib
import json
from decimal import Decimal
from pathlib import Path, PurePosixPath
from typing import Annotated, Any, Literal

from pydantic import (
    Field,
    SerializationInfo,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from ..benchmarking import BenchmarkCase, BenchmarkSuite
from ..models import (
    ExecutorSpec,
    ResourceAccounting,
    ResourceVector,
    StrictModel,
    UtcDateTime,
    new_id,
    utc_now,
)

Digest = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]


def content_digest(value: StrictModel | dict[str, Any]) -> str:
    data = value.model_dump(mode="json") if isinstance(value, StrictModel) else value
    return hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def recipe_implementation_digest() -> str:
    return hashlib.sha256(Path(__file__).with_name("recipes.py").read_bytes()).hexdigest()


class ReviewedMapping(StrictModel):
    candidate: ExecutorSpec
    baseline: ExecutorSpec
    dependencies: list[ExecutorSpec] = Field(default_factory=list)
    executable_dependencies: dict[str, str] = Field(default_factory=dict)

    @property
    def subjects(self) -> list[ExecutorSpec]:
        return [self.candidate, self.baseline, *self.dependencies]


class AssessmentSubject(StrictModel):
    schema_version: Literal["assessment.subject.v1"] = "assessment.subject.v1"
    subject_id: str = Field(default_factory=lambda: new_id("subject"))
    kind: Literal["plugin", "skill", "mcp", "openapi", "provider_package", "command"]
    location: str
    dependency_digests: dict[str, Digest]
    description: str = Field(default="", max_length=10000)
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    declarations: dict[str, Any] = Field(default_factory=dict)


class RecipeLiteralFixture(StrictModel):
    input: dict[str, Any]
    output: dict[str, Any]
    grader_output: dict[str, Any] | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.grader_output is None:
            result.pop("grader_output", None)
        return result


class RecipeFeatureRule(StrictModel):
    path: str = Field(pattern=r"^(?:/.*)?$")
    operation: Literal["length", "type", "enum"]
    values: list[str | int | bool] = Field(default_factory=list, max_length=100)


class ExecutableRecipeExtension(StrictModel):
    schema_version: Literal["assessment.recipe-extension.v1", "assessment.recipe-extension.v2", "assessment.recipe-extension.v3"] = "assessment.recipe-extension.v1"
    generator: ExecutorSpec
    grader: ExecutorSpec
    reference: ExecutorSpec
    independent_fixtures: list[RecipeLiteralFixture] = Field(min_length=2, max_length=100)
    transformed_fixtures: list[RecipeLiteralFixture] = Field(min_length=1, max_length=100)
    fault_outputs: list[dict[str, Any]] = Field(min_length=1, max_length=100)
    feature_rules: dict[str, RecipeFeatureRule]
    variation_features: dict[str, dict[str, str | int | bool]]
    template_families: list[str] = Field(min_length=1, max_length=100)
    truth_schema: dict[str, Any] | None = None
    failure_codes: list[Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]{0,63}$")]] | None = Field(default=None, min_length=1, max_length=32)

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.truth_schema is None:
            result.pop("truth_schema", None)
        if self.failure_codes is None:
            result.pop("failure_codes", None)
        return result

    @model_validator(mode="after")
    def contained_json_programs(self) -> ExecutableRecipeExtension:
        if (self.schema_version != 'assessment.recipe-extension.v1') != (self.truth_schema is not None):
            raise ValueError("semantic artifact grading requires extension v2/v3 and an explicit truth schema")
        if self.schema_version.endswith('.v3') != (self.failure_codes is not None):
            raise ValueError('reviewed failure codes require extension v3')
        if not self.schema_version.endswith('.v3') and any(
                fixture.grader_output is not None for fixture in [*self.independent_fixtures, *self.transformed_fixtures]):
            raise ValueError('independent grader outputs require extension v3')
        if self.failure_codes is not None and len(set(self.failure_codes)) != len(self.failure_codes):
            raise ValueError('duplicate reviewed failure code')
        for spec in (self.generator, self.grader, self.reference):
            config = spec.config
            if self.truth_schema is not None and config.get('argv_literal') is not True:
                raise ValueError('semantic recipe programs require exact literal argv')
            timeout = config.get("timeout_seconds")
            bound = config.get("max_output_bytes", 1_000_000)
            if (spec.kind.value != "command" or spec.side_effect.value != "read" or not spec.idempotent
                    or config.get("inherit_env") or config.get("env") or config.get("shell")
                    or config.get("stdin_json") is not True or config.get("output") != {"type": "json"}
                    or isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0 < timeout <= 30
                    or type(bound) is not int or not 0 < bound <= (16_000_000 if self.truth_schema is not None else 1_000_000)):
                raise ValueError("recipe extensions require bounded read-only JSON command executors")
        if not self.feature_rules or len(self.feature_rules) > 32:
            raise ValueError("recipe extensions require bounded structural feature rules")
        if any(not features or not set(features) <= self.feature_rules.keys() for features in self.variation_features.values()):
            raise ValueError("each reviewed variation must bind known structural features")
        return self


class RecipeDefinition(StrictModel):
    schema_version: Literal["assessment.recipe.v1", "assessment.recipe.v2"] = "assessment.recipe.v1"
    recipe_id: str
    implementation_digest: Digest = Field(default_factory=recipe_implementation_digest)
    capability: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    generator: str
    generator_config: dict[str, Any] = Field(default_factory=dict)
    grader: str
    extractor: str
    variations: list[str] = Field(min_length=1)
    exclusions: list[str] = Field(default_factory=list)
    dependencies: dict[str, Digest] = Field(default_factory=dict)
    screening_cases: Literal[8] = 8
    minimum_holdout_cases: Literal[100] = 100
    minimum_paired_cases: Literal[20] = 20
    maximum_correctness_failures: Literal[0] = 0
    extension: ExecutableRecipeExtension | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy_extension(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.extension is None:
            result.pop("extension", None)
        return result

    @model_validator(mode="after")
    def extension_contract(self) -> RecipeDefinition:
        if self.extension is not None:
            if (self.schema_version != "assessment.recipe.v2" or self.generator != "contained_json:1" or self.grader != "contained_json:1"
                    or self.extractor not in {"structural_json:1", "workbook_structure:1"}
                    or set(self.extension.variation_features) != set(self.variations)):
                raise ValueError("executable recipe identifiers and reviewed variations must agree")
        elif "contained_json:1" in {self.generator, self.grader}:
            raise ValueError("contained recipes require an exact executable extension")
        return self


class GraderValidationEvidence(StrictModel):
    schema_version: Literal["assessment.grader-validation.v1"] = "assessment.grader-validation.v1"
    recipe_digest: Digest
    independent_fixture_digests: list[Digest]
    generator_fixture_digests: list[Digest]
    rejected_fault_count: int = Field(ge=1)


class AssessmentLimits(StrictModel):
    max_operations: int = Field(ge=1, le=100000)
    max_model_turns: int = Field(default=0, ge=0, le=10000)
    max_elapsed_seconds: float = Field(gt=0, le=604800)
    max_cash_usd: Decimal = Field(default=Decimal(0), ge=0)


class AssessmentAuthorization(StrictModel):
    schema_version: Literal["assessment.authorization.v1"] = "assessment.authorization.v1"
    authorization_id: str = Field(default_factory=lambda: new_id("grant"))
    subject_digests: list[Digest] = Field(min_length=1)
    recipe_digests: list[Digest] = Field(min_length=1)
    environment_digests: list[Digest] = Field(min_length=1)
    limits: AssessmentLimits
    remote_disclosure: bool = False
    allowed_destinations: list[str] = Field(default_factory=lambda: ["local", "codex"], min_length=1)
    automatic_admission: bool = False
    issued_at: UtcDateTime = Field(default_factory=utc_now)
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def valid_expiry(self) -> AssessmentAuthorization:
        if self.expires_at <= self.issued_at:
            raise ValueError("authorization expiry must follow issuance")
        return self


class AssessmentScopeAmendment(StrictModel):
    """Operator-approved scope additions; ceilings and counters remain on the root grant."""

    schema_version: Literal["assessment.scope-amendment.v1"] = "assessment.scope-amendment.v1"
    amendment_id: str = Field(default_factory=lambda: new_id("amendment"))
    authorization_id: str
    authorization_digest: Digest
    subject_digests: list[Digest] = Field(min_length=1)
    recipe_digests: list[Digest] = Field(min_length=1)
    environment_digests: list[Digest] = Field(min_length=1)
    reviewed_digests: list[Digest] = Field(min_length=1)
    issued_at: UtcDateTime = Field(default_factory=utc_now)


class AssessmentBudgetAmendment(StrictModel):
    """Absolute operator ceilings on the original ledger, with optimistic concurrency."""

    schema_version: Literal["assessment.budget-amendment.v1"] = "assessment.budget-amendment.v1"
    amendment_id: str = Field(default_factory=lambda: new_id("budget_amendment"))
    authorization_id: str
    authorization_digest: Digest
    previous_amendment_digest: Digest | None = None
    limits: AssessmentLimits
    expires_at: UtcDateTime
    issued_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def valid_expiry(self) -> AssessmentBudgetAmendment:
        if self.expires_at <= self.issued_at:
            raise ValueError("budget amendment expiry must follow issuance")
        return self


class AssessmentEnvironment(StrictModel):
    environment_id: str
    kind: Literal["trusted_local", "container", "codex_sandbox"]
    identity: dict[str, str]
    network: bool = False
    container_image: str | None = None
    cpu_count: float = Field(default=1, gt=0, le=64)
    memory_mb: int = Field(default=256, ge=32, le=65536)
    process_limit: int = Field(default=64, ge=1, le=1024)
    container_runtime: str | None = None
    container_socket: str | None = None
    read_only_roots: list[str] = Field(default_factory=list)
    conformance_digests: dict[str, Digest] | None = None
    differential_conformance_digest: Digest | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.conformance_digests is None:
            result.pop("conformance_digests", None)
        if self.differential_conformance_digest is None:
            result.pop("differential_conformance_digest", None)
        return result

    @model_validator(mode="after")
    def pinned_container(self) -> AssessmentEnvironment:
        if self.kind == "container" and (
            self.container_image is None or ("@sha256:" not in self.container_image and not self.container_image.startswith("sha256:"))
        ):
            raise ValueError("container environments require a digest-pinned image")
        for path in [
            *self.read_only_roots,
            *([self.container_runtime, self.container_socket] if self.kind == "container" else []),
        ]:
            if (
                path is None
                or not Path(path).is_absolute()
                or any(char in path for char in ("\x00", ",", "\n"))
            ):
                raise ValueError("container paths must be explicit absolute local paths")
        return self


ComparisonStructure = Literal["direct", "controlled_agent", "workflow"]


class ComparisonArm(StrictModel):
    executor_id: str
    fingerprint: Digest
    dependencies: dict[str, Digest]
    host_config: dict[str, Any] | None = None


class UtilityPolicy(StrictModel):
    """Dimensions are native measurement keys; never an invented common currency."""

    benefit_dimensions: list[str] = Field(min_length=1, max_length=16)
    guardrail_dimensions: list[str] = Field(min_length=1, max_length=16)
    minimum_resource_benefit: float = Field(default=0.10, ge=0.10, lt=1)
    minimum_success_gain: float = Field(default=0.05, ge=0.05, lt=1)
    maximum_resource_regression: float = Field(default=0.10, ge=0, le=0.10)
    family_error_rate: float = Field(default=0.05, gt=0, le=0.05)

    @model_validator(mode="after")
    def unique_dimensions(self) -> UtilityPolicy:
        for values in (self.benefit_dimensions, self.guardrail_dimensions):
            if len(set(values)) != len(values) or any(not item.strip() for item in values):
                raise ValueError("utility dimensions must be nonempty and unique")
        if "task_success" in self.guardrail_dimensions:
            raise ValueError("task correctness is a qualification gate, not a resource guardrail")
        if not set(self.benefit_dimensions).difference({'task_success'}) <= set(self.guardrail_dimensions):
            raise ValueError("declared resource benefits must also be guarded against regression")
        return self


class DifferentialEnvironment(StrictModel):
    """Reviewed expected inventories, not a claim that permissions were verified."""

    shared_definition_digest: Digest
    control_inventory: dict[str, Digest]
    treatment_inventory: dict[str, Digest]
    candidate_inventory: dict[str, Digest] = Field(min_length=1)
    candidate_paths: list[str]
    candidate_aliases: list[str] = Field(default_factory=list)
    candidate_dynamic_tools: dict[
        Annotated[str, Field(pattern=r"^dynamic:[A-Za-z][A-Za-z0-9_]{0,63}:[A-Za-z][A-Za-z0-9_]{0,63}$")],
        Digest,
    ] = Field(default_factory=dict)

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if not self.candidate_dynamic_tools:
            result.pop("candidate_dynamic_tools", None)
        return result

    @model_validator(mode="after")
    def exact_difference(self) -> DifferentialEnvironment:
        if (set(self.control_inventory) & set(self.candidate_inventory)
                or self.treatment_inventory != {**self.control_inventory, **self.candidate_inventory}
                or set(self.candidate_aliases) & set(self.control_inventory)):
            raise ValueError("treatment inventory must equal control plus the candidate bundle")
        if any(not PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts for path in self.candidate_paths):
            raise ValueError("candidate paths must be bounded absolute worker paths")
        if self.candidate_dynamic_tools:
            if (self.candidate_paths or self.candidate_aliases
                    or self.candidate_inventory != self.candidate_dynamic_tools):
                raise ValueError("dynamic candidates require exact tool inventory and no physical paths or aliases")
        elif not self.candidate_paths:
            raise ValueError("physical candidates require bounded worker paths")
        return self


class ThreeWayAccessDefinition(StrictModel):
    """Exact expected inventories; observed conformance must independently match."""
    schema_version: Literal['assessment.three-way-access.v1'] = 'assessment.three-way-access.v1'
    normal_inventory: dict[str, Digest]
    discovery_inventory: dict[str, Digest] = Field(min_length=1)
    external_candidate_inventory: dict[str, Digest] = Field(min_length=1)
    worker_digests: dict[str, Digest] = Field(min_length=3, max_length=3)
    configuration_digests: dict[str, Digest] = Field(min_length=3, max_length=3)


class IncrementalExperiment(StrictModel):
    schema_version: Literal["assessment.experiment.v1", "assessment.experiment.v2"] = "assessment.experiment.v1"
    stage: Literal["qualification", "marginal_value", "native_catalog", "aeep_value"]
    exposure: Literal["required", "optional"]
    environment: DifferentialEnvironment
    utility: UtilityPolicy
    normal_host: ComparisonArm | None = None
    three_way_access_digest: Digest | None = None
    higher_compute: ComparisonArm | None = None
    reusable_tool: ComparisonArm | None = None
    reusable_artifact_digest: Digest | None = None
    reusable_build_operation_ids: list[str] = Field(default_factory=list)
    feasible_challengers: list[str] = Field(default_factory=list)
    qualification_report_digest: Digest | None = None
    catalog_definition_digest: Digest | None = None
    marginal_report_digest: Digest | None = None

    @model_serializer(mode='wrap')
    def preserve_four_arm(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.schema_version == 'assessment.experiment.v1':
            result.pop('normal_host', None)
            result.pop('three_way_access_digest', None)
        return result

    @model_validator(mode="after")
    def stage_contract(self) -> IncrementalExperiment:
        three_way = self.stage == 'aeep_value'
        if three_way != (self.schema_version == 'assessment.experiment.v2'):
            raise ValueError('three-way value requires experiment.v2')
        if three_way:
            if (self.normal_host is None or self.three_way_access_digest is None
                    or self.qualification_report_digest is None or self.higher_compute is not None
                    or self.reusable_tool is not None or self.reusable_artifact_digest is not None
                    or self.reusable_build_operation_ids or self.catalog_definition_digest is not None
                    or self.marginal_report_digest is not None
                    or self.feasible_challengers != [self.normal_host.executor_id]):
                raise ValueError('three-way requires one normal host, access and qualification evidence')
        elif self.normal_host is not None or self.three_way_access_digest is not None:
            raise ValueError('historical experiments cannot acquire three-way fields')
        if (self.stage == "qualification") != (self.exposure == "required"):
            raise ValueError("only qualification requires candidate invocation")
        if self.stage == "qualification" and self.challengers:
            raise ValueError("qualification does not run comparative challengers")
        if self.stage not in {"qualification", "aeep_value"} and (self.higher_compute is None or self.reusable_tool is None
                or self.reusable_artifact_digest is None or not self.reusable_build_operation_ids
                or self.qualification_report_digest is None):
            raise ValueError("value stages require two frozen challengers, build accounting and qualification evidence")
        ids = [arm.executor_id for arm in self.challengers]
        if len(ids) != len(set(ids)) or not set(self.feasible_challengers) <= set(ids):
            raise ValueError("challenger identities and feasibility must agree")
        if self.stage == "native_catalog" and (self.catalog_definition_digest is None or self.marginal_report_digest is None):
            raise ValueError("native catalog stage requires a frozen catalog and preceding marginal evidence")
        return self

    @property
    def challengers(self) -> list[ComparisonArm]:
        return [self.normal_host] if self.normal_host is not None else [arm for arm in (self.higher_compute, self.reusable_tool) if arm is not None]


class AssessmentSetupRequest(StrictModel):
    """Select configured definitions; no paths, executable code or approval fields."""

    schema_version: Literal['assessment.setup.v1'] = 'assessment.setup.v1'
    authorization_id: str = Field(min_length=1, max_length=200)
    subject_id: str = Field(min_length=1, max_length=200)
    recipe_id: str = Field(min_length=1, max_length=200)
    environment_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    baseline_id: str = Field(min_length=1, max_length=200)
    structure: ComparisonStructure | None = None
    seed: int = Field(default=0, ge=0, le=2147483647)
    case_set_id: str | None = Field(default=None, min_length=1, max_length=200)
    experiment_id: Digest | None = None
    pilot_report_id: str | None = Field(default=None, min_length=1, max_length=200)


class ReusableBaselineArtifact(StrictModel):
    schema_version: Literal["assessment.reusable-baseline.v1"] = "assessment.reusable-baseline.v1"
    executor_fingerprint: Digest
    worker_files: dict[str, Digest] = Field(min_length=1)
    training_input_digests: list[Digest] = Field(min_length=1)
    build_operation_ids: list[str] = Field(min_length=1)


class AssessmentComparison(StrictModel):
    schema_version: Literal["assessment.comparison.v1", "assessment.comparison.v2"] = "assessment.comparison.v1"
    structure: ComparisonStructure
    candidate: ComparisonArm
    baseline: ComparisonArm
    reference: ComparisonArm | None = None
    primary_metric: Literal["wall_time_ms"] = "wall_time_ms"
    primary_condition: str = "router-fresh"
    experiment: IncrementalExperiment | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.experiment is None:
            result.pop("experiment", None)
        return result

    @model_validator(mode="after")
    def versioned_experiment(self) -> AssessmentComparison:
        if (self.schema_version == "assessment.comparison.v2") != (self.experiment is not None):
            raise ValueError("incremental experiments require a v2 comparison")
        if self.experiment is not None:
            ids = [self.candidate.executor_id, self.baseline.executor_id,
                   *(arm.executor_id for arm in self.experiment.challengers)]
            if len(ids) != len(set(ids)):
                raise ValueError("experimental arms must have distinct route identities")
        return self


class AssessmentRunBinding(StrictModel):
    plan_id: str
    source_digest: Digest
    campaign_path: str
    started_at: UtcDateTime = Field(default_factory=utc_now)


class ComparisonEvidence(StrictModel):
    comparison: AssessmentComparison | None = None
    feature_combinations: list[dict[str, str | int | bool]] | None = None

    @model_serializer(mode="wrap")
    def preserve_legacy(self, handler: SerializerFunctionWrapHandler, info: SerializationInfo) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if result.get('execution_failures') == 0 and 'execution_failures' not in self.model_fields_set:
            result.pop('execution_failures', None)
        for key in ("comparison", "feature_combinations", "condition_comparisons", "grader_validation_digest", "recipe_case_set_digest", "preparation_request_ids", "utility_evidence", "pilot", "pilot_report_digest"):
            if result.get(key) is None:
                result.pop(key, None)
        return result


class PilotPolicy(StrictModel):
    """Timing-only design; never qualification or comparative evidence."""

    schema_version: Literal["assessment.pilot.v1"] = "assessment.pilot.v1"
    cases: Literal[8] = 8
    percentile: Literal[95] = 95
    deadline_multiplier: float = Field(default=2, ge=1, le=10)
    minimum_deadline_seconds: float = Field(default=1, gt=0, le=3600)
    maximum_deadline_seconds: float = Field(default=300, gt=0, le=3600)

    @model_validator(mode="after")
    def ordered_bounds(self) -> PilotPolicy:
        if self.minimum_deadline_seconds > self.maximum_deadline_seconds:
            raise ValueError("pilot deadline bounds must be ordered")
        return self


class AssessmentPlan(ComparisonEvidence):
    schema_version: Literal["assessment.plan.v1", "assessment.plan.v2", "assessment.plan.v3", "assessment.plan.v4", "assessment.plan.v5", "assessment.plan.v6"] = "assessment.plan.v1"
    plan_id: str = Field(default_factory=lambda: new_id("plan"))
    subject_digest: Digest
    recipe_digest: Digest
    mapping_digest: Digest
    environment_digest: Digest
    authorization_id: str
    candidate_id: str
    baseline_id: str
    reference_id: str | None = None
    definition_digests: list[Digest] = Field(min_length=1)
    route_fingerprints: dict[str, Digest]
    executable_dependencies: dict[str, Digest] = Field(default_factory=dict)
    suite: BenchmarkSuite
    applicability: dict[str, list[str | int | bool]]
    blocked_reasons: list[str] = Field(default_factory=list)
    setup_cost_ids: list[str] = Field(default_factory=list)
    planning_request_ids: list[str] = Field(default_factory=list)
    recipe_case_set_digest: Digest | None = None
    preparation_request_ids: list[str] | None = None
    pilot: PilotPolicy | None = None
    pilot_report_digest: Digest | None = None

    @model_validator(mode="after")
    def bound_comparison(self) -> AssessmentPlan:
        incremental = self.comparison is not None and self.comparison.experiment is not None
        pilot_version = self.schema_version in {"assessment.plan.v5", "assessment.plan.v6"}
        if pilot_version != (self.pilot is not None or self.pilot_report_digest is not None):
            raise ValueError("pilot semantics require a v5 or v6 plan")
        if self.schema_version == "assessment.plan.v6" and (self.pilot is not None or self.pilot_report_digest is None):
            raise ValueError("v6 requires a main plan linked to a completed pilot")
        if self.pilot is not None and self.pilot_report_digest is not None:
            raise ValueError("a pilot cannot inherit another pilot")
        if self.pilot_report_digest is not None and self.pilot_report_digest not in self.definition_digests:
            raise ValueError("pilot evidence must be bound to reviewed definitions")
        if self.pilot is not None:
            if content_digest(self.pilot) not in self.definition_digests:
                raise ValueError("pilot timing policy must be reviewed")
            if (len(self.suite.cases) != 8 or len({case.case_id for case in self.suite.cases}) != 8
                    or len({content_digest(case.action.input) for case in self.suite.cases}) != 8
                    or any(case.split.value != "qualification" for case in self.suite.cases)
                    or self.suite.repetitions != 1 or len(self.suite.conditions) != 1):
                raise ValueError("pilot requires eight distinct screening cases and one condition")
        if not pilot_version and self.schema_version.endswith(".v4") != incremental:
            raise ValueError("incremental experiments require a v4 plan")
        if not pilot_version and not incremental and self.schema_version.endswith(".v3") != (self.recipe_case_set_digest is not None):
            raise ValueError("materialized executable recipes require a v3 plan")
        if self.schema_version.endswith(".v1"):
            if self.comparison is not None or self.feature_combinations is not None:
                raise ValueError("legacy plans cannot acquire comparison semantics")
        elif self.comparison is None or self.feature_combinations is None:
            raise ValueError("v2 plans require a reviewed comparison and joint feature scope")
        else:
            comparison = self.comparison
            if comparison.candidate.executor_id != self.candidate_id or comparison.baseline.executor_id != self.baseline_id:
                raise ValueError("comparison arms must match the plan routes")
            if (comparison.reference.executor_id if comparison.reference else None) != self.reference_id:
                raise ValueError("comparison reference must match the plan route")
            if comparison.primary_condition not in {condition.value for condition in self.suite.conditions}:
                raise ValueError("primary comparison condition must be present in the suite")
            if content_digest(comparison) not in self.definition_digests:
                raise ValueError("comparison must be bound to reviewed definitions")
            for arm in (comparison.candidate, comparison.baseline, *(comparison.experiment.challengers if comparison.experiment else [])):
                if self.route_fingerprints.get(arm.executor_id) != arm.fingerprint:
                    raise ValueError("comparison arm identity differs from the frozen route")
                qualification_baseline = comparison.experiment is not None and comparison.experiment.stage == "qualification" and arm.executor_id == self.baseline_id
                if not qualification_baseline and arm.executor_id not in {route.route_id for route in self.suite.routes}:
                    raise ValueError("comparison arm is absent from the campaign")
        return self


class DefinitionProposal(StrictModel):
    recipe: RecipeDefinition
    candidate: ExecutorSpec
    explanation: str = Field(max_length=10000)
    missing_requirements: list[str] = Field(default_factory=list)
    planning_request_id: str | None = None


class AssessmentPlanningRequest(StrictModel):
    schema_version: Literal["assessment.planning.v1"] = "assessment.planning.v1"
    plan_id: str = Field(default_factory=lambda: new_id("planning"))
    subject_digest: Digest
    recipe_digest: Digest
    mapping_digest: Digest
    environment_digest: Digest
    authorization_id: str
    definition_digests: list[Digest]
    planner: ExecutorSpec
    executable_dependencies: dict[str, Digest] = Field(default_factory=dict)


class ConformanceProbeRequest(StrictModel):
    schema_version: Literal["assessment.conformance-request.v1", "assessment.conformance-request.v2", "assessment.conformance-request.v3", "assessment.conformance-request.v4"] = "assessment.conformance-request.v1"
    plan_id: str = Field(default_factory=lambda: new_id("conformance_probe"))
    subject_digest: Digest
    recipe_digest: Digest
    mapping_digest: Digest
    environment_digest: Digest
    authorization_id: str
    definition_digests: list[Digest]
    worker_digest: Digest
    executable_dependencies: dict[str, Digest]
    operation: Literal["worker_inspection", "worker_pair_inspection", "composed_pair_inspection"] | None = None
    pair_definition_digest: Digest | None = None
    composed_model_turns: Literal[0, 1] = 0

    @model_validator(mode="before")
    @classmethod
    def strict_composed_allowance(cls, value: Any) -> Any:
        if isinstance(value, dict) and 'composed_model_turns' in value:
            turns = value['composed_model_turns']
            if type(turns) is not int or turns not in {0, 1}:
                raise ValueError('composed model allowance must be the integer zero or one')
        return value

    @model_validator(mode="after")
    def operation_version(self) -> ConformanceProbeRequest:
        if self.schema_version.endswith('.v4'):
            if (self.operation != 'composed_pair_inspection'
                    or self.pair_definition_digest not in self.definition_digests
                    or not self.executable_dependencies):
                raise ValueError('composed inspection requires its frozen definition and dependencies')
        elif self.composed_model_turns != 0:
            raise ValueError('composed model allowance requires a v4 request')
        elif self.operation == 'composed_pair_inspection':
            raise ValueError('composed inspection requires a v4 conformance request')
        elif self.schema_version.endswith('.v3'):
            if self.operation != 'worker_pair_inspection' or self.pair_definition_digest not in self.definition_digests:
                raise ValueError("paired inspection requires its frozen pair definition")
        elif self.pair_definition_digest is not None or self.operation == 'worker_pair_inspection':
            raise ValueError("paired inspection requires a v3 conformance request")
        elif (self.operation is None) != self.schema_version.endswith('.v1'):
            raise ValueError("worker inspection requires a v2 conformance request")
        return self

    @model_serializer(mode="wrap")
    def preserve_connectivity(self, handler: SerializerFunctionWrapHandler) -> dict[str, object]:
        result: dict[str, object] = handler(self)
        if self.operation is None:
            result.pop('operation', None)
        if self.pair_definition_digest is None:
            result.pop('pair_definition_digest', None)
        if not self.schema_version.endswith('.v4'):
            result.pop('composed_model_turns', None)
        return result


class RecipeRuntimeBinding(StrictModel):
    dependencies: dict[str, Digest]


class RecipeMaterializationRequest(StrictModel):
    schema_version: Literal["assessment.recipe-materialization.v1", "assessment.recipe-materialization.v2"] = "assessment.recipe-materialization.v1"
    plan_id: str = Field(default_factory=lambda: new_id("recipe_generation"))
    subject_digest: Digest
    recipe_digest: Digest
    mapping_digest: Digest
    environment_digest: Digest
    authorization_id: str
    definition_digests: list[Digest]
    seed: int
    runtime_dependencies: dict[str, Digest] | None = None

    @model_serializer(mode="wrap")
    def preserve_historical_request(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.runtime_dependencies is None:
            result.pop("runtime_dependencies", None)
        return result


class RecipeCaseSet(StrictModel):
    schema_version: Literal["assessment.recipe-cases.v1"] = "assessment.recipe-cases.v1"
    request_id: str
    recipe_digest: Digest
    environment_digest: Digest
    seed: int
    cases: list[BenchmarkCase] = Field(min_length=141, max_length=141)


class AssessmentProgress(StrictModel):
    schema_version: Literal["assessment.progress.v1"] = "assessment.progress.v1"
    id: str
    plan_id: str
    state: Literal["queued", "running", "cancelled", "indeterminate", "complete"]
    report_id: str | None = None
    started_at: UtcDateTime | None = None
    error_code: str | None = None


class AssessmentReport(ComparisonEvidence):
    schema_version: Literal["assessment.report.v1", "assessment.report.v2", "assessment.report.v3"] = "assessment.report.v1"
    report_id: str = Field(default_factory=lambda: new_id("fit"))
    plan_digest: Digest
    outcome: Literal[
        "useful_within_scope", "no_measured_benefit", "unsuitable", "insufficient_evidence"
    ]
    qualification_passed: bool
    distinct_holdout_cases: int = Field(ge=0)
    distinct_paired_cases: int = Field(ge=0)
    correctness_failures: int = Field(ge=0)
    execution_failures: int = Field(default=0, ge=0)
    tested_variations: list[str]
    condition_comparisons: dict[str, Any] | None = None
    utility_evidence: dict[str, Any] | None = None
    measured_usage: dict[str, float | None]
    measurement_coverage: dict[str, str] = Field(default_factory=dict)
    paired_measurement_cases: dict[str, int] = Field(default_factory=dict)
    paired_savings: dict[str, float | None]
    savings_interval: dict[str, list[float]] = Field(default_factory=dict)
    break_even_uses: dict[str, float | None]
    estimated_production_savings: dict[str, float | None] = Field(default_factory=dict)
    campaign_digest: Digest
    operation_ledger_digest: Digest | None = None
    grader_validation_digest: Digest | None = None
    host_runtime_digests: dict[str, Digest] = Field(default_factory=dict)
    deterministic_reference_comparison: dict[str, float | None] = Field(default_factory=dict)
    explanations: list[str]
    created_at: UtcDateTime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def versioned_utility(self) -> AssessmentReport:
        incremental = self.comparison is not None and self.comparison.experiment is not None
        if self.schema_version.endswith('.v3') != incremental or incremental != (self.utility_evidence is not None):
            raise ValueError("incremental utility requires report v3 with bound comparison evidence")
        return self


class AssessmentOperation(StrictModel):
    operation_id: str
    plan_id: str
    stage: str
    reserved: AssessmentLimits
    started_at: UtcDateTime = Field(default_factory=utc_now)
    elapsed_seconds: float | None = Field(default=None, ge=0)
    accounting: ResourceAccounting | None = None
    resources: ResourceVector | None = None


class AssessmentOperationLedger(StrictModel):
    plan_id: str
    operations: list[AssessmentOperation]


class AssessmentSetupCost(StrictModel):
    cost_id: str = Field(default_factory=lambda: new_id("setup_cost"))
    subject_digest: Digest
    stage: str
    elapsed_seconds: float = Field(ge=0)
    cpu_ms: float = Field(ge=0)


class ScopedAdmission(ComparisonEvidence):
    schema_version: Literal["assessment.admission.v1", "assessment.admission.v2", "assessment.admission.v3"] = "assessment.admission.v1"
    admission_id: str = Field(default_factory=lambda: new_id("admission"))
    executor_id: str
    baseline_id: str
    capability: str
    candidate_fingerprint: Digest
    executable_dependencies: dict[str, Digest] = Field(default_factory=dict)
    baseline_fingerprint: Digest
    host_runtime_digests: dict[str, Digest] = Field(default_factory=dict)
    subject_digest: Digest
    definition_digests: list[Digest]
    recipe_digest: Digest
    mapping_digest: Digest
    environment_digest: Digest
    extractor: str
    applicability: dict[str, list[str | int | bool]]
    qualification_report_id: str
    report_id: str
    authorization_id: str
    expires_at: UtcDateTime

    @model_validator(mode="after")
    def versioned_experiment(self) -> ScopedAdmission:
        if self.schema_version.endswith('.v3') != (self.comparison is not None and self.comparison.experiment is not None):
            raise ValueError("incremental admission requires the assessed v3 comparison binding")
        return self
