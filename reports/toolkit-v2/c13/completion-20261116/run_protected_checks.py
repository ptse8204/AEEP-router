"""Run one digest-bound protected check through existing containment and accounting."""

import argparse
import asyncio
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path

import run_a2a_batch as a2a
from check_linux_install import DOCKER, FROZEN, HERE, SOCKET, WORK, Scope, docker, get, put
from stage_protected_inputs import RESERVE, stage_a2a, stage_formula, tree

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

CHOICES = ("formula", "a2a-selector")
SCOPES = {choice: f"aeep-c13-{choice}-check-20261116" for choice in CHOICES}


def paths(choice):
    return (
        Path("/private/tmp") / SCOPES[choice],
        WORK / f"{choice}-protected-operation-review.json",
        WORK / f"{choice}-protected-approval.json",
        WORK / f"{choice}-protected-execution",
    )


def image(identity, architecture):
    # Query only the image identity and isolation-relevant metadata.
    import json

    observed = json.loads(
        docker(
            "image",
            "inspect",
            "--format",
            (
                '{"id":{{json .Id}},"os":{{json .Os}},"architecture":{{json .Architecture}},'
                '"layers":{{json .RootFS.Layers}},"volumes":{{json (index .Config "Volumes")}},'
                '"healthcheck":{{json (index .Config "Healthcheck")}}}'
            ),
            identity,
        )
    )
    if (
        observed["id"] != identity
        or observed["os"] != "linux"
        or observed["architecture"] != architecture
        or observed["volumes"]
        or observed["healthcheck"]
    ):
        raise ValueError("protected runtime no longer matches the reviewed image")
    return observed["layers"]


def file_pins():
    return {
        path.name: file_digest(path)
        for path in (
            Path(__file__),
            HERE / "stage_protected_inputs.py",
            HERE / "check_linux_install.py",
            HERE / "run_a2a_batch.py",
            HERE / "formula_reference_guest.py",
            Path(DOCKER),
        )
    }


def formula_result(lock, role):
    rule = lock["roles"][role]
    outcomes = dict.fromkeys(lock["identities"], "passed")
    outcomes.update(dict.fromkeys(rule["must_fail"], "failed"))
    unavailable = rule["infrastructure_failure"]
    if unavailable:
        outcomes[rule["affected_test"]] = "error"
    return {
        "role": role,
        "verified_role": True,
        "grade": None if unavailable else int(role == "reference"),
        "exit_code": int(role != "reference"),
        "collected": len(outcomes),
        "outcomes": outcomes,
        "unexpected_count": 0,
        "renderer_timeout_count": int(unavailable),
    }


def call(choice, role, staging):
    scope = SCOPES[choice]
    root = paths(choice)[0]
    if choice == "formula":
        profile = staging["carrier"]
        roots = [Path(staging["bootstrap"]), root / "renderer"]
        options = {
            key: profile[key]
            for key in (
                "container_image",
                "cpu_count",
                "memory_mb",
                "process_limit",
                "container_tmpfs_mb",
            )
        }
        args = [str(root / "renderer/guest.py"), role]
        timeout = 100
    else:
        role_root = root / role
        roots = [a2a.SHARED, role_root]
        options = {
            "container_image": a2a.IMAGE,
            "cpu_count": 1.0,
            "memory_mb": 512,
            "process_limit": 96,
            "container_tmpfs_mb": 32,
        }
        args = [str(a2a.SHARED / "guest.py"), str(role_root), str(FROZEN / "src")]
        timeout = 45
    environment = AssessmentEnvironment(
        environment_id=scope,
        kind="container",
        container_runtime=DOCKER,
        container_socket=SOCKET,
        identity={"input_scope": content_digest(staging["sha256_by_staged_root"])},
        read_only_roots=[str(item) for item in roots],
        network=False,
        **options,
    )
    spec = ExecutorSpec(
        id=f"toolkit.{choice}.protected",
        capability="toolkit.upstream-engineering@1",
        kind="command",
        side_effect="read",
        description="Pinned public verifier with protected inputs",
        config={
            "argv": ["python3", "-I", "-B", *args],
            "argv_literal": True,
            "output": {"type": "json"},
            "timeout_seconds": timeout,
            "max_output_bytes": 60000,
        },
    )
    identity = f"{scope}:{role}"
    ctx = ExecutionContext(
        request=ActionRequest(action_id=identity, capability=spec.capability, input={}),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=identity,
        approved_side_effect=spec.side_effect,
    )
    executor = ContainerExecutor(environment)
    argv, name = executor.command(ctx)
    mounts = {arg for arg in argv if arg.startswith("type=bind,")}
    if (
        mounts != {f"type=bind,src={path},dst={path},readonly" for path in [FROZEN / "src", *roots]}
        or argv[argv.index("--network") + 1] != "none"
        or argv[argv.index("--user") + 1] != "65534:65534"
        or not {"--read-only", "--pull=never", "--cap-drop=ALL", "--security-opt=no-new-privileges"}
        <= set(argv)
    ):
        raise ValueError("protected boundary changed")
    return ctx, executor, {"docker": argv, "container": name, "spec": spec.model_dump(mode="json")}


