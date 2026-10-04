"""One-shot outer supervisor for the pinned synthetic bridge check.

It persists only allowlisted JSON records, never child stdout/stderr payloads.
Process polling covers observed PID/create-time identities only; it cannot prove
complete containment or a hard filesystem quota.
"""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from contextlib import suppress
from pathlib import Path
from typing import Any

import psutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RUNNER = HERE / "discovery_profile_bridge_check.py"
RUNNER_REVIEW = HERE / "workflow-linkage-bridge-runner-review.json"
ROOT_REVIEW = HERE / "workflow-linkage-bridge-root-review.json"
EXECUTION_REVIEW = HERE / "workflow-linkage-bridge-execution-review.json"
TERMINAL_RECORD = HERE / "successor-qualification-terminal.json"
CAMPAIGN_RESULT = HERE / "successor-qualification-result.json"
POLICY = ROOT / "docs" / "ASSESSMENT_TESTING.md"
RESULT = HERE / "discovery-profile-bridge-supervisor-result.jsonl"

RUNNER_SHA = "59d768579bceab6adffb3f09cac7adce2b4eb3e859c16187089ff7ba8460335c"
RUNNER_REVIEW_SHA = "28bc12cc2c7a16f39483395fc2249ec97590b7924a853a019f84dbecd09bf832"
ROOT_REVIEW_SHA = "a12b5760351b912e2b0dd91068d3f4692be7222c12e45ceb5891802e680274c6"
SOURCE_DIGEST = "eaad5bc7b30f3671284b1d7291a4483ff0d87399c2ea13a298be4006bc717ee1"
POLICY_SHA = "c0448f7ecacfdb5392cf9c5bbe06c971a1ebe460f9e159f7c5ee22b88884e997"
ASSESSMENT_ID = "assessment_b7304a6d072c4aae98e45839200e9055"

LAUNCHER_ENV = Path("/Users/edwintse/.local/bin/codex")
LAUNCHER = Path("/Users/edwintse/.codex/packages/standalone/releases/0.154.0-aarch64-apple-darwin/bin/codex")
LAUNCHER_SHA = "4f85982624b3898c8991cb80c0981b2aa71070e3537046c9a95950318a95afcc"
EVIDENCE_LABEL = "synthetic lifecycle only; not live benefit or backend-transfer evidence"

STARTUP_S = 20
CHILD_S = 2700
CHILD_CLEANUP_S = 45
INTERRUPT_S = 5
TERMINATE_S = 5
KILL_WAIT_S = 5
PARENT_WALL_S = STARTUP_S + CHILD_S + CHILD_CLEANUP_S + INTERRUPT_S + TERMINATE_S + KILL_WAIT_S
POLL_S = 0.1
SOURCE_SAMPLE_S = 30
OUTPUT_LIMIT = 256 * 1024
LINE_LIMIT = 64 * 1024
PROCESS_LIMIT = 4096
CHILD_TERMINAL = {"lifecycle_complete", "assessment_not_admitted", "failed"}
SAFE_ENV = ("PATH", "HOME", "TMPDIR", "TMP", "TEMP", "LANG", "LC_ALL", "LC_CTYPE", "TERM")
START_FIELDS = {"status", "temporary_directory", "launcher", "launcher_sha256", "evidence_label"}
END_FIELDS = {
    "status", "failure_code", "stage", "error_type", "source_location", "launcher",
    "launcher_sha256", "elapsed_seconds", "temporary_directory",
    "temporary_bytes_sampled_high_water", "temporary_entries_sampled_high_water",
    "temporary_bytes_final", "temporary_retained_for_review", "plan_id", "report_id",
    "qualification_passed", "report_outcome", "admission_created", "admission_id",
    "assessment_reservation_upper_operations", "assessment_reservation_upper_seconds",
    "lookup_executor_id", "receipt_id", "captured_observation_id", "stale_decision_id",
    "revoked_lookup_reason", "evidence_label",
}
Identity = tuple[int, float]


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _source_digest() -> str:
    src = str(ROOT / "src")
    if src not in sys.path:
        sys.path.insert(0, src)
    from aeep.assessment.verification import verification_source_digest

    return verification_source_digest(ROOT)


