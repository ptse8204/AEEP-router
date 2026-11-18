"""Bind a reference-only PyGLS diagnostic to the terminal first attempt."""

import argparse
import asyncio
import base64
import io
import json
import subprocess
import sys
import tarfile
import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import check_pygls_contract as first
from reconcile_c13_offline_completion import operations, reference

from aeep.assessment.repository import AssessmentRepository
from aeep.models import utc_now
from aeep.store import ReceiptStore

FIRST_REVIEW = "485f09c634380dcdf0c2877f3948e9030f2160789d16ebff4985f1c21835642d"


def audit_first_attempt():
    runner = first.runner
    target = first.TARGET
    reviewed = json.loads(first.read(target / "operation-review.json", FIRST_REVIEW))
    original = target / "execution"
    result = runner.get(original / "result.json")
    ledger = runner.get(original / "ledger.json")
    entries = operations(ledger)
    (row,) = result["observations"]
    launch, unstarted = reviewed["launches"]
    path = original / f"receipt-{row['receipt_id']}.json"
    with ReceiptStore(original / "receipts.sqlite3", read_only=True) as store:
        if (
            AssessmentRepository(store).operation_ledger(first.NAME).model_dump(mode="json")
            != ledger
        ):
            raise ValueError("exported ledger differs from durable accounting")
        receipt = store.get_receipt(row["receipt_id"])
        if (
            receipt is None
            or receipt.model_dump(mode="json") != runner.get(path)
            or receipt.decision_id != row["operation"]
            or receipt.action_id != row["operation"]
            or receipt.metadata.get("container_absent") is not True
            or receipt.metadata.get("operation_review_sha256") != FIRST_REVIEW
        ):
            raise ValueError("exported failed receipt differs from the durable record")
    if (
        result["verified"]
        or result["review_sha256"] != FIRST_REVIEW
        or row["contract_matched"]
        or "score" in row
        or row["operation"] != launch["operation"]
        or entries.keys() != {row["operation"]}
        or unstarted["operation"] in entries
        or receipt.execution_success
        or receipt.error_type != "OBSERVATION_MISMATCH"
    ):
        raise ValueError("reference settlement or unstarted original changed")
    if runner.docker("ps", "-aq", "--filter", f"name=^/{launch['container']}$"):
        raise ValueError("reviewed grader did not clean up")
    return {
        "first_review": reference(target / "operation-review.json"),
        "driver_rehearsal": reference(target / "rehearsal-result.json"),
        "by_delegation": reference(target / "delegated-authority.json"),
        "result": reference(original / "result.json"),
        "ledger": reference(original / "ledger.json"),
        "receipt": reference(path),
        "carrier": reviewed["environment"]["container_image"],
        "reference_gate": receipt.error_type,
        "score": None,
        "finished_operations": 1,
        "reserved_seconds": entries[row["operation"]]["reserved"]["max_elapsed_seconds"],
        "observed_seconds": entries[row["operation"]]["elapsed_seconds"],
        "original_dispatched": False,
        "container_absent": True,
        "matched_saved_ledger": True,
        "raw_guest_error_retained": False,
        "likely_timeout": "Observed duration is consistent with the observer's 22-second child timeout. The receipt contains no guest error class or test progress, so the cause is unknown.",
    }


