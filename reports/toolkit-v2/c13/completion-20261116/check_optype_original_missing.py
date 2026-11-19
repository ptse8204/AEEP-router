"""Reconcile Optype's saved observations and prepare an original-only protected repeat."""

import argparse
import asyncio
import json
from datetime import timedelta
from pathlib import Path

import check_optype_protected_pair as pair
from acquire_full_rebench_leads import TARGET, ref
from stage_repository_transport import encode, read, write

from aeep.assessment.repository_suites import grade_suite_output
from aeep.models import utc_now

DRIVER = Path(__file__).resolve()
PAIR_DRIVER = Path(pair.__file__).resolve()
runner = pair.runner
DIRECTORY = TARGET / "optype-original-only"
PRIOR_REVIEW = "2e0c1538c3220a2c262c39170c4eecedea1abdfff801d53ab8d3b004bd6f557e"


def accepts_absent_issue(reply, payload, expected, code):
    preserved = {node: status for node, status in expected.items() if status == "PASSED"}
    issues = expected.keys() - preserved.keys()
    return (
        code == 1
        and len(preserved) == 404
        and len(issues) == 12
        and pair.BASE_PROBE(reply, payload, preserved, 0)
        and not issues.intersection(reply["statuses"])
    )


async def prepare_case():
    prior = json.loads(read(pair.DIRECTORY / "operation-review.json", PRIOR_REVIEW))
    original_launch = next(launch for launch in prior["launches"] if launch["operation"].endswith(":original"))
    execution = pair.DIRECTORY / "execution"
    result_path = execution / "result.json"
    history = json.loads(result_path.read_bytes())
    reference, original = history["observations"]
    observations_path = execution / "required-test-observations.json"
    required = json.loads(observations_path.read_bytes())
    original_record = required[1]
    receipt_paths = [execution / f"receipt-{record['receipt_id']}.json" for record in (reference, original)]
    settled = json.loads((execution / "ledger.json").read_bytes())["operations"]
    if (
        history["review_sha256"] != PRIOR_REVIEW
        or reference.get("score") != 1.0
        or not reference["contract_matched"]
        or original["contract_matched"]
        or "score" in original
        or required[0]["required_status_counts"] != {"PASSED": 416}
        or original_record["required_status_counts"] != {"PASSED": 404, "MISSING": 12}
        or original_record["pytest_exit"] != 0
        or original_record["archive_sha256"] != original_launch["archive_sha256"]
        or {row["operation_id"] for row in settled} != {reference["operation"], original["operation"]}
        or any(row["elapsed_seconds"] is None for row in settled)
    ):
        raise ValueError("saved original/reference stage did not settle as expected")
    for path in receipt_paths:
        receipt = json.loads(path.read_bytes())
        if (
            receipt["metadata"]["operation_review_sha256"] != PRIOR_REVIEW
            or receipt["metadata"]["container_absent"] is not True
        ):
            raise ValueError("retained receipt does not bind to the completed scope")

    pair.configure([])
    spec, environment, cases = runner.definitions()
    (entry,) = cases
    truth = entry["truth"]
    expected = runner.expected_statuses(truth, "original")
    missing = {node for node, status in expected.items() if status == "FAILED"}
    if set(row["test"] for row in original_record["differences"]) != missing or any(
        row["observed"] != "MISSING" or row["expected"] != "FAILED"
        for row in original_record["differences"]
    ):
        raise ValueError("retained projection differs from the exact issue nodes")

    async def read_only_probe(payload):
        if runner.content_digest(payload) != original_launch["payload_sha256"]:
            raise ValueError("saved observations belong to different grader input")
        projected = {
            **{key: payload[key] for key in ("archive_sha256", "python", "pytest")},
            "exit_code": original_record["pytest_exit"],
            "statuses": {node: status for node, status in expected.items() if node not in missing},
        }
        changes = (
            projected | {"exit_code": 1},
            projected | {"archive_sha256": "0" * 64},
            projected | {"statuses": {}},
            projected | {"statuses": projected["statuses"] | dict.fromkeys(missing, "SKIPPED")},
        )
        if not accepts_absent_issue(projected, payload, expected, 1) or any(
            accepts_absent_issue(altered, payload, expected, 1) for altered in changes
        ):
            raise ValueError("original-only observer guard differs")
        return projected

    replay = await grade_suite_output(entry["input"], truth, entry["roles"]["original"], read_only_probe)
    if replay.valid or replay.quality_score != 0 or replay.detail != "missing_test":
        raise ValueError("ordinary grader did not reject the saved required-node projection")
    evidence = {
        "type": "read_only_required_status_projection",
        "new_grader_invocations": 0,
        "not_a_new_live_receipt": True,
        "result": replay.model_dump(mode="json"),
        "prior_review": ref(pair.DIRECTORY / "operation-review.json"),
        "prior_evidence": [
            ref(path)
            for path in (result_path, observations_path, execution / "ledger.json", *receipt_paths)
        ],
    }
    runner.NAME = "c13-optype-original-missing-20261119"
    runner.ROLES = ("original",)
    runner.MAX_CALLS = 1
    runner.REVIEW = DIRECTORY / "operation-review.json"
    runner.APPROVAL = DIRECTORY / "approval.json"
    runner.RUN = DIRECTORY / "execution"
    runner.verify_probe = accepts_absent_issue

    async def review_fields():
        fields, *_ = await pair.BASE_REVIEW()
        (launch,) = fields["launches"]
        if (
            launch["archive_sha256"] != original_launch["archive_sha256"]
            or launch["payload_sha256"] != original_launch["payload_sha256"]
            or fields["observer_fingerprint"] != prior["observer_fingerprint"]
            or fields["carrier_layers"] != prior["carrier_layers"]
            or fields["environment"] != prior["environment"]
        ):
            raise ValueError("retry would change the protected inputs or carrier")
        return (
            fields | {
                "schema_version": "aeep.c13.optype-original-missing.v1",
                "driver": ref(DRIVER),
                "prior_driver": ref(PAIR_DRIVER),
                "accepted_original_observation": "pytest exit 0, exactly twelve required issue nodes absent, all 404 required preservation nodes passed",
                "expected_canonical_grade_reason": "missing_test",
                "read_only_projection": evidence,
                "reference_replay": False,
                "comparisons_paused": True,
                "waza_excluded": True,
            },
            spec, environment, cases,
        )

    runner.review_fields = review_fields
    return evidence


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    projection = await prepare_case()
    if args.prepare:
        fields, *_ = await runner.review_fields()
        DIRECTORY.mkdir(mode=0o700, exist_ok=True)
        write(DIRECTORY / "saved-observation-reconciliation.json", encode(projection))
        write(runner.REVIEW, encode(fields | {"expires_at": (utc_now() + timedelta(days=7)).isoformat()}))
        print(runner.file_digest(runner.REVIEW))
    else:
        raise SystemExit(0 if await runner.run(args.exact_review) else 1)


if __name__ == "__main__":
    asyncio.run(main())
