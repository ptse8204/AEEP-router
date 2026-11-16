"""Deterministic checks for the sidecar classifier's allowed and rejected evidence."""

from types import SimpleNamespace

from software_observer import HELPER, PREFIX, AttemptObserver, argv_of, per_test, positive_calls

from aeep.assessment.models import content_digest
from aeep.hosts.codex_app_server import _message_digest


def checks():
    direct = " ".join((*PREFIX, "rename", "src/a.py", "module.Old", "module.New"))
    assert argv_of(direct)[4] == "rename"
    assert argv_of(f"/bin/bash -c '{direct}'") == argv_of(direct)
    for command in (
        f"env DEBUG=1 {direct}",
        f"/bin/bash -lc '{direct}; true'",
        f"/bin/bash -lc '{direct}'",
        f"/bin/zsh -c '{direct}'",
        f"{direct} > preview.py",
        direct.replace("src/a.py", "../a.py"),
        direct.replace("src/a.py", "/worker/auth/config.py"),
        f"echo {HELPER}",
    ):
        assert argv_of(command) is None
    observer = AttemptObserver()
    metadata = {
        "attempt_id": "current-attempt",
        "adapter_id": "bound-adapter",
        "worker_digest": "a" * 64,
        "worker_cleanup_confirmed": True,
        "thread_identity_digest": _message_digest({"thread_id": "thread"}),
        "turn_identity_digest": _message_digest({"turn_id": "turn"}),
    }
    start = {
        "type": "commandExecution",
        "cwd": "/workspace",
        "id": "item",
        "command": direct,
        "status": "inProgress",
    }
    end = start | {"status": "completed", "exitCode": 0}
    ids = {"threadId": "thread", "turnId": "turn"}
    observer.handle("item/completed", ids | {"item": end})
    assert not observer.finish(metadata)
    observer.handle("item/started", ids | {"item": start})
    observer.handle("item/completed", ids | {"item": end | {"exitCode": 1}})
    assert not observer.finish(metadata)
    observer.handle("item/started", ids | {"item": start})
    observer.handle("item/completed", ids | {"item": end | {"exitCode": 3, "status": "failed"}})
    [no_op] = observer.finish(metadata)
    assert no_op["transformation_observed"] and not no_op["changed_preview_observed"]
    observer = AttemptObserver()
    observer.handle("item/started", ids | {"item": start})
    observer.handle("item/completed", ids | {"item": end})
    [call] = observer.finish(metadata)
    assert (
        call["libcst_import_observed"]
        and call["transformation_observed"]
        and call["changed_preview_observed"]
    )
    assert not observer.finish(metadata | {"turn_identity_digest": "mismatch"})
    assert direct not in str(call)
    sidecar = {key: metadata[key] for key in ("attempt_id", "adapter_id", "worker_digest")}
    sidecar |= {"cleanup_confirmed": True, "calls": [call]}
    events = [
        SimpleNamespace(kind="action.started", action_digest=call["started_action_digest"]),
        SimpleNamespace(kind="action.completed", action_digest=call["completed_action_digest"]),
        SimpleNamespace(
            kind="artifact.created",
            source_id="adapter:libcst-observer",
            evidence_ref=content_digest(sidecar),
        ),
    ]
    receipt = SimpleNamespace(metadata=metadata)
    journal = SimpleNamespace(events=events)
    assert positive_calls(sidecar, receipt, journal) == [call]
    for changed in (
        sidecar | {"attempt_id": "foreign"},
        sidecar | {"calls": [call | {"completed_action_digest": "unbound"}]},
        sidecar | {"calls": [call | {"changed_preview_observed": False}]},
    ):
        try:
            positive_calls(changed, receipt, journal)
        except ValueError:
            pass
        else:
            raise AssertionError("forged evidence accepted")
    payload = {"archive_sha256": "archive", "python": "3.13.7", "pytest": "8.4.1"}
    reply = payload | {"exit_code": 1, "statuses": {"a::test": "FAILED", "unrelated": "PASSED"}}
    expected = per_test(reply, payload, ["a::test", "b::test"])
    assert expected["required_statuses"] == {"a::test": "FAILED", "b::test": "NOT_REPORTED"}
    try:
        per_test(reply | {"archive_sha256": "foreign"}, payload, ["a::test"])
    except ValueError:
        pass
    else:
        raise AssertionError("foreign grader reply accepted")
    return True


if __name__ == "__main__":
    assert checks()
    print("Observer start/terminal, bypass, tampering and grader projection checks passed.")