def _inside_stage(name: Any) -> Path:
    if not isinstance(name, str) or not name:
        raise ValueError("terminal_path_missing")
    path = (HERE / name).resolve(strict=True)
    if not path.is_relative_to(HERE.resolve()):
        raise ValueError("terminal_path_outside_stage")
    return path


def _verify_campaign_terminal(execution_review_sha: str) -> None:
    if _sha(EXECUTION_REVIEW) != execution_review_sha:
        raise ValueError("execution_review_sha_mismatch")
    review = json.loads(EXECUTION_REVIEW.read_text(encoding="utf-8"))
    if (review.get("status") != "approved_after_campaign"
            or review.get("execution_authorized") is not True
            or review.get("source_digest") != SOURCE_DIGEST
            or review.get("supervisor_sha256") != _sha(Path(__file__))
            or review.get("runner_sha256") != RUNNER_SHA):
        raise ValueError("execution_review_contents_mismatch")

    record_path = _inside_stage(review.get("campaign_terminal_record_path"))
    record_sha = review.get("campaign_terminal_record_sha256")
    if (record_path != TERMINAL_RECORD.resolve() or not isinstance(record_sha, str)
            or _sha(record_path) != record_sha):
        raise ValueError("campaign_terminal_record_mismatch")
    terminal = json.loads(record_path.read_text(encoding="utf-8"))
    if (terminal.get("terminal") is not True
            or terminal.get("assessment_id") != ASSESSMENT_ID
            or terminal.get("source_digest") != SOURCE_DIGEST
            or terminal.get("qualification_status") != "correctness_failed"
            or terminal.get("cleanup_verified") is not True):
        raise ValueError("campaign_not_terminal_or_cleanup_unverified")

    result_path = _inside_stage(terminal.get("result_path"))
    result_sha = terminal.get("result_sha256")
    if (result_path != CAMPAIGN_RESULT.resolve() or not isinstance(result_sha, str)
            or _sha(result_path) != result_sha):
        raise ValueError("campaign_result_mismatch")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if (result.get("assessment_id") != ASSESSMENT_ID
            or result.get("source_digest") != SOURCE_DIGEST
            or result.get("qualification_passed") is not False
            or result.get("proxy_restored") is not True
            or result.get("source_unchanged") is not True):
        raise ValueError("campaign_result_status_or_cleanup_mismatch")


def _verify_pins() -> dict[str, str]:
    actual = {
        "runner_sha256": _sha(RUNNER),
        "runner_review_sha256": _sha(RUNNER_REVIEW),
        "root_review_sha256": _sha(ROOT_REVIEW),
        "policy_sha256": _sha(POLICY),
        "source_digest": _source_digest(),
    }
    expected = {
        "runner_sha256": RUNNER_SHA,
        "runner_review_sha256": RUNNER_REVIEW_SHA,
        "root_review_sha256": ROOT_REVIEW_SHA,
        "policy_sha256": POLICY_SHA,
        "source_digest": SOURCE_DIGEST,
    }
    if actual != expected:
        raise ValueError("pinned_input_mismatch")
    runner_review = json.loads(RUNNER_REVIEW.read_text(encoding="utf-8"))
    root_review = json.loads(ROOT_REVIEW.read_text(encoding="utf-8"))
    if (runner_review.get("status") != "staged_not_executed"
            or runner_review.get("runner", {}).get("sha256") != RUNNER_SHA
            or runner_review.get("policy_read", {}).get("sha256") != POLICY_SHA
            or root_review.get("status") != "static_review_complete_execution_deferred"
            or root_review.get("source_digest") != SOURCE_DIGEST
            or root_review.get("files") != {
                "discovery_profile_bridge_check.py": RUNNER_SHA,
                "workflow-linkage-bridge-runner-review.json": RUNNER_REVIEW_SHA,
            }):
        raise ValueError("pinned_review_contents_mismatch")
    binary = LAUNCHER_ENV.resolve(strict=True)
    if binary != LAUNCHER or _sha(binary) != LAUNCHER_SHA:
        raise ValueError("pinned_native_launcher_mismatch")
    return actual


def _environment() -> dict[str, str]:
    # Forward ordinary process settings only; provider/auth variables are excluded.
    env = {key: os.environ[key] for key in SAFE_ENV if key in os.environ}
    env.update(PYTHONPATH=str(ROOT / "src"), AEEP_NATIVE_CODEX=str(LAUNCHER_ENV))
    return env


