"""Preflight the exact local review with first-party substitutes only."""

import argparse
import contextlib
import hashlib
import io
import json
import os
import socket
import subprocess
import tarfile
import tempfile
import threading
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import run
from local_gate import Gate, bounded_payload, pack, read_usage, reply_digest
from prepare import ENGINE_PORT, PORT, SANDBOX, STAGES, load

from aeep.assessment.repository import AssessmentRepository
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore

MODEL = "qwen3:test-only"
PROMPT = "Test only: add these two numbers."
USAGE = {"prompt_tokens": 107, "completion_tokens": 5, "total_tokens": 112}


@contextlib.contextmanager
def hosting(server):
    with server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join(timeout=5)
            assert not thread.is_alive()


class SyntheticModel(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        assert data["max_tokens"] == 128 and data["temperature"] == 0
        assert data["stream_options"] == {"include_usage": True} and "tools" not in data
        response = (
            b"data: "
            + pack(
                {
                    "model": MODEL,
                    "usage": USAGE,
                    "choices": [{"delta": {"content": "Synthetic reply"}, "finish_reason": "stop"}],
                }
            )
            + b"\n\ndata: [DONE]\n\n"
        )
        self.send_response(200)
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)


def HTTP(port, data, auth):
    session = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        session.request("POST", "/v1/chat/completions", pack(data), {"Authorization": auth})
        response = session.getresponse()
        return response.status, response.read()
    finally:
        session.close()


def gateway_controls():
    input_data = {"model": MODEL, "messages": [{"role": "user", "content": PROMPT}], "stream": True}
    for changed in (
        {"model": "other"},
        {"tools": [{"type": "function"}]},
        {"messages": [{"role": "user", "content": "different"}]},
        {"messages": [{"role": "tool", "content": PROMPT}]},
    ):
        try:
            bounded_payload(input_data | changed, MODEL, PROMPT)
        except ValueError:
            continue
        raise AssertionError("bad gateway input was accepted")

    with (
        hosting(ThreadingHTTPServer(("127.0.0.1", 0), SyntheticModel)) as backend,
        hosting(Gate(0, backend, MODEL, PROMPT, "test-nonce")) as gateway,
    ):
        assert HTTP(gateway, input_data, "wrong")[0] == 401
        code, body = HTTP(gateway, input_data, "Bearer test-nonce")
        assert code == 200 and read_usage(body, True, MODEL) == USAGE
        assert HTTP(gateway, input_data, "Bearer test-nonce")[0] == 429
        assert reply_digest(body, True) == hashlib.sha256(b"Synthetic reply").hexdigest()
    assert read_usage(pack({"model": MODEL, "usage": USAGE}), False, MODEL) == USAGE


def sandbox_controls(review, work):
    probe = work / "first-party-outside-canary"
    probe.write_text("synthetic content for denial check")
    python = Path(os.sys.executable).resolve()
    assert run.file_digest(python) == review["pins"][str(python)]
    code = """
import errno, json, socket, sys
from pathlib import Path
role, canary, protected, allowed, engine = sys.argv[1:]
facts = {}
for key, path in [("outside_read_denied", canary), ("grader_read_denied", protected)]:
    try:
        with open(path, 'rb'):
            facts[key] = False
    except PermissionError:
        facts[key] = True
def connect(host, port):
    try:
        with socket.create_connection((host, int(port)), timeout=0.3):
            return "allowed"
    except PermissionError:
        return "denied"
    except OSError as error:
        return "denied" if error.errno in (errno.EACCES, errno.EPERM) else "unverified"
facts["external_denied"] = connect("192.0.2.10", 443) == "denied"
if role == "serve":
    with socket.socket() as endpoint:
        endpoint.bind(("127.0.0.1", 0))
        endpoint.listen(1)
        facts["child_loopback"] = connect("127.0.0.1", endpoint.getsockname()[1]) == "allowed"
else:
    facts["gateway_allowed"] = connect("127.0.0.1", allowed) == "allowed"
    facts["engine_denied"] = connect("127.0.0.1", engine) == "denied"
print(json.dumps(facts))
"""
    from prepare import FIXTURE

    controls = {}
    with socket.socket() as gateway, socket.socket() as backend:
        gateway.bind(("127.0.0.1", PORT))
        gateway.listen(16)
        backend.bind(("127.0.0.1", ENGINE_PORT))
        backend.listen(16)
        for role in ("live", "serve", "grade"):
            result = subprocess.run(
                [
                    str(SANDBOX),
                    "-f",
                    review["profiles"][role],
                    str(python),
                    "-I",
                    "-B",
                    "-c",
                    code,
                    role,
                    str(probe),
                    str(FIXTURE / "eval.yaml"),
                    str(PORT),
                    str(ENGINE_PORT),
                ],
                cwd="/",
                env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            )
            seen = json.loads(result.stdout)
            expected = {
                "outside_read_denied": True,
                "grader_read_denied": role != "grade",
                "external_denied": True,
            }
            if role == "serve":
                expected["child_loopback"] = True
            else:
                expected.update(gateway_allowed=role == "live", engine_denied=True)
            assert seen == expected, (role, seen, expected)
            controls[role] = seen
    return controls


def listener_controls():
    program = """import socket, sys, time
with socket.socket() as s:
    s.bind((sys.argv[1], int(sys.argv[2])))
    s.listen()
    time.sleep(10)
"""
    for address in ("127.0.0.1", "0.0.0.0"):
        with run.owned(
            [
                str(Path(os.sys.executable).resolve()),
                "-I",
                "-B",
                "-c",
                program,
                address,
                str(ENGINE_PORT),
            ],
            "/",
            {"PATH": "/usr/bin:/bin"},
        ) as proc:
            for _ in range(10):
                if run.listeners(ENGINE_PORT):
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("first-party listener did not start")
            try:
                count = run.group_listeners(proc.pid)
            except RuntimeError:
                assert address == "0.0.0.0"
            else:
                assert address == "127.0.0.1" and count == 1
        assert not run.listeners(ENGINE_PORT)


