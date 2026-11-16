"""Verify the prepared A2A callback with the existing offline executor and ledger."""

import argparse
import asyncio
import json
import re
import shutil
import subprocess
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

from audit_a2a_receipt_bridge import CASES, SETTLED
from check_linux_install import DOCKER, FROZEN, SOCKET, WORK, Scope, docker, get, put
from prepare_a2a_ordinary import TARGET

from aeep.assessment.containment import ContainerExecutor
from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentBudgetAmendment,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentScopeAmendment,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output
from aeep.assessment.verification import verification_source_digest
from aeep.errors import ConfigurationError
from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, utc_now
from aeep.store import ReceiptStore
from aeep_toolkit.install_runtime import file_digest

NAME = "aeep-c13-a2a-batch-20261116"
TAG = "aeep-toolkit-v2/repository-grader:py313-a2a-native-20261116"
PLUGIN = Path("/Applications/Docker.app/Contents/Resources/cli-plugins/docker-buildx")
CONFIG = TARGET / "docker-config"
REVIEW = TARGET / "operation-review.json"
APPROVAL = TARGET / "approval.json"
RESULT = TARGET / "execution"
BUILD = 120
ADDITIONAL = AssessmentLimits(max_operations=5, max_elapsed_seconds=BUILD + 5 + 4 * 35)


def retained(repository, summary):
    grant = AssessmentAuthorization.model_validate(repository.get("authorization", NAME))
    ledger = get(SETTLED / "ledger.json")
    if (
        grant != repository.effective_grant(NAME)
        or ledger != repository.operation_ledger(NAME).model_dump(mode="json")
        or len(ledger["operations"]) != 5
        or any(row["elapsed_seconds"] is None for row in ledger["operations"])
        or grant.allowed_destinations != ["local"]
        or grant.remote_disclosure
        or grant.limits.max_cash_usd
        or grant.limits.max_model_turns
        or file_digest(SETTLED / "ledger.json") != summary["historical_ledger_sha256"]
    ):
        raise ValueError("historical A2A grant or accounting changed")
    return grant


def prepared():
    summary = get(TARGET / "summary.json")
    context = TARGET / "image"
    support = context / "support"
    entries = list(support.rglob("*"))
    if context.resolve() != context or support.resolve() != support:
        raise ValueError("A2A build roots changed")
    if any(path.is_symlink() or not (path.is_dir() or path.is_file()) for path in entries):
        raise ValueError("A2A image context contains an unsupported member")
    inventory = {
        path.relative_to(support).as_posix(): file_digest(path)
        for path in entries
        if path.is_file()
    }
    if (
        content_digest(inventory) != summary["support_inventory_sha256"]
        or set(context.iterdir()) != {support, context / "Dockerfile"}
        or file_digest(context / "Dockerfile") != summary["dockerfile_sha256"]
        or any(
            path.stat().st_mode & 0o777 != (0o555 if path.is_dir() else 0o444)
            for path in [support, *entries]
        )
        or any(
            file_digest(TARGET / name) != digest
            for name, digest in summary["execution_definition_files"].items()
        )
        or summary["source"] != verification_source_digest(FROZEN)
        or get(CONFIG / "config.json") != {"cliPluginsExtraDirs": [str(PLUGIN.parent)]}
    ):
        raise ValueError("A2A prepared runtime or scope changed")
    parent = json.loads(docker("image", "inspect", "--format", "{{json .}}", summary["parent_tag"]))
    if (
        parent["Id"] != summary["parent_image"]
        or parent["RootFS"]["Layers"] != summary["parent_layers"]
    ):
        raise ValueError("local parent alias changed")
    with ReceiptStore(SETTLED / "receipts.sqlite3", read_only=True) as store:
        grant = retained(AssessmentRepository(store), summary)
    return {
        "purpose": "Verify the ordinary callback for two reproduced A2A cases in a private overlay",
        "summary_sha256": file_digest(TARGET / "summary.json"),
        "driver_sha256": file_digest(Path(__file__)),
        "builder_sha256": file_digest(PLUGIN),
        "docker_sha256": file_digest(Path(DOCKER)),
        "expires_at": grant.expires_at.isoformat(),
        "root_grant_digest": content_digest(grant),
        "build_command": [
            DOCKER,
            "--config",
            str(CONFIG),
            "--host",
            f"unix://{SOCKET}",
            "build",
            "--pull=false",
            "--network=none",
            "--platform=linux/arm64",
            "--builder=default",
            "--provenance=false",
            "--sbom=false",
            "--iidfile",
            str(RESULT / "image-id"),
            "--tag",
            TAG,
            str(context),
        ],
        "attempts": summary["staged_callback_checks"],
        "maximum_additional": ADDITIONAL.model_dump(mode="json"),
        "previous_operation_count": 5,
        "models": 0,
        "cash_usd": 0,
        "downloads": 0,
        "retries": 0,
        "provider_disclosure": False,
        "formal_adoption": False,
    }