def _identity(pid: int) -> Identity | None:
    try:
        process = psutil.Process(pid)
        return pid, process.create_time()
    except psutil.Error:
        return None


def _key(identity: Identity) -> str:
    return f"{identity[0]}:{identity[1].hex()}"


def _state(identity: Identity) -> str:
    try:
        process = psutil.Process(identity[0])
        if process.create_time() != identity[1]:
            return "pid_reused"
        if not process.is_running():
            return "gone"
        return "zombie" if process.status() == psutil.STATUS_ZOMBIE else "live"
    except psutil.NoSuchProcess:
        return "gone"
    except psutil.ZombieProcess:
        return "zombie"
    except psutil.Error:
        return "unknown"


def _observe(root: Identity | None, seen: dict[str, Identity], issues: set[str]) -> None:
    if root is None or _state(root) != "live":
        return
    try:
        process = psutil.Process(root[0])
        if process.create_time() != root[1]:
            issues.add("root_identity_changed")
            return
        for child in process.children(recursive=True):
            try:
                identity = child.pid, child.create_time()
                if _key(identity) not in seen and len(seen) >= PROCESS_LIMIT:
                    issues.add("process_tracking_limit")
                    return
                seen[_key(identity)] = identity
            except psutil.Error:
                issues.add("descendant_identity_unavailable")
    except psutil.AccessDenied:
        issues.add("descendant_enumeration_denied")
    except psutil.Error:
        issues.add("descendant_enumeration_failed")


def _signal_owned(identity: Identity, sig: int, issues: set[str]) -> None:
    if _state(identity) != "live":
        return
    try:
        process = psutil.Process(identity[0])
        if process.create_time() != identity[1]:
            return
        process.send_signal(sig)
    except psutil.NoSuchProcess:
        pass
    except psutil.AccessDenied:
        issues.add("owned_signal_denied")
    except psutil.Error:
        issues.add("owned_signal_failed")


