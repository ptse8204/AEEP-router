"""Verify bounded direct LibCST classification and the retained worker runtime."""

import asyncio
import hashlib
import secrets
import shlex
import time
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

from libcst_direct_observer import (
    FLAGS, OBSERVATION, PACKAGE_ROOT, DirectObserver, classify, validate_direct_calls,
)
from prepare_runtime import WORK, docker, read, require_reserve, sha, write
from software_observer import PYTHON
from software_observer_preflight import DIR as PREVIOUS
from verify_workers import REACT, command, make_spec

from aeep.assessment.models import content_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter, _message_digest

HERE = Path(__file__).resolve().parent
OFFLINE = WORK / "libcst-direct-offline-boundary"
RESULT = OFFLINE / "result.json"
REVIEW = OFFLINE / "operation-review.json"
START = "import sys\nsys.path.insert(0, '/opt/aeep-specialists')\n"
IMPORT = START + "import libcst as cst\n"
PARSE = IMPORT + "tree = cst.parse_module('from api import Old\\nx = Old()\\n')\n"
RENAME = (
    PARSE
    + "from libcst.codemod import CodemodContext\n"
    + "from libcst.codemod.commands.rename import RenameCommand\n"
    + "new_tree = RenameCommand(CodemodContext(), 'api.Old', 'api.New').transform_module(tree)\n"
)
VISIT = PARSE + "new_tree = tree.visit(cst.CSTTransformer())\n"
CHANGED = RENAME + "assert new_tree.code != tree.code\n"
UNCHANGED = VISIT + "assert new_tree.code == tree.code\n"
MENTION = START + "print('import libcst; cst.parse_module; transform_module')\n"
BROKEN_PARSE = IMPORT + "cst.parse_module('def !')\n"
CORRECT_OPEN = PARSE.replace("cst.parse_module('from api import Old\\nx = Old()\\n')",
                             "cst.parse_module(Path('sample.py').read_text('utf-8'))")
CORRECT_OPEN = CORRECT_OPEN.replace("tree =", "from pathlib import Path\ntree =")
ORIGIN_PROBE = r"""
import hashlib, json, os, pathlib, subprocess, sys
root = pathlib.Path('/opt/aeep-specialists')
package = root/'libcst'
facts = {'package_present': package.is_dir(), 'read_only_package_root': False}
if facts['package_present']:
    assert root.resolve() == root and package.resolve() == package
    assert not os.access(root, os.W_OK) and not os.access(package, os.W_OK)
    sys.path.insert(0, str(root))
    import libcst
    assert pathlib.Path(libcst.__file__).resolve() == package/'__init__.py'
    files = {}
    for path in sorted(package.rglob('*')):
        assert not path.is_symlink() and not os.access(path, os.W_OK)
        if path.is_file():
            files[str(path.relative_to(package))] = hashlib.sha256(path.read_bytes()).hexdigest()
    assert len(files) > 100
    facts |= {'files_sha256': hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
              'package_file_count': len(files), 'read_only_package_root': True}
fixture = pathlib.Path('/workspace')
(fixture/'sample.py').write_text('from api import Old\nx = Old()\n')
(fixture/'libcst.py').write_text('raise SystemExit(0)\n')
print(json.dumps(facts))
"""


def native(code):
    return [PYTHON, *FLAGS, "-c", code]


def shell(code):
    return ["/bin/bash", "-c", f"{' '.join([PYTHON, *FLAGS, '-'])} <<'PY'\n{code.rstrip()}\nPY"]


@dataclass(frozen=True)
class Event:
    kind: str
    action_digest: str | None = None
    source_id: str | None = None
    evidence_ref: str | None = None


def event(observer, argv, *, completion=None, status=None, item_id="item", turn="turn"):
    item = {
        "type": "commandExecution",
        "command": shlex.join(argv),
        "cwd": "/workspace",
        "status": status or ("completed" if completion is not None else "inProgress"),
        "id": item_id,
        "exitCode": completion,
    }
    observer.handle("item/started" if completion is None else "item/completed", {
        "threadId": "thread", "turnId": turn, "item": item,
    })


