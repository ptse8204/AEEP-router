"""Run a fixed Sales pair with explicit matched deadlines and protected grading."""

import asyncio
import runpy
import sqlite3
import time
from pathlib import Path
from uuid import uuid4

import run_dispatch as prior
from prepare_runtime import read, write
from verify_graders import invoke

from aeep.assessment.boundary import require_managed_boundaries
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.destinations import require_destination
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import AssessmentLimits, content_digest
from aeep.benchmarking import BenchmarkRunner
from aeep.models import ExecutionReceipt, ResourceVector
from aeep_toolkit.worker_readiness import _Document


def canonical_trial_receipt(connection, trial, attempts):
    [(payload, path)] = connection.execute(
        "SELECT r.payload_json, s.database_path FROM trial_receipts r "
        "JOIN trial_stores s USING(trial_id) WHERE r.trial_id=?",
        (trial.trial_id,),
    ).fetchall()
    receipt = ExecutionReceipt.model_validate_json(payload)
    assert trial.receipt_ids == [receipt.receipt_id] and trial.route_id == receipt.executor_id
    store = Path(path).resolve(strict=True)
    assert store.parent == attempts.resolve(strict=True)
    with sqlite3.connect(store.as_uri() + "?mode=ro", uri=True) as archive:
        [(canonical,)] = archive.execute(
            "SELECT payload_json FROM receipts WHERE receipt_id=?", (receipt.receipt_id,)
        ).fetchall()
    assert receipt == ExecutionReceipt.model_validate_json(canonical)
    return receipt


