"""Receipt-bound classification of exact direct Python LibCST commands."""

import ast
import re
import shlex
from unittest.mock import patch

from prepare_runtime import write
from software_observer import PYTHON, QUALIFIED, SOURCE

from aeep.assessment.models import content_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter, _message_digest

PACKAGE_ROOT = "/opt/aeep-specialists"
FLAGS = ("-I", "-S", "-B")
OBSERVATION = "libcst-direct-observer"
LIMIT = 64
HERE_DOC = re.compile(
    r"\A" + re.escape(" ".join((PYTHON, *FLAGS, "-"))) +
    r""" <<'([A-Z][A-Z0-9_]{0,19})'\n(.*?)\n\1\n?\Z""",
    re.DOTALL,
)


def inline_python(command):
    """Decode a Python program from exact argv or a literal POSIX command."""
    if isinstance(command, list):
        argv = command
    elif isinstance(command, str) and len(command) <= 24_000:
        try:
            argv = shlex.split(command)
        except ValueError:
            return None
        if len(argv) == 3 and tuple(argv[:2]) in {("/bin/bash", "-c"), ("/bin/sh", "-c")}:
            if shlex.join(argv) != command:
                return None
            command = argv[2]
            here = HERE_DOC.fullmatch(command)
            if here is not None:
                tag, contents = here.groups()
                return contents if tag not in contents.splitlines() else None
            try:
                argv = shlex.split(command)
            except ValueError:
                return None
        if shlex.join(argv) != command:
            return None
    else:
        return None
    if (
        len(argv) == 6
        and tuple(argv[:5]) == (PYTHON, *FLAGS, "-c")
        and isinstance(argv[5], str)
        and len(argv[5]) <= 8000
    ):
        return argv[5]
    return None


def expression(node, bindings, counts):
    """Recognize only calls with a known immutable receiver and safe arguments."""
    match node:
        case ast.Constant(value=value) if isinstance(value, str) and len(value) <= 5000:
            return ("text",)
        case ast.Name(id=name):
            return bindings.get(name)
        case ast.Attribute(value=ast.Name(id=name), attr="code"):
            return ("text",) if bindings.get(name, ("",))[0] == "tree" else None
        case ast.Call(func=func, args=args, keywords=[]) if isinstance(func, ast.Attribute):
            receiver = expression(func.value, bindings, counts)
            if receiver == ("libcst",) and func.attr == "parse_module" and len(args) == 1:
                if expression(args[0], bindings, counts) == ("text",):
                    counts["parse_calls"] += 1
                    return ("tree", None)
            if receiver == ("libcst",) and func.attr == "CSTTransformer" and not args:
                return ("visitor",)
            if receiver == ("rename",) and func.attr == "transform_module" and len(args) == 1:
                if isinstance(args[0], ast.Name) and bindings.get(args[0].id, ("",))[0] == "tree":
                    counts["transform_calls"] += 1
                    return ("tree", args[0].id)
            if receiver and receiver[0] == "tree" and func.attr == "visit" and len(args) == 1:
                if expression(args[0], bindings, counts) == ("visitor",):
                    counts["transform_calls"] += 1
                    origin = func.value.id if isinstance(func.value, ast.Name) else None
                    return ("tree", origin)
            if receiver == ("path_instance",) and func.attr == "read_text":
                if not args or (len(args) == 1 and literal(args[0], "utf-8")):
                    return ("text",)
            return None
        case ast.Call(func=ast.Name(id=name), args=args, keywords=[]):
            binding = bindings.get(name)
            if binding == ("codemod_context",) and not args:
                return ("context",)
            if binding == ("rename_command",) and len(args) == 3:
                if (
                    expression(args[0], bindings, counts) == ("context",)
                    and all(
                        isinstance(arg, ast.Constant) and isinstance(arg.value, str)
                        and QUALIFIED.fullmatch(arg.value)
                        for arg in args[1:]
                    )
                ):
                    return ("rename",)
            if binding == ("path",) and len(args) == 1 and isinstance(args[0], ast.Constant):
                source = args[0].value
                if isinstance(source, str) and len(source) <= 300 and SOURCE.fullmatch(source):
                    return ("path_instance",)
            if name == "print" and binding is None and len(args) <= 2:
                if all(expression(arg, bindings, counts) == ("text",) for arg in args):
                    return ("printed",)
            return None
    return None


