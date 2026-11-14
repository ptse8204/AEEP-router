"""Run one reviewed, paired SkillRank engineering diagnostic through the toolkit CLI."""

import argparse
import asyncio
import hashlib
import json
import runpy
import shutil
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

from aeep.assessment.adapters import DeclarativeAdapter
from aeep.assessment.models import AssessmentLimits, content_digest
from aeep.assessment.repository_suites import public_archive
from aeep.assessment.service import AssessmentService
from aeep.benchmarking import BenchmarkTrial
from aeep.models import Manifest, utc_now
from aeep.router import Router
from aeep.templates import render
from aeep_toolkit.managed import AEEPAssessmentAdapter, plan_preview
from aeep_toolkit.models import SourcePin
from aeep_toolkit.stack_readiness import EngineeringRunReview, require_engineering_run

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
C13 = HERE.parent
PREP = runpy.run_path(str(HERE / "prepare-current.py"))
PREFIX = PREP["PREFIX"]
LEGACY = runpy.run_path(str(PREFIX / "run.py"))
ENGINE = LEGACY["engine"]
EVIDENCE = runpy.run_path(str(C13 / "repository-usefulness-pilot-20261029/trial-evidence.py"))
SOURCE = C13 / "integration-snapshot-correction-20261103/source.json"


def read(path):
    return json.loads(Path(path).read_bytes())


