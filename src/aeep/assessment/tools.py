"""Focused task tools and bounded assessment requests; no operator privilege arguments."""

from __future__ import annotations

import asyncio
import hashlib
import os
import subprocess
import sys
from typing import Any

from ..errors import ConfigurationError
from ..models import ActionConstraints, ActionRequest, TaskExecutionOutcome
from ..registry import validate_json
from ..store import ReceiptStore
from .models import AssessmentSetupRequest, RecipeDefinition
from .recipes import shipped_recipe


def reviewed_recipes(store: ReceiptStore | None) -> dict[str, RecipeDefinition]:
    if store is None:
        return {}
    with store._lock:
        rows = store._connection.execute(
            "SELECT r.payload_json FROM assessment_records r JOIN assessment_reviews v ON v.digest=r.digest WHERE r.kind='recipe' AND v.revoked=0 ORDER BY r.rowid"
        ).fetchall()
    recipes = [RecipeDefinition.model_validate_json(row[0]) for row in rows]
    return {
        "aeep_recipe_" + hashlib.sha256(recipe.capability.encode()).hexdigest()[:12]: recipe
        for recipe in recipes
        if recipe.generator == "record_template:1" or recipe.extension is not None
    }


def declarations(store: ReceiptStore | None = None, *, tasks_only: bool = False,
                 capabilities: set[str] | None = None) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    result.extend([
        {'name': 'aeep_assessment_options', 'description': 'List existing operator-selected subjects, recipes, environments and configured routes under a current grant. Does not inspect files or approve execution.',
         'inputSchema': {'type': 'object', 'properties': {'authorization_id': {'type': 'string', 'minLength': 1, 'maxLength': 200},
             'after': {'type': 'string', 'maxLength': 400}, 'limit': {'type': 'integer', 'minimum': 1, 'maximum': 50}},
             'required': ['authorization_id'], 'additionalProperties': False}},
        {'name': 'aeep_assessment_setup', 'description': 'Prepare a reviewed-recipe assessment using existing configuration and grant scope. Returns missing review requirements, fixture-generation instructions or a proposed plan; never approves definitions or starts trials.',
         'inputSchema': AssessmentSetupRequest.model_json_schema()},
        {'name': 'aeep_assessment_generate_cases', 'description': 'Generate synthetic fixtures for an existing, operator-reviewed materialization request under its original grant. Cannot approve a recipe, expand limits or replay execution.',
         'inputSchema': {'type': 'object', 'properties': {'materialization_id': {'type': 'string', 'minLength': 1, 'maxLength': 200}},
                         'required': ['materialization_id'], 'additionalProperties': False}},
    ])
    for family in ("csv", "text", "search"):
        recipe = shipped_recipe(family)
        if capabilities is not None and recipe.capability not in capabilities:
            continue
        result.append(
            {
                "name": f"aeep_{family}",
                "description": recipe.description,
                "inputSchema": recipe.input_schema,
                "outputSchema": recipe.output_schema,
            }
        )
    for name, recipe in reviewed_recipes(store).items():
        if capabilities is not None and recipe.capability not in capabilities:
            continue
        result.append(
            {
                "name": name,
                "description": recipe.description,
                "inputSchema": recipe.input_schema,
                "outputSchema": recipe.output_schema,
            }
        )
    for operation in ("start", "status", "report", "cancel", "generate_definition", "structures", "select_structure", "budget"):
        key = "plan_id" if operation in {"start", "structures", "select_structure", "budget"} else "planning_id" if operation == "generate_definition" else "assessment_id"
        result.append(
            {
                "name": f"aeep_assessment_{operation}",
                "description": f"{operation.capitalize()} an assessment under an existing reviewed plan and operator authorization.",
                "inputSchema": {
                    "type": "object",
                    "properties": {key: {"type": "string", "minLength": 1, "maxLength": 200}},
                    "required": [key],
                    "additionalProperties": False,
                },
            }
        )
        if operation == "select_structure":
            result[-1]["inputSchema"]["properties"]["structure"] = {"enum": ["direct", "controlled_agent", "workflow"]}
            result[-1]["inputSchema"]["required"].append("structure")
    if tasks_only:
        result = [item for item in result if not item['name'].startswith('aeep_assessment_')]
        for item in result:
            schema = TaskExecutionOutcome.model_json_schema()
            # Recipe output is validated by the shared executor; the envelope
            # also supports failed/delegated outcomes with no task output.
            schema['properties']['output'] = {}
            item['outputSchema'] = schema
    return result


