"""Verify the adapted offline EOS reference and original with every required test."""

import argparse
import asyncio
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import check_eos_case_repair as diagnosis
import run_grader_repairs_20261120 as prior
from stage_repository_transport import HERE, ROOT, WORK, encode, write

from aeep.assessment.models import content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.models import utc_now
from aeep.store import ReceiptStore

TARGET = WORK / "c13-eos-repaired-pair-20261120"
REVIEW = TARGET / "operation-review.json"
RUNTIME = WORK / "c13-eos-runtime-inputs-20261120" / "runtime.json"
FIXTURE = HERE / "eos_recorded_price_fixture.py"
journal = prior.journal


def native_mapping(truth, inventory):
    ids = set(inventory)
    aliases, bound = {}, {}
    for group in ("fail_to_pass", "pass_to_pass"):
        output = []
        for original in truth[group]:
            matches = [original] if original in ids else []
            if not matches and "[" in original and "]" not in original.rsplit("[", 1)[1]:
                matches = sorted(test for test in ids if test.startswith(original + " "))
                aliases[original] = matches
            if not matches or (len(matches) > 1 and group != "pass_to_pass"):
                raise ValueError("a required test does not have an unambiguous grading role")
            output.extend(matches)
        bound[group] = output
    assert len(aliases) == 60 and sum(len(v) > 1 for v in aliases.values()) == 16
    all_bound = bound["pass_to_pass"] + bound["fail_to_pass"]
    if len(all_bound) != len(set(all_bound)):
        raise ValueError("a native identity was assigned twice")
    return aliases, bound


def observer(spec, selected):
    fixture = FIXTURE.read_text() + "\nNativeCapture = with_price_fixture(NativeCapture)\n"
    spec = diagnosis.observer(spec, selected, fixture)
    argv = list(spec.config["argv"])
    anchor = "';import pytest;assert pytest.__version__ == '"
    setup = (";sys.path.insert(0, '/opt/aeep-c13-eos-overlay');"
             "from importlib.metadata import version;"
             "assert version('scipy') == '1.14.1' and version('GitPython') == '3.1.44'")
    argv[-1] = prior.update_once(argv[-1], anchor, repr(setup) + "\n            + " + anchor)
    compile(argv[-1], "<EOS adaptation>", "exec")
    return spec.model_copy(update={"config": dict(spec.config, argv=argv)})


async def scope_fields():
    original = journal.doc(prior.eos.native.TARGET / "result.json")
    spec, environment, (case,) = prior.eos.definition(original)
    image = journal.doc(RUNTIME)["image"]
    docker, env = journal.docker_settings()
    assert journal.inspect(docker, env, image["id"]) == image and image["layers"][:-1] == original["image"]["layers"]
    environment = environment.model_copy(update={"container_image": image["id"]})
    facts = journal.doc(diagnosis.TARGET / "result.json")
    aliases, native = native_mapping(case["truth"], facts["native_ids"])
    case["truth"].update(native)
    scoped = {}
    for role in ("targeted", "reference", "original"):
        expected = prior.runner.expected_statuses(case["truth"], role)
        selected = sorted(facts["statuses"]) if role == "targeted" else sorted(expected)
        current = observer(spec, selected)

        async def capture(payload, expected=expected, selected=selected, role=role, current=current):
            executor, trial, pin = prior.launch("eos", "repair-" + role, environment, current, payload)
            scoped[role] = (executor, trial, pin, payload, expected, selected)
            return {key: payload[key] for key in ("archive_sha256", "python", "pytest")} | {
                "exit_code": int(role == "original"), "statuses": expected}

        await prior.ordinary(case, role, capture)
    files = [Path(__file__), Path(diagnosis.__file__), diagnosis.HOOK, FIXTURE, RUNTIME,
             diagnosis.TARGET / "result.json", diagnosis.TARGET / "ledger.json", prior.AUTHORITY]
    review = {
        "schema_version": "aeep.c13.eos-adapted-grader.v1",
        "frozen_source": verification_source_digest(prior.locify.VERIFIED_SOURCE),
        "files": {str(path.relative_to(ROOT)): journal.fingerprint(path) for path in files},
        "image": image, "aliases": aliases, "required_count": len(native["fail_to_pass"] + native["pass_to_pass"]),
        "case_sha256": content_digest(case),
        "launches": {role: item[2] | {"observer_sha256": content_digest(item[1].spec), "selected": item[5]}
                     for role, item in scoped.items()},
        "controls": "Select both native matches for each ambiguous preservation ID; keep every assertion.",
        "adapter": "Compatible pinned SciPy, publisher GitPython pin, and two scoped publisher-response replays.",
        "operator_authority": "C13 finite correction delegation and operator direction to continue correcting the grader.",
        "operations": 3, "reserved_seconds": 285, "models": 0, "cash_usd": 0, "retries": 0,
        "formal_adoption": False, "official_benchmark_reproduction": False,
    }
    return review, scoped, case


