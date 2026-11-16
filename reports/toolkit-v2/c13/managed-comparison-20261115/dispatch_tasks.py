"""Bind the four development tasks to the existing managed executor and verifier."""

import asyncio
import hashlib
import json
from pathlib import Path

from prepare_runtime import ROOT, WORK, read, sha
from rebind_source import STACK_REBINDING
from verify_graders import definitions
from verify_workers import EXCEL, REACT, SALES, descriptor, make_spec

from aeep.assessment.adapters import prepare_context
from aeep.assessment.models import DifferentialEnvironment, content_digest
from aeep.benchmarking import BenchmarkCase, BenchmarkSuite
from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import HostProbe, ManagedHostRegistry
from aeep.hosts.codex_pair_inspection import ReviewedSkillProfile, WorkerPairInspection
from aeep.models import ActionRequest, ExecutorSpec, RawExecution, ValidationSpec

REPO_PILOT = Path(__file__).resolve().parents[1] / "repository-usefulness-pilot-20261029"
BEGIN = "Task and artifact paths:\n"


def bind_tasks():
    """Read protected material locally. Callers export metadata and hashes only."""
    images = read(WORK / "verified-image-bindings.json")
    source = read(STACK_REBINDING)["implementation_source"]
    old = read(REPO_PILOT / "collector-definitions.json")
    old_config = old["definitions"][old["pair_definition_digest"]]["control"]["config"]
    tasks = []
    for index, (task, recipe, environment, value, truth, _) in enumerate(definitions()):
        is_doc = index < 2
        domain = "document_data" if is_doc else "software_engineering"
        base = (SALES, EXCEL)[index] if is_doc else REACT
        task_name = task["id"]
        if not is_doc:
            archive = ROOT / task["public_archive"]["path"]
            assert sha(archive) == task["public_archive"]["sha256"] == value["source_sha256"]

        specs = {}
        for role, image in images[domain].items():
            arm = make_spec(base, domain, role, image, offline=False).model_dump(mode="json")
            identity = f"sol-pilot-{index + 1}.{role}"
            arm.update(
                id=identity,
                capability=recipe.capability,
                input_schema=recipe.input_schema,
                output_schema=recipe.output_schema,
            )
            config = arm["config"]
            config["adapter_id"] = f"codex-app-server:{identity}"
            config["managed_worker"]["worker_id"] = identity.replace(".", "-")
            if is_doc:
                instruction = (
                    config["instructions"]
                    .replace(
                        "Use the supplied stack-check skill for isolation and output discipline. ",
                        "",
                    )
                    .split("Task and artifact paths")[0]
                )
            else:
                instruction = old_config["instructions"].split(
                    "Current task JSON and bound artifact paths:"
                )[0]
                config["artifact"] = old_config["artifact"]
                config["input_tree"] = None
                config["assessment_adapter"] = old_config["assessment_adapter"] | {
                    "read_only_roots": [str(archive.parent)],
                }
            config["instructions"] = instruction.rstrip() + "\n" + BEGIN + "{input}"
            specs[role] = ExecutorSpec.model_validate(arm)

        primary, alias, name, digest = descriptor(domain)
        skill_root = str(Path(primary).parent)
        cand_paths = [
            primary,
            alias,
            "/opt/dependencies/runtime" if is_doc else skill_root,
        ]
        shared = {
            "case": task_name,
            "source": source,
            "policy": images[domain]["control"]["policy_sha256"],
            "tools": {"pandas": "2.3.2", "openpyxl": "3.1.5"},
        }
        inventory = {"capable_local_tools": content_digest(shared)}
        difference = DifferentialEnvironment(
            shared_definition_digest=content_digest(shared),
            control_inventory=inventory,
            treatment_inventory=inventory | {"skill:" + name: digest},
            candidate_inventory={"skill:" + name: digest},
            candidate_paths=cand_paths,
            candidate_aliases=[name],
        )
        options = (
            {}
            if is_doc
            else {
                "reviewed_skill": ReviewedSkillProfile(
                    primary_path=primary,
                    alias_path=alias,
                    package_root=skill_root,
                    aliases=[name],
                    files={primary: digest},
                )
            }
        )
        pair = WorkerPairInspection(
            schema_version="assessment.worker-pair-inspection.v3"
            if is_doc
            else "assessment.worker-pair-inspection.v4",
            profile="spreadsheets:1" if is_doc else "reviewed-skill:1",
            differential=difference,
            shared_versions=shared["tools"],
            candidate_skill_digest=digest,
            **specs,
            **options,
        )
        case = BenchmarkCase(
            case_id="development-" + task_name,
            split="training",
            variation=domain,
            template_family=task.get("repository", "skillsbench:" + task_name),
            action=ActionRequest(
                action_id="sol-development-" + task_name, capability=recipe.capability, input=value
            ),
            validators=[
                ValidationSpec(
                    kind="callback",
                    config={
                        "name": "sol-protected-grade",
                        "failure_codes": list(recipe.extension.failure_codes or []),
                    },
                )
            ],
        )
        arms = ("control", "treatment") if index % 2 == 0 else ("treatment", "control")
        suite = BenchmarkSuite(
            suite_id=f"managed-sol-comparison-20261116-{index + 1}",
            domain="development-only",
            seed=71,
            conditions=["fresh-worker"],
            repetitions=1,
            warmup_cases=[],
            max_total_cash_usd="0",
            baseline_route_id=pair.control.id,
            paired_order=True,
            cases=[case],
            routes=[{"route_id": specs[role].id, "executor_id": specs[role].id} for role in arms],
        )
        tasks.append((task, recipe, environment, value, truth, pair, shared, suite))
    return tasks