async def call(service: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from ..mcp.server import _tool_result
    from .service import AssessmentService

    declaration = next(
        (item for item in service.list_tools() if item["name"] == name), None
    )
    if declaration is None:
        raise ConfigurationError("unknown assessment-profile tool")
    validate_json(arguments, declaration["inputSchema"], label=name)
    custom = reviewed_recipes(service.router.store)
    if name in {"aeep_csv", "aeep_text", "aeep_search"} or name in custom:
        recipe = custom[name] if name in custom else shipped_recipe(name.removeprefix("aeep_"))
        from ..hosts.codex_dynamic_tools import current_dynamic_call
        callback = current_dynamic_call()
        request = ActionRequest(
                capability=recipe.capability, input=arguments,
                constraints=ActionConstraints(max_side_effect=service.approved_side_effect)
                if service.profile == 'task' else ActionConstraints())
        if callback is not None:
            request = request.model_copy(update={'action_id': callback.action_id})
        outcome = await service.router.execute(
            request,
            approved_side_effect=service.approved_side_effect,
            allow_unsafe_executor=service.allow_unsafe_executor,
        )
        if service.profile == 'task':
            return _tool_result(
                service.router.task_outcome(outcome, approved_side_effect=service.approved_side_effect).model_dump(mode='json'),
                is_error=not outcome.ok,
            )
        return _tool_result(
            outcome.output
            if outcome.ok
            else service.router.compact_outcome(outcome).model_dump(mode="json"),
            is_error=not outcome.ok,
        )
    manifest = service.router.manifest_path
    if manifest is None or service.router.store.path == ":memory:":
        raise ConfigurationError("assessment workers require a persistent operator manifest")
    assessment = AssessmentService(service.router, manifest.parent / ".aeep" / "assessments")
    operation = name.removeprefix("aeep_assessment_")
    if operation == 'options':
        from .onboarding import setup_options
        return _tool_result(setup_options(assessment, **arguments))
    if operation == 'setup':
        from .onboarding import prepare_setup
        return _tool_result(prepare_setup(assessment, AssessmentSetupRequest.model_validate(arguments)))
    if operation == 'generate_cases':
        from .extensions import materialize
        cases = await materialize(assessment, arguments['materialization_id'])
        # Expected answers and task files remain in the coordinator's case store.
        return _tool_result({'case_set_id': cases.request_id, 'case_count': len(cases.cases), 'recipe_digest': cases.recipe_digest})
    if operation == "structures":
        return _tool_result(assessment.comparison_choices(arguments["plan_id"]))
    if operation == "budget":
        return _tool_result(assessment.budget_preview(arguments["plan_id"]))
    if operation == "select_structure":
        selected_plan = assessment.select_structure(arguments["plan_id"], arguments["structure"])
        return _tool_result({"plan": selected_plan.model_dump(mode="json"), "review_required": True, "budget": assessment.budget_preview(selected_plan.plan_id)})
    if operation == "generate_definition":
        from .planning import generate
        proposal = await generate(assessment, arguments["planning_id"])
        return _tool_result({"proposal": proposal.model_dump(mode="json"), "review_required": True})
    if operation == "start":
        assessment_id = assessment.enqueue(arguments["plan_id"])
        if assessment.status(assessment_id)["state"] == "queued":
            process = await asyncio.to_thread(
                subprocess.Popen,
                [
                    sys.executable,
                    "-m",
                    "aeep.assessment.worker",
                    "--manifest",
                    str(manifest),
                    "--directory",
                    str(assessment.directory),
                    "--assessment",
                    assessment_id,
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env={
                    key: value
                    for key, value in os.environ.items()
                    if key in {"PATH", "SYSTEMROOT", "PYTHONPATH", "HOME", "USERPROFILE"}
                },
                start_new_session=True,
            )
            service.assessment_workers = [
                worker for worker in service.assessment_workers if worker.poll() is None
            ]
            service.assessment_workers.append(process)
        return _tool_result({"assessment_id": assessment_id, "budget": assessment.budget_preview(arguments["plan_id"])})
    assessment_id = arguments["assessment_id"]
    if operation == "cancel":
        assessment.cancel(assessment_id)
    job = assessment.status(assessment_id)
    return _tool_result(
        assessment.repository.get("report", job["report_id"])
        if operation == "report" and job["report_id"]
        else job
    )