def diagnostic_program(program):
    """Expose only bounded progress and an enum on interrupted reference calls."""
    changes = {
        "        log = root / 'tests.log'": """        progress = root / 'progress.json'
        boot = boot.replace(
            ';export=capture.export;',
            ';capture=type("ProgressCapture",(type(capture),),'
            '{"pytest_runtest_logstart":lambda self,nodeid,location:'
            'Path(' + repr(str(progress)) + ').write_text(json.dumps({"active":nodeid}))})('
            + repr(collect_only) + ');export=capture.export;'
        )
        log = root / 'tests.log'""",
        "            child = subprocess.run(": "            try:\n                child = subprocess.run(",
        "                stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)": """                    stdout=stream, stderr=subprocess.STDOUT, timeout=22, check=False)
            except subprocess.TimeoutExpired:
                return failure_progress(request, progress, 'child_timeout')
        if not events.is_file():
            return failure_progress(request, progress, 'no_native_events', child.returncode)""",
        "def main():": """def failure_progress(request, progress, category, child_exit=None):
    active = None
    if progress.is_file() and not progress.is_symlink() and progress.stat().st_size <= 8192:
        try:
            value = json.loads(progress.read_text()).get('active')
        except (UnicodeError, ValueError, AttributeError, OSError):
            pass
        else:
            if isinstance(value, str) and value.isprintable() and len(value.encode()) <= 1024:
                active = value
    return {'archive_sha256':request['archive_sha256'], 'category':category,
            'active_test':active, 'child_exit':child_exit}


def main():""",
    }
    for before, after in changes.items():
        if program.count(before) != 1:
            raise ValueError("observer anchor drifted")
        program = program.replace(before, after)
    compile(program, "<PyGLS timeout diagnostic>", "exec")
    return program


def rehearse(program):
    # Check the exact generated statement on the host without starting pytest.
    namespace = {"__name__": "diagnostic_fixture"}
    exec(compile(program, "<reviewed observer>", "exec"), namespace)

    old_exec = namespace["subprocess"].run
    old_path = namespace["Path"]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)

        def temp_repo(path):
            if path == "/tmp/aeep-repository-native-v6":
                return root / "source"
            return old_path(path)

        def timeout(command, **kwargs):
            boot = command[-1]
            compile(boot, "<reviewed timeout child>", "exec")
            (Path(kwargs["cwd"]) / "progress.json").write_text(
                '{"active":"tests/test_public.py::test_sample"}'
            )
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        tar = io.BytesIO()
        with tarfile.open(fileobj=tar, mode="w:gz"):
            pass
        payload = {
            "archive": base64.b64encode(tar.getvalue()).decode(),
            "archive_sha256": first.digest(tar.getvalue()),
            "python": ".".join(map(str, sys.version_info[:2])),
            "pytest": first.CORE["pytest"],
            "test_paths": ["tests/test_public.py"],
            "wheels": [],
        }
        with (
            patch.dict(namespace, Path=temp_repo),
            patch.object(namespace["subprocess"], "run", timeout),
            patch.object(sys, "stdin", io.StringIO(json.dumps(payload))),
        ):
            diagnostic = namespace["main"]()
        assert namespace["subprocess"].run is old_exec
        assert diagnostic == {
            "archive_sha256": payload["archive_sha256"],
            "active_test": "tests/test_public.py::test_sample",
            "category": "child_timeout",
            "child_exit": None,
        }
    return True


def executor_diagnostic(raw, payload, required):
    reply = raw.output
    record = {
        "archive_sha256": payload["archive_sha256"],
        "executor_status": raw.status.value,
        "executor_exit": raw.exit_code,
        "executor_error_category": raw.error_type
        if raw.error_type in {"TIMEOUT", "NONZERO_EXIT", "INVALID_JSON", "EXECUTION_ERROR"}
        else None,
    }
    if (
        isinstance(reply, dict)
        and set(reply) == {"archive_sha256", "category", "active_test", "child_exit"}
        and reply["archive_sha256"] == payload["archive_sha256"]
        and reply["category"] in ("child_timeout", "no_native_events")
    ):
        active = reply["active_test"]
        record.update(
            observer_category=reply["category"],
            last_required_test=active if isinstance(active, str) and active in required else None,
            child_exit=reply["child_exit"] if type(reply["child_exit"]) is int else None,
        )
    return record