async def main(args):
    review, scoped, case = await scope_fields()
    if args.prepare:
        free = shutil.disk_usage(ROOT).free
        if free <= 768*2**20:
            raise ValueError("insufficient available space for scoped checks")
        write(REVIEW, encode(review | {"minimum_free_bytes": free - 768*2**20,
            "expires_at": (utc_now() + timedelta(hours=2)).isoformat()}))
        print(journal.fingerprint(REVIEW))
        return

    stored = journal.doc(REVIEW)
    expiry = datetime.fromisoformat(stored["expires_at"])
    if (utc_now() >= expiry or journal.fingerprint(REVIEW) != args.execute
            or stored != review | {key: stored[key] for key in ("expires_at", "minimum_free_bytes")}):
        raise ValueError("review differs or expired")
    write(TARGET / "started.json", encode({"review_sha256": args.execute}))
    diagnosis.REVIEW = REVIEW
    definition, auth, request = prior.prior.grant("eos-adapted-grader", args.execute, expiry, 3, 285)
    outcomes = {}
    with ReceiptStore(TARGET / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("c13_eos_adapted_grade_scope", content_digest(definition), definition)
        repo.approve_bundle(auth, {content_digest(definition): definition.model_dump(mode="json")})
        try:
            for role, (executor, trial, pin, payload, expected, selected) in scoped.items():
                raw, receipt = await diagnosis.run_checked(
                    repo, store, request, stored | {"launch": pin}, args.execute, executor, trial,
                )
                write(TARGET / f"{role}-receipt.json", encode(receipt.model_dump(mode="json")))
                outcome = outcomes[role] = {"receipt": receipt.receipt_id, "score": None}
                try:
                    output = diagnosis.validate(raw.output, payload, selected)
                except (ValueError, TypeError):
                    outcome["transport_error"] = raw.error_type or "invalid diagnostic response"
                    break
                write(TARGET / f"{role}-observations.json", encode(output))
                outcome.update(statuses={k: v for k, v in output["statuses"].items() if v != "PASSED"},
                    passed=sum(v == "PASSED" for v in output["statuses"].values()),
                    failures=output["failure_sites"], fixture_requests=output["fixture_requests"])
                fixtures = {name for name in selected if name.endswith(("::test_cache_integration", "::test_key_to_array_resampling"))}
                outcome["accepted"] = (sorted(output["fixture_requests"]) == sorted(fixtures)
                    and output["exit_code"] == int(role == "original")
                    and all(output["statuses"][test] == expected[test] for test in selected))
                if not outcome["accepted"]:
                    break
                if role == "targeted":
                    continue

                async def graded(current, payload=payload, output=output):
                    if current != payload:
                        raise ConfigurationError("protected grade payload drifted")
                    return {key: output[key] for key in ("archive_sha256", "python", "pytest", "exit_code", "statuses")}

                grade = await prior.ordinary(case, role, graded)
                assert grade.quality_score == (0 if role == "original" else 1)
                outcome["score"] = grade.quality_score
        finally:
            write(TARGET / "ledger.json", encode(repo.operation_ledger(auth.authorization_id).model_dump(mode="json")))
            write(TARGET / "result.json", encode(outcomes))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--execute")
    asyncio.run(main(parser.parse_args()))