def checks():
    accepted = {
        "import-only": (native(IMPORT), (1, 0, 0, 0, 0)),
        "parse": (native(PARSE), (1, 1, 0, 0, 0)),
        "heredoc-transform": (shell(CHANGED), (1, 1, 1, 0, 1)),
        "inline-noop": (native(UNCHANGED), (1, 1, 1, 1, 0)),
        "workspace-source-read": (shell(CORRECT_OPEN), (1, 1, 0, 0, 0)),
    }
    for argv, values in accepted.values():
        assert tuple(classify(shlex.join(argv)).values()) == values
    rejected = {
        "mere-code-mention": native(MENTION),
        "shadowing-package-root": native(IMPORT.replace(PACKAGE_ROOT, "/workspace")),
        "implicit-environment": [PYTHON, "-B", "-c", PARSE],
        "script-file": [PYTHON, *FLAGS, "sample.py"],
        "different-python": ["python3", *FLAGS, "-c", IMPORT],
        "dynamic-import": native(START + "__import__('libcst')\n"),
        "skipped-branch": native(START + "if False:\n    import libcst\n"),
        "except-masked-exit": native(IMPORT + "try:\n    cst.parse_module('def !')\nexcept Exception:\n    pass\n"),
        "forged-summary": native(IMPORT + "print('invoked a transform')\n"),
        "rebinding": native(IMPORT + "cst = 'shadow'\n"),
        "exec": native(IMPORT + "exec('cst = None')\n"),
        "unsupported-scan": native(IMPORT + "print(cst.__dict__)\n"),
        "early-success-exit": native(IMPORT + "import os\nos._exit(0)\n"),
        "workspace-path-escape": native(CORRECT_OPEN.replace("sample.py", "../sample.py")),
        "shell-composition": ["/bin/bash", "-c", shlex.join(native(IMPORT)) + " || true"],
        "environment-prefix": ["/bin/bash", "-c", "PYTHONPATH=. " + shlex.join(native(IMPORT))],
        "shell-early-heredoc": ["/bin/bash", "-c", shell(IMPORT)[2] + "\ntrue\nPY"],
        "login-shell-framing": ["/bin/bash", "-lc", shell(IMPORT)[2]],
    }
    # A forged textual claim cannot produce an observation of a transform.
    assert classify(rejected.pop("forged-summary"))["transform_calls"] == 0
    assert all(classify(shlex.join(argv)) is None for argv in rejected.values())
    assert classify(shlex.join(native(IMPORT)) + " || :") is None
    assert classify(shlex.join(native(IMPORT)).replace("-c ", "-c$IFS ", 1)) is None
    observer = DirectObserver()
    for item, first, last, status, code in (
        ("positive", shell(CHANGED), shell(CHANGED), "completed", 0),
        ("import-only", native(IMPORT), native(IMPORT), "completed", 0),
        ("import-failed", native(IMPORT), native(IMPORT), "failed", 1),
        ("parse-failed", native(BROKEN_PARSE), native(BROKEN_PARSE), "failed", 1),
        ("false-success-identity", native(IMPORT), native(PARSE), "completed", 0),
        ("false-success-status", native(IMPORT), native(IMPORT), "failed", 0),
    ):
        event(observer, first, item_id=item)
        event(observer, last, item_id=item, completion=code, status=status)
    event(observer, native(IMPORT), item_id="end-only", completion=0)
    event(observer, native(IMPORT), item_id="duplicate")
    event(observer, native(IMPORT), item_id="duplicate")
    event(observer, native(IMPORT), item_id="duplicate", completion=0)
    event(observer, native(IMPORT), item_id="mismatched-turn")
    event(observer, native(IMPORT), item_id="mismatched-turn", turn="other", completion=0)
    metadata = {
        "thread_identity_digest": _message_digest({"thread_id": "thread"}),
        "turn_identity_digest": _message_digest({"turn_id": "turn"}),
        "attempt_id": "attempt",
        "adapter_id": "adapter",
        "worker_digest": "worker",
        "worker_cleanup_confirmed": True,
    }
    receipt = SimpleNamespace(metadata=metadata)
    calls = observer.finish(metadata)
    assert len(calls) == 2 and [call["transform_calls"] for call in calls] == [1, 0]
    binding = {"worker_digest": "worker", "package_available": True, "package_tree_sha256": "tree"}
    sidecar = {
        "attempt_id": "attempt", "adapter_id": "adapter", "worker_digest": "worker",
        "package_tree_sha256": "tree", "cleanup_confirmed": True, "calls": calls,
    }
    action_events = [
        Event(kind, call[digest])
        for call in calls
        for kind, digest in (
            ("action.started", "started_action_digest"),
            ("action.completed", "completed_action_digest"),
        )
    ]
    artifact = Event("artifact.created", source_id=OBSERVATION, evidence_ref=content_digest(sidecar))
    journal = SimpleNamespace(events=[artifact, *action_events])
    assert validate_direct_calls(sidecar, receipt, journal, binding) == calls
    for modified, actual, events, actual_binding in (
        (sidecar | {"attempt_id": "wrong"}, receipt, journal, binding),
        (sidecar | {"calls": []}, receipt, journal, binding),
        (sidecar, receipt, SimpleNamespace(events=[artifact, *action_events[:-1]]), binding),
        (sidecar, receipt, SimpleNamespace(events=action_events), binding),
        (sidecar, receipt, journal, binding | {"package_tree_sha256": "wrong"}),
        (sidecar, receipt, journal, binding | {"package_available": False}),
        (sidecar, SimpleNamespace(metadata=metadata | {"worker_cleanup_confirmed": False}),
         journal, binding),
    ):
        try:
            validate_direct_calls(modified, actual, events, actual_binding)
        except ValueError:
            pass
        else:
            raise AssertionError("tampered record accepted")
    return {
        "accepted_fixtures": len(accepted),
        "rejected_classifier_fixtures": len(rejected) + 2,
        "observed_and_masked_native_event_fixtures": 10,
        "rejected_receipt_tampering_fixtures": 7,
    }


