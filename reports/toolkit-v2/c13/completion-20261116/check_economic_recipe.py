"""Check the ordinary reference and grader commands on the retained Linux carrier."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

from check_linux_install import DOCKER, FROZEN, WORK, Scope, docker, get, put, verified_image
from prepare_economic_recipe import BUILDER, HERE, OUT, definitions

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentLimits,
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


def prepared():
    recipe, environment, cases, examples, codes = definitions()
    if any(
        get(OUT / f"{name}.json") != model.model_dump(mode="json")
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
    for label, spec, payload, expected in commands:
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
                         HERE / "economic_recipe_guest.py", BUILDER, *sorted(OUT.glob("*.json")))
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
    return review, recipe, executor, operations


def prepare():
    review, _recipe, _executor, _operations = prepared()
    put(REVIEW, {**review, "expires_at": (utc_now() + timedelta(days=7)).isoformat()})
    print(file_digest(REVIEW))


async def run(exact):
    if (
        file_digest(REVIEW) != exact or RESULT.exists()
        or not APPROVAL.is_file()
        or get(APPROVAL) != {"approved": True, "review_sha256": exact}
    ):
        raise ValueError("this exact unstarted runtime check requires operator approval")
    record = get(REVIEW)
    expires = datetime.fromisoformat(record.pop("expires_at"))
    checked, recipe, executor, operations = prepared()
    if record != checked or expires <= utc_now() or shutil.disk_usage(WORK).free < RESERVE:
        raise ValueError("reviewed definitions, image, authority or storage changed")

    RESULT.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    ref = content_digest(scope)
    request = RecipeMaterializationRequest(
        plan_id=NAME, authorization_id=NAME, subject_digest=ref, recipe_digest=ref,
        environment_digest=ref, mapping_digest=ref, definition_digests=[ref], seed=0,
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
            put(RESULT / f"{operation.split(':')[-1]}.json", row)
            observations.append(row)
            if not matched:
                break
        put(RESULT / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    verified = len(observations) == len(operations) and all(row["contract_matched"] for row in observations)
    put(RESULT / "result.json", {"review_sha256": exact, "verified": verified, "observations": observations, "models": 0, "cash_usd": 0})
    return verified


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare()
    else:
        raise SystemExit(not asyncio.run(run(args.exact_review)))
