"""First-party controls for the retained Waza driver, with a copied ledger."""

import contextlib
import hashlib
import io
import shutil
from pathlib import Path
from unittest.mock import patch

import check
import prepare
import run
from service_resume import RETAINED, categorize, execute, observed_process

from aeep.assessment.repository import AssessmentRepository
from aeep.store import ReceiptStore

REPLY = "Distinct first-party completion"
STAGES = ["service_and_boundaries", "waza_local_inference", "protected_grade"]


def driver_control(review, file, root, case):
    work = root / case
    work.mkdir()
    shutil.copytree(file.parent / "public", work / "public")
    database = work / "copy.sqlite3"
    with ReceiptStore(review["database"], read_only=True) as source, ReceiptStore(database) as copy:
        source._connection.backup(copy._connection)
    variant = review | {"work": str(work), "database": str(database)}
    port = prepare.ENGINE_PORT
    version = review["archive"]["version"]
    manifest = review["pins"][review["model_manifest"]]
    local_json = run.local_json

    def metadata(port_number, path):
        if port_number != port:
            return local_json(port_number, path)
        if path == "/api/version":
            return {"version": "other" if case == "version_mismatch" else version}
        if path == "/api/tags":
            return {
                "models": [
                    {
                        "name": review["model"],
                        "digest": "0" * 64 if case == "model_mismatch" else manifest,
                    }
                ]
            }
        raise AssertionError("unreviewed metadata path")

    service_running = False

    @contextlib.contextmanager
    def simulated_service(argv, cwd, env, categories):
        assert argv == run.profile_argv(
            variant,
            "serve",
            [str(RETAINED / "runtime/ollama"), "serve"],
        )
        assert env["OLLAMA_MODELS"] == str(RETAINED / "models")
        assert env["OLLAMA_NO_CLOUD"] == "1"
        categories.add("gpu_discovery")
        nonlocal service_running
        service_running = True
        try:
            yield type("Service", (), {"pid": 123, "poll": lambda self: None})()
        finally:
            service_running = False

    class Exit:
        def wait(self, timeout):
            assert timeout in (145, 25)
            return 1 if timeout == 25 and case == "failed_task" else 0

    @contextlib.contextmanager
    def simulated_worker(argv, cwd, env):
        grade = cwd.name == "grader"
        role = "grade" if grade else "live"
        key = "waza_grade" if grade else "waza_live"
        assert argv == run.profile_argv(variant, role, review["commands"][key])
        if grade:
            assert "COPILOT_API_KEY" not in env
            data = prepare.load(cwd / "minimal-result.json")
            trial = data["tasks"][0]["runs"][0]
            assert trial["final_output"] == REPLY
            score = int(case != "failed_task")
            trial["validations"] = {
                "exact-total": {"type": "text", "score": score, "passed": bool(score)}
            }
            prepare.write(cwd / "graded.json", data)
        else:
            assert env["COPILOT_BASE_URL"] == f"http://127.0.0.1:{prepare.PORT}/v1"
            token_digest = hashlib.sha256(REPLY.encode()).hexdigest()
            [gateway] = gateways
            assert gateway.authorization == "Bearer " + env["COPILOT_API_KEY"]
            gateway.forwarded = 1
            gateway.usage = check.USAGE
            gateway.normalized_reply_sha256 = token_digest
            prepare.write(
                cwd / "run.json",
                {
                    "tasks": [
                        {
                            "test_id": "receipt-total",
                            "runs": [
                                {
                                    "attempts": 1,
                                    "run_number": 1,
                                    "status": "passed",
                                    "final_output": REPLY,
                                }
                            ],
                        }
                    ],
                },
            )
        yield Exit()

    gateways = []
    gate_factory = run.Gate

    def gateway(*args):
        instance = gate_factory(*args)
        gateways.append(instance)
        return instance

    def retained(binding, directory, max_seconds):
        assert binding == variant and directory == work and max_seconds == 0
        return {
            "executable": str(RETAINED / "runtime/ollama"),
            "executable_sha256": run.file_digest(RETAINED / "runtime/ollama"),
            "model_manifest_sha256": manifest,
        }

    def bound_listener(port_number):
        return ["p123", f"n127.0.0.1:{port}"] if port_number == port and service_running else []

    with (
        patch.multiple(
            run,
            verify=lambda *args, **kwargs: None,
            local_json=metadata,
            owned=simulated_worker,
            listeners=bound_listener,
            group_listeners=lambda pid: 1,
            Gate=gateway,
            install=run.install,
            metered=run.metered,
            observe_service=run.observe_service,
        ),
        patch("service_resume.observed_process", simulated_service),
        patch("service_resume.verify_tree", retained),
    ):
        result = execute(variant, work / file.name, run.file_digest(file))
    operations = sorted(result["operations"]["operations"], key=lambda row: row["started_at"])
    expected = {
        "version_mismatch": "version_identity",
        "model_mismatch": "model_inventory",
    }.get(case)
    assert (result["passed"], result.get("cleanup_uncertain", False)) == (
        expected is None,
        False,
    ), result
    stages = [operation["stage"].removeprefix("waza_local_") for operation in operations]
    assert stages == (STAGES[:1] if expected else STAGES), (case, stages)
    assert not (work / "scratch").exists()
    assert not run.listeners(prepare.PORT) and not run.listeners(port)
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        receipt = repo.get("toolkit_component_receipt", operations[0]["operation_id"])
    facts = receipt["metadata"]["facts"]
    if expected:
        assert facts["readiness_phase"] == expected
        assert facts["service_stderr_categories"] == ["gpu_discovery"]
        assert gateways[0].forwarded == 0
    else:
        assert facts["readiness_phase"] == "complete"
        assert result["provider"]["provider_usage"] == check.USAGE
        assert result["grade"]["score"] == int(case != "failed_task")
        assert result["grade"]["reply_sha256"] == result["provider"]["reply_sha256"]
    return {"stages": stages, "readiness_phase": facts["readiness_phase"]}


def diagnostic_controls(review, file, work):
    categories = set()
    categorize(io.BytesIO(b"unrelated text " + b"x" * 4073 + b"permission denied"), categories)
    assert categories == {"permission_denied"}
    categories.clear()
    interpreter = str(Path(run.os.sys.executable).resolve())
    with observed_process(
        [interpreter, "-I", "-B", "-c", "import sys;sys.stderr.write('listening on; denied')"],
        work,
        {"PATH": "/usr/bin:/bin"},
        categories,
    ) as child:
        assert child.wait(timeout=5) == 0
    assert categories == {"listener_started"}
    # The pinned launch policy denies writes in the retained runtime and excludes
    # the installed model entirely from both the Waza and protected grader roles.
    for role in ("serve", "live", "grade"):
        profile = Path(review["profiles"][role]).read_text().splitlines()
        assert not any(
            line.startswith("(allow file-write") and str(RETAINED) in line for line in profile
        )
        if role != "serve":
            assert not any(str(RETAINED) in line for line in profile)
    return {
        case: driver_control(review, file, work, case)
        for case in ("complete", "failed_task", "version_mismatch", "model_mismatch")
    }