async def prepare():
    reason = audit_first_attempt()
    observations = []
    first.configure(observations)
    runner = first.runner
    spec, environment, [subject] = runner.definitions()
    argv = [*spec.config["argv"]]
    argv[-1] = diagnostic_program(argv[-1])
    spec = spec.model_copy(update={"config": spec.config | {"argv": argv}})
    assert rehearse(argv[-1])

    first_review = runner.get(first.TARGET / "operation-review.json")
    target = first.TARGET / "timeout-diagnostic"
    runner.NAME = first.NAME + "-reference-diagnostic"
    runner.REVIEW = target / "operation-review.json"
    runner.APPROVAL = target / "approval.json"
    runner.RUN = target / "execution"
    runner.ROLES, runner.MAX_CALLS = ("reference",), 1
    runner.definitions = lambda: (spec, environment, [subject])
    receipt_identity = runner.NAME
    required = set(subject["truth"]["pass_to_pass"])

    class InspectingExecutor(runner.ContainerExecutor):
        async def execute(self, context):
            raw = await super().execute(context)
            facts = executor_diagnostic(raw, context.request.input, required)
            runner.put(
                runner.RUN / "worker-diagnostic.json",
                {"operation": context.attempt_id, "plan": receipt_identity, **facts},
            )
            return raw

    runner.ContainerExecutor = InspectingExecutor

    async def review_fields():
        scope, *_ = await first.BASE_REVIEW()
        (launch,) = scope["launches"]
        reference_launch = first_review["launches"][0]
        same = ("archive_sha256", "payload_sha256", "required_tests", "payload_bytes")
        if (
            any(launch[k] != reference_launch[k] for k in same)
            or scope["carrier_layers"] != first_review["carrier_layers"]
            or scope["environment"] != first_review["environment"]
            or scope["cases"] != first_review["cases"]
            or scope["case_fingerprints"] != first_review["case_fingerprints"]
        ):
            raise ValueError("diagnostic changed protected payload, environment or case")
        return (
            scope
            | {
                "schema_version": "aeep.c13.pygls-timeout-diagnostic-review.v1",
                "driver": reference(Path(__file__)),
                "terminal_first_attempt": reason,
                "observer_sha256": first.digest(argv[-1].encode()),
                "execution_scope": "One reference-only call. Observe child timeout or missing events, retain the last required test when available, and preserve ordinary grade if the protected suite succeeds.",
                "explicit_repeat_approval_required": True,
                "ordinary_original_role_dispatch": False,
                "comparisons_paused": True,
                "waza_excluded": True,
            },
            spec,
            environment,
            [subject],
        )

    runner.review_fields = review_fields
    return reason, observations


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--exact-review")
    option = parser.parse_args()
    reason, observations = await prepare()
    runner = first.runner
    if not option.prepare:
        try:
            passed = await runner.run(option.exact_review)
        finally:
            if observations and runner.RUN.exists():
                runner.put(runner.RUN / "required-test-observations.json", observations)
        raise SystemExit(0 if passed else 1)
    if runner.REVIEW.exists() or runner.RUN.exists():
        raise ValueError("preserve the prepared diagnostic and any terminal attempt")
    scope, *_ = await runner.review_fields()
    runner.REVIEW.parent.mkdir(mode=0o700)
    runner.put(runner.REVIEW, scope | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    print(
        json.dumps(
            {
                "schema_version": "aeep.c13.pygls-reference-reconciliation.v1",
                "attempt": reason,
                "tested_diagnostic": {
                    "review": reference(runner.REVIEW),
                    "driver": reference(Path(__file__)),
                    "observer_sha256": scope["observer_sha256"],
                    "substituted_timeout_captured": True,
                    "maximum_operations": scope["maximum_operations"],
                    "maximum_reserved_seconds": scope["maximum_reserved_seconds"],
                    "state": "unapproved_unstarted",
                },
                "unchanged_software_pool": {
                    "source": reference(runner.HERE / "djpress-protected-result-20261118.json"),
                    "reproduced_rows": 50,
                    "repository_families": 29,
                    "minimum_missing_rows_if_all_eligible": 196,
                },
                "waza_excluded": True,
                "comparisons_paused": True,
                "new_model_turns": 0,
                "cash_usd": 0,
            },
            indent=2,
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