def _drain(proc: subprocess.Popen[bytes], selector: selectors.BaseSelector,
           buffer: bytearray, state: dict[str, Any],
           on_record: Callable[[str, dict[str, Any]], None] | None) -> None:
    assert proc.stdout is not None
    while True:
        try:
            chunk = os.read(proc.stdout.fileno(), 65_536)
        except BlockingIOError:
            return
        except OSError:
            state["protocol_issue"] = "output_read_failed"
            return
        if not chunk:
            with suppress(KeyError, ValueError):
                selector.unregister(proc.stdout)
            state["pipe_closed"] = True
            return
        state["output_bytes"] += len(chunk)
        over_limit = state["output_bytes"] > OUTPUT_LIMIT
        buffer.extend(chunk)
        while b"\n" in buffer:
            line, _, rest = buffer.partition(b"\n")
            buffer[:] = rest
            if len(line) > LINE_LIMIT:
                state["protocol_issue"] = "oversized_line"
                continue
            try:
                record = json.loads(line.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                state["protocol_issue"] = "non_json_output"
                continue
            if not isinstance(record, dict):
                state["protocol_issue"] = "non_object_output"
                continue
            if record.get("status") == "started":
                try:
                    temp = Path(record["temporary_directory"]).resolve(strict=True)
                    temp_root = Path(tempfile.gettempdir()).resolve(strict=True)
                    valid = (temp.is_dir() and temp.is_relative_to(temp_root)
                             and record.get("launcher") == str(LAUNCHER)
                             and record.get("launcher_sha256") == "sha256:" + LAUNCHER_SHA
                             and record.get("evidence_label") == EVIDENCE_LABEL)
                except (KeyError, OSError, TypeError, ValueError):
                    valid = False
                if not valid or state["started_record"] is not None:
                    state["protocol_issue"] = "invalid_or_duplicate_started_record"
                    state["stop_reason"] = "started_record_invalid"
                    continue
                safe = {key: record[key] for key in START_FIELDS if key in record}
                state["started_record"] = safe
                state["started_at"] = time.monotonic()
                if on_record:
                    on_record("child_started", safe)
            elif record.get("status") in CHILD_TERMINAL:
                valid = (record.get("launcher") == str(LAUNCHER)
                         and record.get("launcher_sha256") == "sha256:" + LAUNCHER_SHA)
                if not valid or state["terminal_record"] is not None:
                    state["protocol_issue"] = "invalid_or_duplicate_terminal_record"
                    continue
                safe = {key: record[key] for key in END_FIELDS if key in record}
                state["terminal_record"] = safe
                state["terminal_at"] = time.monotonic()
                if on_record:
                    on_record("child_terminal", safe)
            else:
                state["protocol_issue"] = "unexpected_json_record"
        if len(buffer) > LINE_LIMIT:
            state["protocol_issue"] = "oversized_unterminated_line"
            state["stop_reason"] = "output_limit"
            return
        if over_limit:
            state["stop_reason"] = "output_limit"
            return


def _wait_until(deadline: float, root: Identity | None, seen: dict[str, Identity],
                issues: set[str], proc: subprocess.Popen[bytes],
                selector: selectors.BaseSelector | None, buffer: bytearray,
                state: dict[str, Any],
                on_record: Callable[[str, dict[str, Any]], None] | None,
                poll_s: float) -> None:
    while time.monotonic() < deadline:
        _observe(root, seen, issues)
        if selector is not None:
            _drain(proc, selector, buffer, state, on_record)
        statuses = [_state(identity) for identity in seen.values()]
        if all(status in {"gone", "zombie", "pid_reused"} for status in statuses):
            return
        time.sleep(min(poll_s, max(0.0, deadline - time.monotonic())))


def _cleanup(proc: subprocess.Popen[bytes], root: Identity | None,
             seen: dict[str, Identity], issues: set[str],
             selector: selectors.BaseSelector | None, buffer: bytearray,
             state: dict[str, Any], deadline: float, poll_s: float, interrupt_s: float,
             terminate_s: float) -> None:
    def observe_safely() -> None:
        try:
            _observe(root, seen, issues)
        except BaseException:
            issues.add("descendant_observation_failed_during_cleanup")

    def signal_safely(identity: Identity, sig: int) -> None:
        try:
            _signal_owned(identity, sig, issues)
        except BaseException:
            issues.add("owned_signal_failed_during_cleanup")

    def wait_safely(until: float) -> None:
        try:
            _wait_until(until, root, seen, issues, proc, selector, buffer, state,
                        None, poll_s)
        except BaseException:
            issues.add("cleanup_wait_failed")

    try:
        if root is not None:
            signal_safely(root, signal.SIGINT)
        wait_safely(min(deadline, time.monotonic() + interrupt_s))
    finally:
        observe_safely()
        for identity in tuple(seen.values()):
            signal_safely(identity, signal.SIGTERM)
        wait_safely(min(deadline, time.monotonic() + terminate_s))
        observe_safely()
        for identity in tuple(seen.values()):
            signal_safely(identity, signal.SIGKILL)
        wait_safely(deadline)


def _drive(command: list[str], *, cwd: Path, env: dict[str, str],
           startup_s: float, runtime_s: float, poll_s: float,
           parent_wall_s: float = PARENT_WALL_S,
           interrupt_s: float = INTERRUPT_S,
           terminate_s: float = TERMINATE_S,
           on_record: Callable[[str, dict[str, Any]], None] | None = None,
           source_guard: Callable[[], str | None] | None = None) -> dict[str, Any]:
    launched = time.monotonic()
    deadline = launched + parent_wall_s
    proc: subprocess.Popen[bytes] | None = None
    selector: selectors.BaseSelector | None = None
    root: Identity | None = None
    seen: dict[str, Identity] = {}
    issues: set[str] = set()
    buffer = bytearray()
    state: dict[str, Any] = {
        "output_bytes": 0, "pipe_closed": False, "started_record": None,
        "started_at": None, "terminal_record": None, "terminal_at": None,
        "protocol_issue": None, "stop_reason": None,
    }
    failure: BaseException | None = None
    try:
        proc = subprocess.Popen(command, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                bufsize=0, start_new_session=True)
        root = _identity(proc.pid)
        if root is None:
            issues.add("root_identity_unavailable")
        else:
            seen[_key(root)] = root
        selector = selectors.DefaultSelector()
        assert proc.stdout is not None
        os.set_blocking(proc.stdout.fileno(), False)
        selector.register(proc.stdout, selectors.EVENT_READ)
        next_source = launched + SOURCE_SAMPLE_S
        exit_seen: float | None = None
        while True:
            _observe(root, seen, issues)
            _drain(proc, selector, buffer, state, on_record)
            now = time.monotonic()
            code = proc.poll()
            if code is not None and exit_seen is None:
                exit_seen = now
            if state["started_at"] is None and now - launched >= startup_s:
                state["stop_reason"] = state["stop_reason"] or "startup_timeout"
            elif state["started_at"] is not None and now - state["started_at"] >= runtime_s:
                state["stop_reason"] = state["stop_reason"] or "child_runtime_deadline"
            if now >= deadline:
                state["stop_reason"] = state["stop_reason"] or "parent_wall_deadline"
            if (state["terminal_at"] is not None and code is None
                    and now - state["terminal_at"] >= 10):
                state["stop_reason"] = state["stop_reason"] or "post_terminal_exit_timeout"
            if "process_tracking_limit" in issues:
                state["stop_reason"] = state["stop_reason"] or "process_tracking_limit"
            if source_guard is not None and now >= next_source and state["stop_reason"] is None:
                state["stop_reason"] = source_guard()
                next_source = now + SOURCE_SAMPLE_S
            if state["stop_reason"] or (code is not None and state["pipe_closed"]):
                break
            if exit_seen is not None and now - exit_seen >= 10:
                state["stop_reason"] = "descendant_kept_output_pipe_open"
                break
            selector.select(min(poll_s, max(0.0, deadline - now)))
    except BaseException as exc:
        failure = exc
        state["stop_reason"] = state["stop_reason"] or "supervisor_interrupted_or_failed"
    finally:
        try:
            if proc is not None:
                cleanup_needed = False
                try:
                    _observe(root, seen, issues)
                    statuses = [_state(identity) for identity in seen.values()]
                    cleanup_needed = (
                        proc.poll() is None
                        or any(status in {"live", "unknown"} for status in statuses)
                    )
                except BaseException as exc:
                    issues.add("pre_cleanup_observation_exception_" + type(exc).__name__)
                    cleanup_needed = True
                if cleanup_needed:
                    try:
                        _cleanup(proc, root, seen, issues, selector, buffer, state,
                                 deadline, poll_s, interrupt_s, terminate_s)
                    except BaseException as exc:
                        issues.add("cleanup_exception_" + type(exc).__name__)
                        # Escalate only identities whose creation times still match.
                        for identity in tuple(seen.values()):
                            for sig in (signal.SIGTERM, signal.SIGKILL):
                                try:
                                    _signal_owned(identity, sig, issues)
                                except BaseException:
                                    issues.add("owned_escalation_failed")
                        try:
                            _wait_until(deadline, root, seen, issues, proc, selector,
                                        buffer, state, None, poll_s)
                        except BaseException:
                            issues.add("final_owned_wait_failed")
        finally:
            if proc is not None:
                if selector is not None:
                    try:
                        selector.close()
                    except Exception:
                        issues.add("selector_close_failed")
                if proc.stdout is not None:
                    try:
                        proc.stdout.close()
                    except OSError:
                        issues.add("pipe_close_failed")

    if proc is not None and proc.poll() is None and time.monotonic() < deadline:
        try:
            proc.wait(timeout=max(0.0, deadline - time.monotonic()))
        except subprocess.TimeoutExpired:
            issues.add("root_wait_expired")
    states = {_key(identity): _state(identity) for identity in seen.values()}
    if any(status in {"live", "unknown"} for status in states.values()):
        cleanup_state = "incomplete_or_unknown"
    elif issues or any(status == "zombie" for status in states.values()):
        cleanup_state = "unknown"
    else:
        cleanup_state = "verified_for_observed_identities"
    result: dict[str, Any] = {
        "exit_code": proc.poll() if proc is not None else None,
        "started_record": state["started_record"],
        "terminal_record": state["terminal_record"],
        "stop_reason": state["stop_reason"],
        "protocol_issue": state["protocol_issue"],
        "output_bytes_seen": state["output_bytes"],
        "elapsed_seconds": round(time.monotonic() - launched, 3),
        "cleanup_state": cleanup_state,
        "cleanup_issues": sorted(issues),
        "observed_processes": [{"pid": pid, "create_time": created} for pid, created in seen.values()],
        "observed_process_states": states,
        "process_tree_completeness": "unknown; polling cannot prove no detached or missed child",
        "parent_wall_limit_seconds": parent_wall_s,
    }
    if failure is not None:
        result["supervisor_exception_type"] = type(failure).__name__
    return result


def _append(stream: Any, record: dict[str, Any]) -> None:
    stream.write(json.dumps(record, ensure_ascii=True, sort_keys=True) + "\n")
    stream.flush()
    os.fsync(stream.fileno())


def _run_once(execution_review_sha: str) -> int:
    if RESULT.exists():
        raise SystemExit("one_shot_result_already_exists")
    try:
        _verify_campaign_terminal(execution_review_sha)
        pins = _verify_pins()
    except Exception:
        raise SystemExit("preflight_rejected") from None
    with RESULT.open("x", encoding="utf-8") as output:
        _append(output, {"record_type": "supervisor_started", "result_path": str(RESULT),
                         "supervisor_sha256": _sha(Path(__file__)), "runner_sha256": RUNNER_SHA,
                         "execution_review_sha256": execution_review_sha,
                         "source_digest": SOURCE_DIGEST, "evidence_label": EVIDENCE_LABEL})
        source_state = {"current": pins["source_digest"]}

        def guard() -> str | None:
            try:
                current = _source_digest()
            except Exception:
                source_state["current"] = "unavailable"
                return "source_digest_check_unavailable"
            source_state["current"] = current
            return None if current == SOURCE_DIGEST else "verification_source_changed"

        def save_child(kind: str, record: dict[str, Any]) -> None:
            _append(output, {"record_type": kind, **record})

        outcome = _drive([sys.executable, str(RUNNER)], cwd=ROOT, env=_environment(),
                         startup_s=STARTUP_S, runtime_s=CHILD_S + CHILD_CLEANUP_S,
                         poll_s=POLL_S, on_record=save_child, source_guard=guard)
        source_guard_problem = guard()
        child_end = outcome["terminal_record"]
        child_started = outcome["started_record"]
        protocol_valid = (
            outcome["protocol_issue"] is None
            and child_started is not None
            and child_end is not None
            and child_started.get("temporary_directory") == child_end.get("temporary_directory")
        )
        if (outcome["cleanup_state"] != "verified_for_observed_identities"
                or source_state["current"] != SOURCE_DIGEST
                or source_guard_problem is not None
                or not protocol_valid or outcome["stop_reason"] is not None):
            status = "incomplete_or_unknown"
        elif child_end["status"] == "failed" or outcome["exit_code"] != 0:
            status = "runner_terminal_failure"
        elif child_end["status"] == "assessment_not_admitted":
            status = "completed_without_admission"
        else:
            status = "synthetic_lifecycle_complete_observed_tree_only"
        _append(output, {"record_type": "supervisor_terminal", "status": status,
                         "source_digest_after": source_state["current"],
                         "source_guard_problem": source_guard_problem,
                         "runner_terminal_status": child_end.get("status") if child_end else None,
                         "runner_exit_code": outcome["exit_code"], "stop_reason": outcome["stop_reason"],
                         "protocol_issue": outcome["protocol_issue"],
                         "cleanup_state": outcome["cleanup_state"],
                         "cleanup_issues": outcome["cleanup_issues"],
                         "observed_processes": outcome["observed_processes"],
                         "observed_process_states": outcome["observed_process_states"],
                         "process_tree_completeness": outcome["process_tree_completeness"],
                         "output_bytes_seen": outcome["output_bytes_seen"],
                         "elapsed_seconds": outcome["elapsed_seconds"],
                         "parent_wall_limit_seconds": PARENT_WALL_S})
    print(f"RESULT: {RESULT}")
    return 0 if status in {"synthetic_lifecycle_complete_observed_tree_only", "completed_without_admission"} else 125


def _self_check() -> int:
    """Fake subprocess-only check of success, timeout cleanup and PID scope."""
    env = {"PATH": os.defpath}
    unrelated = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"],
                                 stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL, start_new_session=True)
    unrelated_id = _identity(unrelated.pid)
    if unrelated_id is None:
        unrelated.kill()
        unrelated.wait()
        raise RuntimeError("self_check_identity_unavailable")
    try:
        with tempfile.TemporaryDirectory(prefix="aeep-supervisor-self-check-") as temp:
            temp_dir = str(Path(temp).resolve())
            start = json.dumps({"status": "started", "temporary_directory": temp_dir,
                                "launcher": str(LAUNCHER), "launcher_sha256": "sha256:" + LAUNCHER_SHA,
                                "evidence_label": EVIDENCE_LABEL})
            end = json.dumps({"status": "assessment_not_admitted", "temporary_directory": temp_dir,
                              "launcher": str(LAUNCHER),
                              "launcher_sha256": "sha256:" + LAUNCHER_SHA,
                              "evidence_label": EVIDENCE_LABEL})
            success_code = ("import time; print(" + repr(start) + ",flush=True); print(" + repr(end)
                            + ",flush=True); time.sleep(.05)")
            success = _drive([sys.executable, "-c", success_code], cwd=Path(temp), env=env,
                             startup_s=1, runtime_s=2, poll_s=.02, parent_wall_s=3,
                             interrupt_s=.2, terminate_s=.2)
            if (success["exit_code"] != 0 or success["started_record"] is None
                    or success["terminal_record"] is None
                    or success["protocol_issue"] is not None
                    or success["started_record"].get("temporary_directory")
                    != success["terminal_record"].get("temporary_directory")
                    or success["cleanup_state"] != "verified_for_observed_identities"):
                raise RuntimeError("self_check_success_failed")
            sleeper = "import time; time.sleep(60)"
            spawn_code = (
                "import subprocess,sys,time\n"
                "subprocess.Popen([sys.executable,'-c'," + repr(sleeper) + "],start_new_session=True)\n"
                "print(" + repr(start) + ",flush=True)\n"
                "try:\n time.sleep(60)\nexcept KeyboardInterrupt:\n pass\n"
            )
            timeout = _drive([sys.executable, "-c", spawn_code], cwd=Path(temp), env=env,
                             startup_s=1, runtime_s=.4, poll_s=.02, parent_wall_s=3,
                             interrupt_s=.2, terminate_s=.2)
            if (timeout["stop_reason"] != "child_runtime_deadline"
                    or timeout["started_record"] is None
                    or timeout["protocol_issue"] is not None
                    or timeout["cleanup_state"] != "verified_for_observed_identities"
                    or len(timeout["observed_processes"]) < 2):
                diagnostic = {
                    "stop_reason": timeout["stop_reason"],
                    "started_record_seen": timeout["started_record"] is not None,
                    "protocol_issue": timeout["protocol_issue"],
                    "cleanup_state": timeout["cleanup_state"],
                    "cleanup_issues": timeout["cleanup_issues"],
                    "observed_process_count": len(timeout["observed_processes"]),
                    "observed_process_states": list(timeout["observed_process_states"].values()),
                }
                raise RuntimeError("self_check_timeout_cleanup_failed "
                                   + json.dumps(diagnostic, sort_keys=True))
            if (_state(unrelated_id) != "live"
                    or _key(unrelated_id) in timeout["observed_process_states"]):
                raise RuntimeError("self_check_unrelated_process_not_preserved")
    finally:
        _signal_owned(unrelated_id, signal.SIGTERM, set())
        try:
            unrelated.wait(timeout=2)
        except subprocess.TimeoutExpired:
            _signal_owned(unrelated_id, signal.SIGKILL, set())
            unrelated.wait(timeout=2)
    print(json.dumps({"status": "self_check_passed", "fake_child_success": True,
                      "fake_timeout_cleanup": True, "unrelated_process_survived": True,
                      "process_tree_completeness": "not proven by polling"}, sort_keys=True))
    return 0


def main() -> int:
    if sys.argv[1:] == ["--self-check"]:
        return _self_check()
    if (len(sys.argv) != 3 or sys.argv[1] != "--execution-review-sha256"
            or len(sys.argv[2]) != 64 or any(c not in "0123456789abcdef" for c in sys.argv[2])):
        raise SystemExit("usage: discovery_profile_bridge_supervisor.py --execution-review-sha256 HEX")
    try:
        return _run_once(sys.argv[2])
    except SystemExit:
        raise
    except Exception as exc:
        print(json.dumps({"status": "supervisor_failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 125


if __name__ == "__main__":
    raise SystemExit(main())