async def verify_prompt(pair, suite):
    """Exercise the actual renderer with a recording adapter and no worker process."""
    [case] = suite.cases
    rendered = []

    class Recorder:
        async def probe(self):
            return HostProbe(adapter_id="fixture", status="ready")

        async def execute(self, context):
            data = json.loads(context.instruction.split(BEGIN, 1)[1])
            assert (
                data["task"] == case.action.input["task"]
                and data["task_id"] == case.action.input["task_id"]
            )
            artifact = context.config.artifact
            assert artifact is not None and artifact.input_field not in data
            assert data["input_path"] == "/workspace/" + artifact.input_name
            assert data["output_path"] == "/workspace/" + artifact.output_name
            assert not {"truth", "tests", "reference", "fail_to_pass", "pass_to_pass"} & data.keys()
            if "source_sha256" in case.action.input:
                assert data["base_sha256"] == content_digest(case.action.input)
                assert data["editable_paths"] == case.action.input["editable_paths"]
            rendered.append(hashlib.sha256(context.instruction.encode()).hexdigest())
            return RawExecution(status="success", output={})

    registry = ManagedHostRegistry()
    for arm in (pair.control, pair.treatment):
        registry.register(arm.config["adapter_id"], Recorder())
    executor = ManagedHostExecutor(registry)
    for arm in (pair.control, pair.treatment):
        context = ExecutionContext(request=case.action, spec=arm, estimate=arm.estimate, attempt=1)
        context, _ = prepare_context(context)
        result = await executor.execute(context)
        assert result.metadata["task_instruction_sha256"] == rendered[-1]
    assert len(rendered) == 2 and rendered[0] == rendered[1]
    return rendered[0]


async def task_pins():
    metadata = []
    for task, recipe, environment, _, _, pair, shared, suite in bind_tasks():
        metadata.append(
            {
                "task_id": task["id"],
                "recipe_digest": content_digest(recipe),
                "protected_environment_digest": content_digest(environment),
                "pair_digest": content_digest(pair),
                "shared_definition_digest": content_digest(shared),
                "suite_digest": content_digest(suite),
                "instruction_sha256": await verify_prompt(pair, suite),
                "arm_order": [route.route_id for route in suite.routes],
            }
        )
    assert len({row["instruction_sha256"] for row in metadata}) == 4
    return metadata


if __name__ == "__main__":
    print(json.dumps(asyncio.run(task_pins()), indent=2))
