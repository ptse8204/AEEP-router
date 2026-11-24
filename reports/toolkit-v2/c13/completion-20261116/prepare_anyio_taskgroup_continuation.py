"""Bind a compatible Trio runtime for the ungraded AnyIO task-group case."""

import argparse
import asyncio
import json
import tomllib
from collections import Counter
from datetime import timedelta
from pathlib import Path

import check_anyio_taskgroup_contract as prior
from packaging.requirements import Requirement
from stage_repository_transport import digest, read, write

from aeep.models import utc_now
from aeep_toolkit.install_runtime import file_digest

WORK = prior.WORK / "trio-correction"
PARENT = "9a4b7a1bcc643944225fdb4d3c7d2bb1211671a233947b48bd60b22da17f40f6"
WHEEL_AUDIT = "2a1d68265fdd6d5af17c833e1dc686a0d91fd94eeb7dc31dab304e46494884d8"
NAME = prior.NAME + "-trio-031"
runner = prior.runner


def artifact(path):
    return {"path": path.relative_to(prior.ROOT).as_posix(), "sha256": file_digest(path)}


async def prepare(expires_at):
    old_review_path = prior.WORK / "operation-review.json"
    old_review = json.loads(read(old_review_path, PARENT))
    old = prior.WORK / "execution"
    result = runner.get(old / "result.json")
    (attempt,) = result["observations"]
    (charge,) = runner.get(old / "ledger.json")["operations"]
    receipt_path = old / f"receipt-{attempt['receipt_id']}.json"
    receipt = runner.get(receipt_path)
    reply = runner.get(old / "observation-reference.json")
    if (
        result["review_sha256"] != PARENT
        or result["verified"]
        or attempt["contract_matched"]
        or charge["operation_id"] != attempt["operation"]
        or receipt["action_id"] != attempt["operation"]
        or receipt["metadata"]["operation_review_sha256"] != PARENT
        or not receipt["metadata"]["container_absent"]
        or receipt["execution_success"]
        or charge["elapsed_seconds"] is None
        or reply["exit_code"] != 1
        or reply["archive_sha256"] != old_review["launches"][0]["archive_sha256"]
    ):
        raise ValueError("expected the same terminal reference observation and settled charge")
    nonpassing = {node: status for node, status in reply["statuses"].items() if status == "FAILED"}
    other = sorted(node for node in nonpassing if "[trio" not in node)
    if len(nonpassing) != 41 or other != [
        "tests/test_taskgroups.py::test_start_crash_before_started_call[asyncio]"
    ]:
        raise ValueError("the known failure signature changed")

    prior.configure()
    fields, spec, env, (case,) = await runner.review_fields()
    if fields != {k: v for k, v in old_review.items() if k != "expires_at"}:
        raise ValueError("the failed scope no longer reconstructs exactly")
    wheel_record = json.loads(read(WORK / "wheel-audit.json", WHEEL_AUDIT))
    public = prior.subject()[1]
    (dependency,) = tomllib.loads(public["pyproject.toml"].decode())["project"][
        "optional-dependencies"
    ]["trio"]
    requirement = Requirement(dependency)
    if (
        requirement.name != "trio"
        or "0.30.0" in requirement.specifier
        or "0.31.0" not in requirement.specifier
    ):
        raise ValueError("new wheel does not resolve the declared runtime mismatch")

    assets = prior.batch.assets
    pins = runner.get(prior.lowlevel.TARGET / "operation-review.json")["package_pins"]
    old_wheels, old_support = assets.WHEELS, assets.SUPPORT
    assets.WHEELS, assets.SUPPORT = WORK / "wheels", WORK / "support"
    for name, pin in pins.items():
        source = old_wheels / pin["filename"]
        if name == "trio":
            pin.update(
                version="0.31.0",
                filename=wheel_record["name"],
                sha256=wheel_record["sha256"],
                size=wheel_record["bytes"],
                url=wheel_record["url"],
            )
            source = WORK / pin["filename"]
        blob = read(source, pin["sha256"])
        destination = assets.WHEELS / pin["filename"]
        if not destination.exists():
            write(destination, blob)
        read(destination, pin["sha256"])
    support = assets.SUPPORT / "anyio"
    tree = assets.support_check("anyio", pins, prepare=not support.exists())
    argv = list(spec.config["argv"])
    old_root = str(old_support / "anyio")
    if argv[-1].count(old_root) != 2 or argv[-1].count("'trio': '0.30.0'") != 1:
        raise ValueError("protected grader bootstrap differs")
    argv[-1] = (
        argv[-1].replace(old_root, str(support)).replace("'trio': '0.30.0'", "'trio': '0.31.0'")
    )
    capture = (
        prior.batch.FROZEN / "integrations/assessment-runtime/repository_suite_native_capture.py"
    )
    diagnostic = Path(__file__).with_name("pytest_failure_diagnostics.py")
    hook = repr(capture.read_text())
    if argv[-1].count(hook) != 1 or argv[-1].count("assert set(native) == {'statuses'}") != 2:
        raise ValueError("native failure-report hook differs")
    decorated = capture.read_text() + "\n" + diagnostic.read_text()
    decorated += "\nNativeCapture = diagnostic_capture(NativeCapture)\n"
    argv[-1] = (
        argv[-1]
        .replace(hook, repr(decorated))
        .replace(
            "assert set(native) == {'statuses'}",
            "assert set(native) == {'statuses', 'failure_sites'}",
        )
    )
    compile(argv[-1], "<reviewed Trio-compatible observer>", "exec")
    spec = spec.model_copy(update={"config": spec.config | {"argv": argv}})
    env = env.model_copy(
        update={
            "environment_id": NAME,
            "read_only_roots": [
                str(support) if root == old_root else root for root in env.read_only_roots
            ],
        }
    )
    runner.NAME = NAME
    runner.definitions = lambda: (spec, env, [case])
    review, _, _, _ = await prior.BASE_FIELDS()
    for after, before in zip(review["launches"], old_review["launches"], strict=True):
        if any(
            after[key] != before[key]
            for key in ("archive_sha256", "payload_sha256", "payload_bytes", "required_tests")
        ):
            raise ValueError("the protected task or grading assertions changed")

    def score_reply(reply):
        return {key: value for key, value in reply.items() if key != "failure_sites"}

    def checked_reply(reply, payload, expected, code):
        if not isinstance(reply, dict) or not isinstance(reply.get("failure_sites"), list):
            return False
        runner.put(runner.RUN / f"observation-{'original' if code else 'reference'}.json", reply)
        return prior.BASE_VERIFY(score_reply(reply), payload, expected, code)

    runner.scorer_reply, runner.verify_probe = score_reply, checked_reply
    return review | {
        "wrapper_sha256": file_digest(Path(__file__)),
        "prior_review": artifact(old_review_path),
        "prior_ledger": artifact(old / "ledger.json"),
        "prior_receipt": artifact(receipt_path),
        "prior_observation": artifact(old / "observation-reference.json"),
        "settled_prior_seconds": charge["elapsed_seconds"],
        "reference_status_counts": dict(Counter(reply["statuses"].values())),
        "non_trio_failed_test": other[0],
        "runtime_requirement": str(requirement),
        "wheel_audit": artifact(WORK / "wheel-audit.json"),
        "sanitized_failure_capture": artifact(diagnostic),
        "package_pins": pins,
        "readonly_import_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
        "storage_floor_bytes": assets.FLOOR,
        "retry": False,
        "authority": "Prepared only. The reference repeat requires exact approval.",
        "expires_at": expires_at,
    }


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--execute")
    parser.add_argument("--approval", type=Path)
    args = parser.parse_args()
    if args.execute:
        if not args.approval:
            parser.error("--execute requires the exact approval record")
        current = json.loads(read(args.review, args.execute))
        review_path, approval_path, run_path = (
            args.review.resolve(),
            args.approval.resolve(),
            WORK / "execution",
        )

        async def revalidate():
            fields = await prepare(current["expires_at"])
            runner.REVIEW, runner.APPROVAL, runner.RUN = review_path, approval_path, run_path
            runner.review_fields = revalidate
            return fields, *runner.definitions()

        runner.review_fields = revalidate
        runner.REVIEW, runner.APPROVAL, runner.RUN = review_path, approval_path, run_path
        raise SystemExit(not await runner.run(args.execute))
    if args.approval:
        parser.error("--approval is only used with --execute")
    review = await prepare((utc_now() + timedelta(hours=24)).isoformat())
    encoded = (json.dumps(review, sort_keys=True, indent=2) + "\n").encode()
    write(args.review, encoded)
    print(digest(encoded))


if __name__ == "__main__":
    asyncio.run(main())