def literal(node, value):
    return isinstance(node, ast.Constant) and type(node.value) is type(value) and node.value == value


def startup(statements):
    if len(statements) <= 2:
        return False
    match statements[:2]:
        case [
            ast.Import(names=[ast.alias(name="sys", asname=None)]),
            ast.Expr(value=ast.Call(
                func=ast.Attribute(
                    value=ast.Attribute(value=ast.Name(id="sys"), attr="path"), attr="insert"
                ),
                args=[position, location], keywords=[],
            )),
        ]:
            return literal(position, 0) and literal(location, PACKAGE_ROOT)
    return False


def compare_preview(node, bindings):
    match node:
        case ast.Compare(
            left=ast.Attribute(value=ast.Name(id=after), attr="code"),
            ops=[operator],
            comparators=[ast.Attribute(value=ast.Name(id=before), attr="code")],
        ):
            if bindings.get(after) == ("tree", before) and isinstance(operator, (ast.Eq, ast.NotEq)):
                return "equal" if isinstance(operator, ast.Eq) else "different"
    return None


def classify(command):
    """Accept a bounded program whose successful exit implies each counted call ran."""
    source = inline_python(command)
    if source is None or len(source) > 8000:
        return None
    try:
        tree = ast.parse(source)
        if sum(1 for _ in ast.walk(tree)) > 240 or not startup(tree.body):
            return None
    except (SyntaxError, RecursionError, ValueError):
        return None
    bindings = {"sys": ("sys",)}
    counts = {"import_calls": 0, "parse_calls": 0, "transform_calls": 0}
    preview_matches = {"equal": 0, "different": 0}

    def bind(name, value):
        if name in bindings or name == "print" or name.startswith("_") or value is None:
            return False
        bindings[name] = value
        return True

    imports = {
        ("libcst.codemod", "CodemodContext"): "codemod_context",
        ("libcst.codemod.commands.rename", "RenameCommand"): "rename_command",
        ("pathlib", "Path"): "path",
    }
    for statement in tree.body[2:]:
        match statement:
            case ast.Import(names=[ast.alias(name="libcst", asname=alias)]):
                if not bind(alias or "libcst", ("libcst",)):
                    return None
                counts["import_calls"] += 1
            case ast.ImportFrom(module=module, names=[ast.alias(name=name, asname=alias)], level=0):
                binding = imports.get((module, name))
                if binding is None or not bind(alias or name, (binding,)):
                    return None
            case ast.Assign(targets=[ast.Name(id=name)], value=node):
                value = expression(node, bindings, counts)
                if value == ("printed",) or not bind(name, value):
                    return None
            case ast.Expr(value=node):
                if expression(node, bindings, counts) is None:
                    return None
            case ast.Assert(test=test, msg=None):
                comparison = compare_preview(test, bindings)
                if comparison is None:
                    return None
                preview_matches[comparison] += 1
            case _:
                return None
    if not counts["import_calls"]:
        return None
    return counts | {"equal_preview_assertions": preview_matches["equal"],
                     "different_preview_assertions": preview_matches["different"]}


class DirectObserver:
    def __init__(self):
        self.starts = {}
        self.completed = []
        self.overflow = False

    def handle(self, method, params):
        if method not in {"item/started", "item/completed"}:
            return
        item = params.get("item")
        if not isinstance(item, dict) or item.get("type") != "commandExecution":
            return
        if item.get("cwd") != "/workspace":
            return
        keys = (params.get("threadId"), params.get("turnId"), item.get("id"))
        if not all(isinstance(key, str) and 0 < len(key) <= 128 for key in keys):
            return
        command = item.get("command")
        counts = classify(command)
        if counts is None:
            return
        digest = content_digest(command)
        event_digest = _message_digest(item).removeprefix("sha256:")
        if method == "item/started":
            if item.get("status") != "inProgress":
                return
            if keys in self.starts:
                self.starts[keys] = None
            elif len(self.starts) >= LIMIT:
                self.overflow = True
            else:
                self.starts[keys] = (digest, event_digest)
            return
        start = self.starts.pop(keys, None)
        if (
            start is None or start[0] != digest or item.get("status") != "completed"
            or type(item.get("exitCode")) is not int or item["exitCode"] != 0
        ):
            return
        if len(self.completed) >= LIMIT:
            self.overflow = True
            return
        self.completed.append({
            "thread_identity_digest": _message_digest({"thread_id": keys[0]}),
            "turn_identity_digest": _message_digest({"turn_id": keys[1]}),
            "item_ref": content_digest(keys),
            "command_digest": digest,
            "started_action_digest": start[1],
            "completed_action_digest": event_digest,
            "exit_code": 0,
            **counts,
        })

    def finish(self, metadata):
        return [
            item for item in self.completed
            if all(item[key] == metadata.get(key) for key in (
                "thread_identity_digest", "turn_identity_digest"
            ))
        ]