def archive_controls(work):
    def archive(name, filenames):
        path = work / name
        with tarfile.open(path, mode="w:gz") as stream:
            for filename in filenames:
                part = tarfile.TarInfo(filename)
                part.size = 3
                part.mode = 0o555
                stream.addfile(part, io.BytesIO(b"elf"))
        return path

    target = work / "runtime"
    target.mkdir()
    assert run.unpack(archive("good.tgz", ["ollama"]), target, 10).read_bytes() == b"elf"
    try:
        run.unpack(archive("escape.tgz", ["../bad"]), target, 10)
    except (tarfile.FilterError, ValueError):
        assert not (work / "bad").exists()
    else:
        raise AssertionError("escaped archive was accepted")
    guard = run.RestrictedRedirect(["github.com"])
    guard.verify("https://github.com/ollama/ollama")
    for url in (
        "https://example.invalid/file",
        "http://github.com/file",
        "https://user@github.com/file",
    ):
        try:
            guard.verify(url)
        except ValueError:
            continue
        raise AssertionError("unreviewed redirect accepted")


def grading_controls(work):
    path = work / "waza.json"
    reply = "synthetic fixture reply"
    one = {
        "test_id": "receipt-total",
        "status": "passed",
        "runs": [
            {
                "attempts": 1,
                "run_number": 1,
                "status": "passed",
                "final_output": reply,
                "usage": {"provider": "custom", "input_tokens": 107, "output_tokens": 5},
            }
        ],
    }
    path.write_bytes(pack({"tasks": [one]}))
    handoff, _, reply_sha = run.minimal_reply(path)
    assert reply_sha == hashlib.sha256(reply.encode()).hexdigest()
    trial = handoff["tasks"][0]["runs"][0]
    assert trial["final_output"] == reply
    for score in (1, 0):
        trial["validations"] = {
            "exact-total": {"type": "text", "score": score, "passed": bool(score)}
        }
        path.write_bytes(pack(handoff))
        assert run.grading_result(path, reply_sha)["score"] == score
    trial["final_output"] = "substituted"
    path.write_bytes(pack(handoff))
    try:
        run.grading_result(path, reply_sha)
    except ValueError:
        pass
    else:
        raise AssertionError("an unbound reply was accepted")


def ledger_controls(review, review_path, work, *, uncertain=False):
    database = work / ("interrupted.sqlite3" if uncertain else "scope.sqlite3")
    with ReceiptStore(review["database"], read_only=True) as source, ReceiptStore(database) as copy:
        source._connection.backup(copy._connection)
    variant = review | {"database": str(database)}
    ref = run.file_digest(review_path)
    with ReceiptStore(database) as store:
        repo = AssessmentRepository(store)
        request, amendments = run.amend(repo, variant, ref)
        assert (
            amendments["budget"]["previous_amendment_digest"]
            == review["grant_baseline"]["predecessor"]
        )
        with run.metered(repo, request, variant, ref, "download_and_install"):
            pass
        if uncertain:
            try:
                with run.metered(repo, request, variant, ref, "service_and_boundaries"):
                    raise run.CleanupUncertain("first-party interrupted fixture")
            except run.CleanupUncertain:
                pass
            try:
                with run.metered(repo, request, variant, ref, "waza_local_inference"):
                    raise AssertionError("the unresolved plan executed again")
            except ConfigurationError:
                return
            raise AssertionError("unsettled operation allowed more dispatch")
        for stage in ("service_and_boundaries", "waza_local_inference", "protected_grade"):
            with run.metered(repo, request, variant, ref, stage):
                pass
        ledger = repo.operation_ledger(request.plan_id)
        assert len(ledger.operations) == 4
        assert sum(row.reserved.max_model_turns for row in ledger.operations) == 1
        assert sum(row.reserved.max_elapsed_seconds for row in ledger.operations) == sum(
            row["reserved_seconds"] for row in STAGES.values()
        )
        assert all(row.reserved.max_cash_usd == 0 for row in ledger.operations)


def main(file):
    file = file.resolve()
    review = load(file)
    run.verify(review, file)
    gateway_controls()
    with tempfile.TemporaryDirectory(prefix="waza-first-party-", dir=file.parent) as scratch:
        work = Path(scratch)
        sandbox = sandbox_controls(review, work)
        listener_controls()
        archive_controls(work)
        grading_controls(work)
        ledger_controls(review, file, work)
        ledger_controls(review, file, work, uncertain=True)
    run.verify(review, file)
    print(
        json.dumps(
            {
                "review_sha256": run.file_digest(file),
                "verified_pins": len(review["pins"]),
                "sandbox_first_party_controls": sandbox,
                "listener_controls": "owned loopback listener accepted, wildcard listener rejected, both stopped",
                "gateway": "one accepted completion, unbound sender and second completion denied; bad model, tools, task and role rejected",
                "artifact_controls": "exact paths, unsafe archive member and unreviewed HTTPS redirects",
                "grade_controls": "both binary outcomes and mismatched reply rejection checked with substitutes",
                "copied_ledger": "four exact reservations settle on success; uncertain cleanup stops the next reservation",
                "downloaded_software_bytes": 0,
                "upstream_processes_started": 0,
                "model_calls": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("review", type=Path)
    main(parser.parse_args().review)
