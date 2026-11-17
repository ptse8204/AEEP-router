"""Rehearse all pyserde dispatch branches without building or running upstream code."""

import asyncio
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import check_pyserde_ordinary as driver

from aeep.models import RawExecution

SCENARIOS = {
    "matching": (5, True, ""),
    "reference_failed": (2, False, ""),
    "partial_passed": (5, False, ""),
    "build_failed": (1, False, ""),
    "wrong_required_identity": (2, False, "complete native observations"),
    "uncertain_cleanup": (2, False, "retain the reservation"),
    "no_approval": (0, False, "exact review approval is required"),
    "expired": (0, False, "drifted or expired"),
    "changed_binding": (0, False, "drifted or expired"),
}


async def exercise(path, scenario, expected):
    path.mkdir()
    operations = []
    with patch.multiple(
        driver,
        REVIEW=path / "review.json",
        APPROVAL=path / "approval.json",
        RUN=path / "run",
    ):
        record, _, _, _, _, truth, _ = await driver.inspect()
        if scenario == "changed_binding":
            record["calls"]["reference"]["archive_sha256"] = "0" * 64
        expiry = driver.utc_now() + driver.timedelta(hours=-1 if scenario == "expired" else 1)
        driver.put(driver.REVIEW, {**record, "expires_at": expiry.isoformat()})
        exact = driver.file_digest(driver.REVIEW)
        if scenario != "no_approval":
            driver.put(driver.APPROVAL, {"approved": True, "review_sha256": exact})
        actual_docker = driver.docker
        derived = "sha256:" + "a" * 64

        def docker(*args, **kwargs):
            if args[0] == "ps":
                return (
                    "synthetic-uncertain"
                    if scenario == "uncertain_cleanup" and len(operations) > 1
                    else ""
                )
            assert args[:2] in {("image", "inspect"), ("image", "ls")}
            return actual_docker(*args, **kwargs)

        async def build(_, ctx):
            assert ctx.spec.config["argv"] == record["build_spec"]["config"]["argv"]
            operations.append("build")
            if scenario == "build_failed":
                return RawExecution(status="failed", error_type="SYNTHETIC_BUILD_FAILURE")
            return RawExecution(status="success")

        async def container(executor, ctx):
            role = ctx.attempt_id.rsplit(":", 1)[1]
            assert executor.environment.container_image == derived
            operations.append(role)
            payload = ctx.request.input
            statuses = dict.fromkeys(truth.fail_to_pass + truth.pass_to_pass, "PASSED")
            passed = (role == "reference" and scenario != "reference_failed") or (
                role == "serialization_only" and scenario == "partial_passed"
            )
            if not passed:
                statuses[truth.fail_to_pass[0]] = "FAILED"
            if scenario == "wrong_required_identity":
                del statuses[truth.fail_to_pass[0]]
            reply = {key: payload[key] for key in ("python", "pytest", "archive_sha256")} | {
                "exit_code": 0 if passed else 1,
                "statuses": statuses,
            }
            return RawExecution(status="success", output=reply)

        count, verified, error = expected
        with (
            patch.object(driver, "docker", docker),
            patch.object(driver, "validate_image", return_value=derived),
            patch.object(driver.CommandExecutor, "execute", build),
            patch.object(driver.ContainerExecutor, "execute", container),
        ):
            try:
                assert await driver.run(exact) is verified
                assert (
                    not error
                    and driver.get(driver.RUN / "result.json")["formal_case_adopted"] is False
                )
            except (RuntimeError, ValueError) as exc:
                assert error and error in str(exc), (scenario, str(exc))
            if count:
                try:
                    await driver.run(exact)
                except (RuntimeError, ValueError) as exc:
                    assert "terminal or interrupted attempt exists" in str(exc), str(exc)
                else:
                    raise AssertionError("replayed a terminal or interrupted attempt")
        assert operations == ["build", *driver.ROLES][:count], (scenario, operations)
        if count:
            with driver.ReceiptStore(driver.RUN / "receipts.sqlite3", read_only=True) as store:
                state = dict(
                    store._connection.execute(
                        "SELECT state,count(*) FROM assessment_operations GROUP BY state"
                    ).fetchall()
                )
            assert state.get("complete", 0) == count - (scenario == "uncertain_cleanup")
            assert state.get("reserved", 0) == (scenario == "uncertain_cleanup")
        else:
            assert not driver.RUN.exists()
        return {"scenario": scenario, "dispatched_substitutes": count, "passed": True}


async def main():
    rows = []
    with TemporaryDirectory(prefix="driver-rehearsal-", dir=driver.PRIVATE) as directory:
        for scenario, expected in SCENARIOS.items():
            rows.append(await exercise(Path(directory) / scenario, scenario, expected))
    print(
        json.dumps(
            {
                "review_sha256": driver.file_digest(driver.REVIEW),
                "scenarios": rows,
                "upstream_executions": 0,
                "image_builds": 0,
                "model_turns": 0,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