async def runtime_check(role, image):
    require_reserve()
    assert docker("image", "inspect", "--format", "{{.Id}}", image["id"]) == image["id"]
    spec = make_spec(REACT, "software_engineering", role, image, offline=True)
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    transport = adapter.transport
    argv = transport.argv
    assert argv[argv.index("--network") + 1] == "none" and "--mount" not in argv
    assert "--read-only" in argv and "--cap-drop=ALL" in argv
    assert not any("PROXY=" in arg for arg in argv)
    assert adapter._worker_process_id
    name = "aeep-" + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
    assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    outcomes = {}
    tick = time.monotonic()
    try:
        await transport.start()
        origin = await command(transport, ORIGIN_PROBE)
        assert origin["package_present"] == (role == "treatment")
        assert origin["read_only_package_root"] == (role == "treatment")
        variants = {"import": native(IMPORT), "mention": native(MENTION)}
        if role == "treatment":
            variants |= {
                "parse": native(PARSE), "heredoc_transform_changed": shell(CHANGED),
                "noop_transform": native(UNCHANGED), "read_workspace_source": shell(CORRECT_OPEN),
                "parse_error": native(BROKEN_PARSE),
            }
        for label, payload in variants.items():
            reply = await transport.request("command/exec", {
                "command": payload, "cwd": "/workspace", "timeoutMs": 15000, "outputBytesCap": 2000,
            }, timeout=20)
            code = reply["exitCode"]
            fail = label == "parse_error" or (label == "import" and role == "control")
            if fail:
                assert type(code) is int and code != 0
            else:
                assert code == 0, (label, code, str(reply.get("stderr", "")).splitlines()[-1:])
            outcomes[label] = code
        if role == "control":
            assert outcomes["import"] != 0  # The fake workspace module would exit zero if loaded.
    finally:
        await adapter.close()
        assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    return {
        "worker_image": image["id"], "facts": origin, "exit_codes": outcomes,
        "worker_cleanup_confirmed": True, "elapsed_seconds": time.monotonic() - tick,
    }


async def main():
    assert not RESULT.exists()
    OFFLINE.mkdir(mode=0o700)
    images = read(PREVIOUS / "images.json")
    review = {
        "authority": "Operator requested first bounded direct LibCST runtime verification.",
        "driver_sha256": sha(Path(__file__)),
        "classifier_sha256": sha(HERE / "libcst_direct_observer.py"),
        "previous_images_sha256": sha(PREVIOUS / "images.json"),
        "maximum_workers": 2,
        "maximum_commands_per_worker": 8,
        "maximum_reserved_seconds": 300,
        "model_turns": 0,
        "cash_usd": "0",
        "builds": 0,
        "network": "none",
        "credential_mounts": 0,
    }
    write(REVIEW, review)
    cases = checks()
    async with asyncio.timeout(review["maximum_reserved_seconds"]):
        workers = {role: await runtime_check(role, image) for role, image in images.items()}
    write(RESULT, {
        "review_sha256": sha(REVIEW), "workers": workers, "checks": cases,
        "model_turns": 0, "cash_usd": "0",
    })
    print(sha(RESULT))


if __name__ == "__main__":
    asyncio.run(main())