def sha(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    with path.open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def facts(work):
    database, source, pair, shared, scheduler, prior, subject, recipe, environment, cases = PREP["stage"]()
    assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
    proxy = read(ENGINE.PREVIOUS / "operation-review.json")
    current = ENGINE.proxy_state(proxy)
    assert not current["Running"] and current == read(PREFIX / "operation-review.json")["proxy"]
    snapshot = LEGACY["legacy"]["snapshot"](database)
    assert utc_now() < datetime.fromisoformat(snapshot["expires_at"])
    case, = cases.cases
    archive_delivery = {}
    public_archive_hashes = set()
    for arm in ("control", "treatment"):
        executor = getattr(pair, arm)
        config = executor.managed_host_config()
        projection = DeclarativeAdapter.model_validate(executor.config["assessment_adapter"])
        assert projection.input_transform == "repository_archive:1" and config.artifact
        original = public_archive(case.action.input, projection.read_only_roots)
        public_archive_hashes.add(original["source_sha256"])
        value = original.pop(config.artifact.input_field)
        original.update(input_path="/workspace/" + config.artifact.input_name,
                        output_path="/workspace/" + config.artifact.output_name)
        prompt = str(render(config.instructions, {"input": original}))
        assert value not in prompt and len(prompt) < 60_000
        archive_delivery[arm] = hashlib.sha256(prompt.encode()).hexdigest()
    assert ENGINE.budget.self_check() == 7
    assert public_archive_hashes == {case.action.input["source_sha256"]}
    pins = [Path(__file__).resolve(), HERE / "prepare-current.py", SOURCE,
            Path(LEGACY["__file__"]), Path(ENGINE.__file__), Path(ENGINE.budget.__file__),
            Path(EVIDENCE["__file__"]), PREP["PRIVATE"] / "scheduler.json", HERE / "current-draft.json"]
    historical = read(PREFIX / "result.json")
    assert historical["passed"] and snapshot["counters"][1] == historical["grant_after"][1]
    return {
        "purpose": "SkillRank controlled diagnostic. No candidate or selection usefulness claim.",
        "source": source, "work": str(work), "database": database, "grant": snapshot,
        "bound_files": {str(path): sha(path) for path in pins}, "proxy": current,
        "model": "gpt-6.1-sol", "reasoning_effort": "medium", "destination": "existing Codex proxy",
        "pair_ref": content_digest(pair), "shared_ref": content_digest(shared),
        "scheduler_ref": content_digest(scheduler), "grader_environment_ref": content_digest(environment),
        "recipe_ref": content_digest(recipe), "subject_ref": content_digest(subject),
        "source_revision": read(HERE / "sol-pair-reuse-audit.json")["task_provenance"]["source_revision"],
        "case_id": case.case_id, "public_input_ref": content_digest(case.action.input), "prompt_refs": archive_delivery,
        "public_archive_sha256": case.action.input["source_sha256"],
        "operator_scope": "Two fresh zero-turn worker/collector checks; only public Markdownify and the reviewed treatment skill. Protected grading stays local.",
        "maximum_operations": 120, "maximum_model_turns": 2, "maximum_reserved_seconds": 5500,
        "maximum_cash_usd": "0", "automatic_retry": False, "comparisons": "PAUSED",
        "installs": 0, "downloads": 0, "image_changes": 0, "release": False,
        "expires_at": snapshot["expires_at"],
    }


def audit(service, plan, pair, review, report):
    adapter = AEEPAssessmentAdapter(service, plan.plan_id, SourcePin.model_validate(read(SOURCE)))
    job = adapter.preview()["job"]
    assert job and job["state"] == "complete" and job["error_code"] is None
    bundle = adapter.normalize(job["report_id"])
    assert len(bundle.runs) == 2 and not adapter.details["normalization_gaps"] and not adapter.details["unresolved_operations"]
    assert read(report / "toolkit-evidence.json") == bundle.model_dump(mode="json")
    assert (report / "report.html").is_file() and (report / "report.md").is_file()
    path = service.directory / plan.plan_id / "campaign.sqlite3"
    summaries = []
    expected = {(review["case_id"], wire): review["prompt_refs"][arm]
                for wire, arm in (("turn", "control"), ("skill", "treatment"))}
    with sqlite3.connect(path.as_uri() + "?mode=ro", uri=True) as connection:
        trials = [BenchmarkTrial.model_validate_json(row[0]) for row in connection.execute("SELECT payload_json FROM trials")]
        assert len(trials) == 2
        for trial in trials:
            record = EVIDENCE["read_trial"](connection, trial, pair, expected, path.parent / "attempts")
            EVIDENCE["require_complete"](record)
            receipt = record.pop("receipt")
            assert receipt["metadata"]["model_turn_count"] == 1
            assert trial.retry_fallback_count == 0
            assert receipt["metadata"]["actual_model"] == review["model"]
            counts = {key: receipt["actual_resources"][key] for key in record["token_capture"]["known_fields"]}
            verified, = [item for item in trial.case_validation if item.kind.value == "callback" and item.trust.value == "verified"]
            summaries.append(record | {"arm": "control" if trial.route_id == plan.baseline_id else "treatment",
                                         "receipt_id": receipt["receipt_id"], "score": verified.quality_score,
                                         "provider_tokens": counts, "wall_time_ms": trial.wall_time_ms,
                                         "grading_wall_time_ms": trial.grading_wall_time_ms})
    scheduler = service.repository.get("scheduler_observation", plan.plan_id)
    assert scheduler["definition_ref"] == review["scheduler_ref"]
    assert set(scheduler["trial_refs"].values()) == {row["canonical_trial_ref"] for row in summaries}
    return {"report_id": job["report_id"], "trials": summaries, "scheduler": scheduler}


async def execute(review, digest):
    work = Path(review["work"])
    assert not work.exists() and facts(work) == review
    database, source, pair, shared, scheduler, prior, subject, recipe, environment, cases = PREP["stage"]()
    work.mkdir(mode=0o700)
    save(work / "started.json", {"review_sha256": digest, "comparisons": "PAUSED", "automatic_retry": False})
    ENGINE.WORK, ENGINE.MANIFEST, ENGINE.CAMPAIGNS = work, work / "manifest.json", work / "campaigns"
    ENGINE.emit = lambda name, value: save(work / name, value)
    base = Manifest.model_validate(read(ENGINE.BASE))
    manifest = base.model_copy(update={"database": database, "executors": [pair.control, pair.treatment]})
    save(ENGINE.MANIFEST, manifest.model_dump(mode="json"))
    router = Router.from_manifest(ENGINE.MANIFEST)
    service = AssessmentService(router, ENGINE.CAMPAIGNS)
    repo = service.repository
    proxy = read(ENGINE.PREVIOUS / "operation-review.json")
    initial = ENGINE.previous.counters(repo)
    pending = ENGINE.reserved(repo)
    assert list(initial) == review["grant"]["counters"]
    original_reserve = ENGINE.budget.install(repo, repo.store._connection, initial, review)
    overhead = None
    started = time.perf_counter()
    excluded = 0.0
    finished_proxy = False
    result = {"review_sha256": digest, "passed": False, "comparisons": "PAUSED"}
    phase = "definition and overhead"
    try:
        scope = ENGINE.materialization(repo, "skillrank-markdownify-sol-overhead-20261113", subject, recipe, environment)
        ENGINE.scoped_approval(repo, [scope])
        overhead = scope.plan_id + ":exclusive"
        repo.reserve(scope, overhead, AssessmentLimits(max_operations=1, max_elapsed_seconds=200),
                     stage="owned_skillrank_preparation_overhead")
        repo.put("shared_environment_definition", content_digest(shared), ENGINE.previous.Document(value=shared))
        phase = "worker and collector conformance"
        assert ENGINE.proxy_state(proxy) == review["proxy"]
        ENGINE.docker("start", review["proxy"]["Id"])
        active = ENGINE.proxy_state(proxy)
        assert active["Id"] == review["proxy"]["Id"] and active["Image"] == review["proxy"]["Image"]
        assert active["Running"] and active["Networks"]["aeep-reviewed-model-private"]["IPAddress"] == "172.18.0.2"
        ids = ENGINE.worker_requests(service, "skillrank-markdownify-sol", pair, recipe, subject, source)
        prior_collect = ENGINE.inspection.collect
        ENGINE.inspection.collect = ENGINE.inspect_collector(prior_collect)
        nested = time.perf_counter()
        try:
            observed = await ENGINE.inspection.execute_pair(service, *ids)
        finally:
            excluded += time.perf_counter() - nested
            ENGINE.inspection.collect = prior_collect
        inspections = [repo.get("worker_pair_inspection", "pair-inspection:"+identity)["observations"] for identity in ids]
        assert observed["probes_match"] and observed["model_turns"] == 0
        assert all(row["cleanup_confirmed"] and not row.get("cleanup_error_type")
                   and row["inspection"]["collector_boundary"] == {"collector_connection_denied": True} for row in inspections)
        readiness = ENGINE.readiness(repo, "skillrank-markdownify-sol", ids, pair, source)
        phase = "canonical plan and budget"
        plan = PREP["draft"](service, source, pair, scheduler, prior, subject, recipe, environment, cases, readiness)
        engineering = EngineeringRunReview(plan_digest=content_digest(plan), implementation_source=source,
            scope_request_id="skillrank-markdownify-sol-execution-20261113", case_ids=(review["case_id"],), maximum_model_turns=2)
        ref = repo.put("toolkit_engineering_run", content_digest(engineering), engineering)
        exact_environment = PREP["AssessmentEnvironment"].model_validate(repo.get("environment", plan.environment_digest))
        execution = ENGINE.materialization(repo, engineering.scope_request_id, subject, recipe, exact_environment,
                                           mapping=plan.mapping_digest, definitions=(*plan.definition_digests, ref))
        ENGINE.scoped_approval(repo, [execution])
        require_engineering_run(repo, ref, plan=plan, source_digest=source)
        service._verify_dependencies(plan)
        source_pin = SourcePin.model_validate(read(SOURCE))
        preview = plan_preview(plan, source_pin)
        allowance = service.budget_preview(plan.plan_id)["campaign_allowance"]["upper_allowance"]
        assert allowance["model_turns"] == 2 and allowance["cash_usd"] == "0"
        ENGINE.budget.require_room(ENGINE.previous.counters(repo), initial,
            AssessmentLimits(max_operations=allowance["operations"], max_model_turns=2,
                             max_elapsed_seconds=allowance["elapsed_seconds"]), review)
        assert set(ENGINE.reserved(repo)) <= set(pending) | {overhead}
        plan_path = work / "plan.json"
        save(plan_path, plan.model_dump(mode="json"))
        save(work / "dispatch-ready.json", {"plan_id": plan.plan_id, "plan_ref": content_digest(plan), "review": ref,
                                             "budget": allowance, "worker_inspections": ids})
        result["plan_id"] = plan.plan_id
        phase = "ordinary CLI managed SkillRank"
        target = work / "result"
        argv = [sys.executable, "-B", "-m", "aeep_toolkit", "eval", "managed", "run", "--plan", str(plan_path),
            "--source", str(SOURCE), "--scheduler", str(PREP["PRIVATE"] / "scheduler.json"), "--manifest", str(ENGINE.MANIFEST),
            "--directory", str(ENGINE.CAMPAIGNS), "--output", str(target), "--reviewed-digest", preview["review_sha256"],
            "--engineering-review", ref]
        assert utc_now() < datetime.fromisoformat(review["expires_at"])
        assert all(sha(path) == value for path, value in review["bound_files"].items())
        nested = time.perf_counter()
        try:
            process = await asyncio.create_subprocess_exec(*argv, cwd=ROOT, env=ENGINE.PATH_ENV,
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            try:
                output, error = await asyncio.wait_for(process.communicate(), timeout=1300)
            finally:
                if process.returncode is None:
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=20)
            save(work / "cli.json", {"exit_code": process.returncode,
                "stdout_sha256": hashlib.sha256(output).hexdigest(), "stderr_sha256": hashlib.sha256(error).hexdigest()})
            assert process.returncode == 0
        finally:
            excluded += time.perf_counter() - nested
        phase = "canonical grade/receipt audit"
        result.update(audit(service, plan, pair, review, target), passed=True)
    except (Exception, asyncio.CancelledError, KeyboardInterrupt) as error:
        result.update(stopped_phase=phase, error_type=type(error).__name__)
    finally:
        try:
            current = ENGINE.proxy_state(proxy)
            if current["Running"] and current["Id"] == review["proxy"]["Id"]:
                ENGINE.docker("stop", "--time", "5", current["Id"])
            finished_proxy = ENGINE.proxy_state(proxy) == review["proxy"]
        except Exception:
            finished_proxy = False
        result["proxy_restored_stopped"] = finished_proxy
        if overhead and finished_proxy and phase != "worker and collector conformance":
            try:
                repo.finish_operation(overhead, elapsed_seconds=max(0, time.perf_counter() - started - excluded))
            except Exception as error:
                result.update(passed=False, accounting_error_type=type(error).__name__)
        after = ENGINE.previous.counters(repo)
        result["grant_after"] = list(after)
        result["new_unresolved_reservations"] = sorted(set(ENGINE.reserved(repo)) - set(pending))
        result["turns"] = after[1] - initial[1]
        result["passed"] &= finished_proxy and not result["new_unresolved_reservations"] and result["turns"] == 2
        save(work / "terminal.json", result)
        repo.reserve = original_reserve
        await router.close()
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("review_file", type=Path)
    parser.add_argument("--prepare-work", type=Path)
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    if args.prepare_work:
        save(args.review_file, facts(args.prepare_work.resolve()))
        print(sha(args.review_file))
    else:
        identity = sha(args.review_file)
        assert args.execute_approved == identity
        assert read(args.review_file.with_name("operator-approval.json")) == {"approved": True, "review_sha256": identity}
        outcome = asyncio.run(execute(read(args.review_file), identity))
        print(json.dumps(outcome, indent=2))
        raise SystemExit(not outcome["passed"])
