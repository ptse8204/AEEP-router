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


def main(argv: list[str] | None = None) -> None:
    from .cli import read_bytes

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    bind = commands.add_parser('bind', help='Print a named binding for existing plan/source files; no writes')
    bind.add_argument('--plan', type=Path, required=True)
    bind.add_argument('--source', type=Path, required=True)
    bind.add_argument('--configuration', required=True)
    for name in ('plan', 'run', 'report'):
        command = commands.add_parser(name)
        command.add_argument('--workflow', type=Path, required=True)
        command.add_argument('--configuration', required=True)
        if name != 'plan':
            command.add_argument('--reviewed-digest', required=True)
            command.add_argument('--manifest', type=Path, required=True)
            command.add_argument('--directory', type=Path)
            command.add_argument('--output', type=Path, required=True)
        if name == 'report':
            command.add_argument('--report-id', required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == 'bind':
            files = {name: WorkflowFile(path=str(getattr(args, name).absolute()),
                     sha256=hashlib.sha256(read_bytes(getattr(args, name))).hexdigest())
                     for name in ('plan', 'source')}
            workflow = EvaluationWorkflow(configurations={args.configuration: WorkflowConfiguration(**files)})
            print(workflow.model_dump_json(indent=2))
            return
        preview, plan, source = prepare(args.workflow, args.configuration)
        if args.operation == 'plan':
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
            delegated += ['--reviewed-digest', preview['backend_review']['review_sha256']]
        else:
            delegated += ['--report-id', args.report_id]
        managed_main(delegated)
    except (ValueError, OSError):
        parser.exit(2, 'Workflow inputs or exact review are invalid. No automatic retry.\n')


if __name__ == '__main__':
    main()
