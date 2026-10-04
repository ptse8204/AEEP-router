"""Assessment commands; authorization and review are deliberately operator-only."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import typer

from ..errors import ConfigurationError
from ..router import Router
from .models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentSetupRequest,
    RecipeDefinition,
)
from .service import AssessmentService

app = typer.Typer(help="Propose, review and run bounded plugin assessments.")


@app.callback()
def configure(
    ctx: typer.Context,
    manifest: Path = typer.Option(..., "--manifest", "-m"),
    directory: Path | None = typer.Option(None, "--directory"),
) -> None:
    router = Router.from_manifest(manifest)
    ctx.obj = AssessmentService(
        router, directory or manifest.resolve().parent / ".aeep" / "assessments"
    )
    ctx.call_on_close(lambda: asyncio.run(router.close()))


def emit(value: Any) -> None:
    typer.echo(
        value.model_dump_json(indent=2)
        if hasattr(value, "model_dump_json")
        else json.dumps(value, indent=2)
    )


@app.command("inspect")
def inspect(ctx: typer.Context, location: Path, kind: str = "plugin") -> None:
    emit(ctx.obj.inspect_local(location, kind=kind))


@app.command('setup-options')
def setup_options(ctx: typer.Context, authorization: str, after: str = '', limit: int = 50) -> None:
    """List configured choices without inspecting files or executing candidates."""
    from .onboarding import setup_options as options
    emit(options(ctx.obj, authorization, after=after, limit=limit))


@app.command('setup')
def setup(ctx: typer.Context, subject: str, recipe: str, candidate: str, baseline: str,
          authorization: str, environment: str, structure: str | None = None, seed: int = 0,
          case_set: str | None = None, experiment: str | None = None, pilot_report: str | None = None) -> None:
    """Prepare a plan or fixture request from existing configuration; approve nothing."""
    from .onboarding import prepare_setup
    emit(prepare_setup(ctx.obj, AssessmentSetupRequest.model_validate(dict(subject_id=subject, recipe_id=recipe,
        candidate_id=candidate, baseline_id=baseline, authorization_id=authorization, environment_id=environment,
        structure=structure, seed=seed, case_set_id=case_set, experiment_id=experiment, pilot_report_id=pilot_report))))


@app.command('define-experiment')
def define_experiment(ctx: typer.Context, file: Path) -> None:
    """Store an inert experimental definition; operator review is a separate action."""
    from .models import IncrementalExperiment, content_digest
    experiment = IncrementalExperiment.model_validate_json(file.read_bytes())
    digest = ctx.obj.repository.put('experiment', content_digest(experiment), experiment)
    emit({'experiment_id': digest, 'reviewed': False})


@app.command('define-task-scope')
def define_task_scope(ctx: typer.Context, file: Path) -> None:
    """Store inert task delegation; use the existing exact review/revoke commands."""
    from ..models import TaskScope
    scope = TaskScope.model_validate_json(file.read_bytes())
    digest = ctx.obj.repository.put('task_scope', scope.scope_id, scope)
    emit({'scope_id': scope.scope_id, 'digest': digest, 'reviewed': False})


@app.command("propose")
def propose(
    ctx: typer.Context,
    subject: str,
    family: str,
    candidate: str,
    baseline: str,
    authorization: str,
    environment: Path,
    seed: int = 0,
    structure: str | None = None,
    case_set: str | None = None,
    experiment: Path | None = None,
    pilot_policy: Path | None = None,
    pilot_report: str | None = None,
) -> None:
    if structure not in {None, "direct", "controlled_agent", "workflow"}:
        raise ConfigurationError("structure must be direct, controlled_agent or workflow")
    from .models import IncrementalExperiment, PilotPolicy
    emit(
        ctx.obj.propose(
            subject_id=subject,
            family=family,
            candidate_id=candidate,
            baseline_id=baseline,
            authorization_id=authorization,
            environment=AssessmentEnvironment.model_validate_json(environment.read_bytes()),
            seed=seed,
            structure=structure,
            case_set_id=case_set,
            experiment=IncrementalExperiment.model_validate_json(experiment.read_bytes()) if experiment else None,
            pilot=PilotPolicy.model_validate_json(pilot_policy.read_bytes()) if pilot_policy else None,
            pilot_report_id=pilot_report,
        )
    )


@app.command("pilot-timing")
def pilot_timing(ctx: typer.Context, report: str) -> None:
    """Read pooled timing for a new reviewed budget; never expand authority."""
    from .pilot import timing_preview
    emit(timing_preview(ctx.obj, report))


@app.command("signin-worker")
def signin_worker(ctx: typer.Context, request: str) -> None:
    """Run only in your own terminal: bounded protected Codex device login."""
    from ..hosts.codex_signin import signin_worker as signin
    emit(asyncio.run(signin(ctx.obj, request)))


@app.command("prepare-recipe")
def prepare_recipe(ctx: typer.Context, subject: str, recipe: str, authorization: str, environment: Path, seed: int = 0) -> None:
    """Create an inert request for reviewed, contained recipe generation."""
    from .extensions import prepare
    emit(prepare(ctx.obj, subject_id=subject, recipe_id=recipe, authorization_id=authorization,
        environment=AssessmentEnvironment.model_validate_json(environment.read_bytes()), seed=seed))


@app.command("workbook-definition")
def workbook_definition() -> None:
    """Export the inert workbook definition for operator review and define/prepare-recipe."""
    from .workbook import workbook_recipe
    emit(workbook_recipe())


@app.command("skillsbench-definition")
def skillsbench_definition(asset_root: Path | None = typer.Option(None, "--asset-root")) -> None:
    """Export the inert, pinned SkillsBench offer-letter adaptation for review."""
    from .skillsbench_recipe import skillsbench_offer_letter_recipe
    emit(skillsbench_offer_letter_recipe(asset_root))


@app.command("generate-cases")
def generate_cases(ctx: typer.Context, request: str) -> None:
    """Execute an exact reviewed recipe under an existing grant."""
    from .extensions import materialize
    emit(asyncio.run(materialize(ctx.obj, request)))


@app.command("show")
def show(ctx: typer.Context, kind: str, identity: str) -> None:
    emit(ctx.obj.repository.get(kind, identity))


@app.command("review")
def review(ctx: typer.Context, digest: str, revoke: bool = False) -> None:
    ctx.obj.repository.review(digest, revoke=revoke)
    emit({"digest": digest, "reviewed": not revoke})


@app.command("authorize")
def authorize(ctx: typer.Context, file: Path) -> None:
    grant = AssessmentAuthorization.model_validate_json(file.read_bytes())
    ctx.obj.repository.grant(grant)
    emit(grant)


@app.command("amend-scope")
def amend_scope(ctx: typer.Context, file: Path) -> None:
    """Apply an exact reviewed bundle without creating a new budget."""
    from .models import AssessmentBudgetAmendment, AssessmentScopeAmendment
    bundle = json.loads(file.read_text())
    amendment = AssessmentScopeAmendment.model_validate(bundle["amendment"])
    budget = AssessmentBudgetAmendment.model_validate(bundle["budget_amendment"]) if "budget_amendment" in bundle else None
    ctx.obj.repository.approve_bundle(amendment, bundle["definitions"], budget_amendment=budget)
    emit(amendment)


@app.command("amend-budget")
def amend_budget(ctx: typer.Context, file: Path) -> None:
    """Approve absolute ceilings on an existing ledger; never reset usage."""
    from .models import AssessmentBudgetAmendment
    amendment = AssessmentBudgetAmendment.model_validate_json(file.read_bytes())
    ctx.obj.repository.approve_budget_amendment(amendment)
    emit(amendment)


@app.command("revoke")
def revoke(ctx: typer.Context, authorization: str) -> None:
    ctx.obj.repository.revoke(authorization)
    emit({"authorization": authorization, "revoked": True})


@app.command("run")
def run(ctx: typer.Context, plan_id: str) -> None:
    typer.echo(json.dumps(ctx.obj.budget_preview(plan_id)), err=True)
    assessment_id = ctx.obj.enqueue(plan_id)
    emit(asyncio.run(ctx.obj.run(assessment_id)))


@app.command("structures")
def structures(ctx: typer.Context, plan_id: str) -> None:
    emit(ctx.obj.comparison_choices(plan_id))


@app.command("select-structure")
def select_structure(ctx: typer.Context, plan_id: str, structure: str) -> None:
    if structure not in {"direct", "controlled_agent", "workflow"}:
        raise ConfigurationError("unknown comparison structure")
    emit(ctx.obj.select_structure(plan_id, structure))


@app.command("budget")
def budget(ctx: typer.Context, plan_id: str) -> None:
    emit(ctx.obj.budget_preview(plan_id))


@app.command("status")
def status(ctx: typer.Context, assessment_id: str) -> None:
    emit(ctx.obj.status(assessment_id))


@app.command("report")
def report(ctx: typer.Context, assessment_id: str) -> None:
    job = ctx.obj.status(assessment_id)
    emit(ctx.obj.repository.get("report", job["report_id"]) if job["report_id"] else job)


@app.command("cancel")
def cancel(ctx: typer.Context, assessment_id: str) -> None:
    ctx.obj.cancel(assessment_id)
    emit(ctx.obj.status(assessment_id))


@app.command("admit")
def admit(ctx: typer.Context, report_id: str) -> None:
    emit(asyncio.run(ctx.obj.admit_resolved(report_id)))


@app.command("define")
def define(ctx: typer.Context, file: Path) -> None:
    recipe = RecipeDefinition.model_validate_json(file.read_bytes())
    digest = ctx.obj.repository.put("recipe", recipe.recipe_id, recipe)
    emit({"recipe_id": recipe.recipe_id, "digest": digest, "reviewed": False})


@app.command("inspect-host")
def inspect_host(ctx: typer.Context, plan_id: str, executor_id: str) -> None:
    emit(asyncio.run(ctx.obj.inspect_host(plan_id, executor_id)))


@app.command("prepare-planning")
def prepare_planning(ctx: typer.Context, subject: str, family: str, planner: str, authorization: str, environment: Path) -> None:
    from .planning import prepare
    emit(prepare(ctx.obj, subject_id=subject, family=family, planner_id=planner, authorization_id=authorization, environment=AssessmentEnvironment.model_validate_json(environment.read_bytes())))


@app.command("generate-definition")
def generate_definition(ctx: typer.Context, planning_id: str) -> None:
    from .planning import generate
    emit(asyncio.run(generate(ctx.obj, planning_id)))


@app.command("install-definition")
def install_definition(ctx: typer.Context, proposal_digest: str) -> None:
    from .planning import install_reviewed_candidate
    emit(install_reviewed_candidate(ctx.obj, proposal_digest))


@app.command("approve-bundle")
def approve_review_bundle(ctx: typer.Context, file: Path) -> None:
    from .onboarding import approve_bundle
    approve_bundle(ctx.obj, file)
    emit({"reviewed": True, "file": str(file)})


@app.command("recover")
def recover_assessment(ctx: typer.Context, assessment_id: str) -> None:
    from .recovery import recover
    emit(asyncio.run(recover(ctx.obj, assessment_id)))


@app.command('incremental-routes')
def incremental_routes(definition: Path) -> None:
    """Export inert four-arm routes from reviewed workers and observed model settings."""
    from ..hosts.base import HostModel
    from ..hosts.workers import ManagedWorkerBinding
    from ..models import ManagedHostInvocation, ReviewedHostSkill
    from .onboarding import incremental_host_routes

    value = json.loads(definition.read_text())
    routes = incremental_host_routes(
        recipe=RecipeDefinition.model_validate(value['recipe']),
        control_worker=ManagedWorkerBinding.model_validate(value['control_worker']),
        treatment_worker=ManagedWorkerBinding.model_validate(value['treatment_worker']),
        higher_worker=ManagedWorkerBinding.model_validate(value['higher_worker']),
        reusable_worker=ManagedWorkerBinding.model_validate(value['reusable_worker']),
        candidate_invocation=ManagedHostInvocation.model_validate(value['candidate_invocation']),
        model=HostModel.model_validate(value['model']),normal_effort=value['normal_effort'],
        effort_order=tuple(value['effort_order']),timeout_seconds=value['timeout_seconds'],
        protocol_user_agent=value['protocol_user_agent'],native_catalog=value.get('native_catalog',False),
        search_roots=tuple(value.get('search_roots', [])),
        background_skills=tuple(ReviewedHostSkill.model_validate(item) for item in value.get('background_skills',[])))
    emit({'status':'review_required','routes':[item.model_dump(mode='json') for item in routes]})


@app.command('prepare-conformance')
def prepare_conformance(ctx: typer.Context, source_plan_id: str, definition: Path) -> None:
    """Prepare a separate one-turn connectivity probe for operator scope/review."""
    from .boundary import BoundaryProbeDefinition, prepare_model_probe
    emit(prepare_model_probe(ctx.obj,source_plan_id=source_plan_id,
        definition=BoundaryProbeDefinition.model_validate_json(definition.read_bytes())))


@app.command('run-conformance')
def run_conformance(ctx: typer.Context, request_id: str) -> None:
    """Spend the existing grant on the exact reviewed connectivity probe, once."""
    from .boundary import execute_model_probe
    emit(asyncio.run(execute_model_probe(ctx.obj,request_id)))


@app.command('prepare-reusable')
def prepare_reusable(ctx: typer.Context, training_plan_id: str, planner_id: str, environment: Path) -> None:
    """Prepare a training-only reusable-tool build using the existing bounded planner."""
    from .planning import prepare_reusable as prepare
    emit(prepare(ctx.obj,training_plan_id=training_plan_id,planner_id=planner_id,
        environment=AssessmentEnvironment.model_validate_json(environment.read_bytes())))


@app.command('prepare-worker-inspection')
def prepare_worker_inspection(ctx: typer.Context, source_request: str) -> None:
    """Prepare turn-free policy, inventory and harmless sandbox inspection for review."""
    from ..hosts.codex_inspection import prepare
    emit(prepare(ctx.obj, source_request))


@app.command('inspect-worker')
def inspect_worker(ctx: typer.Context, request: str) -> None:
    """Run one reviewed worker inspection; never start a model turn or approve use."""
    from ..hosts.codex_inspection import execute
    emit(asyncio.run(execute(ctx.obj, request)))


@app.command('prepare-pair-inspection')
def prepare_pair_inspection(ctx: typer.Context, control_source: str, treatment_source: str, definition: Path) -> None:
    """Prepare one exact paired-worker probe set; preparation grants no authority."""
    from ..hosts.codex_pair_inspection import WorkerPairInspection, prepare_pair
    emit(prepare_pair(ctx.obj,control_source,treatment_source,WorkerPairInspection.model_validate_json(definition.read_bytes())))


@app.command('inspect-pair')
def inspect_pair(ctx: typer.Context, control_request: str, treatment_request: str) -> None:
    """Run the reviewed turn-free pair; never approve conformance or candidates."""
    from ..hosts.codex_pair_inspection import execute_pair
    emit(asyncio.run(execute_pair(ctx.obj,control_request,treatment_request)))
