"""Verify the exact four protected graders offline, retaining minimized receipts."""

import asyncio
import json
import time
from pathlib import Path

from freeze_study import DATABASE
from prepare_runtime import (
    DESIGN,
    DOCKER_PATH,
    LOCAL,
    ROOT,
    SOCKET,
    WORK,
    docker,
    read,
    require_reserve,
    sha,
    write,
)

from aeep.assessment import containment
from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.extensions import grader_results
from aeep.assessment.models import AssessmentEnvironment, RecipeDefinition, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.repository_suites import grade_suite_output, reference_outputs
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionReceipt, ResourceVector, SideEffect, utc_now
from aeep.store import ReceiptStore

RUNTIME_ROOT = Path(containment.__file__).resolve().parents[2]
SALES = LOCAL / "skillsbench-sales-handoff-20261105/sales-prepared/plan.json"
EXCEL = LOCAL / "skillsbench-document-managed-20261106/managed-execution/excel-prepared/plan.json"


def definitions():
    tasks = read(DESIGN)["tasks_in_execution_order"]
    result = []
    for task, plan_path in zip(tasks[:2], (SALES, EXCEL), strict=True):
        historical = read(plan_path)
        with ReceiptStore(DATABASE, read_only=True) as store:
            repo = AssessmentRepository(store)
            recipe = RecipeDefinition.model_validate(
                repo.get("recipe", historical["recipe_digest"])
            )
            env = AssessmentEnvironment.model_validate(
                repo.get("environment", historical["environment_digest"])
            )
        assert content_digest(recipe) == task["protected_grader"]["historical_recipe_digest"]
        [case] = historical["suite"]["cases"]
        assert (
            case["case_id"] == task["id"]
            and content_digest(case["action"]["input"]) == task["task_input_digest"]
        )
        assert (
            content_digest(case["validators"])
            == task["protected_grader"]["original_validator_binding"]
        )
        assert env.container_image == task["protected_grader"]["image"] and not env.network
        result.append(
            (
                task,
                recipe,
                env,
                case["action"]["input"],
                case["validators"][0]["config"]["expected"],
                None,
            )
        )
    path = ROOT / tasks[2]["protected_grader"]["historical_recipe"]["path"]
    assert sha(path) == tasks[2]["protected_grader"]["historical_recipe"]["sha256"]
    recipe = RecipeDefinition.model_validate(read(path))
    cases = {row["input"]["task_id"]: row for row in recipe.generator_config["cases"]}
    for task in tasks[2:]:
        case = cases[task["id"]]
        assert content_digest(case["input"]) == task["task_input_digest"]
        assert content_digest(case["truth"]) == task["protected_grader"]["binding"]
        assert case["reference"]["sha256"] == task["protected_grader"]["reference_digest"]
        env = AssessmentEnvironment(
            environment_id="sol-comparison-repository-grader",
            kind="container",
            identity={"purpose": "protected comparison grader"},
            container_image=task["protected_grader"]["image"],
            container_runtime=DOCKER_PATH,
            container_socket=SOCKET,
            memory_mb=512,
            process_limit=96,
        )
        result.append((task, recipe, env, case["input"], case["truth"], case["fault_outputs"]))
    return result


