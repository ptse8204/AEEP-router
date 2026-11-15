"""Apply only the exact local Waza review after explicit approval."""

import argparse
import contextlib
import hashlib
import json
import os
import secrets
import shutil
import signal
import stat
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from http.client import HTTPConnection
from pathlib import Path

from local_gate import Gate
from prepare import ENGINE_PORT, PORT, ROOT, SANDBOX, STAGES, grant_snapshot, load, write

from aeep.assessment.identity import file_digest
from aeep.assessment.models import (
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.execution import EventJournal
from aeep.models import ExecutionReceipt, RawExecution, ResourceVector, StrictModel, utc_now
from aeep.store import ReceiptStore


class CleanupUncertain(RuntimeError):
    """Preserve scratch and the open reservation when owned cleanup is uncertain."""


class BoundDefinition(StrictModel):
    review_sha256: str
    implementation_source: str
    role: str


class RestrictedRedirect(urllib.request.HTTPRedirectHandler):
    max_redirections = 3

    def __init__(self, hosts):
        self.hosts = frozenset(hosts)

    def verify(self, url):
        parsed = urllib.parse.urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in self.hosts
            or parsed.username is not None
            or parsed.password is not None
            or parsed.port not in (443, None)
        ):
            raise ValueError("artifact endpoint was outside the reviewed HTTPS inventory")

    def redirect_request(self, req, stream, code, msg, headers, url):
        self.verify(url)
        return super().redirect_request(req, stream, code, msg, headers, url)


def disk_guard(work, threshold):
    if shutil.disk_usage(work).free < threshold:
        raise RuntimeError("storage reserve reached")


def get_artifact(asset, target, review, deadline):
    guard = RestrictedRedirect(review["allowed_download_hosts"])
    guard.verify(asset["url"])
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), guard)
    digest = hashlib.sha256()
    length = 0
    with opener.open(asset["url"], timeout=30) as response, target.open("xb") as out:
        while chunk := response.read(1024 * 1024):
            length += len(chunk)
            if length > asset["size"] or time.monotonic() >= deadline:
                raise RuntimeError("artifact byte or time ceiling reached")
            disk_guard(target.parent, review["minimum_host_free_bytes"])
            digest.update(chunk)
            out.write(chunk)
    if length != asset["size"] or digest.hexdigest() != asset["sha256"]:
        raise RuntimeError("artifact byte identity differs")


def unpack(archive, target, max_bytes):
    size = 0
    seen = set()
    with tarfile.open(archive, mode="r|gz") as stream:
        for member in stream:
            if (
                not (member.isdir() or member.isfile())
                or len(seen) >= 4096
                or member.size < 0
                or size + member.size > max_bytes
            ):
                raise ValueError("unexpected archive member or expansion limit")
            identity = Path(member.name)
            if identity.is_absolute() or ".." in identity.parts or identity in seen:
                raise ValueError("unsafe or duplicate archive member")
            seen.add(identity)
            size += member.size
            stream.extract(member, path=target, filter="data")
    # Release packaging may put the portable program at the archive root or at bin/ollama.
    options = [path for path in (target / "ollama", target / "bin/ollama") if path.is_file()]
    if len(options) != 1:
        raise ValueError("archive has no unique portable executable")
    executable = options[0]
    if not executable.stat().st_mode & stat.S_IXUSR:
        raise ValueError("portable executable lacks its executable bit")
    return executable


def install(review, work, max_seconds):
    retained = work / "retained"
    retained.mkdir(mode=0o700)
    archive = retained / "ollama-darwin.tgz"
    models = retained / "models"
    blobs = models / "blobs"
    blobs.mkdir(parents=True, mode=0o700)
    deadline = time.monotonic() + max_seconds - 45
    get_artifact(review["archive"], archive, review, deadline)
    for asset in review["model_assets"]:
        get_artifact(asset, blobs / ("sha256-" + asset["sha256"]), review, deadline)
    disk_guard(work, review["minimum_host_free_bytes"] + review["maximum_archive_expanded_bytes"])
    runtime = retained / "runtime"
    runtime.mkdir(mode=0o700)
    executable = unpack(archive, runtime, review["maximum_archive_expanded_bytes"])
    subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", str(executable)],
        env={"PATH": "/usr/bin:/bin"},
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
        timeout=15,
    )
    name, tag = review["model"].split(":")
    manifest = models / "manifests" / "registry.ollama.ai" / "library" / name / tag
    manifest.parent.mkdir(parents=True)
    write(manifest, Path(review["model_manifest"]).read_bytes())
    return {
        "executable": str(executable),
        "executable_sha256": file_digest(executable),
        "artifact_count": 1 + len(review["model_assets"]),
        "download_bytes": review["maximum_download_response_bytes"],
        "model_manifest_sha256": file_digest(manifest),
    }