def watch_direct_workers(directory, bindings):
    dispatch = CodexAppServerAdapter.execute

    async def observe(adapter, context):
        binding = bindings.get(adapter.adapter_id)
        if binding is None:
            return await dispatch(adapter, context)
        assert adapter._worker is not None and binding["worker_digest"] == adapter._worker.digest()
        observer = DirectObserver()
        detach = adapter.transport.subscribe(observer.handle)
        try:
            raw = await dispatch(adapter, context)
        finally:
            detach()
        attempt = context.attempt_id
        calls = observer.finish(raw.metadata)
        assert not calls or binding["package_available"], "control unexpected direct package use"
        record = {
            "attempt_id": attempt,
            "adapter_id": adapter.adapter_id,
            "worker_digest": binding["worker_digest"],
            "package_tree_sha256": binding["package_tree_sha256"],
            "cleanup_confirmed": raw.metadata.get("worker_cleanup_confirmed") is True,
            "calls": calls,
            "overflow": observer.overflow,
            "unobserved_libcst_paths": "unknown",
        }
        write(directory / (content_digest(attempt) + ".json"), record)
        adapter._journals[attempt].append(
            "artifact.created", OBSERVATION, evidence_ref=content_digest(record)
        )
        return raw

    return patch.object(CodexAppServerAdapter, "execute", observe)


def validate_direct_calls(sidecar, receipt, journal, binding):
    metadata = receipt.metadata
    if (
        sidecar["attempt_id"] != metadata.get("attempt_id")
        or sidecar["adapter_id"] != metadata.get("adapter_id")
        or sidecar["worker_digest"] != metadata.get("worker_digest")
        or sidecar["worker_digest"] != binding["worker_digest"]
        or sidecar["package_tree_sha256"] != binding["package_tree_sha256"]
        or not sidecar["cleanup_confirmed"]
        or not metadata.get("worker_cleanup_confirmed")
        or not any(
            event.kind == "artifact.created"
            and event.source_id in {OBSERVATION, "adapter:" + OBSERVATION}
            and event.evidence_ref == content_digest(sidecar)
            for event in journal.events
        )
    ):
        raise ValueError("direct observer record is not bound to the canonical receipt")
    starts = {event.action_digest for event in journal.events if event.kind == "action.started"}
    ends = {event.action_digest for event in journal.events if event.kind == "action.completed"}
    calls = sidecar["calls"]
    if len(calls) > LIMIT or (calls and not binding["package_available"]):
        raise ValueError("direct observer coverage exceeds the reviewed worker binding")
    if len({call["item_ref"] for call in calls}) != len(calls):
        raise ValueError("direct observer record contains duplicate command identities")
    for call in calls:
        if (
            call["thread_identity_digest"] != metadata.get("thread_identity_digest")
            or call["turn_identity_digest"] != metadata.get("turn_identity_digest")
            or call["started_action_digest"] not in starts
            or call["completed_action_digest"] not in ends
            or call["exit_code"] != 0
            or not 1 <= call["import_calls"] <= 120
            or not all(0 <= call[name] <= 120 for name in (
                "parse_calls", "transform_calls", "equal_preview_assertions",
                "different_preview_assertions",
            ))
        ):
            raise ValueError("direct observer record lacks matching native action events")
    return calls
