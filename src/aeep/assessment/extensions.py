"""Reviewed JSON recipe programs run through controlled executors, never imports."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from ..accounting import aggregate_accounting
from ..benchmarking import BenchmarkCase, BenchmarkSplit
from ..errors import ConfigurationError
from ..models import (
    ActionConstraints,
    ActionRequest,
    ExecutorKind,
    ExecutorSpec,
    TrustLevel,
    ValidationKind,
    ValidationResult,
    ValidationSpec,
    new_id,
)
from ..registry import validate_json
from ..workflow import pointer_get
from .models import (
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlan,
    AssessmentSubject,
    ExecutableRecipeExtension,
    RecipeCaseSet,
    RecipeDefinition,
    RecipeMaterializationRequest,
    RecipeRuntimeBinding,
    content_digest,
)

if TYPE_CHECKING:
    from .service import AssessmentService


def structural_features(recipe: RecipeDefinition, value: dict[str, Any]) -> dict[str, str | int | bool] | None:
    if recipe.extractor == 'workbook_structure:1':
        from .workbook import workbook_features
        return workbook_features(value)
    extension = recipe.extension
    if extension is None or len(json.dumps(value, ensure_ascii=False)) > 100000:
        return None
    result: dict[str, str | int | bool] = {}
    try:
        for name, rule in extension.feature_rules.items():
            item = pointer_get(value, rule.path)
            if rule.operation == "length" and isinstance(item, (str, list, dict)):
                result[name] = len(item)
            elif rule.operation == "type":
                result[name] = type(item).__name__
            elif rule.operation == "enum" and isinstance(item, (str, int, bool)) and item in rule.values:
                result[name] = item
            else:
                return None
    except (ValueError, KeyError, IndexError, TypeError):
        return None
    return result


def prepare(service: AssessmentService, *, subject_id: str, recipe_id: str,
            authorization_id: str, environment: AssessmentEnvironment, seed: int) -> RecipeMaterializationRequest:
    from .identity import runtime_dependencies

    subject = AssessmentSubject.model_validate(service.repository.get("subject", subject_id))
    recipe = RecipeDefinition.model_validate(service.repository.get("recipe", recipe_id))
    require_environment(recipe, environment)
    recipe_digest = content_digest(recipe)
    environment_digest = service.repository.put("environment", content_digest(environment), environment)
    dependencies = runtime_dependencies()
    runtime = RecipeRuntimeBinding(dependencies=dependencies)
    runtime_digest = service.repository.put("recipe_runtime", content_digest(runtime), runtime)
    request = RecipeMaterializationRequest(schema_version="assessment.recipe-materialization.v2", subject_digest=content_digest(subject), recipe_digest=recipe_digest,
        mapping_digest=recipe_digest, environment_digest=environment_digest, authorization_id=authorization_id,
        definition_digests=[recipe_digest, environment_digest, runtime_digest], seed=seed,
        runtime_dependencies=dependencies)
    service.repository.put("recipe_materialization_request", request.plan_id, request)
    return request


def require_environment(recipe: RecipeDefinition, environment: AssessmentEnvironment) -> None:
    if recipe.extension is None:
        raise ConfigurationError("recipe has no executable extension")
    if environment.kind != "container" or environment.network or environment.read_only_roots:
        raise ConfigurationError("recipe programs require a pinned offline container without extra host roots")


async def invoke(service: AssessmentService, scope: AssessmentPlan | RecipeMaterializationRequest,
                 spec: ExecutorSpec, value: dict[str, Any], *, stage: str, operation_id: str | None = None,
                 elapsed_times: list[float] | None = None) -> tuple[Any, float]:
    from .containment import ContainerExecutor
    from .identity import verify_dependencies

    recipe = RecipeDefinition.model_validate(service.repository.get("recipe", scope.recipe_digest))
    environment = AssessmentEnvironment.model_validate(service.repository.get("environment", scope.environment_digest))
    require_environment(recipe, environment)
    if recipe.extension is None or spec not in (recipe.extension.generator, recipe.extension.grader, recipe.extension.reference):
        raise ConfigurationError("recipe executor is not in its reviewed definition")
    service.repository.authorize(scope)
    if isinstance(scope, RecipeMaterializationRequest):
        if not scope.runtime_dependencies or content_digest(RecipeRuntimeBinding(dependencies=scope.runtime_dependencies)) not in scope.definition_digests:
            raise ConfigurationError("recipe materialization runtime must be frozen and reviewed")
        verify_dependencies(scope.runtime_dependencies)
    operation_id = operation_id or new_id("recipe_call")
    timeout = float(spec.config["timeout_seconds"])
    service.repository.reserve(scope, operation_id,
        AssessmentLimits(max_operations=1, max_elapsed_seconds=timeout + 5), stage=stage)
    started = time.perf_counter()
    router = None
    outcome = None
    try:
        router = service.router._campaign_router([spec], plan_digest=content_digest(scope),
            database=service.directory / scope.plan_id / "recipe-operations" / f"{operation_id}.sqlite3",
            snapshot_bound_digests={
                content_digest(scope), scope.subject_digest, scope.recipe_digest,
                scope.mapping_digest, scope.environment_digest, *scope.definition_digests,
                *([scope.recipe_case_set_digest] if isinstance(scope, AssessmentPlan) and scope.recipe_case_set_digest else []),
            })
        router._executors[ExecutorKind.COMMAND] = ContainerExecutor(environment)
        def check() -> None:
            service.repository.authorize(scope)
            if isinstance(scope, RecipeMaterializationRequest):
                verify_dependencies(scope.runtime_dependencies or {})
            else:
                service._verify_dependencies(scope)
        router._trial_check = check
        outcome = await router.execute(ActionRequest(capability=spec.capability, input=value,
            constraints=ActionConstraints(allowed_executor_ids=[spec.id])))
        for receipt in outcome.receipts:
            stored = router.store.get_receipt(receipt.receipt_id)
            if stored is not None:
                service.repository.put("recipe_receipt", stored.receipt_id, stored)
        if not outcome.ok:
            raise ConfigurationError("recipe program failed; candidate correctness is not evaluated")
    finally:
        try:
            if router is not None:
                await router.close()
        finally:
            elapsed = time.perf_counter() - started
            if elapsed_times is not None:
                elapsed_times.append(elapsed)
            service.repository.finish_operation(operation_id, elapsed_seconds=elapsed,
                accounting=aggregate_accounting(outcome.receipts) if outcome else None)
    return outcome.output, elapsed


async def materialize(service: AssessmentService, request_id: str) -> RecipeCaseSet:
    request = RecipeMaterializationRequest.model_validate(service.repository.get("recipe_materialization_request", request_id))
    service.repository.authorize(request)
    with service.router.store._lock:
        exists = service.router.store._connection.execute(
            "SELECT 1 FROM assessment_records WHERE kind='recipe_case_set' AND id=?", (request_id,)).fetchone()
    if exists:
        return RecipeCaseSet.model_validate(service.repository.get("recipe_case_set", request_id))
    recipe = RecipeDefinition.model_validate(service.repository.get("recipe", request.recipe_digest))
    assert recipe.extension is not None
    payload, _elapsed = await invoke(service, request, recipe.extension.generator,
        {"seed": request.seed, "stages": [{"split": split.value, "count": count} for split, count in STAGES],
         "variations": recipe.variations}, stage="recipe_generation", operation_id=f"{request_id}-generator")
    if not isinstance(payload, dict) or set(payload) != {"cases"} or not isinstance(payload["cases"], list) or len(payload["cases"]) != 141:
        raise ConfigurationError("recipe generator must return exactly 141 synthetic cases")
    cases = []
    offset = 0
    all_inputs: set[str] = set()
    for split, count in STAGES:
        observed_inputs: set[str] = set()
        variation_counts = dict.fromkeys(recipe.variations, 0)
        for index, raw in enumerate(payload["cases"][offset:offset + count]):
            if not isinstance(raw, dict) or set(raw) != {"input", "output", "variation", "template_family"}:
                raise ConfigurationError("recipe generator returned an invalid case contract")
            validate_json(raw["input"], recipe.input_schema, label="generated recipe input")
            validate_json(raw["output"], recipe.extension.truth_schema or recipe.output_schema, label="generated recipe truth")
            variation = raw["variation"]
            if variation not in variation_counts or raw["template_family"] not in recipe.extension.template_families:
                raise ConfigurationError("generated case uses an unreviewed variation or template")
            features = structural_features(recipe, raw["input"])
            if features is None or any(features.get(key) != expected for key, expected in recipe.extension.variation_features[variation].items()):
                raise ConfigurationError("generated structure does not match its reviewed variation")
            input_digest = content_digest(raw["input"])
            if input_digest in all_inputs:
                raise ConfigurationError("recipe generator reused an input across experiment stages")
            observed_inputs.add(input_digest)
            all_inputs.add(input_digest)
            variation_counts[variation] += 1
            validators = [ValidationSpec(kind=ValidationKind.CALLBACK,
                config={"name": grader_name(raw["input"], raw["output"]), "expected": raw["output"]})]
            if recipe.extension.failure_codes is not None:
                validators[0].config["failure_codes"] = recipe.extension.failure_codes
            if recipe.extension.truth_schema is None:
                validators[0].config.pop("expected")  # Preserve historical case digests.
                validators.append(ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": raw["output"]}))
            cases.append(BenchmarkCase(case_id=f"{request_id}-{split.value}-{index}", split=split,
                variation=variation, template_family=raw["template_family"],
                action=ActionRequest(capability=recipe.capability, input=raw["input"]),
                validators=validators))
        if len(observed_inputs) != count or (split == BenchmarkSplit.HOLDOUT and max(variation_counts.values()) - min(variation_counts.values()) > 1):
            raise ConfigurationError("generated cases must be distinct and holdout variations balanced")
        offset += count
    record = RecipeCaseSet(request_id=request_id, recipe_digest=request.recipe_digest,
        environment_digest=request.environment_digest, seed=request.seed, cases=cases)
    service.repository.put("recipe_case_set", request_id, record)
    return record


STAGES = ((BenchmarkSplit.QUALIFICATION, 8), (BenchmarkSplit.TRAINING, 28), (BenchmarkSplit.HOLDOUT, 105))


def grader_name(value: dict[str, Any], expected: dict[str, Any]) -> str:
    return "contained_recipe_" + content_digest({"input": value, "expected": expected})


def grader_results(reply: Any, extension: ExecutableRecipeExtension, count: int) -> list[ValidationResult]:
    """Only exact reviewed codes may leave the contained grader; never its free text."""
    diagnostic = extension.failure_codes is not None
    keys = {"valid", "failure_codes"} if diagnostic else {"valid"}
    if (not isinstance(reply, dict) or set(reply) != keys
            or not isinstance(reply.get("valid"), list) or len(reply["valid"]) != count
            or any(type(value) is not bool for value in reply["valid"])):
        raise ConfigurationError("recipe grader returned an invalid result; assessment blocked")
    codes = reply.get("failure_codes", [None] * count)
    if diagnostic and (not isinstance(codes, list) or len(codes) != count
            or any((code is not None if valid else code not in (extension.failure_codes or []))
                   for valid, code in zip(reply["valid"], codes, strict=True))):
        raise ConfigurationError("recipe grader returned an unreviewed failure code; assessment blocked")
    return [ValidationResult(kind=ValidationKind.CALLBACK, valid=valid,
                quality_score=1.0 if valid else 0.0, detail=code or "", trust=TrustLevel.VERIFIED)
            for valid, code in zip(reply["valid"], codes, strict=True)]


def callbacks(service: AssessmentService, plan: AssessmentPlan, recipe: RecipeDefinition) -> dict[str, Any]:
    from ..validators import ValidationContext

    assert recipe.extension is not None
    grader = recipe.extension.grader
    result = {}
    for case in [*plan.suite.cases, *plan.suite.warmup_cases]:
        expected = case.validators[-1].config["expected"]

        async def grade(context: ValidationContext, truth: dict[str, Any] = expected) -> ValidationResult:
            reply, _elapsed = await invoke(service, plan, grader,
                {"examples": [{"input": context.input, "output": context.output, "expected": truth}]}, stage="recipe_grading")
            assert recipe.extension is not None
            return grader_results(reply, recipe.extension, 1)[0]

        result[grader_name(case.action.input, expected)] = grade
    return result


async def validate_grader(service: AssessmentService, plan: AssessmentPlan, recipe: RecipeDefinition,
                          program_seconds: list[float]) -> tuple[list[BenchmarkCase], int]:
    from .recipes import faulty_outputs

    assert recipe.extension is not None
    extension = recipe.extension
    literals = [BenchmarkCase(case_id=f"extension-literal-{index}", split=BenchmarkSplit.QUALIFICATION,
        action=ActionRequest(capability=recipe.capability, input=fixture.input),
        validators=[ValidationSpec(kind=ValidationKind.EXACT_MATCH, config={"expected": fixture.output})])
        for index, fixture in enumerate([*extension.independent_fixtures, *extension.transformed_fixtures])]
    checked = [*literals, *plan.suite.cases, *plan.suite.warmup_cases]
    for case in checked:
        validate_json(case.action.input, recipe.input_schema, label="recipe validation input")
        validate_json(case.validators[-1].config["expected"], extension.truth_schema or recipe.output_schema, label="recipe validation truth")
    truths = [case.validators[-1].config["expected"] for case in checked]
    outputs_from_reference = []
    inputs = [case.action.input for case in checked]
    for batch in bounded_batches(inputs) if extension.truth_schema is not None else [inputs]:
        reference, _elapsed = await invoke(service, plan, extension.reference,
            {"inputs": batch}, stage="grader_reference", elapsed_times=program_seconds)
        if (not isinstance(reference, dict) or set(reference) != {"outputs"}
                or not isinstance(reference["outputs"], list) or len(reference["outputs"]) != len(batch)):
            raise ConfigurationError("generator or independent reference disagrees with reviewed truth")
        outputs_from_reference.extend(reference['outputs'])
    if extension.truth_schema is None and outputs_from_reference != truths:
        raise ConfigurationError("generator or independent reference disagrees with reviewed truth")
    examples: list[dict[str, Any]] = []
    decisions = []
    for fixture in [*extension.independent_fixtures, *extension.transformed_fixtures]:
        if fixture.grader_output is not None:
            validate_json(fixture.grader_output, recipe.output_schema, label="independent grader output")
            examples.append({"input": fixture.input, "output": fixture.grader_output, "expected": fixture.output})
            decisions.append(True)
    for index, case in enumerate(checked if extension.truth_schema is not None else [*literals, *plan.suite.cases[:8]]):
        expected = case.validators[-1].config["expected"]
        correct = outputs_from_reference[index] if extension.truth_schema is not None else expected
        validate_json(correct, recipe.output_schema, label="reference recipe output")
        # Every generated answer is checked. Faults additionally challenge literals
        # and screening cases, without duplicating each large artifact 141 times.
        outputs = [correct, *faulty_outputs(correct), *extension.fault_outputs] if index < len(literals) + 8 else [correct]
        examples.extend({"input": case.action.input, "output": output, "expected": expected}
            for output in outputs)
        decisions.extend([True, *[False for _ in outputs[1:]]])
    observed: list[bool | None] = []
    for batch in bounded_batches(examples) if extension.truth_schema is not None else [examples]:
        reply, _elapsed = await invoke(service, plan, extension.grader, {"examples": batch}, stage="grader_probe", elapsed_times=program_seconds)
        observed.extend(result.valid for result in grader_results(reply, extension, len(batch)))
    if observed != decisions:
        raise ConfigurationError("executable grader failed independent correctness/fault validation")
    faults = sum(not item for item in decisions)
    return literals, faults


def bounded_batches(values: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Leave room for the JSON envelope inside existing one-megabyte stdin bounds."""
    result: list[list[dict[str, Any]]] = []
    batch: list[dict[str, Any]] = []
    size = 0
    for value in values:
        length = len(json.dumps(value).encode()) + 2
        if length > 750000:
            raise ConfigurationError('recipe validation item exceeds its contained input bound')
        if batch and size + length > 750000:
            result.append(batch)
            batch, size = [], 0
        batch.append(value)
        size += length
    if batch:
        result.append(batch)
    return result