def prepare(choice):
    root, review, approval, output = paths(choice)
    if any(path.exists() for path in (review, approval, output)):
        raise ValueError("prepare only a new protected scope")
    architecture = "amd64" if choice == "formula" else "arm64"
    image_id = (
        get(HERE / "formula-offline-preparation.json")["carrier"]["id"]
        if choice == "formula"
        else a2a.IMAGE
    )
    layers = image(image_id, architecture)
    staging = stage_formula(root) if choice == "formula" else stage_a2a(root)
    seconds = 120 if choice == "formula" else 60
    roles = staging["roles"]
    if choice == "formula":
        lock = get(root / "renderer/protected-fixtures/protected-fixture-lock.json")
        expectations = {role: formula_result(lock, role) for role in roles}
    else:
        expectations = {}
    source = verification_source_digest(FROZEN)
    put(
        review,
        {
            "choice": choice,
            "scope": SCOPES[choice],
            "implementation_source": source,
            "source_file_sha256": file_pins(),
            "staged": staging,
            "image_id": image_id,
            "architecture": architecture,
            "image_layers": layers,
            "roles": roles,
            "expectations": expectations,
            "launches": {role: call(choice, role, staging)[2] for role in roles},
            "maximum_operations": len(roles),
            "reserved_seconds_per_operation": seconds,
            "maximum_reserved_seconds": len(roles) * seconds,
            "expires_at": (utc_now() + timedelta(days=7)).isoformat(),
            "network": False,
            "models": 0,
            "cash_usd": 0,
            "downloads": 0,
            "builds": 0,
            "automatic_retries": 0,
            "repeat_scope": (
                "Only A2A issue 472. Two successful pairs and five prior charges remain unchanged."
                if choice == "a2a-selector"
                else "Four first protected verifier roles and no model turns."
            ),
        },
    )
    print(file_digest(review))


def verify_files(staging):
    return all(
        content_digest(tree(Path(path))) == expected
        for path, expected in staging["sha256_by_staged_root"].items()
    )


