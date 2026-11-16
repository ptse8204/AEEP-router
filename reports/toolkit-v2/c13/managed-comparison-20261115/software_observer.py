"""Host-side observations for exact LibCST helper calls and protected test outcomes."""

import re
import shlex
from unittest.mock import patch

from prepare_runtime import read, sha, write
from verify_graders import invoke

from aeep.assessment.models import content_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter, _message_digest
from aeep_toolkit.worker_readiness import _Document

PYTHON = "/usr/local/bin/python3"
HELPER = "/opt/aeep-specialists/aeep_libcst_reviewed.py"
PREFIX = (PYTHON, "-I", "-B", HELPER)
WORD = re.compile(r"[A-Za-z0-9_./-]{1,300}\Z")
SOURCE = re.compile(r"(?:[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}/)*[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}\.py\Z")
QUALIFIED = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,12}\Z")
STATUSES = {"PASSED", "FAILED", "ERROR", "SKIPPED", "XFAIL"}


def argv_of(command):
    """Accept immutable interpreter argv or its simple pinned POSIX shell framing."""
    if isinstance(command, str) and len(command) <= 2048 and HELPER in command:
        try:
            argv = shlex.split(command)
        except ValueError:
            return None
        if len(argv) == 3 and tuple(argv[:2]) in {
            ("/bin/bash", "-c"),
            ("/bin/sh", "-c"),
        }:
            command = argv[2]
            argv = command.split()
        if " ".join(argv) != command:
            return None
    elif isinstance(command, list):
        argv = command
    else:
        return None
    if len(argv) not in (6, 8) or not all(isinstance(x, str) and WORD.fullmatch(x) for x in argv):
        return None
    if tuple(argv[:4]) != PREFIX or not SOURCE.fullmatch(argv[5]):
        return None
    if len(argv) == 6 and argv[4] == "check":
        return tuple(argv)
    if len(argv) == 8 and argv[4] == "rename" and all(QUALIFIED.fullmatch(x) for x in argv[6:]):
        return tuple(argv)
    return None


class AttemptObserver:
    def __init__(self):
        self.starts = {}
        self.completed = []
        self.overflow = False

    def handle(self, method, params):
        if method not in {"item/started", "item/completed"}:
            return
        item = params.get("item")
        if (
            not isinstance(item, dict)
            or item.get("type") != "commandExecution"
            or item.get("cwd") != "/workspace"
        ):
            return
        argv = argv_of(item.get("command"))
        keys = (params.get("threadId"), params.get("turnId"), item.get("id"))
        if argv is None or not all(isinstance(key, str) and 0 < len(key) <= 128 for key in keys):
            return
        digest = content_digest(argv)
        if method == "item/started" and item.get("status") == "inProgress":
            if len(self.starts) >= 64:
                self.overflow = True
            elif keys not in self.starts:
                self.starts[keys] = (digest, _message_digest(item).removeprefix("sha256:"))
            else:
                self.starts.pop(keys)
            return
        start = self.starts.pop(keys, None)
        code = item.get("exitCode")
        status = item.get("status")
        changed = status == "completed" and type(code) is int and code == 0
        unchanged = (
            argv[4] == "rename"
            and type(code) is int
            and code == 3
            and status in {"completed", "failed"}
        )
        if not start or start[0] != digest or not (changed or unchanged):
            return
        if len(self.completed) >= 64:
            self.overflow = True
            return
        self.completed.append(
            {
                "thread_identity_digest": _message_digest({"thread_id": keys[0]}),
                "turn_identity_digest": _message_digest({"turn_id": keys[1]}),
                "item_ref": content_digest(keys),
                "command_digest": digest,
                "started_action_digest": start[1],
                "completed_action_digest": _message_digest(item).removeprefix("sha256:"),
                "operation": argv[4],
                "exit_code": code,
                "libcst_import_observed": True,
                "syntax_parse_observed": True,
                "transformation_observed": argv[4] == "rename",
                "changed_preview_observed": argv[4] == "rename" and changed,
            }
        )

    def finish(self, metadata):
        return [
            item
            for item in self.completed
            if all(
                item[key] == metadata.get(key)
                for key in ("thread_identity_digest", "turn_identity_digest")
            )
        ]