async def invoke(task, executor, spec, value, stage, directory):
    require_reserve(51)
    attempt = f"sol-comparison-20261116-grader-{task['id']}-{stage}"
    context = ExecutionContext(
        request=ActionRequest(action_id=attempt, capability=spec.capability, input=value),
        spec=spec,
        estimate=spec.estimate,
        attempt=1,
        attempt_id=attempt,
        approved_side_effect=SideEffect.READ,
    )
    argv, name = executor.command(context)
    assert name == container_name(attempt) and "--pull=never" in argv and "--read-only" in argv
    for flag, expected in (("--network", "none"), ("--user", "65534:65534")):
        assert argv[argv.index(flag) + 1] == expected
    mounts = [argv[i + 1] for i, arg in enumerate(argv) if arg == "--mount"]
    assert mounts == [f"type=bind,src={RUNTIME_ROOT},dst={RUNTIME_ROOT},readonly"]
    assert "-v" not in argv
    assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    started = utc_now()
    clock = time.perf_counter()
    raw = None
    try:
        raw = await executor.execute(context)
    finally:
        elapsed = time.perf_counter() - clock
        clean = not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
        passed = clean and raw is not None and raw.status.value == "success"
        receipt = ExecutionReceipt(
            decision_id=attempt,
            action_id=attempt,
            capability=spec.capability,
            executor_id=spec.id,
            executor_kind="command",
            status="success" if passed else "failed",
            started_at=started,
            ended_at=utc_now(),
            estimated=spec.estimate,
            execution_success=passed,
            error_type=raw.error_type if raw else "INTERRUPTED",
            actual_resources=ResourceVector(latency_ms=elapsed * 1000),
            metadata={
                "task_id": task["id"],
                "stage": stage,
                "cleanup_confirmed": clean,
                "container_image": executor.environment.container_image,
                "executor_digest": content_digest(spec),
                "request_digest": content_digest(value),
                "observed_resource_dimensions": ["latency_ms"],
                "model_turns": 0,
            },
        )
        write(directory / (attempt + ".json"), receipt.model_dump(mode="json"))
    if not passed:
        raise RuntimeError(f"protected invocation failed at {attempt}: {receipt.error_type}")
    return raw.output


async def verify_task(task, recipe, environment, value, truth, faults, directory):
    executor = ContainerExecutor(environment)
    extension = recipe.extension
    assert extension is not None
    assert (
        docker("image", "inspect", "--format", "{{.Id}}", environment.container_image)
        == environment.container_image
    )
    try:
        if faults is None:
            reference = await invoke(
                task, executor, extension.reference, {"inputs": [value]}, "reference", directory
            )
            [answer] = reference["outputs"]
            assert isinstance(answer, dict)

            async def grade(output, variant):
                reply = await invoke(
                    task,
                    executor,
                    extension.grader,
                    {"examples": [{"input": value, "output": output, "expected": truth}]},
                    variant,
                    directory,
                )
                return grader_results(reply, extension, 1)[0]

            controls = extension.fault_outputs
        else:
            [answer] = reference_outputs(recipe, [value])

            async def grade(output, variant):
                async def probe(payload):
                    return await invoke(
                        task, executor, extension.grader, payload, variant, directory
                    )

                return await grade_suite_output(value, truth, output, probe)

            controls = faults
        variants = [("pass-reference", answer, True), ("reject-missing", {}, False)]
        variants += [(f"reject-fault-{i}", fault, False) for i, fault in enumerate(controls)]
        seen = []
        for variant, output, expected in variants:
            result = await grade(output, variant)
            seen.append(
                {
                    "variant": variant,
                    "output_sha256": content_digest(output),
                    "valid": result.valid,
                    "score": result.quality_score,
                    "detail": result.detail,
                    "expected_valid": expected,
                }
            )
            write(directory / (task["id"] + "-" + variant + "-grade.json"), seen[-1])
            if result.valid is not expected or result.quality_score != float(expected):
                raise RuntimeError(f"unexpected protected grade for {task['id']} {variant}")
        return {
            "grade_controls": seen,
            "recipe_digest": content_digest(recipe),
            "grader_environment_digest": content_digest(environment),
            "grader_image": environment.container_image,
            "input_digest": content_digest(value),
        }
    finally:
        await executor.close()


async def verify():
    directory = WORK / "grader-receipts"
    directory.mkdir(mode=0o700, exist_ok=True)
    assert not any(directory.iterdir())
    outcomes = {}
    for entry in definitions():
        task = entry[0]
        outcomes[task["id"]] = await verify_task(*entry, directory)
    summary = {
        "passed": True,
        "model_turns": 0,
        "cash_usd": "0",
        "tasks": outcomes,
        "receipts": {
            path.name: sha(path) for path in sorted(directory.glob("sol-comparison-*.json"))
        },
    }
    write(WORK / "protected-grader-verification.json", summary)
    print(json.dumps({name: len(row["grade_controls"]) for name, row in outcomes.items()}))


if __name__ == "__main__":
    asyncio.run(verify())
