"""Prepare the retained paired diagnostic without contacting a provider."""

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentPlan, AssessmentSubject, IncrementalExperiment,
    IntegrationCaseSet, RecipeDefinition, UtilityPolicy, content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.scheduling import SchedulerDefinition
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_pair_inspection import WorkerPairInspection
from aeep.hosts.workers import binding_from_config
from aeep.models import Manifest
from aeep.router import Router
from aeep.store import ReceiptStore
from aeep_toolkit.skillrank_scheduler import SkillRankCoordinator

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PRIVATE = ROOT / ".aeep" / HERE.name
PRIOR = C13 / "integration-snapshot-correction-20261103/managed-unstarted"
PREFIX = C13 / "skillsbench-software-substitute-20261109/managed-preparation/managed-engineering"


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def stage():
    audit = load(HERE / "sol-pair-reuse-audit.json")
    source = verification_source_digest(ROOT)
    pair_file = PRIVATE / "sol-pair-draft/pair.json"
    shared_file = pair_file.with_name("shared.json")
    scheduler_file = PRIVATE / "scheduler.json"
    assert all(sha(Path(path)) == digest for path, digest in audit["draft_files"].items())
    scheduler = SchedulerDefinition.model_validate(load(scheduler_file))
    assert content_digest(scheduler) == audit["scheduler_ref"]
    verify_dependencies(scheduler.executable_dependencies)
    assert not Path(scheduler.workspace).exists()
    original = WorkerPairInspection.model_validate(load(pair_file))
    shared = load(shared_file)
    assert content_digest(shared) == original.differential.shared_definition_digest
    assert content_digest(original) == audit["proposed_pair_ref"]
    shared["source_sha256"] = source
    differential = original.differential.model_dump(mode="json")
    common = differential["control_inventory"] | {"common_profile": content_digest(shared)}
    differential.update(shared_definition_digest=content_digest(shared), control_inventory=common,
                        treatment_inventory=common | differential["candidate_inventory"])
    pair = WorkerPairInspection.model_validate(original.model_dump(mode="json") | {"differential": differential})
    for role in ("control", "treatment"):
        config = getattr(pair, role).managed_host_config()
        assert tuple(config.model_constraints.allowed_model_ids) == ("gpt-6.1-sol",)
        assert tuple(config.reasoning_efforts) == ("medium",)
        assert not config.store_prompt and not config.store_output
        worker = binding_from_config(config.managed_worker)
        assert worker and worker.image == audit["images"][role]
        assert subprocess.check_output(["docker", "image", "inspect", "--format", "{{.Id}}", worker.image],
                                       text=True, timeout=15).strip() == worker.image
    plan_id = load(PRIOR / "plan-managed.json")["plan_id"]
    root_db = load(PREFIX / "operation-review.json")["database"]
    with ReceiptStore(root_db, read_only=True) as store:
        repo = AssessmentRepository(store)
        prior = AssessmentPlan.model_validate(repo.get("plan", plan_id))
        subject = AssessmentSubject.model_validate(repo.get("subject", prior.subject_digest))
        recipe = RecipeDefinition.model_validate(repo.get("recipe", prior.recipe_digest))
        environment = AssessmentEnvironment.model_validate(repo.get("environment", prior.environment_digest))
        campaign_cases = IntegrationCaseSet.model_validate(repo.get("integration_case_set", prior.integration_case_set_digest))
        grant = repo.current_grant(prior.authorization_id)
        assert grant.limits.max_cash_usd == 0
    case, = campaign_cases.cases
    assert case.case_id == audit["task_provenance"]["independent_case_id"]
    assert content_digest(case.action.input) == load(HERE / "managed-input-readiness-audit.json")["public_input_ref"]
    assert campaign_cases.cases == prior.suite.cases
    return root_db, source, pair, shared, scheduler, prior, subject, recipe, environment, campaign_cases


def draft(service, source, pair, scheduler, prior, subject, recipe, environment, cases, readiness=None):
    repo = service.repository
    environment = environment.model_copy(update={
        "environment_id": "skillrank-markdownify-sol-current-grader",
        "identity": {**environment.identity, "source_digest": source},
        "conformance_digests": ({
            getattr(pair, role).id: row["conformance_digest"]
            for role, row in readiness["boundaries"].items()
        } if readiness else None),
        "differential_conformance_digest": readiness["differential_conformance_digest"] if readiness else None,
    })
    for kind, model in (("recipe", recipe), ("environment", environment), ("subject", subject), ("scheduler", scheduler)):
        ref = content_digest(model)
        try:
            assert content_digest(repo.get(kind, ref)) == ref
        except Exception as exc:
            from aeep.errors import ConfigurationError
            if not isinstance(exc, ConfigurationError):
                raise
            repo.put(kind, ref, model)
    case_set = cases.model_copy(update={
        "request_id": "skillrank-markdownify-sol-current-cases",
        "environment_digest": content_digest(environment),
    })
    case_ref = repo.put("integration_case_set", content_digest(case_set), case_set)
    repo.review(case_ref)
    repo.review(content_digest(scheduler))
    repo.review(content_digest(recipe))
    plan = service.propose(subject_id=content_digest(subject), family=content_digest(recipe),
        candidate_id=pair.treatment.id, baseline_id=pair.control.id,
        authorization_id=prior.authorization_id, environment=environment,
        seed=cases.seed, structure="controlled_agent", integration_case_set_id=case_ref,
        scheduler_digest=content_digest(scheduler),
        experiment=IncrementalExperiment(stage="qualification", exposure="required",
            environment=pair.differential, utility=UtilityPolicy(
                benefit_dimensions=["wall_time_ms"], guardrail_dimensions=["wall_time_ms"])))
    assert plan.schema_version == "assessment.plan.v9" and plan.suite.cases == cases.cases
    assert plan.suite.repetitions == 1 and plan.suite.conditions == ["fresh-worker"]
    assert [route.executor_id for route in plan.suite.routes] == [pair.control.id, pair.treatment.id]
    SkillRankCoordinator(repo, plan).require_runtime()
    return plan


def main(work):
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    database, source, pair, shared, scheduler, prior, subject, recipe, environment, cases = stage()
    work.mkdir(mode=0o700)
    draft_db = work / "isolated.sqlite3"
    with ReceiptStore(database, read_only=True) as live, ReceiptStore(draft_db) as copy:
        live._connection.backup(copy._connection)
    base = Manifest.model_validate(load(Path(database).with_suffix(".json")))
    manifest = base.model_copy(update={"database": str(draft_db), "executors": [pair.control, pair.treatment]})
    router = Router(manifest)
    service = AssessmentService(router, work / "planning")
    try:
        plan = draft(service, source, pair, scheduler, prior, subject, recipe, environment, cases)
        budget = service.budget_preview(plan.plan_id)
        assert budget["minimum_trial_model_turns"] == 2 and budget["campaign_allowance"]["fits_remaining"]
        print(json.dumps({
            "source": source, "scheduler": content_digest(scheduler), "pair": content_digest(pair),
            "schema": plan.schema_version, "draft_plan_digest": content_digest(plan),
            "case": plan.suite.cases[0].case_id, "public_inputs_sha256": content_digest(plan.suite.cases[0].action.input),
            "routes": [route.executor_id for route in plan.suite.routes],
            "budget": budget["campaign_allowance"]["upper_allowance"], "blocked_reasons": plan.blocked_reasons,
            "fresh_live_conformance": "REQUIRED", "provider_contact": False, "models_dispatched": 0,
        }, indent=2))
    finally:
        import asyncio
        asyncio.run(router.close())


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("work", type=Path)
    main(parser.parse_args().work.resolve())
