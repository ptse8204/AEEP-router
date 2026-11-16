"""One operator-reviewed development campaign using AEEP's existing managed executors."""

import argparse
import asyncio
import hashlib
import html
import json
import runpy
import sys
import time
from pathlib import Path
from uuid import uuid4

from dispatch_tasks import REPO_PILOT, bind_tasks, task_pins
from prepare_renewal import snapshot
from prepare_runtime import (
    DESIGN,
    DESIGN_SHA256,
    ROOT,
    WORK,
    docker,
    read,
    require_reserve,
    sha,
    write,
)
from rebind_source import SOURCE_ROOT, STACK_REBINDING, register
from verify_graders import invoke

from aeep.assessment import verification
from aeep.assessment.boundary import BoundaryProbeDefinition, require_managed_boundaries
from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.destinations import require_destination
from aeep.assessment.extensions import grader_results
from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (
    AssessmentBudgetAmendment,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    ConformanceProbeRequest,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository_suites import grade_suite_output
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkRunner
from aeep.hosts import codex_pair_inspection as inspection
from aeep.hosts.workers import binding_from_config
from aeep.models import ResourceVector, utc_now
from aeep.router import Router
from aeep_toolkit.stack_readiness import require_stack_complete
from aeep_toolkit.worker_readiness import _Document, prepare_readiness

HERE = Path(__file__).resolve().parent
BASE = ROOT.parent / "aeep-agent-router/.aeep/live-review-v3/aeep.json"
REVIEW = HERE / "sol-dispatch-review.json"
APPROVAL = WORK / "operator-dispatch-approval.json"
RUN = WORK / "dispatch-run"
BUDGET = REPO_PILOT / "review-budget.py"
TRIAL = REPO_PILOT / "trial-evidence.py"
COLLECTOR = REPO_PILOT / "run-collector.py"
PROXY_FORMAT = '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Memory":{{json .HostConfig.Memory}},"MemorySwap":{{json .HostConfig.MemorySwap}},"Networks":{{json .NetworkSettings.Networks}}}'


def explicit_approval(identity):
    if sha(REVIEW) != identity or not APPROVAL.is_file() or APPROVAL.is_symlink():
        raise RuntimeError("exact dispatch approval required")
    if read(APPROVAL) != {"approved": True, "review_sha256": identity}:
        raise RuntimeError("exact dispatch approval required")


def proxy_state(ref):
    return json.loads(docker("inspect", "--format", PROXY_FORMAT, ref))


def reservations(repo):
    return {
        row[0]
        for row in repo.store._connection.execute(
            "SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'"
        )
    }


def verify_assets(review):
    require_reserve(51)
    assert sha(DESIGN) == DESIGN_SHA256 == review["design_sha256"]
    assert Path(verification.__file__).resolve().parents[3] == SOURCE_ROOT
    assert str(SOURCE_ROOT) == review["frozen_source"]
    assert verification.verification_source_digest(SOURCE_ROOT) == review["implementation_source"]
    for file, digest in review["pins"].items():
        assert sha(Path(file)) == digest
    for image in review["worker_images"]:
        assert docker("image", "inspect", "--format", "{{.Id}}", image) == image


def scope(repo, original, requests, directory, stamp):
    definitions = {}
    for req in requests:
        for digest in {
            req.subject_digest,
            req.recipe_digest,
            req.environment_digest,
            req.mapping_digest,
            *req.definition_digests,
        }:
            row = repo.store._connection.execute(
                "SELECT payload_json FROM assessment_records WHERE digest=?", (digest,)
            ).fetchone()
            if row is None:
                raise RuntimeError("scope definition is unavailable")
            definitions[digest] = json.loads(row[0])
    revised = AssessmentScopeAmendment(
        authorization_id="onboarding",
        authorization_digest=content_digest(original),
        subject_digests=sorted({req.subject_digest for req in requests}),
        recipe_digests=sorted({req.recipe_digest for req in requests}),
        environment_digests=sorted({req.environment_digest for req in requests}),
        reviewed_digests=sorted(definitions),
    )
    write(
        directory / f"{stamp}-scope.json",
        {
            "amendment": revised.model_dump(mode="json"),
            "definition_refs": sorted(definitions),
        },
    )
    repo.approve_bundle(revised, definitions)


def store_doc(repo, kind, value):
    return repo.put(kind, content_digest(value), value)


def request(repo, stamp, subject_ref, recipe_ref, environment, mapping=None):
    env_ref = store_doc(repo, "environment", environment)
    linked = mapping or recipe_ref
    selected = RecipeMaterializationRequest(
        plan_id=stamp,
        subject_digest=subject_ref,
        recipe_digest=recipe_ref,
        mapping_digest=linked,
        environment_digest=env_ref,
        authorization_id="onboarding",
        definition_digests=sorted({subject_ref, recipe_ref, env_ref, linked}),
        seed=71,
    )
    repo.put("recipe_materialization_request", selected.plan_id, selected)
    return selected


def collector_probe(original):
    scripts = runpy.run_path(str(COLLECTOR))

    async def collect(adapter, config, journal, recheck):
        facts = await original(adapter, config, journal, recheck)
        if not facts.get("inspection_complete"):
            raise RuntimeError("worker policy and identity inspection incomplete")
        worker = binding_from_config(config.managed_worker)
        assert worker is not None
        container = "aeep-" + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
        running = json.loads(
            await inspection.docker(
                worker,
                "exec",
                "-i",
                "--user",
                "65534:65534",
                container,
                "python3",
                "-I",
                "-c",
                scripts["PORTS"],
            )
        )["loopback_listener_ports"]
        assert len(running) == 1 and type(running[0]) is int and 1 <= running[0] <= 65535
        recheck()
        program = scripts["DENIED"].replace("PORT", str(running[0]))
        journal.append(
            "action.started",
            "collector-access-start",
            action_digest=hashlib.sha256(program.encode()).hexdigest(),
        )
        seen = await inspection.command(adapter, program)
        assert seen == {"collector_connection_denied": True}
        journal.append("action.completed", "collector-access-complete")
        journal.append(
            "artifact.created", "collector-denied-result", evidence_ref=content_digest(seen)
        )
        return facts | {"collector_boundary": seen}

    return collect


async def authenticate_pair(
    service, original, task, recipe, pair, shared, subject_ref, folder, verify
):
    repo = service.repository
    recipe_ref = store_doc(repo, "recipe", recipe)
    shared_ref = store_doc(repo, "shared_environment_definition", _Document(value=shared))
    assert pair.differential.shared_definition_digest == shared_ref
    sources = []
    for role in ("control", "treatment"):
        executor = getattr(pair, role)
        worker = binding_from_config(executor.managed_host_config().managed_worker)
        assert worker is not None
        environment = AssessmentEnvironment(
            environment_id=executor.id + "-inspection",
            kind="codex_sandbox",
            identity={"image": worker.image, "source": shared["source"]},
        )
        require_destination(executor, environment, repo.effective_grant("onboarding"))
        map_ref = store_doc(
            repo,
            "boundary_probe_definition",
            BoundaryProbeDefinition(
                name="worker_inspection",
                executor=executor,
                expected={},
            ),
        )
        ref = store_doc(repo, "environment", environment)
        value = ConformanceProbeRequest(
            schema_version="assessment.conformance-request.v2",
            plan_id=executor.id + "-source",
            operation="worker_inspection",
            subject_digest=subject_ref,
            recipe_digest=recipe_ref,
            mapping_digest=map_ref,
            environment_digest=ref,
            authorization_id="onboarding",
            definition_digests=[recipe_ref, ref, map_ref],
            worker_digest=worker.digest(),
            executable_dependencies=runtime_dependencies(),
        )
        repo.put("conformance_request", value.plan_id, value)
        sources.append(value.plan_id)
    draft = inspection.prepare_pair(service, *sources, pair)
    requests = [ConformanceProbeRequest.model_validate(item) for item in draft["requests"]]
    scope(repo, original, requests, folder, "pair")
    verify()
    ids = [item.plan_id for item in requests]
    original_collect = inspection.collect
    original_dependency = inspection.DEPENDENCY
    try:
        inspection.collect = collector_probe(original_collect)
        # The retained artifact-tool build reads CSV values as text.
        inspection.DEPENDENCY = original_dependency.replace("[1,'Ada']", "['1','Ada']")
        observation = await inspection.execute_pair(service, *ids)
    finally:
        inspection.collect = original_collect
        inspection.DEPENDENCY = original_dependency
    assert observation["probes_match"] and observation["model_turns"] == 0
    ready = prepare_readiness(service, *ids)
    repo.approve_bundle(
        AssessmentScopeAmendment.model_validate(ready["amendment"]), ready["definitions"]
    )
    references = {
        getattr(pair, role).id: row["conformance_digest"]
        for role, row in ready["boundaries"].items()
    }
    assert len(references) == 2 and all(
        row["observed_probe_count"] == 11 for row in ready["boundaries"].values()
    )
    write(
        folder / "authenticated-readiness.json",
        {
            "task": task["id"],
            "boundaries": ready["boundaries"],
            "differential_conformance_digest": ready["differential_conformance_digest"],
        },
    )
    return references


async def run_task(service, original, entry, proof, refs, subject_ref, folder, verify):
    task, recipe, protected, value, truth, pair, _, suite = entry
    repo = service.repository
    limits = AssessmentLimits
    pending_before_task = reservations(repo)
    care = protected.model_copy(update={"conformance_digests": refs})
    recipe_ref = store_doc(repo, "recipe", recipe)
    plan_name = suite.suite_id
    binding = _Document(
        value={
            "suite": content_digest(suite),
            "pair": content_digest(pair),
            "environment": content_digest(care),
            "recipe": recipe_ref,
        }
    )
    bind_ref = store_doc(repo, "toolkit_development_schedule", binding)
    work = request(repo, plan_name, subject_ref, recipe_ref, care, bind_ref)
    scope(repo, original, [work], folder, "trial")
    attempts = folder / "attempts"
    attempts.mkdir(mode=0o700)
    grader_dir = folder / "grades"
    grader_dir.mkdir(mode=0o700)
    proof_reader = runpy.run_path(str(TRIAL))
    expected = {(task["id"], role): proof["instruction_sha256"] for role in ("turn", "skill")}
    all_specs = [pair.control, pair.treatment]
    expected_order = [route.route_id for route in suite.routes]
    seen, benchmark, active = [], None, None

    async def before_trial(router, route, trial):
        nonlocal active
        verify()
        if active is not None or expected_order[len(seen)] != route.route_id:
            raise RuntimeError("the fixed trial schedule differs")
        spec = router.registry.get(route.executor_id)
        grant = repo.authorize(work)
        require_destination(spec, care, grant)
        repo.reserve(
            work,
            trial.trial_id,
            limits(max_operations=1, max_model_turns=1, max_elapsed_seconds=305, max_cash_usd=0),
            stage="managed_sol_trial",
            require_settled_plan=True,
        )
        active = trial.trial_id
        router._trial_deadline = asyncio.get_running_loop().time() + 300
        await router._resolve_host_identity(spec)
        identity = router.store.host_runtime_digests.get(spec.id)
        if identity is None:
            raise RuntimeError("managed runtime identity unavailable")
        router.store.expected_host_runtime_digests[spec.id] = identity[1]
        require_managed_boundaries(repo, care, [spec], {spec.id: identity[1]})
        router._trial_boundary_references = refs

        def check():
            verify()
            repo.authorize(work)
            require_managed_boundaries(repo, care, [spec], {spec.id: identity[1]})
            return refs[spec.id]

        router._trial_check = check

    async def grade(context):
        assert active is not None and recipe.extension is not None
        spec = recipe.extension.grader

        async def observe(payload):
            verify()
            operation = active + "-protected-grade"
            seconds = int(spec.config["timeout_seconds"]) + 5
            repo.reserve(
                work,
                operation,
                limits(max_operations=1, max_elapsed_seconds=seconds),
                stage="protected_development_grade",
            )
            executor = ContainerExecutor(protected)
            began = time.perf_counter()
            try:
                result = await invoke(task, executor, spec, payload, active, grader_dir)
            finally:
                await executor.close()
                receipt_path = (
                    grader_dir / f"sol-comparison-20261116-grader-{task['id']}-{active}.json"
                )
                if receipt_path.is_file() and read(receipt_path)["metadata"]["cleanup_confirmed"]:
                    elapsed = time.perf_counter() - began
                    repo.finish_operation(
                        operation,
                        elapsed_seconds=elapsed,
                        resources=ResourceVector(latency_ms=elapsed * 1000),
                    )
            return result

        if recipe.extension.schema_version.endswith(".v5"):
            return await grade_suite_output(value, truth, context.output, observe)
        data = await observe(
            {"examples": [{"input": value, "output": context.output, "expected": truth}]}
        )
        return grader_results(data, recipe.extension, 1)[0]

    def factory():
        op = plan_name + "-router-" + uuid4().hex
        repo.reserve(
            work,
            op,
            limits(max_operations=1, max_elapsed_seconds=30),
            stage="development_router_setup",
        )
        start = time.perf_counter()
        try:
            router = service.router._campaign_router(
                all_specs,
                plan_digest=bind_ref,
                database=attempts / (op + ".sqlite3"),
                snapshot_bound_digests={
                    bind_ref,
                    subject_ref,
                    recipe_ref,
                    content_digest(care),
                    *refs.values(),
                },
            )
            router.validator_callbacks["sol-protected-grade"] = grade
            return router
        finally:
            repo.finish_operation(op, elapsed_seconds=time.perf_counter() - start)

    def after_trial(trial):
        nonlocal active
        assert active == trial.trial_id and benchmark is not None
        record = proof_reader["read_trial"](benchmark.connection, trial, pair, expected, attempts)
        record["agent_wall_seconds"] = (
            trial.wall_time_ms / 1000 if trial.wall_time_ms is not None else None
        )
        record["verification_wall_seconds"] = (
            trial.grading_wall_time_ms / 1000 if trial.grading_wall_time_ms is not None else None
        )
        write(folder / f"trial-{len(seen) + 1}.json", record)
        if record["worker_cleanup_confirmed"] and trial.wall_time_ms is not None:
            repo.finish_operation(
                trial.trial_id,
                elapsed_seconds=trial.wall_time_ms / 1000,
                accounting=trial.accounting,
                resources=trial.actual_resources,
            )
        proof_reader["require_complete"](record)
        assert trial.host_models == {trial.route_id: "gpt-6.1-sol"}
        assert trial.failure_category in (None, "task_failure")
        assert reservations(repo) == pending_before_task
        seen.append(record)
        active = None

    benchmark = BenchmarkRunner(
        factory,
        folder / "campaign.sqlite3",
        before_trial=before_trial,
        after_trial=after_trial,
        separate_grading=True,
    )
    # The report interval excludes trial, grading and fresh-router operations.
    report_op = plan_name + ":report"
    report = await benchmark.run(suite)
    assert len(seen) == 2 and all(case.split.value == "training" for case in suite.cases)
    repo.reserve(
        work,
        report_op,
        limits(max_operations=1, max_elapsed_seconds=30),
        stage="development_report_export",
    )
    began = time.perf_counter()
    try:
        write(folder / "campaign.json", report.model_dump(mode="json"))
        values = []
        for record in seen:
            receipt = record["receipt"]
            observed = record["token_capture"]["known_fields"]
            values.append(
                {
                    "arm": "control" if receipt["executor_id"] == pair.control.id else "treatment",
                    "score": int(record["task_grade"]),
                    "tokens": {k: receipt["actual_resources"][k] for k in observed},
                    "token_capture": record["token_capture"],
                    "candidate_loading": record["candidate_loading"],
                    "task_prompt_sha256": proof["instruction_sha256"],
                    "receipt_ref": record["receipt_ref"],
                    "agent_wall_seconds": record["agent_wall_seconds"],
                    "verification_wall_seconds": record["verification_wall_seconds"],
                }
            )
        control = next(row for row in values if row["arm"] == "control")
        treatment = next(row for row in values if row["arm"] == "treatment")
        return {
            "task": task["id"],
            "arms": values,
            "treatment_minus_control_score": treatment["score"] - control["score"],
            "treatment_minus_control_tokens": {
                key: treatment["tokens"][key] - control["tokens"][key]
                for key in control["tokens"].keys() & treatment["tokens"].keys()
            },
            "campaign_sha256": content_digest(report),
        }
    finally:
        repo.finish_operation(report_op, elapsed_seconds=time.perf_counter() - began)


def render_result(result, target):
    columns = (
        "Task",
        "Control score",
        "Treatment score",
        "Treatment - control input tokens",
        "Treatment - control output tokens",
        "Treatment - control seconds",
    )
    rows = []
    for item in result["tasks"]:
        arms = {arm["arm"]: arm for arm in item["arms"]}
        base, treatment = arms["control"], arms["treatment"]
        gap = item["treatment_minus_control_tokens"]
        rows.append(
            (
                item["task"],
                base["score"],
                treatment["score"],
                gap.get("input_tokens"),
                gap.get("output_tokens"),
                round(treatment["agent_wall_seconds"] - base["agent_wall_seconds"], 3),
            )
        )
    rows = [tuple("Unknown" if value is None else str(value) for value in row) for row in rows]
    heading = "Managed GPT-6.1 Sol comparison"
    notice = (
        f"{len(rows)}/4 verified pairs. Development observations. Review {result['review_sha256']}."
    )
    with (target / "report.md").open("x") as output:
        output.write("# " + heading + "\n\n" + notice + "\n\n")
        for row in [columns, ["---"] * len(columns), *rows]:
            output.write("| " + " | ".join(row) + " |\n")
        output.write(
            "\n[Receipt links, all measured token categories and accounting](result.json)\n"
        )
    with (target / "report.html").open("x") as output:
        output.write('<!doctype html><meta charset="utf-8"><title>' + heading + "</title>")
        output.write("<h1>" + heading + "</h1><p>" + html.escape(notice) + "</p><table><thead><tr>")
        for value in columns:
            output.write("<th scope='col'>" + html.escape(value) + "</th>")
        output.write("</tr></thead><tbody>")
        for row in rows:
            output.write(
                "<tr>" + "".join("<td>" + html.escape(value) + "</td>" for value in row) + "</tr>"
            )
        output.write(
            "</tbody></table><p><a href='result.json'>Receipt links, all measured token categories and accounting</a></p>"
        )


async def execute(identity):
    if sys.flags.optimize:
        raise RuntimeError("verification requires ordinary Python assertion handling")
    explicit_approval(identity)
    review = read(REVIEW)
    verify_assets(review)
    assert await task_pins() == review["tasks"]
    proposed = AssessmentBudgetAmendment.model_validate(read(WORK / "expiry-only-renewal.json"))
    original, effective, counters, predecessor, old_pending = snapshot()
    assert list(counters[1:]) == review["grant"]["unchanged_counters"]
    assert predecessor == proposed.previous_amendment_digest and effective.limits == proposed.limits
    assert content_digest(proposed) == review["grant"]["canonical_amendment_digest"]
    assert content_digest(old_pending) == review["grant"]["prior_reservations_sha256"]
    assert utc_now() < proposed.expires_at
    assert proxy_state(review["proxy"]["Id"]) == review["proxy"] and not review["proxy"]["Running"]
    router = Router.from_manifest(BASE)
    service = AssessmentService(router, RUN / "campaigns")
    repo = service.repository
    old_reserve = repo.reserve
    started = False
    proxy_operation = None
    start_elapsed = 0.0
    active_proxy = False
    outcome = {
        "review_sha256": identity,
        "completed": False,
        "comparisons_are_development_only": True,
        "tasks": [],
    }
    try:
        RUN.mkdir(mode=0o700)
        started = True
        write(RUN / "started.json", {"review_sha256": identity, "automatic_retry": False})
        register(repo, read(STACK_REBINDING))
        require_stack_complete(
            repo, review["stack_completion_ref"], source_digest=review["implementation_source"]
        )
        repo.approve_budget_amendment(proposed)
        runpy.run_path(str(BUDGET))["install"](repo, router.store._connection, counters[1:], review)
        entries = bind_tasks()
        subject_ref = store_doc(
            repo,
            "subject",
            _Document(
                value={
                    "purpose": "four-task development only",
                    "design_sha256": DESIGN_SHA256,
                    "review_sha256": identity,
                }
            ),
        )

        def verify():
            verify_assets(review)
            assert utc_now() < proposed.expires_at
            assert reservations(repo) >= {line[0] for line in old_pending}
            state = proxy_state(review["proxy"]["Id"])
            assert state["Running"] and set(state["Networks"]) == set(review["proxy"]["Networks"])
            for key in ("Id", "Image", "Memory", "MemorySwap"):
                assert state[key] == review["proxy"][key]
            for name, details in state["Networks"].items():
                assert details["NetworkID"] == review["proxy"]["Networks"][name]["NetworkID"]
            assert state["Networks"]["aeep-reviewed-model-private"]["IPAddress"] == "172.18.0.2"

        stamp = "sol-development-proxy-20261116"
        support = request(
            repo,
            stamp,
            subject_ref,
            store_doc(repo, "recipe", entries[0][1]),
            AssessmentEnvironment(
                environment_id=stamp, kind="trusted_local", identity={"review": identity}
            ),
        )
        scope(repo, original, [support], RUN, "proxy")
        proxy_operation = stamp + ":owned-start-stop"
        repo.reserve(
            support,
            proxy_operation,
            AssessmentLimits(max_operations=1, max_elapsed_seconds=120),
            stage="retained_codex_proxy_control",
        )
        lifecycle_start = time.perf_counter()
        active_proxy = True
        try:
            docker("start", review["proxy"]["Id"])
        finally:
            start_elapsed = time.perf_counter() - lifecycle_start
        assert proxy_state(review["proxy"]["Id"])["Running"]
        async with asyncio.timeout(review["proxy_session_wall_timeout_seconds"]):
            ready = []
            for entry in entries:
                task, recipe, _, _, _, pair, shared, _ = entry
                folder = RUN / task["id"]
                folder.mkdir(mode=0o700)
                ready.append(
                    await authenticate_pair(
                        service, original, task, recipe, pair, shared, subject_ref, folder, verify
                    )
                )
            for entry, proof, refs in zip(entries, review["tasks"], ready, strict=True):
                verify()
                folder = RUN / entry[0]["id"]
                outcome["tasks"].append(
                    await run_task(
                        service, original, entry, proof, refs, subject_ref, folder, verify
                    )
                )
        outcome["completed"] = len(outcome["tasks"]) == 4
    except BaseException as error:
        if started:
            outcome.update(completed=False, error_type=type(error).__name__)
        raise
    finally:
        if started:
            if active_proxy:
                cleanup_clock = time.perf_counter()
                try:
                    if proxy_state(review["proxy"]["Id"])["Running"]:
                        docker("stop", "--time", "5", review["proxy"]["Id"])
                    outcome["proxy_restored_stopped"] = not proxy_state(review["proxy"]["Id"])[
                        "Running"
                    ]
                    if outcome["proxy_restored_stopped"]:
                        repo.finish_operation(
                            proxy_operation,
                            elapsed_seconds=start_elapsed + time.perf_counter() - cleanup_clock,
                        )
                except BaseException as error:
                    outcome.update(completed=False, cleanup_error=type(error).__name__)
            outcome["new_unsettled_operations"] = sorted(
                reservations(repo) - {line[0] for line in old_pending}
            )
            if outcome["new_unsettled_operations"]:
                outcome["completed"] = False
            outcome["operation_ledgers"] = (
                {
                    name: repo.operation_ledger(name).model_dump(mode="json")
                    for name in [stamp, *(entry[-1].suite_id for entry in entries)]
                }
                if proxy_operation is not None
                else {}
            )
            write(RUN / "result.json", outcome)
            render_result(outcome, RUN)
        repo.reserve = old_reserve
        await router.close()
    if not outcome["completed"]:
        raise RuntimeError("campaign stopped with retained canonical evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved", required=True)
    args = parser.parse_args()
    asyncio.run(execute(args.execute_approved))