def exact_approval(digest):
    if not (
        not RESULT.exists()
        and REVIEW.is_file()
        and file_digest(REVIEW) == digest
        and APPROVAL.is_file()
    ):
        return False
    approval = get(APPROVAL)
    return (
        set(approval) == {"approved", "review_sha256"}
        and approval["approved"] is True
        and approval["review_sha256"] == digest
    )


async def run(exact):
    if not exact_approval(exact):
        raise ValueError("this unstarted A2A repeat requires its exact authority")
    review = prepared()
    if (
        review != get(REVIEW)
        or datetime.fromisoformat(review["expires_at"]) <= utc_now()
        or docker("image", "ls", "--filter", "reference=" + TAG, "-q")
        or shutil.disk_usage(WORK).free < 52 * 1024**3
    ):
        raise ValueError("review, expiration, image tag or space changed")
    summary = get(TARGET / "summary.json")
    RESULT.mkdir(mode=0o700)
    scope = Scope(review_sha256=exact)
    reference = content_digest(scope)
    measurements = []
    with ReceiptStore(SETTLED / "receipts.sqlite3") as store:
        repo = AssessmentRepository(store)
        grant = retained(repo, summary)
        (subject,) = grant.subject_digests
        repo.put("toolkit_c13_a2a_ordinary_scope", reference, scope)
        repo.approve_bundle(
            AssessmentScopeAmendment(
                authorization_id=NAME,
                amendment_id=NAME + ":ordinary",
                authorization_digest=content_digest(grant),
                subject_digests=[subject],
                recipe_digests=[subject],
                environment_digests=[subject],
                reviewed_digests=[reference],
            ),
            {
                subject: repo.get("toolkit_c13_a2a_batch_scope", subject),
                reference: scope.model_dump(mode="json"),
            },
            budget_amendment=AssessmentBudgetAmendment(
                amendment_id=NAME + ":ordinary-budget",
                authorization_id=NAME,
                authorization_digest=content_digest(grant),
                expires_at=grant.expires_at,
                limits=AssessmentLimits(
                    max_operations=grant.limits.max_operations + ADDITIONAL.max_operations,
                    max_elapsed_seconds=grant.limits.max_elapsed_seconds
                    + ADDITIONAL.max_elapsed_seconds,
                ),
            ),
        )
        scope_request = RecipeMaterializationRequest(
            plan_id=NAME,
            authorization_id=NAME,
            subject_digest=subject,
            recipe_digest=subject,
            environment_digest=subject,
            mapping_digest=subject,
            definition_digests=[subject, reference],
            seed=0,
        )

        async def call(label, context, executor, validate, *, owned=None):
            if file_digest(REVIEW) != exact or shutil.disk_usage(WORK).free < 52 * 1024**3:
                raise ValueError("review or host reserve changed before dispatch")
            reservation = AssessmentLimits(
                max_operations=1,
                max_elapsed_seconds=float(context.spec.config["timeout_seconds"]) + 5,
            )
            repo.reserve(
                scope_request,
                context.attempt_id,
                reservation,
                stage="ordinary_a2a_recipe",
                require_settled_plan=True,
            )
            started, tick = utc_now(), time.monotonic()
            raw = await executor.execute(context)
            if owned and docker("ps", "-aq", "--filter", f"name=^/{owned}$"):
                raise RuntimeError("owned grader cleanup is uncertain")
            if not owned and raw.status.value == "timeout":
                raise RuntimeError("derived image creation is uncertain")
            result, error = None, raw.error_type
            if raw.status.value == "success":
                try:
                    result = validate(raw.output)
                except (
                    ValueError,
                    KeyError,
                    OSError,
                    TypeError,
                    subprocess.SubprocessError,
                ) as exc:
                    error = type(exc).__name__
            receipt = ExecutionReceipt(
                decision_id=context.attempt_id,
                action_id=context.attempt_id,
                capability=context.spec.capability,
                executor_id=context.spec.id,
                executor_kind=context.spec.kind,
                status="success" if result is not None else "failed",
                execution_success=result is not None,
                started_at=started,
                ended_at=utc_now(),
                estimated=context.estimate,
                actual_resources=raw.resources,
                error_type=None if result is not None else error or "A2A_OBSERVER_UNVERIFIED",
                metadata={
                    "review_sha256": exact,
                    "container_absent": True if owned else None,
                    **(
                        {
                            "protected_observation_sha256": content_digest(result),
                            "result_counts": dict(Counter(result["statuses"].values())),
                        }
                        if owned and result is not None
                        else {}
                    ),
                },
            )
            store.save_receipt(receipt)
            repo.finish_operation(
                context.attempt_id, elapsed_seconds=time.monotonic() - tick, resources=raw.resources
            )
            measurements.append(
                {
                    "role": label,
                    "receipt_id": receipt.receipt_id,
                    "contract_matched": result is not None,
                }
            )
            put(RESULT / f"{label}.json", measurements[-1])
            return result

        def image(_):
            identity = (RESULT / "image-id").read_text().strip()
            inspected = json.loads(docker("image", "inspect", "--format", "{{json .}}", TAG))
            if (
                not re.fullmatch(r"sha256:[0-9a-f]{64}", identity)
                or inspected["Id"] != identity
                or inspected["RootFS"]["Layers"][:-1] != summary["parent_layers"]
                or inspected["Os"] != "linux"
                or inspected["Architecture"] != "arm64"
                or inspected["Config"]["User"] != "65534:65534"
                or inspected["Config"].get("Volumes")
                or inspected["Config"].get("Healthcheck")
            ):
                raise ValueError("derived grader image or permissions differ")
            return identity

        build = ExecutorSpec(
            id="repository.suite.a2a-build",
            capability="toolkit.upstream-engineering@1",
            kind="command",
            side_effect="write",
            description="Build one offline COPY-only overlay",
            config={
                "argv": review["build_command"],
                "argv_literal": True,
                "timeout_seconds": BUILD,
                "max_output_bytes": 65_536,
                "output": {"type": "text"},
                "env": {
                    "HOME": str(TARGET),
                    "PATH": "/usr/bin:/bin",
                    "LC_ALL": "C",
                    "DOCKER_BUILDKIT": "1",
                },
            },
        )
        builder = CommandExecutor()
        try:
            derived = await call(
                "build", execution_context(build, NAME + ":ordinary-build", {}), builder, image
            )
        finally:
            await builder.close()
        if derived:
            template = get(TARGET / "environment-template.json")
            environment = AssessmentEnvironment.model_validate(
                {
                    **template,
                    "container_image": derived,
                    "identity": {"operation_review_sha256": exact},
                }
            )
            put(RESULT / "environment.json", environment.model_dump(mode="json"))
            observer = ExecutorSpec.model_validate(get(TARGET / "observer.json"))
            executor = ContainerExecutor(environment)
            parent = ContainerExecutor(AssessmentEnvironment.model_validate(template))
            for case in sorted(CASES):
                inputs = get(TARGET / f"{case}.json")
                for role in ("reference", "original"):
                    binding = review["attempts"][case][role]
                    operation = f"aeep-c13-a2a-ordinary:{case}:{role}"

                    async def probe(
                        payload,
                        binding=binding,
                        operation=operation,
                        case=case,
                        role=role,
                        truth=inputs["truth"],
                    ):
                        context = execution_context(observer, operation, payload)
                        argv, owned = executor.command(context)
                        parent_argv, _ = parent.command(context)
                        if (
                            content_digest(payload) != binding["payload_sha256"]
                            or owned != binding["container"]
                            or len(argv) != binding["argument_count"]
                            or argv
                            != [
                                derived if arg == template["container_image"] else arg
                                for arg in parent_argv
                            ]
                            or docker("ps", "-aq", "--filter", f"name=^/{owned}$")
                        ):
                            raise ValueError(
                                "actual invocation differs from the prepared boundary or payload"
                            )

                        def check(reply):
                            return matching_observation(reply, payload, truth, role)

                        reply = await call(f"{case}-{role}", context, executor, check, owned=owned)
                        if reply is None:
                            raise ConfigurationError("protected A2A observation was indeterminate")
                        return reply

                    try:
                        grade = await grade_suite_output(
                            inputs["input"], inputs["truth"], inputs["artifacts"][role], probe
                        )
                    except ConfigurationError:
                        break
                    if grade.quality_score != binding["expected_score"]:
                        raise ValueError("ordinary score differs from verified historical outcome")
            await executor.close()
        put(RESULT / "ledger.json", repo.operation_ledger(NAME).model_dump(mode="json"))
    verified = len(measurements) == 5 and all(row["contract_matched"] for row in measurements)
    put(
        RESULT / "result.json",
        {
            "verified": verified,
            "historical_ledger_sha256": summary["historical_ledger_sha256"],
            "review_sha256": exact,
            "operations": measurements,
            "image_id": derived,
            "models": 0,
            "cash_usd": 0,
            "formal_cases_adopted": 0,
        },
    )
    return verified


