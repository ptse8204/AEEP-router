"""Complete the protected Skelebot pair after the observed metadata error."""

import argparse
import asyncio
import json
import shutil
import time
import tomllib
from datetime import datetime, timedelta
from pathlib import Path

import check_retained_carrier_batch as batch
from stage_repository_transport import digest, read, write

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import SuiteTruthV6, archive_files, grade_suite_output
from aeep.models import ExecutionReceipt, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

runner = batch.runner
VERIFY = runner.verify_probe
KEY = "skelebot"
TARGET = batch.WORK / KEY
ATTEMPT = TARGET / "execution"
CORRECTION = TARGET / "with-compatible-artifactory"
META = TARGET / "package-metadata"
NEW_ARTIFACT = "e15bb76dcc0afe5e6aa6fb74cff24a6638638489ea735b88b82a67984e4ec4a1"


def metadata(truth, *, prepare=False):
    public = archive_files(SuiteTruthV6.model_validate(truth).source.read(), large=True)
    declared = tomllib.loads(public["pyproject.toml"].decode())["project"]
    version = public["VERSION"].decode().strip()
    if (
        declared["name"] != KEY
        or version != "2.1.1"
        or 'metadata.version("skelebot")' not in public["skelebot/common.py"].decode()
    ):
        raise ValueError("project metadata interface differs")
    payload = (
        f"Metadata-Version: 2.1\nName: {KEY}\nVersion: {version}\n"
        f"Requires-Python: {declared['requires-python']}\n"
        + "".join(f"Requires-Dist: {require}\n" for require in declared["dependencies"])
        + "\n"
    ).encode()
    path = META / f"{KEY}-{version}.dist-info" / "METADATA"
    if prepare and not path.exists():
        write(path, payload)
        path.chmod(0o444)
    read(path, digest(payload))
    if (
        path.stat().st_mode & 0o777 != 0o444
        or list(META.rglob("METADATA")) != [path]
        or any(p.is_symlink() or (p.is_file() and p != path) for p in META.rglob("*"))
    ):
        raise ValueError("metadata-only projection changed")
    return digest(payload)


