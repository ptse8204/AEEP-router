"""Resolve reviewed upstream integration tasks using the existing record store."""

from __future__ import annotations

from ..errors import ConfigurationError
from ..registry import validate_json
from .models import (
    AssessmentEnvironment,
    IncrementalExperiment,
    IntegrationCaseSet,
    RecipeDefinition,
    content_digest,
)
from .repository import AssessmentRepository


def require_integration_cases(
    repository: AssessmentRepository,
    identity: str,
    *,
    recipe: RecipeDefinition,
    environment: AssessmentEnvironment,
    seed: int,
    experiment: IncrementalExperiment | None,
) -> IntegrationCaseSet:
    """Read and validate only. This neither reviews nor authorizes execution."""
    record = IntegrationCaseSet.model_validate(repository.get("integration_case_set", identity))
    digest = content_digest(record)
    with repository.store._lock:
        row = repository.store._connection.execute(
            "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)
        ).fetchone()
    if row is None or row[0]:
        raise ConfigurationError("integration task set is unreviewed or revoked")
    if (
        recipe.extension is None
        or experiment is None
        or experiment.stage != "qualification"
        or experiment.exposure != "required"
        or experiment.challengers
        or record.recipe_digest != content_digest(recipe)
        or record.environment_digest != content_digest(environment)
        or record.seed != seed
        or recipe.dependencies.get("benchmark_pack") != record.benchmark_pack_digest
    ):
        raise ConfigurationError(
            "integration tasks differ from the exact recipe, pack, environment or required-use check"
        )
    for case in record.cases:
        if (
            case.action.capability != recipe.capability
            or case.variation not in recipe.variations
            or case.template_family not in recipe.extension.template_families
            or not case.validators
        ):
            raise ConfigurationError("integration task differs from its reviewed grader contract")
        validate_json(case.action.input, recipe.input_schema, label="integration task input")
    return record
