"""Check the ordinary reference and grader commands on the retained Linux carrier."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import DOCKER, FROZEN, WORK, Scope, docker, get, put, verified_image
from prepare_economic_recipe import BUILDER, CORRECTED, HERE, OUT, definitions

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-economic-ordinary-20261116"
REVIEW = HERE / "economic-ordinary-operation-review.json"
APPROVAL = WORK / "economic-ordinary-approval.json"
RESULT = WORK / "economic-ordinary-execution"
RESERVE = 52 * 1024**3
CONTINUATION = HERE / "economic-ordinary-continuation-review.json"
CONTINUATION_APPROVAL = WORK / "economic-ordinary-continuation-approval.json"
CONTINUATION_RESULT = WORK / "economic-ordinary-continuation-execution"


def prepared(*, continuation=False):
    draft = CORRECTED if continuation else OUT
    recipe, environment, cases, examples, codes = definitions(inline=continuation)
    if any(
        get(draft / f"{name}.json") != model.model_dump(mode="json")
        for name, model in (("recipe", recipe), ("environment", environment), ("case-set", cases))
    ):
        raise ValueError("prepared ordinary definitions changed")
    assert recipe.extension is not None
    commands = [
        ("reference", recipe.extension.reference, {"inputs": [examples[0]["input"]]},
         {"outputs": [examples[0]["output"]]}),
        *[(f"grade-{index:02d}", recipe.extension.grader, {"examples": [example]},
           {"valid": [code is None], "failure_codes": [code]})
          for index, (example, code) in enumerate(zip(examples, codes, strict=True))],
    ]
    executor = ContainerExecutor(environment)
    launches = []
    operations = []
    for label, spec, payload, expected in commands[1:] if continuation else commands:
        if continuation:
            label = "retry-" + label
        operation = NAME + ":" + label
        context = ExecutionContext(
            request=ActionRequest(action_id=operation, capability=spec.capability, input=payload),
            spec=spec,
            estimate=spec.estimate,
            attempt=1,
            attempt_id=operation,
            approved_side_effect=spec.side_effect,
        )
        argv, container = executor.command(context)
        mounts = {arg for arg in argv if arg.startswith("type=bind,")}
        root = FROZEN / "src"
        if (
            mounts != {f"type=bind,src={root},dst={root},readonly"}
            or argv[argv.index("--network") + 1] != "none"
            or argv[argv.index("--user") + 1] != "65534:65534"
            or not {"--read-only", "--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges"} <= set(argv)
        ):
            raise ValueError("ordinary recipe escaped its reviewed boundary")
        seconds = spec.config["timeout_seconds"] + 5
        operations.append((context, expected, container, seconds))
        launches.append({
            "operation": operation, "launch": argv, "container": container,
            "executor_sha256": content_digest(spec),
            "payload_sha256": content_digest(payload), "expected_sha256": content_digest(expected),
            "expected_grader_code": (expected.get("failure_codes") or [None])[0],
            "reserved_seconds": seconds,
        })
    review = {
        "purpose": "Check pinned ordinary economic reference and grader with one correct artifact and eight controls.",
        "source": verification_source_digest(FROZEN),
        "docker_sha256": file_digest(Path(DOCKER)),
        "image_layers": verified_image(),
        "files": {
            str(path.relative_to(HERE.parents[3])): file_digest(path)
            for path in (Path(__file__), HERE / "prepare_economic_recipe.py",
                         HERE / "economic_recipe_guest.py", BUILDER, *sorted(draft.glob("*.json")))
        },
        "operations": launches,
        "maximum_operations": len(operations),
        "maximum_reserved_seconds": sum(item[3] for item in operations),
        "models": 0,
        "cash_usd": 0,
        "retries": 0,
        "provider_disclosure": False,
        "formal_stage": False,
    }
    if continuation:
        prior = get(RESULT / "result.json")
        ledger = get(RESULT / "ledger.json")
        root_approval = file_digest(REVIEW)
        if (
            prior["review_sha256"] != root_approval or prior["verified"]
            or [item["contract_matched"] for item in prior["observations"]] != [True, False]
            or len(ledger["operations"]) != 2
            or any(item["elapsed_seconds"] is None for item in ledger["operations"])
        ):
            raise ValueError("continuation requires the exact settled two-operation outcome")
        review.update(
            purpose="Continue one corrected grader and eight unstarted controls. Reuse the verified reference.",
            parent_review_sha256=root_approval,
            parent_result_sha256=file_digest(RESULT / "result.json"),
            parent_ledger_sha256=file_digest(RESULT / "ledger.json"),
            cumulative_maximum_operations=11,
            cumulative_maximum_reserved_seconds=260,
        )
    return review, recipe, executor, operations


def prepare(*, continuation=False):
    destination = CONTINUATION if continuation else REVIEW
    if continuation:
        recipe, environment, cases, _examples, _codes = definitions(inline=True)
        CORRECTED.mkdir(mode=0o700)
        for name, model in (("recipe", recipe), ("environment", environment), ("case-set", cases)):
            put(CORRECTED / f"{name}.json", model.model_dump(mode="json"))
    review, _recipe, _executor, _operations = prepared(continuation=continuation)
    expiry = get(REVIEW)["expires_at"] if continuation else (utc_now() + timedelta(days=7)).isoformat()
    put(destination, {**review, "expires_at": expiry})
    print(file_digest(destination))


async def run(exact, *, continuation=False):
    review_path = CONTINUATION if continuation else REVIEW
    approval = CONTINUATION_APPROVAL if continuation else APPROVAL
    output = CONTINUATION_RESULT if continuation else RESULT
    if (
        file_digest(review_path) != exact or output.exists()
        or not approval.is_file()
        or get(approval) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("this exact unstarted runtime check requires operator approval")
    record = get(review_path)
    expires = datetime.fromisoformat(record.pop("expires_at"))
    checked, recipe, executor, operations = prepared(continuation=continuation)
    if record != checked or expires <= utc_now() or shutil.disk_usage(WORK).free < RESERVE:
        raise ValueError("reviewed definitions, image, authority or storage changed")

    output.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    initial = Scope(review_sha256=record["parent_review_sha256"]) if continuation else scope
    root_ref = content_digest(initial)
    request = RecipeMaterializationRequest(
        plan_id=NAME, authorization_id=NAME, subject_digest=root_ref, recipe_digest=root_ref,
        environment_digest=root_ref, mapping_digest=root_ref, definition_digests=[root_ref, ref], seed=0,
    )
    grant = AssessmentAuthorization(
        authorization_id=NAME, subject_digests=[ref], recipe_digests=[ref],
        environment_digests=[ref], allowed_destinations=["local"], expires_at=expires,
        remote_disclosure=False, limits=AssessmentLimits(
            max_operations=record["maximum_operations"],
            max_elapsed_seconds=record["maximum_reserved_seconds"], max_model_turns=0,
        ),
    )
    observations = []
    with ReceiptStore(RESULT / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("economic_ordinary_scope", ref, scope)
        if continuation:
            root = AssessmentAuthorization.model_validate(repo.get("authorization", NAME))
            old = get(RESULT / "ledger.json")
            if (
                repo.effective_grant(NAME) != root
                or repo.operation_ledger(NAME).model_dump(mode="json") != old
                or expires != root.expires_at
                or root.limits.max_model_turns or root.limits.max_cash_usd
                or root.allowed_destinations != ["local"] or root.remote_disclosure
                or root.limits.max_operations + 1 != record["cumulative_maximum_operations"]
                or root.limits.max_elapsed_seconds != record["cumulative_maximum_reserved_seconds"]
            ):
                raise ValueError("continuation must preserve the original ledger and ceilings")
            amend = AssessmentScopeAmendment(
                amendment_id=NAME + ":inline", authorization_id=NAME,
                authorization_digest=content_digest(root), subject_digests=[root_ref],
                recipe_digests=[root_ref], environment_digests=[root_ref], reviewed_digests=[ref],
            )
            limit = AssessmentBudgetAmendment(
                amendment_id=NAME + ":one-operation", authorization_id=NAME,
                authorization_digest=content_digest(root), expires_at=expires,
                limits=AssessmentLimits(
                    max_operations=record["cumulative_maximum_operations"],
                    max_elapsed_seconds=root.limits.max_elapsed_seconds, max_model_turns=0,
                ),
            )
            repo.approve_bundle(amend, {
                root_ref: initial.model_dump(mode="json"), ref: scope.model_dump(mode="json"),
            }, budget_amendment=limit)
        else:
            repo.approve_bundle(grant, {ref: scope.model_dump(mode="json")})
        for context, expected, container, seconds in operations:
            operation = context.request.action_id
            name_filter = f"name=^/{container}$"
            if docker("ps", "-aq", "--filter", name_filter) or shutil.disk_usage(WORK).free < RESERVE:
                raise RuntimeError("contained worker not fresh or host reserve unavailable")
            repo.reserve(
                request, operation,
                AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds, max_model_turns=0),
                stage="ordinary_economic_recipe", require_settled_plan=True,
            )
            started, clock = utc_now(), time.monotonic()
            raw = await executor.execute(context)
            if docker("ps", "-aq", "--filter", name_filter):
                raise RuntimeError("uncertain worker cleanup; preserve the reservation")
            matched = raw.status.value == "success" and raw.output == expected
            if matched and "valid" in expected:
                assert recipe.extension is not None
                grader_results(raw.output, recipe.extension, 1)
            metadata = {
                "review_sha256": exact, "contract_matched": matched, "container_absent": True,
                "expected_sha256": content_digest(expected),
                "matched_grader_code": (expected.get("failure_codes") or [None])[0] if matched else None,
            }
            receipt = ExecutionReceipt(
                decision_id=operation, action_id=operation, capability=context.spec.capability,
                executor_id=context.spec.id, executor_kind=context.spec.kind,
                status="success" if matched else "failed", execution_success=matched,
                started_at=started, ended_at=utc_now(), estimated=context.estimate,
                actual_resources=raw.resources,
                error_type=None if matched else "ECONOMIC_RECIPE_CONTRACT_MISMATCH",
                metadata=metadata,
            )
            store.save_receipt(receipt)
            repo.finish_operation(operation, elapsed_seconds=time.monotonic() - clock, resources=raw.resources)
            row = {"operation": operation, "receipt_id": receipt.receipt_id, **metadata}
            put(output / f"{operation.split(':')[-1]}.json", row)
            observations.append(row)
            if not matched:
                break
        put(output / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    verified = len(observations) == len(operations) and all(row["contract_matched"] for row in observations)
    put(output / "result.json", {"review_sha256": exact, "verified": verified, "observations": observations, "models": 0, "cash_usd": 0})
    return verified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--prepare-continuation", action="store_true")
    mode.add_argument("--exact-review")
    mode.add_argument("--continue-review")
    args = parser.parse_args()
    if args.prepare or args.prepare_continuation:
        prepare(continuation=args.prepare_continuation)
    else:
        raise SystemExit(not asyncio.run(run(args.exact_review or args.continue_review, continuation=bool(args.continue_review))))