async def plan(expires, *, prepare=False):
    diagnostic = TARGET / "diagnostic"
    prior = runner.get(diagnostic / "result.json")
    previous = runner.get(diagnostic / "ledger.json")
    if (
        prior["observations"]
        != {"exit_code": 2, "classes": ["PackageNotFoundError"], "collection_emitted": True}
        or prior["grade"]
        or len(previous["operations"]) != 2
        or any(item["elapsed_seconds"] is None for item in previous["operations"])
    ):
        raise ValueError("settled package metadata diagnostic differs")
    startup = TARGET / "startup"
    old = runner.get(startup / "result.json")
    if (
        old["grade"]
        or old["observations"]["class"] != "AttributeError"
        or old["observations"]["sites"][-1] != ["dependency", "artifactory.py", 425]
    ):
        raise ValueError("the recorded Python 3.13 incompatibility changed")
    previous = runner.get(startup / "ledger.json")
    if len(previous["operations"]) != 5 or any(
        item["elapsed_seconds"] is None for item in previous["operations"]
    ):
        raise ValueError("earlier operations are not fully settled")
    original = runner.get(TARGET / "operation-review.json")
    batch.assets.SUPPORT = batch.WORK / "support"
    pins = original["package_pins"]
    tree = batch.assets.support_check(KEY, batch.import_only_pins(KEY, pins))
    if (
        digest(json.dumps(tree, sort_keys=True).encode())
        != original["read_only_import_tree_sha256"]
    ):
        raise ValueError("retained dependencies changed")
    faults, case = batch.cases()[KEY]
    batch.configure(KEY, case, faults, pins)
    metadata_sha = metadata(case["truth"], prepare=prepare)
    first, env, _ = runner.definitions()
    if (
        content_digest(first) != original["observer_fingerprint"]
        or env.model_dump(mode="json") != original["environment"]
    ):
        raise ValueError("first-attempt runtime was changed")
    manifest = runner.get(TARGET / "artifactory-compatibility-acquisition.json")
    if manifest["sha256"] != NEW_ARTIFACT or manifest["version"] != "1.0.2":
        raise ValueError("the replacement publisher wheel pin changed")
    imports = TARGET / "compatible-libraries"
    replacement = dict(batch.import_only_pins(KEY, pins))
    replacement["dohq-artifactory"] = manifest | {"name": "dohq-artifactory"}
    for name, pin in replacement.items():
        source = (
            TARGET / "compatibility-wheels" if name == "dohq-artifactory" else batch.assets.WHEELS
        ) / pin["filename"]
        body = read(source, pin["sha256"])
        staged = imports / pin["filename"]
        if prepare and not staged.exists():
            write(staged, body)
        read(staged, pin["sha256"])
    batch.assets.WHEELS = imports
    batch.assets.SUPPORT = TARGET / "compatibility-support"
    tree = batch.assets.support_check(
        KEY, replacement, prepare=prepare and not (batch.assets.SUPPORT / KEY).exists()
    )
    argv = list(first.config["argv"])
    argv[-1] = batch.observer(KEY, replacement)
    start = "            + ';import pytest;"
    if argv[-1].count(start) != 1:
        raise ValueError("native observer boundary changed")
    extra = f";sys.path.insert(0,{str(META)!r});assert version('skelebot')=='2.1.1'"
    argv[-1] = argv[-1].replace(start, "            + " + repr(extra) + "\n" + start)
    spec = first.model_copy(update={"config": first.config | {"argv": argv}})
    env = env.model_copy(update={"read_only_roots": [str(batch.assets.SUPPORT / KEY), str(META)]})
    executor = ContainerExecutor(env)
    launches, actions = [], []
    for index, role in enumerate(("reference", "original")):
        expected = runner.expected_statuses(case["truth"], role)

        async def capture(payload, role=role, index=index, expected=expected):
            if content_digest(payload) != original["launches"][index]["payload_sha256"]:
                raise ValueError("protected payload differs from the initial review")
            action = runner.context(spec, f"{runner.NAME}:compatible:{role}", payload)
            command, owner = executor.command(action)
            mounts = {
                f"type=bind,src={path},dst={path},readonly"
                for path in (
                    str(batch.FROZEN / "src"),
                    *env.read_only_roots,
                )
            }
            if {arg for arg in command if arg.startswith("type=bind,")} != mounts or (
                command[command.index("--network") + 1] != "none"
                or command[command.index("--user") + 1] != "65534:65534"
                or not {
                    "--pull=never",
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                }
                <= set(command)
            ):
                raise ValueError("metadata projection escaped its isolated boundary")
            actions.append(action)
            launches.append(
                {
                    "role": role,
                    "container": owner,
                    "action": action.request.action_id,
                    "argv_sha256": content_digest({"argv": command}),
                    "payload_sha256": content_digest(payload),
                }
            )
            return {k: payload[k] for k in ("archive_sha256", "python", "pytest")} | {
                "exit_code": int(role == "original"),
                "statuses": expected,
            }

        rehearsed = await grade_suite_output(
            case["input"], case["truth"], case["roles"][role], capture
        )
        if rehearsed.quality_score != int(role == "reference"):
            raise ValueError("ordinary correction contract differs")
    return (
        {
            "driver_sha256": file_digest(Path(__file__)),
            "parent_sha256": file_digest(TARGET / "operation-review.json"),
            "diagnostic_result_sha256": file_digest(diagnostic / "result.json"),
            "diagnostic_ledger_sha256": file_digest(diagnostic / "ledger.json"),
            "metadata_sha256": metadata_sha,
            "replacement_wheel_sha256": NEW_ARTIFACT,
            "new_import_tree_sha256": digest(json.dumps(tree, sort_keys=True).encode()),
            "startup_result_sha256": file_digest(startup / "result.json"),
            "startup_ledger_sha256": file_digest(startup / "ledger.json"),
            "environment": env.model_dump(mode="json"),
            "observer": content_digest(spec),
            "launches": launches,
            "expires_at": expires,
            "additional_operations": 2,
            "additional_reserved_seconds": 100,
            "retries": 0,
            "downloads": 0,
            "installations": 0,
            "models": 0,
            "cash_usd": 0,
            "provider_disclosure": False,
        },
        case,
        executor,
        actions,
        previous,
    )


