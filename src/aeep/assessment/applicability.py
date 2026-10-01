"""Execution-only admission checks. No assessment work is started from this module."""

from __future__ import annotations

import hashlib
from pathlib import Path

from ..errors import ConfigurationError, InputValidationError, NoRouteError
from ..models import ActionRequest, ExecutorSpec, utc_now
from ..qualification import behavior_fingerprint
from ..registry import validate_json
from ..store import ReceiptStore
from .identity import verify_dependencies
from .models import (
    AssessmentEnvironment,
    AssessmentSubject,
    RecipeDefinition,
    ScopedAdmission,
    content_digest,
    recipe_implementation_digest,
)
from .recipes import recipe_features, shipped_recipe
from .repository import AssessmentRepository


def require_applicable(
    store: ReceiptStore,
    spec: ExecutorSpec,
    request: ActionRequest | None,
    baseline: ExecutorSpec | None = None,
) -> None:
    with store._lock:
        marker = store._connection.execute(
            "SELECT admission_id, revoked FROM assessment_admissions WHERE executor_id=?",
            (spec.id,),
        ).fetchone()
        if marker is None:
            return
        if marker[1] or request is None:
            raise NoRouteError("scoped automatic use is revoked or lacks applicability evidence")
        repository = AssessmentRepository(store)
        try:
            admission = ScopedAdmission.model_validate(repository.get("admission", marker[0]))
            repository.authorize(admission)
            try:
                verify_dependencies(admission.executable_dependencies)
            except (ConfigurationError, OSError):
                repository.revoke_admission(spec.id)
                raise
            for executor_id, digest in admission.host_runtime_digests.items():
                binding = store.host_runtime_digests.get(executor_id)
                if binding is None or binding[1] != digest:
                    raise ConfigurationError("assessed host identity is unresolved or changed")
            if admission.candidate_fingerprint != behavior_fingerprint(spec):
                repository.revoke_admission(spec.id)
                raise ConfigurationError("candidate identity changed")
            if admission.expires_at <= utc_now():
                raise ConfigurationError("admission expired or candidate changed")
            if baseline is None or behavior_fingerprint(baseline) != admission.baseline_fingerprint:
                if baseline is not None:
                    repository.revoke_admission(spec.id)
                raise ConfigurationError("admission baseline identity changed")
            from .boundary import require_differential, require_managed_boundaries
            from .models import AssessmentPlan, AssessmentReport, ReviewedMapping
            mapping = ReviewedMapping.model_validate(repository.get("mapping", admission.mapping_digest))
            environment = AssessmentEnvironment.model_validate(repository.get("environment", admission.environment_digest))
            require_managed_boundaries(repository, environment,
                [spec, baseline, *mapping.dependencies], admission.host_runtime_digests)
            if admission.comparison is not None and admission.comparison.experiment is not None:
                report = AssessmentReport.model_validate(repository.get("report", admission.report_id))
                assessed_plan = AssessmentPlan.model_validate(repository.get("plan", report.plan_digest))
                require_differential(repository, environment, assessed_plan)
            recipe = RecipeDefinition.model_validate(
                repository.get("recipe", admission.recipe_digest)
            )
            family = (
                recipe.generator.split(":")[1]
                if recipe.generator.startswith("builtin:")
                else "record_template"
            )
            if recipe.implementation_digest != recipe_implementation_digest() or (
                recipe.extension is None and recipe.generator != "record_template:1"
                and content_digest(shipped_recipe(family)) != admission.recipe_digest
            ):
                repository.revoke_admission(spec.id)
                raise ConfigurationError("reviewed recipe changed")
            validate_json(request.input, recipe.input_schema, label="assessed task input")
            observed = recipe_features(recipe, request.input)
            if (
                observed is None
                or set(observed) != set(admission.applicability)
                or any(value not in admission.applicability[key] for key, value in observed.items())
            ):
                raise ConfigurationError("request lies outside the assessed scope")
            if admission.feature_combinations is not None and observed not in admission.feature_combinations:
                raise ConfigurationError("request combines features that were not assessed together")
            subject = AssessmentSubject.model_validate(
                repository.get("subject", admission.subject_digest)
            )
            location = Path(subject.location)
            for name, digest in subject.dependency_digests.items():
                path = location / name if location.is_dir() else location
                if (
                    path.is_symlink()
                    or not path.is_file()
                    or hashlib.sha256(path.read_bytes()).hexdigest() != digest
                ):
                    repository.revoke_admission(spec.id)
                    raise ConfigurationError("assessed plugin dependency changed")
        except (ConfigurationError, InputValidationError, ValueError, OSError, IndexError) as exc:
            raise NoRouteError(
                "scoped automatic use is not applicable; use a feasible baseline"
            ) from exc