def execution_context(spec, operation, payload):
    return ExecutionContext(
        request=ActionRequest(action_id=operation, capability=spec.capability, input=payload),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=operation,
        approved_side_effect=spec.side_effect,
    )


def matching_observation(reply, payload, truth, role):
    expected = dict.fromkeys(truth["fail_to_pass"] + truth["pass_to_pass"], "PASSED")
    if role == "original":
        expected.update(dict.fromkeys(truth["fail_to_pass"], "FAILED"))
    if (
        not isinstance(reply, dict)
        or set(reply) != {"archive_sha256", "python", "pytest", "exit_code", "statuses"}
        or any(reply[key] != payload[key] for key in ("archive_sha256", "python", "pytest"))
        or type(reply["exit_code"]) is not int
        or reply["exit_code"] != int(role == "original")
        or not isinstance(reply["statuses"], dict)
        or len(reply["statuses"]) > 10_000
        or any(reply["statuses"].get(key) != value for key, value in expected.items())
        or any(value != "PASSED" for key, value in reply["statuses"].items() if key not in expected)
    ):
        raise ValueError("protected A2A collection, runtime or outcomes changed")
    return reply


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    request = parser.add_mutually_exclusive_group(required=True)
    request.add_argument("--prepare", action="store_true")
    request.add_argument("--exact-review")
    args = parser.parse_args()
    if args.prepare:
        CONFIG.mkdir(mode=0o700)
        put(CONFIG / "config.json", {"cliPluginsExtraDirs": [str(PLUGIN.parent)]})
        put(REVIEW, prepared())
        print(file_digest(REVIEW))
    else:
        raise SystemExit(0 if asyncio.run(run(args.exact_review)) else 1)