async def run_pair(service, original, entry, proof, refs, subject, folder, verify, timeout):
    task, recipe, protected, value, truth, pair, _, suite = entry
    extension = recipe.extension
    assert extension is not None and task["id"] == "sales-pivot-analysis"
    repo = service.repository
    before = prior.reservations(repo)
    care = protected.model_copy(update={"conformance_digests": refs})
    recipe_ref = prior.store_doc(repo, "recipe", recipe)
    schedule = _Document(
        value={
            "suite": content_digest(suite),
            "pair": content_digest(pair),
            "environment": content_digest(care),
            "task_deadline_seconds": timeout,
        }
    )
    binding = prior.store_doc(repo, "toolkit_development_schedule", schedule)
    request = prior.request(repo, suite.suite_id, subject, recipe_ref, care, binding)
    prior.scope(repo, original, [request], folder, "trial")
    attempts = folder / "attempts"
    grades = folder / "grades"
    for directory in (attempts, grades):
        directory.mkdir(mode=0o700)
    proof_reader = runpy.run_path(str(prior.TRIAL))
    expected = {(task["id"], role): proof["instruction_sha256"] for role in ("turn", "skill")}
    specs = [pair.control, pair.treatment]
    order = [spec.id for spec in specs]
    active = None
    observed = []

    async def before_trial(router, route, trial):
        nonlocal active
        verify()
        assert active is None and route.route_id == order[len(observed)]
        spec = router.registry.get(route.executor_id)
        assert spec.managed_host_config().timeout_seconds == timeout
        require_destination(spec, care, repo.authorize(request))
        repo.reserve(
            request,
            trial.trial_id,
            AssessmentLimits(max_operations=1, max_model_turns=1, max_elapsed_seconds=timeout + 5),
            stage="managed_sol_trial",
            require_settled_plan=True,
        )
        active = trial.trial_id
        router._trial_deadline = asyncio.get_running_loop().time() + timeout
        await router._resolve_host_identity(spec)
        identity = router.store.host_runtime_digests[spec.id][1]
        router.store.expected_host_runtime_digests[spec.id] = identity
        router._trial_boundary_references = refs

        def check():
            verify()
            repo.authorize(request)
            require_managed_boundaries(repo, care, [spec], {spec.id: identity})
            return refs[spec.id]

        check()
        router._trial_check = check

    async def grade(context):
        assert active is not None
        verify()
        spec = extension.grader
        operation = active + "-protected-grade"
        limit = int(spec.config["timeout_seconds"]) + 5
        repo.reserve(
            request,
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=limit),
            stage="protected_development_grade",
        )
        executor = ContainerExecutor(protected)
        started = time.perf_counter()
        try:
            reply = await invoke(
                task,
                executor,
                spec,
                {"examples": [{"input": value, "output": context.output, "expected": truth}]},
                active,
                grades,
            )
        finally:
            await executor.close()
            receipt = grades / f"sol-comparison-20261116-grader-{task['id']}-{active}.json"
            if receipt.is_file() and read(receipt)["metadata"]["cleanup_confirmed"]:
                elapsed = time.perf_counter() - started
                repo.finish_operation(
                    operation,
                    elapsed_seconds=elapsed,
                    resources=ResourceVector(latency_ms=elapsed * 1000),
                )
        return grader_results(reply, extension, 1)[0]

    def factory():
        operation = suite.suite_id + "-router-" + uuid4().hex
        repo.reserve(
            request,
            operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=30),
            stage="development_router_setup",
        )
        started = time.perf_counter()
        try:
            worker_router = service.router._campaign_router(
                specs,
                plan_digest=binding,
                database=attempts / (operation + ".sqlite3"),
                snapshot_bound_digests={
                    binding,
                    subject,
                    recipe_ref,
                    content_digest(care),
                    *refs.values(),
                },
            )
            worker_router.validator_callbacks["sol-protected-grade"] = grade
            return worker_router
        finally:
            repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - started)

    def after_trial(trial):
        nonlocal active
        assert active == trial.trial_id and trial.wall_time_ms is not None
        canonical = canonical_trial_receipt(benchmark.connection, trial, attempts)
        wall = trial.wall_time_ms / 1000
        # Settle the canonical charge even when a later evidence gate rejects the result.
        if canonical.metadata.get("worker_cleanup_confirmed") is True:
            repo.finish_operation(
                active,
                elapsed_seconds=wall,
                accounting=trial.accounting,
                resources=trial.actual_resources,
            )
        record = proof_reader["read_trial"](benchmark.connection, trial, pair, expected, attempts)
        record.update(
            agent_wall_seconds=wall,
            verification_wall_seconds=trial.grading_wall_time_ms / 1000,
        )
        write(folder / f"trial-{len(observed) + 1}.json", record)
        proof_reader["require_complete"](record)
        assert trial.host_models == {trial.route_id: "gpt-6.1-sol"}
        assert trial.failure_category in (None, "task_failure")
        assert prior.reservations(repo) == before
        fields = record["token_capture"]["known_fields"]
        observed.append(
            {
                "arm": "control" if trial.route_id == pair.control.id else "treatment",
                "score": int(record["task_grade"]),
                "tokens": {key: getattr(canonical.actual_resources, key) for key in fields},
                "token_capture": record["token_capture"],
                "candidate_loading": record["candidate_loading"],
                "receipt_ref": record["receipt_ref"],
                "task_prompt_sha256": proof["instruction_sha256"],
                "agent_wall_seconds": wall,
                "verification_wall_seconds": record["verification_wall_seconds"],
            }
        )
        active = None

    benchmark = BenchmarkRunner(
        factory,
        folder / "campaign.sqlite3",
        before_trial=before_trial,
        after_trial=after_trial,
        separate_grading=True,
    )
    report = await benchmark.run(suite)
    control, treatment = observed
    assert control["arm"] == "control" and treatment["arm"] == "treatment"
    operation = suite.suite_id + ":report"
    repo.reserve(
        request,
        operation,
        AssessmentLimits(max_operations=1, max_elapsed_seconds=30),
        stage="development_report_export",
    )
    started = time.perf_counter()
    try:
        write(folder / "campaign.json", report.model_dump(mode="json"))
        return {
            "task": task["id"],
            "task_deadline_seconds": timeout,
            "arms": observed,
            "treatment_minus_control_score": treatment["score"] - control["score"],
            "treatment_minus_control_tokens": {
                key: treatment["tokens"][key] - control["tokens"][key]
                for key in control["tokens"].keys() & treatment["tokens"].keys()
            },
            "campaign_sha256": content_digest(report),
        }
    finally:
        repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - started)