def fresh_environment(root):
    paths = {name: root / name for name in ("home", "tmp", "config", "cache", "data", "state")}
    for path in paths.values():
        path.mkdir(mode=0o700)
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(paths["home"]),
        "TMPDIR": str(paths["tmp"]),
        "XDG_CONFIG_HOME": str(paths["config"]),
        "XDG_CACHE_HOME": str(paths["cache"]),
        "XDG_DATA_HOME": str(paths["data"]),
        "XDG_STATE_HOME": str(paths["state"]),
        "LC_ALL": "C",
        "DO_NOT_TRACK": "1",
        "CI": "true",
    }


def listeners(port):
    status = subprocess.run(
        ["/usr/sbin/lsof", "-nP", "-iTCP:" + str(port), "-sTCP:LISTEN", "-FpPn"],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    if status.returncode == 1 and not status.stdout and not status.stderr:
        return []
    if status.returncode or status.stderr:
        raise RuntimeError("listener identity is uncertain")
    return [line for line in status.stdout.splitlines() if line.startswith(("p", "n"))]


def group_listeners(pid):
    status = subprocess.run(
        ["/usr/sbin/lsof", "-nP", "-a", "-g", str(pid), "-iTCP", "-sTCP:LISTEN", "-FpPn"],
        env={"PATH": "/usr/bin:/bin"},
        capture_output=True,
        text=True,
        timeout=5,
    )
    if status.returncode or status.stderr:
        raise RuntimeError("owned listener inventory is unavailable")
    addresses = [line[1:] for line in status.stdout.splitlines() if line.startswith("n")]
    if f"127.0.0.1:{ENGINE_PORT}" not in addresses or not all(
        address.startswith("127.0.0.1:") or address.startswith("[::1]:") for address in addresses
    ):
        raise RuntimeError("a non-loopback listener was observed")
    return len(addresses)


def local_json(port, path):
    http = HTTPConnection("127.0.0.1", port, timeout=3)
    try:
        http.request("GET", path)
        result = http.getresponse()
        body = result.read(262145)
        if result.status != 200 or len(body) > 262144:
            raise RuntimeError("unexpected local metadata response")
        return json.loads(body)
    finally:
        http.close()


def profile_argv(review, role, argv):
    return [str(SANDBOX), "-f", review["profiles"][role], *argv]


def spawn(argv, cwd, env):
    return subprocess.Popen(
        argv,
        cwd=cwd,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def group_exists(pid):
    try:
        os.killpg(pid, 0)
    except ProcessLookupError:
        return False
    return True


def stop_owned(proc):
    # Each launch owns its session and process group. Never search for and stop
    # another process by command name or port.
    with contextlib.suppress(ProcessLookupError):
        os.killpg(proc.pid, signal.SIGTERM)
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(proc.pid, signal.SIGKILL)
        proc.wait(timeout=4)
    for _ in range(10):
        if not group_exists(proc.pid):
            return
        time.sleep(0.1)
    raise CleanupUncertain("owned process group cleanup is uncertain")


@contextlib.contextmanager
def owned(argv, cwd, env):
    proc = spawn(argv, cwd, env)
    try:
        yield proc
    finally:
        try:
            stop_owned(proc)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CleanupUncertain("owned process group cleanup is uncertain") from error


def observe_service(server, review, installation):
    deadline = time.monotonic() + 35
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise RuntimeError("retained Ollama bootstrap failed")
        try:
            facts = local_json(ENGINE_PORT, "/api/version")
        except OSError:
            time.sleep(0.25)
            continue
        if facts.get("version") != review["archive"]["version"]:
            raise RuntimeError("local server reports a different version")
        break
    else:
        raise RuntimeError("local server startup window ended")
    observed = listeners(ENGINE_PORT)
    if observed != [f"p{server.pid}", f"n127.0.0.1:{ENGINE_PORT}"]:
        raise RuntimeError("Ollama is not the owned loopback-only listener")
    tags = local_json(ENGINE_PORT, "/api/tags")["models"]
    if (
        len(tags) != 1
        or tags[0]["name"] != review["model"]
        or (tags[0]["digest"].removeprefix("sha256:") != installation["model_manifest_sha256"])
    ):
        raise RuntimeError("installed local model drifted")
    return {"version": facts["version"], "model_manifest_verified": True, "loopback_only": True}


def checked_json(path):
    if path.is_symlink() or path.stat().st_nlink != 1 or path.stat().st_size > 1024 * 1024:
        raise ValueError("unexpected result path or response size")
    return load(path)


def minimal_reply(path):
    result = checked_json(path)
    [task] = result["tasks"]
    [run] = task["runs"]
    usage = run.get("usage")
    if (
        task["test_id"] != "receipt-total"
        or task.get("cached")
        or result.get("is_baseline")
        or run["attempts"] != 1
        or run["run_number"] != 1
        or run.get("error_msg")
        or run["status"] in {"error", "skipped"}
        or run.get("tool_events")
        or run.get("session_digest", {}).get("tool_calls")
        or (
            usage is not None
            and (not isinstance(usage, dict) or usage.get("provider") not in {"", None, "custom"})
        )
    ):
        raise ValueError("Waza run lacks a single uncached local turn")
    reply = run["final_output"]
    if not isinstance(reply, str) or not 0 < len(reply.encode()) <= 4096:
        raise ValueError("Waza lacks a bounded reply")
    raw_usage = {}
    usage = usage or {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_write_tokens",
        "turns",
    ):
        if key in usage:
            if type(usage[key]) is not int or usage[key] < 0:
                raise ValueError("Waza token measurements are malformed")
            raw_usage[key] = usage[key]
    handoff = {
        "schemaVersion": "1.4",
        "eval_id": "aeep-waza-ollama-protected",
        "tasks": [
            {
                "test_id": task["test_id"],
                "status": "passed",
                "runs": [
                    {"run_number": 1, "attempts": 1, "status": "passed", "final_output": reply}
                ],
            }
        ],
    }
    return handoff, raw_usage, hashlib.sha256(reply.encode()).hexdigest()


def grading_result(path, reply_hash):
    [task] = checked_json(path)["tasks"]
    [run] = task["runs"]
    result = run["validations"]["exact-total"]
    score = result["score"]
    if (
        task["test_id"] != "receipt-total"
        or run["run_number"] != 1
        or result["type"] != "text"
        or type(result["passed"]) is not bool
        or type(score) not in (int, float)
        or score != int(result["passed"])
        or hashlib.sha256(run["final_output"].encode()).hexdigest() != reply_hash
    ):
        raise ValueError("protected grade does not bind the original reply and assertion")
    return {"task_id": task["test_id"], "score": score, "maximum": 1, "protected": True}


def verify(review, review_file, *, started=False):
    root = review_file.parent.resolve()
    if (
        review["schema_version"] != "aeep.operator.waza-ollama.v1"
        or Path(review["work"]) != root
        or review["implementation_source"] != verification_source_digest(ROOT)
        or not utc_now() < datetime.fromisoformat(review["expires_at"])
        or review["stages"] != STAGES
        or review["max_cash_usd"] != "0"
        or review["ports"] != {"gateway": PORT, "ollama": ENGINE_PORT}
        or review["maximum_remote_model_turns"] != 0
        or review["maximum_local_model_turns"] != 1
    ):
        raise RuntimeError("review scope, source or expiry changed")
    if not started:
        disk_guard(root, review["start_free_bytes"])
        assert not any((root / name).exists() for name in ("started.json", "retained", "scratch"))
        assert not listeners(PORT) and not listeners(ENGINE_PORT)
        assert (
            grant_snapshot(review["database"], review["grant_baseline"]["id"])
            == review["grant_baseline"]
        )
    for file, digest in review["pins"].items():
        if file_digest(Path(file)) != digest:
            raise RuntimeError("reviewed file drifted")
    assert f"localhost:{PORT}" in Path(review["profiles"]["live"]).read_text()
    assert "localhost:*" in Path(review["profiles"]["serve"]).read_text()
    assert "allow network" not in Path(review["profiles"]["grade"]).read_text()


def amend(repo, review, ref):
    grant = review["grant_baseline"]
    records = {}
    by_role = {}
    for role in ("subject", "recipe", "environment", "mapping"):
        definition = BoundDefinition(
            review_sha256=ref, implementation_source=review["implementation_source"], role=role
        )
        digest = content_digest(definition)
        repo.put("toolkit_waza_local_scope", digest, definition)
        records[digest] = definition.model_dump(mode="json")
        by_role[role] = digest
    scope = AssessmentScopeAmendment(
        authorization_id=grant["id"],
        authorization_digest=grant["root"],
        subject_digests=[by_role["subject"]],
        recipe_digests=[by_role["recipe"]],
        environment_digests=[by_role["environment"]],
        reviewed_digests=list(records),
    )
    budget = AssessmentBudgetAmendment(
        authorization_id=grant["id"],
        authorization_digest=grant["root"],
        previous_amendment_digest=grant["predecessor"],
        expires_at=datetime.fromisoformat(review["expires_at"]),
        limits=AssessmentLimits.model_validate(review["grant_absolute_limits"]),
    )
    repo.approve_bundle(scope, records, budget_amendment=budget)
    request = RecipeMaterializationRequest(
        plan_id="waza-local-" + ref[:16],
        authorization_id=grant["id"],
        subject_digest=by_role["subject"],
        recipe_digest=by_role["recipe"],
        environment_digest=by_role["environment"],
        mapping_digest=by_role["mapping"],
        definition_digests=list(records),
        seed=0,
    )
    repo.put("recipe_materialization_request", request.plan_id, request)
    return request, {
        "scope": scope.model_dump(mode="json"),
        "budget": budget.model_dump(mode="json"),
    }


@contextlib.contextmanager
def metered(repo, request, review, ref, stage):
    limits = review["stages"][stage]
    operation = request.plan_id + ":" + stage
    reserved = AssessmentLimits(
        max_operations=limits["operations"],
        max_model_turns=limits["model_turns"],
        max_elapsed_seconds=limits["reserved_seconds"],
        max_cash_usd="0",
    )
    repo.reserve(
        request, operation, reserved, stage="waza_local_" + stage, require_settled_plan=True
    )
    journal = EventJournal(operation)
    journal.append("execution.started", "start")
    started, clock = utc_now(), time.monotonic()
    safe_facts = {}
    error = None
    try:
        yield safe_facts
    except BaseException as failure:
        error = type(failure).__name__
        if isinstance(failure, CleanupUncertain):
            safe_facts["cleanup_uncertain"] = True
        raise
    finally:
        elapsed = time.monotonic() - clock
        journal.append("execution.failed" if error else "execution.completed", "terminal")
        execution = journal.evidence(
            "reviewed_waza_local", RawExecution(status="failed" if error else "success")
        )
        journal_ref = repo.put("execution_evidence", content_digest(execution), execution)
        resources = ResourceVector(
            latency_ms=elapsed * 1000,
            input_tokens=safe_facts.get("input_tokens", 0),
            output_tokens=safe_facts.get("output_tokens", 0),
            cached_input_tokens=safe_facts.get("cached_input_tokens", 0),
        )
        receipt = ExecutionReceipt(
            decision_id=operation,
            action_id=operation,
            capability="toolkit.upstream-engineering@1",
            executor_id="toolkit.waza-ollama." + stage,
            executor_kind="command",
            status="failed" if error else "success",
            started_at=started,
            ended_at=utc_now(),
            estimated={},
            actual_resources=resources,
            execution_success=error is None,
            error_type=error,
            metadata={
                "review_sha256": ref,
                "execution_evidence_ref": journal_ref,
                "facts": safe_facts,
                "scope": "stack_integration",
                "remote_model_turns": 0,
                "cash_authority_usd": "0",
            },
        )
        repo.store.save_receipt(receipt)
        repo.put("toolkit_component_receipt", operation, receipt)
        if not safe_facts.get("cleanup_uncertain"):
            repo.finish_operation(
                operation, elapsed_seconds=elapsed, resources=receipt.actual_resources
            )


def run(review, file, ref):
    work = file.parent
    execute = work / "scratch"
    live, grader, ollama = (execute / leaf for leaf in ("model-task", "grader", "ollama"))
    fixture = load(work / "public/tasks/receipt-total.yaml")
    baseline = review["grant_baseline"]
    with ReceiptStore(review["database"]) as store:
        repo = AssessmentRepository(store)
        write(work / "started.json", {"review_sha256": ref})
        request, amendments = amend(repo, review, ref)
        write(work / "applied-authority.json", amendments)
        outcome = {"passed": False, "cleanup_uncertain": True, "error_type": "Interrupted"}
        try:
            with metered(repo, request, review, ref, "download_and_install") as installed:
                installed.update(
                    install(review, work, STAGES["download_and_install"]["reserved_seconds"])
                )
            verify(review, file, started=True)
            for path in (live, grader, ollama):
                path.mkdir(mode=0o700, parents=True)
            ollama_env = fresh_environment(ollama) | {
                "OLLAMA_HOST": f"127.0.0.1:{ENGINE_PORT}",
                "OLLAMA_MODELS": str(work / "retained/models"),
                "OLLAMA_NO_CLOUD": "1",
                "OLLAMA_NOPRUNE": "1",
                "OLLAMA_CONTEXT_LENGTH": "8192",
                "OLLAMA_NUM_PARALLEL": "1",
                "OLLAMA_MAX_LOADED_MODELS": "1",
                "OLLAMA_KEEP_ALIVE": "120",
                "OLLAMA_MAX_QUEUE": "1",
            }
            nonce = secrets.token_urlsafe(32)
            live_env = fresh_environment(live) | {
                "COPILOT_HOME": str(live / "config"),
                "COPILOT_CLI_PATH": review["copilot"],
                "COPILOT_API_KEY": nonce,
                "COPILOT_BASE_URL": f"http://127.0.0.1:{PORT}/v1",
                "COPILOT_PROVIDER": "openai",
                "COPILOT_WIRE_API": "completions",
                "WAZA_NO_UPDATE_CHECK": "1",
            }
            assert file_digest(Path(installed["executable"])) == installed["executable_sha256"]
            with contextlib.ExitStack() as service:
                with metered(repo, request, review, ref, "service_and_boundaries") as facts:
                    try:
                        server = service.enter_context(
                            owned(
                                profile_argv(review, "serve", [installed["executable"], "serve"]),
                                ollama,
                                ollama_env,
                            )
                        )
                        gate = service.enter_context(
                            Gate(
                                PORT,
                                ENGINE_PORT,
                                review["model"],
                                fixture["inputs"]["prompt"],
                                nonce,
                            )
                        )
                        gateway_thread = threading.Thread(target=gate.serve_forever, daemon=True)
                        gateway_thread.start()
                        service.callback(gate.shutdown)
                        facts.update(observe_service(server, review, installed))
                        assert local_json(PORT, "/v1/models")["data"][0]["id"] == review["model"]
                    except BaseException:
                        service.close()
                        raise
                with metered(repo, request, review, ref, "waza_local_inference") as captured:
                    try:
                        with owned(
                            profile_argv(review, "live", review["commands"]["waza_live"]),
                            live,
                            live_env,
                        ) as proc:
                            captured["process_exit_code"] = proc.wait(timeout=145)
                            if captured["process_exit_code"] != 0:
                                raise RuntimeError("Waza reported an execution failure")
                        handoff, waza_usage, reply_hash = minimal_reply(live / "run.json")
                        usage = gate.facts()
                        if usage["forwarded"] != 1 or usage["rejected"] or not usage["usage"]:
                            raise ValueError(
                                "one protected local model completion was not observed"
                            )
                        reply = handoff["tasks"][0]["runs"][0]["final_output"]
                        if (
                            hashlib.sha256(reply.strip().encode()).hexdigest()
                            != usage["normalized_reply_sha256"]
                        ):
                            raise ValueError("Waza reply did not match the local completion")
                        captured.update(
                            reply_sha256=reply_hash,
                            waza_reported_usage=waza_usage,
                            output_retained=False,
                            model_manifest_sha256=installed["model_manifest_sha256"],
                            owned_loopback_listeners=group_listeners(server.pid),
                        )
                    finally:
                        counts = gate.facts()
                        captured.update(
                            local_completion_requests=counts["forwarded"],
                            denied_gateway_requests=counts["rejected"],
                            provider_usage=counts["usage"],
                            normalized_provider_reply_sha256=counts["normalized_reply_sha256"],
                        )
                        if counts["usage"]:
                            captured.update(
                                input_tokens=counts["usage"]["prompt_tokens"],
                                output_tokens=counts["usage"]["completion_tokens"],
                            )
                            if "cached_prompt_tokens" in counts["usage"]:
                                captured["cached_input_tokens"] = counts["usage"][
                                    "cached_prompt_tokens"
                                ]
                        try:
                            service.close()
                            if listeners(PORT) or listeners(ENGINE_PORT):
                                raise RuntimeError("local listeners remain")
                        except BaseException:
                            raise CleanupUncertain(
                                "local runtime cleanup could not be verified"
                            ) from None
                    captured["cleanup_verified"] = True
            verify(review, file, started=True)
            write(grader / "minimal-result.json", handoff)
            grade_env = fresh_environment(grader) | {
                "WAZA_NO_UPDATE_CHECK": "1",
                "COPILOT_HOME": str(grader / "config"),
            }
            with metered(repo, request, review, ref, "protected_grade") as grade:
                with owned(
                    profile_argv(review, "grade", review["commands"]["waza_grade"]),
                    grader,
                    grade_env,
                ) as proc:
                    exit_code = proc.wait(timeout=25)
                grade["process_exit_code"] = exit_code
                if exit_code not in {0, 1}:
                    raise RuntimeError("offline grader reported an infrastructure failure")
                grade.update(
                    grading_result(grader / "graded.json", reply_hash), reply_sha256=reply_hash
                )
                grade["cleanup_verified"] = True
            outcome = {
                "passed": True,
                "model": review["model"],
                "native_runtime": installed,
                "provider": captured,
                "grade": grade,
            }
        except (Exception, KeyboardInterrupt) as error:
            outcome = {
                "passed": False,
                "error_type": type(error).__name__,
                "automatic_retry": False,
                "cleanup_uncertain": isinstance(error, CleanupUncertain),
            }
        finally:
            if (
                execute.exists()
                and not execute.is_symlink()
                and not outcome.get("cleanup_uncertain")
            ):
                try:
                    if listeners(PORT) or listeners(ENGINE_PORT):
                        raise CleanupUncertain("local listeners remain")
                    shutil.rmtree(execute)
                except Exception as error:
                    outcome.update(
                        passed=False, cleanup_uncertain=True, cleanup_error=type(error).__name__
                    )
        ledger = repo.operation_ledger(request.plan_id)
        outcome["operations"] = ledger.model_dump(mode="json")
        outcome["authorization_id"] = baseline["id"]
        outcome["comparison"] = "PAUSED"
        write(work / "result.json", outcome)
        return outcome


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    parser.add_argument("--execute-approved")
    args = parser.parse_args()
    file = args.review.resolve()
    review = load(file)
    ref = file_digest(file)
    verify(review, file)
    if args.execute_approved is None:
        print(
            json.dumps(
                {"review_sha256": ref, "verified_pins": len(review["pins"]), "execution": False}
            )
        )
    else:
        approval = load(file.with_name("operator-approval.json"))
        if not (
            args.execute_approved == ref == approval["review_sha256"]
            and approval["approved"] is True
        ):
            raise SystemExit("explicit approval for this exact review is required")
        result = run(review, file, ref)
        print(json.dumps(result, indent=2))
        raise SystemExit(not result["passed"])