async def execute(
    exact,
    review,
    case,
    executor,
    actions,
    previous,
    *,
    target=TARGET,
    correction=CORRECTION,
    budget_predecessor=":startup:budget",
):
    if (correction / "started.json").exists() or shutil.disk_usage(
        target
    ).free < batch.assets.FLOOR:
        raise ValueError("correction already started or host space below the reserve")
    started = datetime.fromisoformat(review["expires_at"])
    if started <= utc_now():
        raise ValueError("review expired")
    outcomes = {}
    used = len(previous["operations"])
    if len(actions) != 2 or any(
        operation["elapsed_seconds"] is None for operation in previous["operations"]
    ):
        raise ValueError("paired continuation requires two new roles and settled prior operations")
    amendment_id = f"{runner.NAME}:{correction.name}"
    with ReceiptStore(target / "execution" / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        grant = AssessmentAuthorization.model_validate(repo.get("authorization", runner.NAME))
        if (
            repo.operation_ledger(runner.NAME).model_dump(mode="json") != previous
            or repo.current_grant(runner.NAME).limits
            != AssessmentLimits(max_operations=used, max_elapsed_seconds=used * 50)
            or grant.remote_disclosure
            or grant.allowed_destinations != ["local"]
            or grant.limits != AssessmentLimits(max_operations=2, max_elapsed_seconds=100)
        ):
            raise ValueError("parent ledger or limits drifted")
        (old,) = grant.subject_digests
        scope = runner.Scope(review_sha256=exact)
        new = content_digest(scope)
        repo.put("c13_retained_pair_continuation_scope", new, scope)
        repo.approve_bundle(
            AssessmentScopeAmendment(
                amendment_id=amendment_id + ":scope",
                authorization_id=runner.NAME,
                authorization_digest=content_digest(grant),
                subject_digests=[old],
                recipe_digests=[old],
                environment_digests=[old],
                reviewed_digests=[new],
            ),
            {
                old: repo.get("c13_cached_repository_pair_scope", old),
                new: scope.model_dump(mode="json"),
            },
            budget_amendment=AssessmentBudgetAmendment(
                authorization_id=runner.NAME,
                amendment_id=amendment_id + ":budget",
                authorization_digest=content_digest(grant),
                previous_amendment_digest=content_digest(
                    repo.get("budget_amendment", runner.NAME + budget_predecessor)
                ),
                expires_at=started,
                limits=AssessmentLimits(
                    max_operations=used + 2, max_elapsed_seconds=(used + 2) * 50
                ),
            ),
        )
        request = RecipeMaterializationRequest(
            plan_id=runner.NAME,
            authorization_id=runner.NAME,
            subject_digest=old,
            recipe_digest=old,
            environment_digest=old,
            mapping_digest=old,
            definition_digests=[old, new],
            seed=0,
        )
        runner.put(correction / "started.json", {"review_sha256": exact})
        try:
            for launch, action in zip(review["launches"], actions, strict=True):
                role = launch["role"]
                operation, owner = action.request.action_id, launch["container"]
                if (
                    runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$")
                    or shutil.disk_usage(target).free < batch.assets.FLOOR
                ):
                    raise ValueError("container ownership or disk availability changed")
                expected = runner.expected_statuses(case["truth"], role)
                repo.reserve(
                    request,
                    operation,
                    AssessmentLimits(max_operations=1, max_elapsed_seconds=50),
                    stage="protected_retained_pair_continuation",
                    require_settled_plan=True,
                )
                started, watch = utc_now(), time.monotonic()
                raw = await executor.execute(action)
                if runner.docker("ps", "-aq", "--filter", f"name=^/{owner}$"):
                    raise RuntimeError("owned correction container is not verified absent")
                observed = raw.output if isinstance(raw.output, dict) else None
                complete = raw.status.value == "success" and VERIFY(
                    observed, action.request.input, expected, int(role == "original")
                )
                receipt = ExecutionReceipt(
                    decision_id=operation,
                    action_id=operation,
                    capability=action.spec.capability,
                    executor_id=action.spec.id,
                    executor_kind=action.spec.kind,
                    estimated=action.estimate,
                    started_at=started,
                    ended_at=utc_now(),
                    status="success" if complete else "failed",
                    execution_success=complete,
                    actual_resources=raw.resources,
                    error_type=None if complete else raw.error_type or "OBSERVATION_MISMATCH",
                    metadata={
                        "container_absent": True,
                        "review_sha256": exact,
                        "observation_sha256": content_digest(observed)
                        if observed is not None
                        else None,
                    },
                )
                store.save_receipt(receipt)
                repo.finish_operation(
                    operation, elapsed_seconds=time.monotonic() - watch, resources=raw.resources
                )
                runner.put(correction / f"receipt-{role}.json", receipt.model_dump(mode="json"))
                outcomes[role] = {
                    "receipt_id": receipt.receipt_id,
                    "grade": None,
                    "observation": observed,
                }
                if not complete:
                    break

                async def candidate(payload, action=action, observed=observed):
                    if content_digest(payload) != content_digest(action.request.input):
                        raise ValueError(
                            "settled observation does not bind to the ordinary payload"
                        )
                    return observed

                outcome = await grade_suite_output(
                    case["input"], case["truth"], case["roles"][role], candidate
                )
                if outcome.quality_score != int(role == "reference"):
                    raise ValueError("ordinary grader verdict differs")
                outcomes[role]["grade"] = outcome.quality_score
        finally:
            await executor.close()
            runner.put(
                correction / "ledger.json",
                repo.operation_ledger(runner.NAME).model_dump(mode="json"),
            )
    complete = set(outcomes) == {"reference", "original"} and all(
        row["grade"] is not None for row in outcomes.values()
    )
    runner.put(
        correction / "result.json",
        {"verified": complete, "review_sha256": exact, "observations": outcomes},
    )
    return complete


async def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--prepare", action="store_true")
    modes.add_argument("--execute")
    args = parser.parse_args()
    path = CORRECTION / "review-compatible-artifactory.json"
    old = None if args.prepare else json.loads(read(path, args.execute))
    parent_expiry = datetime.fromisoformat(
        runner.get(TARGET / "with-metadata/review-preserve-expiry.json")["expires_at"]
    )
    expires = (
        max(utc_now() + timedelta(hours=3), parent_expiry).isoformat()
        if old is None
        else old["expires_at"]
    )
    review, *context = await plan(expires, prepare=args.prepare)
    if args.prepare:
        CORRECTION.mkdir(mode=0o700, exist_ok=True)
        runner.put(path, review)
        print(file_digest(path))
    else:
        if review != old:
            raise ValueError("exact reviewed correction changed")
        raise SystemExit(not await execute(args.execute, review, *context))


if __name__ == "__main__":
    asyncio.run(main())
