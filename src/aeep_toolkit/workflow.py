"""Select exact assessment inputs; execution stays in the existing managed bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ContractModel, Digest, Identifier, SourcePin


class WorkflowFile(ContractModel):
    path: str = Field(min_length=1, max_length=4096)
    sha256: Digest

    @model_validator(mode='after')
    def bounded_path(self) -> WorkflowFile:
        if '\\' in self.path or '\x00' in self.path or '..' in PurePosixPath(self.path).parts:
            raise ValueError('workflow inputs require bounded paths without traversal')
        return self


class WorkflowConfiguration(ContractModel):
    plan: WorkflowFile
    source: WorkflowFile


class EvaluationWorkflow(ContractModel):
    schema_version: Literal['aeep.toolkit.workflow.v1'] = 'aeep.toolkit.workflow.v1'
    backend: Literal['managed'] = 'managed'
    configurations: dict[Identifier, WorkflowConfiguration] = Field(min_length=1, max_length=16)


class CandidateBinding(ContractModel):
    path: str = Field(min_length=1, max_length=4096)
    sha256: Digest


class StackConfiguration(ContractModel):
    evaluator: Literal['managed', 'agent-skill-eval', 'waza', 'skillrank']
    candidate: CandidateBinding
    benchmark: WorkflowFile
    asset_root: str = Field(min_length=1, max_length=4096)
    task_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    components: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    assessment: WorkflowConfiguration | None = None
    benchmark_recipe: WorkflowFile | None = None

    @model_validator(mode='after')
    def explicit_selection(self) -> StackConfiguration:
        if len(set(self.task_ids)) != len(self.task_ids) or len(set(self.components)) != len(self.components):
            raise ValueError('workflow tasks and components must be distinct')
        return self


class StackWorkflow(ContractModel):
    schema_version: Literal['aeep.toolkit.workflow.v2'] = 'aeep.toolkit.workflow.v2'
    registry: WorkflowFile
    policy: WorkflowFile
    configurations: dict[Identifier, StackConfiguration] = Field(min_length=1, max_length=16)


def _read(binding: WorkflowFile, root: Path) -> tuple[Path, bytes]:
    from .cli import read_bytes

    path = Path(binding.path)
    path = path if path.is_absolute() else root / path
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('workflow input parents cannot be symlinks')
    raw = read_bytes(path)
    if hashlib.sha256(raw).hexdigest() != binding.sha256:
        raise ValueError('workflow input changed after binding')
    return path.absolute(), raw


def prepare(definition: Path, configuration: str) -> tuple[dict[str, Any], Path, Path]:
    """Read metadata only. Current authority/conformance are deliberately not inferred."""
    from aeep.assessment.models import AssessmentPlan, content_digest

    from .cli import read_json
    from .managed import plan_preview

    workflow = EvaluationWorkflow.model_validate(read_json(definition))
    if configuration not in workflow.configurations:
        raise ValueError('unknown workflow configuration')
    selected = workflow.configurations[configuration]
    plan_path, plan_raw = _read(selected.plan, definition.absolute().parent)
    source_path, source_raw = _read(selected.source, definition.absolute().parent)
    plan = AssessmentPlan.model_validate_json(plan_raw)
    source = SourcePin.model_validate_json(source_raw)
    comparison = plan.comparison
    if comparison is None or comparison.structure != 'controlled_agent' or comparison.experiment is None:
        raise ValueError('managed workflow requires an existing controlled-agent experiment')
    backend = plan_preview(plan, source)
    facts = {
        'workflow': workflow.model_dump(mode='json'),
        'configuration': configuration,
        'backend_review': backend,
    }
    preview = {
        **facts,
        'review_sha256': content_digest(facts),
        'case_count': len(plan.suite.cases),
        'task_families': sorted({case.template_family for case in plan.suite.cases if case.template_family}),
        'candidate_inventory': comparison.experiment.environment.candidate_inventory,
        'exposure': comparison.experiment.exposure,
        'stage': comparison.experiment.stage,
        'gates': {
            'stack_integration': 'NOT_VERIFIED_BY_PREVIEW',
            'candidate_usefulness': 'NOT_ASSESSED',
            'selection_usefulness': 'NOT_ASSESSED',
        },
        'notice': 'Metadata selection only. No grant, worker, installation or model is started. Execution rechecks the canonical plan, source, authority, accounting and conformance through the existing service. A named configuration does not qualify its capability bundle.',
    }
    return preview, plan_path, source_path


def prepare_stack(definition: Path, configuration: str) -> dict[str, Any]:
    """Inspect the complete selected stack; never create a plan, grant or runtime."""
    from aeep.assessment.models import content_digest

    from .benchmarks import BenchmarkPack, inspect_pack
    from .candidate import inspect
    from .cli import read_json
    from .installation import PreviewPolicy, preview
    from .models import ExtensionRegistry

    workflow = StackWorkflow.model_validate(read_json(definition))
    if configuration not in workflow.configurations:
        raise ValueError('unknown stack configuration')
    selected = workflow.configurations[configuration]
    root = definition.absolute().parent
    _, registry_raw = _read(workflow.registry, root)
    _, policy_raw = _read(workflow.policy, root)
    registry = ExtensionRegistry.model_validate_json(registry_raw)
    policy = PreviewPolicy.model_validate_json(policy_raw)
    pack_path, pack_raw = _read(selected.benchmark, root)
    pack = BenchmarkPack.model_validate_json(pack_raw)
    candidate_path = Path(selected.candidate.path)
    candidate_path = candidate_path if candidate_path.is_absolute() else root/candidate_path
    candidate = inspect(candidate_path.absolute())
    if candidate.sha256 != selected.candidate.sha256:
        raise ValueError('selected candidate bytes changed')
    asset_root = Path(selected.asset_root)
    asset_root = asset_root if asset_root.is_absolute() else root/asset_root
    tasks = inspect_pack(pack, asset_root.absolute(), selected.task_ids)
    installation = preview(registry, selected.components, policy, profile='full')
    engine = 'aeep-evaluator' if selected.evaluator == 'managed' else selected.evaluator
    if engine not in selected.components or pack.pack_id not in selected.components:
        raise ValueError('selected evaluator and benchmark pack must be explicit components')
    blockers = list(installation.blockers)
    if any(task.rights_review_ref is None for task in pack.tasks if task.task_id in selected.task_ids):
        blockers.append('selected task asset rights have no exact review reference')
    assessment = None
    if selected.assessment is None:
        blockers.append('canonical assessment preparation and applicable worker/grader evidence remain required')
    else:
        plan_path, plan_raw = _read(selected.assessment.plan, root)
        source_path, source_raw = _read(selected.assessment.source, root)
        from aeep.assessment.models import AssessmentPlan, RecipeDefinition

        from .managed import plan_preview
        plan = AssessmentPlan.model_validate_json(plan_raw)
        source = SourcePin.model_validate_json(source_raw)
        if source.artifact_sha256 != candidate.sha256:
            raise ValueError('assessment source differs from the selected candidate package')
        if {case.action.input.get('task_id') for case in plan.suite.cases} != set(selected.task_ids):
            raise ValueError('canonical assessment task selection differs from the benchmark pack')
        if selected.benchmark_recipe is None:
            blockers.append('canonical grader recipe has no selected task-pack binding')
        else:
            _, recipe_raw = _read(selected.benchmark_recipe, root)
            recipe = RecipeDefinition.model_validate_json(recipe_raw)
            if (content_digest(recipe) != plan.recipe_digest
                    or recipe.dependencies.get('benchmark_pack') != content_digest(pack.model_dump(mode='json'))):
                raise ValueError('canonical grader recipe differs from the exact task-pack assets')
        assessment = {'plan_path':str(plan_path), 'source_path':str(source_path),
                      'backend_review':plan_preview(plan, source)}
    if selected.evaluator != 'managed':
        blockers.append('selected external evaluator workflow dispatch is not implemented; no fallback is inferred')
    facts = {'workflow':workflow.model_dump(mode='json'), 'configuration':configuration,
             'candidate':candidate.describe(), 'benchmark':tasks, 'benchmark_path':str(pack_path),
             'installation':installation.model_dump(mode='json'), 'assessment':assessment}
    return {**facts, 'review_sha256':content_digest(facts), 'blockers':blockers,
            'gates':{'stack_integration':'NOT_VERIFIED_BY_PREVIEW', 'candidate_usefulness':'NOT_ASSESSED',
                     'selection_usefulness':'NOT_ASSESSED'},
            'notice':'Complete selected metadata only. No installation, definition review, canonical plan creation or execution. Dispatch additionally requires current all-integration evidence.'}


def main(argv: list[str] | None = None) -> None:
    from .cli import read_bytes

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    bind = commands.add_parser('bind', help='Print a named binding for existing plan/source files; no writes')
    bind.add_argument('--plan', type=Path, required=True)
    bind.add_argument('--source', type=Path, required=True)
    bind.add_argument('--configuration', required=True)
    for name in ('plan', 'prepare', 'run', 'report'):
        command = commands.add_parser(name)
        command.add_argument('--workflow', type=Path, required=True)
        command.add_argument('--configuration', required=True)
        if name in {'run', 'report'}:
            command.add_argument('--reviewed-digest', required=True)
            command.add_argument('--manifest', type=Path, required=True)
            command.add_argument('--directory', type=Path)
            command.add_argument('--output', type=Path, required=True)
        if name == 'report':
            command.add_argument('--report-id', required=True)
        if name == 'run':
            command.add_argument('--stack-readiness', help='Canonical current-source all-integration completion record')
            command.add_argument('--engineering-review', help='Canonical finite required-use integration review')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'bind':
            files = {name: WorkflowFile(path=str(getattr(args, name).absolute()),
                     sha256=hashlib.sha256(read_bytes(getattr(args, name))).hexdigest())
                     for name in ('plan', 'source')}
            workflow = EvaluationWorkflow(configurations={args.configuration: WorkflowConfiguration(**files)})
            print(workflow.model_dump_json(indent=2))
            return
        from .cli import read_json
        version = read_json(args.workflow).get('schema_version', 'aeep.toolkit.workflow.v1')
        if version == 'aeep.toolkit.workflow.v2':
            preview = prepare_stack(args.workflow, args.configuration)
            if args.operation in {'plan', 'prepare'}:
                print(json.dumps(preview, indent=2))
                return
            if preview['blockers'] or preview['assessment'] is None:
                raise ValueError('selected stack is not executable')
            plan, source = Path(preview['assessment']['plan_path']), Path(preview['assessment']['source_path'])
            backend_review = preview['assessment']['backend_review']
        else:
            preview, plan, source = prepare(args.workflow, args.configuration)
            backend_review = preview['backend_review']
        if args.operation in {'plan', 'prepare'}:
            print(json.dumps(preview, indent=2))
            return
        if args.reviewed_digest != preview['review_sha256']:
            raise ValueError('exact selected workflow review required')
        from .managed import main as managed_main

        # This fixed argv delegates all execution/export and recovery to the existing path.
        delegated = [args.operation, '--plan', str(plan), '--source', str(source),
                     '--manifest', str(args.manifest), '--output', str(args.output)]
        if args.directory is not None:
            delegated += ['--directory', str(args.directory)]
        if args.operation == 'run':
            if args.stack_readiness is not None:
                delegated += ['--stack-readiness', args.stack_readiness]
            if args.engineering_review is not None:
                delegated += ['--engineering-review', args.engineering_review]
            delegated += ['--reviewed-digest', backend_review['review_sha256']]
        else:
            delegated += ['--report-id', args.report_id]
        managed_main(delegated)
    except (ValueError, OSError):
        parser.exit(2, 'Workflow inputs or exact review are invalid. No automatic retry.\n')


if __name__ == '__main__':
    main()