def watch_software_workers(directory, bindings):
    """This process-only patch observes both arms equally; the adapter controls execution."""
    dispatch = CodexAppServerAdapter.execute

    async def observe(adapter, context):
        binding = bindings.get(adapter.adapter_id)
        if binding is None:
            return await dispatch(adapter, context)
        assert adapter._worker is not None and binding["worker_digest"] == adapter._worker.digest()
        observer = AttemptObserver()
        detach = adapter.transport.subscribe(observer.handle)
        try:
            raw = await dispatch(adapter, context)
        finally:
            detach()
        attempt = context.attempt_id
        calls = observer.finish(raw.metadata)
        assert not calls or binding["helper_sha256"] is not None
        record = {
            "attempt_id": attempt,
            "adapter_id": adapter.adapter_id,
            "worker_digest": binding["worker_digest"],
            "helper_sha256": binding["helper_sha256"],
            "cleanup_confirmed": raw.metadata.get("worker_cleanup_confirmed") is True,
            "calls": calls,
            "overflow": observer.overflow,
            "unobserved_direct_imports_and_commands": "unknown",
        }
        write(directory / (content_digest(attempt) + ".json"), record)
        adapter._journals[attempt].append(
            "artifact.created", "libcst-observer", evidence_ref=content_digest(record)
        )
        return raw

    return patch.object(CodexAppServerAdapter, "execute", observe)


def per_test(reply, payload, required):
    if (
        not isinstance(reply, dict)
        or set(reply) != {"exit_code", "statuses", "archive_sha256", "python", "pytest"}
        or any(reply[key] != payload[key] for key in ("archive_sha256", "python", "pytest"))
        or type(reply["exit_code"]) is not int
        or reply["exit_code"] not in {0, 1, 2, 3, 4, 5}
        or not isinstance(reply["statuses"], dict)
        or len(reply["statuses"]) > 10000
        or any(
            not isinstance(value, str) or value not in STATUSES
            for value in reply["statuses"].values()
        )
    ):
        raise ValueError("protected grader reply differs from the pinned protocol")
    return {
        "pytest_exit": reply["exit_code"],
        "required_statuses": {key: reply["statuses"].get(key, "NOT_REPORTED") for key in required},
        "protected_test_identity_digest": content_digest(required),
    }


def observe_grader(truth_by_task, repository):
    async def grade(task, executor, spec, payload, trial_id, directory):
        reply = await invoke(task, executor, spec, payload, trial_id, directory)
        truth = truth_by_task[task["id"]]
        required = truth["fail_to_pass"] + truth["pass_to_pass"]
        record = per_test(reply, payload, required)
        [receipt] = list(directory.glob(f"*-{trial_id}.json"))
        raw = read(receipt)
        assert raw["metadata"]["cleanup_confirmed"] and raw["metadata"][
            "request_digest"
        ] == content_digest(payload)
        assert raw["metadata"]["task_id"] == task["id"] and raw["metadata"]["stage"] == trial_id
        evidence = {
            **record,
            "trial_id": trial_id,
            "task": task["id"],
            "grader_receipt_sha256": sha(receipt),
            "grader_request_digest": raw["metadata"]["request_digest"],
        }
        repository.put("protected_test_diagnostics", trial_id, _Document(value=evidence))
        write(directory / ("per-test-" + content_digest(trial_id) + ".json"), evidence)
        return reply

    return patch("run_dispatch.invoke", grade)


def positive_calls(sidecar, receipt, journal):
    metadata = receipt.metadata
    if (
        sidecar["attempt_id"] != metadata.get("attempt_id")
        or sidecar["adapter_id"] != metadata.get("adapter_id")
        or sidecar["worker_digest"] != metadata.get("worker_digest")
        or not sidecar["cleanup_confirmed"]
        or not metadata.get("worker_cleanup_confirmed")
        or not any(
            event.kind == "artifact.created"
            and event.source_id in {"libcst-observer", "adapter:libcst-observer"}
            and event.evidence_ref == content_digest(sidecar)
            for event in journal.events
        )
    ):
        raise ValueError("tool observer sidecar does not belong to the canonical receipt")
    starts = {event.action_digest for event in journal.events if event.kind == "action.started"}
    ends = {event.action_digest for event in journal.events if event.kind == "action.completed"}
    for call in sidecar["calls"]:
        if (
            call["thread_identity_digest"] != metadata.get("thread_identity_digest")
            or call["turn_identity_digest"] != metadata.get("turn_identity_digest")
            or call["started_action_digest"] not in starts
            or call["completed_action_digest"] not in ends
        ):
            raise ValueError("tool observer sidecar lacks canonical event corroboration")
    return sidecar["calls"]