async def execute(choice, exact):
    root, review_path, approval_path, output = paths(choice)
    if file_digest(review_path) != exact:
        raise ValueError("protected operation review changed")
    approval = get(approval_path) if approval_path.is_file() else {}
    if approval.get("approved") is not True or approval.get("review_sha256") != exact:
        raise ValueError("exact operator approval required for protected execution")
    review = get(review_path)
    staged = review["staged"]
    expiry = datetime.fromisoformat(review["expires_at"])
    roles = tuple(review["roles"])
    seconds = review["reserved_seconds_per_operation"]
    scope = SCOPES[choice]
    expected_roles = (
        ("reference", "wrong-value", "incomplete", "renderer-unavailable")
        if choice == "formula"
        else ("reference", "original")
    )
    if (
        review["scope"] != scope
        or review["choice"] != choice
        or expiry <= utc_now()
        or review["maximum_operations"] != len(roles)
        or roles != expected_roles
        or review["maximum_reserved_seconds"] != seconds * len(roles)
        or review["implementation_source"] != verification_source_digest(FROZEN)
        or review["source_file_sha256"] != file_pins()
        or review["image_layers"] != image(review["image_id"], review["architecture"])
    ):
        raise ValueError("approved protected operation drift")
    contexts = {role: call(choice, role, staged) for role in roles}
    if {role: item[2] for role, item in contexts.items()} != review["launches"]:
        raise ValueError("protected launch changed")
    if not verify_files(staged):
        raise ValueError("protected mount changed")
    output.mkdir(mode=0o700)
    exact_scope = Scope(review_sha256=exact)
    ref = content_digest(exact_scope)
    grant = AssessmentAuthorization(
        authorization_id=scope,
        subject_digests=[ref],
        recipe_digests=[ref],
        environment_digests=[ref],
        allowed_destinations=["local"],
        limits=AssessmentLimits(
            max_operations=len(roles), max_model_turns=0, max_elapsed_seconds=seconds * len(roles)
        ),
        expires_at=expiry,
        remote_disclosure=False,
    )
    request = RecipeMaterializationRequest(
        plan_id=scope,
        authorization_id=scope,
        subject_digest=ref,
        recipe_digest=ref,
        mapping_digest=ref,
        environment_digest=ref,
        definition_digests=[ref],
        seed=0,
    )
    progress = {}
    with ReceiptStore(output / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        repo.put("toolkit_c13_protected_review", ref, exact_scope)
        repo.approve_bundle(grant, {ref: exact_scope.model_dump(mode="json")})
        for role, (ctx, executor, launch) in contexts.items():
            pattern = f"name=^/{launch['container']}$"
            if (
                docker("ps", "-aq", "--filter", pattern)
                or shutil.disk_usage(root).free < RESERVE
                or file_digest(review_path) != exact
                or not verify_files(staged)
            ):
                raise ValueError("owned worker or protected assets are no longer ready")
            repo.reserve(
                request,
                ctx.attempt_id,
                AssessmentLimits(max_operations=1, max_elapsed_seconds=seconds),
                stage="protected_reference",
            )
            started, clock = utc_now(), time.monotonic()
            raw = await executor.execute(ctx)
            if docker("ps", "-aq", "--filter", pattern):
                raise RuntimeError("owned cleanup uncertain; keep unresolved reservation")
            if choice == "formula":
                valid = (
                    raw.status.value == "success"
                    and isinstance(raw.output, dict)
                    and content_digest(raw.output) == content_digest(review["expectations"][role])
                )
                observation = raw.output if valid else None
            else:
                binding = get(root / role / "binding.json")
                valid = a2a.verified_role(binding, raw)
                observation = a2a.retained_observation(binding, raw)
            receipt = ExecutionReceipt(
                decision_id=ctx.attempt_id,
                action_id=ctx.attempt_id,
                capability=ctx.spec.capability,
                executor_id=ctx.spec.id,
                executor_kind=ctx.spec.kind,
                status="success" if valid else "failed",
                execution_success=valid,
                error_type=None if valid else "PROTECTED_CHECK_UNVERIFIED",
                started_at=started,
                ended_at=utc_now(),
                estimated=ctx.estimate,
                actual_resources=raw.resources,
                metadata={
                    "role": role,
                    "review_sha256": exact,
                    "observation": observation,
                    "container_absent": True,
                },
            )
            store.save_receipt(receipt)
            repo.finish_operation(
                ctx.attempt_id, elapsed_seconds=time.monotonic() - clock, resources=raw.resources
            )
            put(output / f"{role}-receipt.json", receipt.model_dump(mode="json"))
            progress[role] = {"verified": valid, "receipt_id": receipt.receipt_id}
            if not valid:
                break
        put(output / "ledger.json", repo.operation_ledger(scope).model_dump(mode="json"))
    completed = len(progress) == len(roles) and all(row["verified"] for row in progress.values())
    put(
        output / "result.json",
        {
            "review_sha256": exact,
            "passed": completed,
            "roles": progress,
            "dispatched_models": 0,
            "cash_usd": 0,
            "formal_stage_assigned": False,
        },
    )
    return completed


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("choice", choices=CHOICES)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--prepare", action="store_true")
    mode.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        prepare(args.choice)
    else:
        raise SystemExit(not asyncio.run(execute(args.choice, args.exact_review)))
