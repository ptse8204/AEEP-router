"""Select exact assessment inputs; execution stays in the existing managed bridge."""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, SerializerFunctionWrapHandler, model_serializer, model_validator

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


class SetupFiles(ContractModel):
    request: WorkflowFile
    source: WorkflowFile
    manifest: WorkflowFile


class WorkflowRuntimeBinding(ContractModel):
    installation: WorkflowFile
    components: dict[Identifier, Identifier] = Field(min_length=1, max_length=32)
    references: tuple[WorkflowFile, ...] = Field(default=(), max_length=16)

    @model_serializer(mode='wrap')
    def preserve_existing(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if not self.references:
            result.pop('references', None)
        return result


class StackConfiguration(ContractModel):
    evaluator: Literal['managed', 'agent-skill-eval', 'waza', 'skillrank']
    candidate: CandidateBinding
    benchmark: WorkflowFile
    asset_root: str = Field(min_length=1, max_length=4096)
    task_ids: tuple[Identifier, ...] = Field(min_length=1, max_length=256)
    components: tuple[Identifier, ...] = Field(min_length=1, max_length=32)
    assessment: WorkflowConfiguration | None = None
    benchmark_recipe: WorkflowFile | None = None
    preparation: SetupFiles | None = None
    scheduler: WorkflowFile | None = None
    scanner: WorkflowFile | None = None
    catalog: WorkflowFile | None = None
    runtimes: dict[Identifier, WorkflowRuntimeBinding] = Field(default_factory=dict, max_length=16)

    @model_serializer(mode='wrap')
    def preserve_existing(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        result: dict[str, Any] = handler(self)
        if self.scheduler is None:
            result.pop('scheduler', None)
        if self.scanner is None:
            result.pop('scanner', None)
        if self.catalog is None:
            result.pop('catalog', None)
        if not self.runtimes:
            result.pop('runtimes', None)
        return result

    @model_validator(mode='after')
    def explicit_selection(self) -> StackConfiguration:
        if len(set(self.task_ids)) != len(self.task_ids) or len(set(self.components)) != len(self.components):
            raise ValueError('workflow tasks and components must be distinct')
        if any(not set(binding.components) <= set(self.components) for binding in self.runtimes.values()):
            raise ValueError('runtime bindings may provide selected components only')
        if self.scanner is not None and 'skill-scanner' not in self.components:
            raise ValueError('scanner binding requires explicit component selection')
        if self.catalog is not None and 'skillrank' not in self.components:
            raise ValueError('catalog binding requires explicit SkillRank selection')
        if self.assessment is not None and self.preparation is not None:
            raise ValueError('select either an existing assessment or canonical preparation inputs')
        return self


class StackWorkflow(ContractModel):
    schema_version: Literal['aeep.toolkit.workflow.v2'] = 'aeep.toolkit.workflow.v2'
    registry: WorkflowFile
    policy: WorkflowFile
    configurations: dict[Identifier, StackConfiguration] = Field(min_length=1, max_length=16)


def _read(binding: WorkflowFile, root: Path, *, integration_plan: bool = False) -> tuple[Path, bytes]:
    from .cli import read_bytes, read_plan_bytes

    path = Path(binding.path)
    path = path if path.is_absolute() else root / path
    if any(parent.is_symlink() for parent in path.parents):
        raise ValueError('workflow input parents cannot be symlinks')
    raw = read_plan_bytes(path) if integration_plan else read_bytes(path)
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
    """Inspect the selected stack; canonical preparation is a separate explicit step."""
    from aeep.assessment.models import content_digest

    from .benchmarks import BenchmarkPack, inspect_pack, parse_pack
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
    pack = parse_pack(json.loads(pack_raw))
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
    if not isinstance(pack, BenchmarkPack):
        blockers.append('MCP state-output execution requires a reviewed ToolHive/server binding and protected database verifier; file recipes cannot execute this pack')
    if any(task.rights_review_ref is None for task in pack.tasks if task.task_id in selected.task_ids):
        blockers.append('selected task asset rights have no exact review reference')
    assessment = None
    preparation = None
    if selected.preparation is not None:
        from aeep.assessment.models import AssessmentSetupRequest, RecipeDefinition

        request_path, request_raw = _read(selected.preparation.request, root)
        source_path, source_raw = _read(selected.preparation.source, root)
        manifest_path, _ = _read(selected.preparation.manifest, root)
        request = AssessmentSetupRequest.model_validate_json(request_raw)
        source = SourcePin.model_validate_json(source_raw)
        if source.artifact_sha256 != candidate.sha256:
            raise ValueError('preparation source differs from the selected candidate package')
        if selected.benchmark_recipe is None:
            raise ValueError('canonical preparation requires the exact benchmark recipe')
        _, recipe_raw = _read(selected.benchmark_recipe, root)
        recipe = RecipeDefinition.model_validate_json(recipe_raw)
        if recipe.dependencies.get('benchmark_pack') != content_digest(pack.model_dump(mode='json')):
            raise ValueError('preparation recipe differs from the selected pack')
        preparation = {'request_path':str(request_path), 'source_path':str(source_path),
                       'manifest_path':str(manifest_path), 'request':request.model_dump(mode='json'),
                       'recipe_digest':content_digest(recipe)}
        blockers.append('canonical plan preparation is selected but has not been performed')
    elif selected.assessment is None:
        blockers.append('canonical assessment preparation and applicable worker/grader evidence remain required')
    else:
        plan_path, plan_raw = _read(selected.assessment.plan, root, integration_plan=True)
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
    scheduler_binding: dict[str, str] | None = None
    if selected.scheduler is not None:
        from aeep.assessment.scheduling import SchedulerDefinition

        scheduler_path, scheduler_raw = _read(selected.scheduler, root)
        scheduler = SchedulerDefinition.model_validate_json(scheduler_raw)
        if selected.evaluator != 'agent-skill-eval' or scheduler.adapter_id != 'agent-skill-eval.controlled.v1':
            raise ValueError('selected evaluator differs from the scheduling definition')
        reference = content_digest(scheduler)
        if preparation is not None and request.scheduler_digest != reference:
            raise ValueError('setup request differs from the selected scheduler')
        if assessment is not None and plan.scheduler_digest != reference:
            raise ValueError('canonical plan differs from the selected scheduler')
        scheduler_binding = {'path':str(scheduler_path), 'definition_ref':reference}
    if selected.evaluator not in {'managed', 'agent-skill-eval'} or (selected.evaluator == 'agent-skill-eval' and scheduler_binding is None):
        blockers.append('selected external evaluator workflow dispatch is not implemented; no fallback is inferred')
    if selected.evaluator == 'managed' and (
            (preparation is not None and request.scheduler_digest is not None)
            or (assessment is not None and plan.scheduler_digest is not None)):
        raise ValueError('managed selection cannot run an external scheduler plan')
    scanner_preview = None
    if selected.scanner is not None:
        from .workflow_security import scan_preview
        scanner_preview, _, _ = scan_preview(definition, configuration)
    runtime_setup = None
    if selected.runtimes:
        from .workflow_runtime import lifecycle_preview

        runtime_setup, _ = lifecycle_preview(definition, configuration, tuple(selected.runtimes), operation='setup')
        blockers.extend(runtime_setup['blockers'])
    from aeep.assessment.verification import verification_source_digest

    facts: dict[str, Any] = {'workflow':workflow.model_dump(mode='json'), 'configuration':configuration,
             'candidate':candidate.describe(), 'benchmark':tasks, 'benchmark_path':str(pack_path),
             'installation':installation.model_dump(mode='json'), 'assessment':assessment,
             'preparation':preparation, 'implementation_source':verification_source_digest(Path(__file__).parents[2])}
    if scheduler_binding is not None:
        facts['scheduler'] = scheduler_binding
    if scanner_preview is not None:
        facts['scanner'] = scanner_preview
    if runtime_setup is not None:
        facts['runtime_setup'] = {name:runtime_setup[name] for name in ('review_sha256','installation_plans','observations','blockers')}
    if selected.catalog is not None:
        from .workflow_catalog import CatalogRuntimeDefinition
        _, catalog_raw = _read(selected.catalog, root)
        catalog_definition = CatalogRuntimeDefinition.model_validate_json(catalog_raw)
        if catalog_definition.runtime_id not in selected.runtimes:
            raise ValueError('catalog definition refers to an unselected runtime')
        facts['catalog'] = {'definition_ref':content_digest(catalog_definition),
                            'functional_readiness':'NOT_VERIFIED_BY_PREVIEW'}
    return {**facts, 'review_sha256':content_digest(facts), 'blockers':blockers,
            'gates':{'stack_integration':'NOT_VERIFIED_BY_PREVIEW', 'candidate_usefulness':'NOT_ASSESSED',
                     'selection_usefulness':'NOT_ASSESSED'},
            'notice':'Complete selected metadata only. No installation, definition review, canonical plan creation or execution. Dispatch additionally requires current all-integration evidence.'}


def main(argv: list[str] | None = None) -> None:
    from aeep.errors import ConfigurationError

    from .cli import read_bytes

    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    bind = commands.add_parser('bind', help='Print a named binding for existing plan/source files; no writes')
    bind.add_argument('--plan', type=Path, required=True)
    bind.add_argument('--source', type=Path, required=True)
    bind.add_argument('--configuration', required=True)
    rights = commands.add_parser('define-rights', help='Store an inert exact task-asset rights determination; grants no authority')
    rights.add_argument('--file', type=Path, required=True)
    rights.add_argument('--manifest', type=Path, required=True)
    scheduler = commands.add_parser('define-scheduler', help='Store an inert external scheduling definition; grants no authority')
    scheduler.add_argument('--file', type=Path, required=True)
    scheduler.add_argument('--manifest', type=Path, required=True)
    accounting = commands.add_parser('define-accounting', help='Store an inert workflow overhead scope; grants no authority')
    accounting.add_argument('--file', type=Path, required=True)
    accounting.add_argument('--manifest', type=Path, required=True)
    for name in ('plan', 'prepare', 'run', 'report'):
        command = commands.add_parser(name)
        command.add_argument('--workflow', type=Path, required=True)
        command.add_argument('--configuration', required=True)
        command.add_argument('--accounting', type=Path, help='Exact reviewed scope for canonical workflow overhead accounting')
        command.add_argument('--operation-id', help='Fresh durable accounting identity; never reuse or reset after interruption')
        if name in {'run', 'report'}:
            command.add_argument('--reviewed-digest', required=True)
            command.add_argument('--manifest', type=Path, required=True)
            command.add_argument('--directory', type=Path)
            command.add_argument('--output', type=Path, required=True)
        if name == 'prepare':
            command.add_argument('--write-plan', type=Path, help='Explicitly draft canonical records and bound files in a new output directory')
            command.add_argument('--reviewed-digest', help='Exact inert workflow preview being prepared')
            command.add_argument('--directory', type=Path)
        if name == 'report':
            command.add_argument('--report-id', required=True)
        command.add_argument('--scan-report', help='Canonical selected scanner observation; required only when configured')
        if name == 'run':
            command.add_argument('--stack-readiness', help='Canonical current-source all-integration completion record')
            command.add_argument('--engineering-review', help='Canonical finite required-use integration review')
    scan_command = commands.add_parser('scan', help='Explicit static scanning through the existing contained executor')
    scan_command.add_argument('--workflow', type=Path, required=True)
    scan_command.add_argument('--configuration', required=True)
    scan_command.add_argument('--accounting', type=Path)
    scan_command.add_argument('--operation-id')
    scan_command.add_argument('--reviewed-digest')
    define_scanner = commands.add_parser('define-scanner', help='Store an inert scanner runtime definition; no review or execution')
    define_scanner.add_argument('--file', type=Path, required=True)
    define_scanner.add_argument('--manifest', type=Path, required=True)
    define_catalog = commands.add_parser('define-catalog', help='Store an inert exact catalog runtime definition; no review or execution')
    define_catalog.add_argument('--file', type=Path, required=True)
    define_catalog.add_argument('--manifest', type=Path, required=True)
    catalog_command = commands.add_parser('catalog', help='Explicit selected SkillRank search/show through a reviewed offline worker')
    catalog_command.add_argument('--workflow', type=Path, required=True)
    catalog_command.add_argument('--configuration', required=True)
    catalog_command.add_argument('--mode', choices=('search','show'), required=True)
    catalog_command.add_argument('--value', required=True, help='Metadata query or owner/skill identifier; never flags or a URL')
    catalog_command.add_argument('--accounting', type=Path)
    catalog_command.add_argument('--operation-id')
    catalog_command.add_argument('--reviewed-digest', help='Omit for inert preview; execution requires an accounting v4 scope')
    worker_readiness = commands.add_parser('prepare-worker-readiness',
        help='Draft canonical readiness from settled paired-worker observations; no review or execution')
    worker_readiness.add_argument('--manifest', type=Path, required=True)
    worker_readiness.add_argument('--control-request', required=True)
    worker_readiness.add_argument('--treatment-request', required=True)
    worker_readiness.add_argument('--output', type=Path, required=True)
    for name in ('setup', 'readiness', 'remove'):
        command = commands.add_parser(name, help='Selected private runtimes; functional evidence remains separate')
        command.add_argument('--workflow', type=Path, required=True)
        command.add_argument('--configuration', required=True)
        command.add_argument('--runtime', action='append', required=True, help='Explicit runtime binding; repeat for independent runtimes')
        command.add_argument('--accounting', type=Path, help='Exact accounting v2 scope; required when applying setup/removal')
        command.add_argument('--operation-id')
        command.add_argument('--reviewed-digest', help='Exact operation-specific lifecycle preview; omit for inspection only')
    args = parser.parse_args(argv)
    try:
        if args.operation == 'scan':
            from .workflow_security import scan
            print(json.dumps(scan(args.workflow, args.configuration, accounting=args.accounting,
                operation_key=args.operation_id, reviewed_digest=args.reviewed_digest), indent=2))
            return
        if args.operation == 'catalog':
            from .workflow_catalog import catalog
            print(json.dumps(catalog(args.workflow,args.configuration,args.mode,args.value,
                accounting=args.accounting,operation_key=args.operation_id,reviewed_digest=args.reviewed_digest),indent=2))
            return
        if args.operation == 'prepare-worker-readiness':
            import asyncio

            from aeep.assessment.service import AssessmentService
            from aeep.router import Router

            from .worker_readiness import prepare_readiness

            if args.output.exists() or not args.output.parent.is_dir():
                raise ValueError('worker readiness output requires a new file in an existing directory')
            router = Router.from_manifest(args.manifest)
            try:
                service = AssessmentService(router, args.manifest.absolute().parent / '.aeep/assessments')
                result = prepare_readiness(service, args.control_request, args.treatment_request)
                with args.output.open('x') as stream:
                    json.dump(result, stream, indent=2)
                    stream.write('\n')
                print(json.dumps({'output':str(args.output.absolute()), 'reviewed':False,
                    'execution_authorized':False, 'workers_started':False}))
            finally:
                asyncio.run(router.close())
            return
        if args.operation in {'define-rights', 'define-scheduler', 'define-accounting', 'define-scanner', 'define-catalog'}:
            import asyncio

            from aeep.assessment.repository import AssessmentRepository
            from aeep.assessment.scheduling import SchedulerDefinition
            from aeep.router import Router

            from .workflow_accounting import WorkflowAccountingDefinition
            from .workflow_catalog import CatalogRuntimeDefinition
            from .workflow_preparation import TaskRightsReview
            from .workflow_security import ScannerRuntimeDefinition

            record = (TaskRightsReview.model_validate_json(read_bytes(args.file)) if args.operation == 'define-rights'
                      else WorkflowAccountingDefinition.model_validate_json(read_bytes(args.file)) if args.operation == 'define-accounting'
                      else ScannerRuntimeDefinition.model_validate_json(read_bytes(args.file)) if args.operation == 'define-scanner'
                      else CatalogRuntimeDefinition.model_validate_json(read_bytes(args.file)) if args.operation == 'define-catalog'
                      else SchedulerDefinition.model_validate_json(read_bytes(args.file)))
            kind = ('toolkit_task_rights' if args.operation == 'define-rights' else
                    'toolkit_workflow_accounting' if args.operation == 'define-accounting' else 'toolkit_scanner_runtime' if args.operation == 'define-scanner' else 'toolkit_catalog_runtime' if args.operation == 'define-catalog' else 'scheduler')
            router = Router.from_manifest(args.manifest)
            try:
                from aeep.assessment.models import content_digest

                ref = AssessmentRepository(router.store).put(kind, content_digest(record), record)
                print(json.dumps({'rights_review_ref' if args.operation == 'define-rights' else 'accounting_ref' if args.operation == 'define-accounting' else 'scanner_ref' if args.operation == 'define-scanner' else 'catalog_ref' if args.operation == 'define-catalog' else 'scheduler_ref':ref,
                                  'reviewed':False, 'execution_authorized':False}))
            finally:
                asyncio.run(router.close())
            return
        if args.operation in {'setup', 'readiness', 'remove'}:
            from .workflow_runtime import lifecycle

            result = lifecycle(args.workflow, args.configuration, tuple(args.runtime),
                               operation=args.operation, reviewed_digest=args.reviewed_digest,
                               accounting=args.accounting, operation_key=args.operation_id)
            print(json.dumps(result, indent=2))
            if result.get('complete') is False:
                parser.exit(2, 'Runtime lifecycle has partial failures. Inspect retained journals and costs; no automatic retry.\n')
            return
        if args.operation == 'bind':
            files = {name: WorkflowFile(path=str(getattr(args, name).absolute()),
                     sha256=hashlib.sha256(read_bytes(getattr(args, name))).hexdigest())
                     for name in ('plan', 'source')}
            workflow = EvaluationWorkflow(configurations={args.configuration: WorkflowConfiguration(**files)})
            print(workflow.model_dump_json(indent=2))
            return
        from .workflow_accounting import account_workflow

        with account_workflow(args.accounting, workflow_file=args.workflow,
                              configuration=args.configuration, stage=args.operation,
                              operation_key=args.operation_id,
                              manifest=getattr(args, 'manifest', None)) as meter:
            from .cli import read_json
            version = read_json(args.workflow).get('schema_version', 'aeep.toolkit.workflow.v1')
            if version == 'aeep.toolkit.workflow.v2':
                preview = prepare_stack(args.workflow, args.configuration)
                preview['workflow_accounting'] = meter.describe() if meter else {'coverage': 'NOT_RECORDED'}
                if args.operation == 'prepare' and args.write_plan is not None:
                    from .workflow_preparation import prepare_canonical

                    result = prepare_canonical(args.workflow, args.configuration,
                        reviewed_digest=args.reviewed_digest, destination=args.write_plan,
                        directory=args.directory)
                    result['workflow_accounting'] = meter.describe() if meter else {'coverage': 'NOT_RECORDED'}
                    print(json.dumps(result, indent=2))
                    return
                if args.operation in {'plan', 'prepare'}:
                    print(json.dumps(preview, indent=2))
                    return
                if args.operation == 'run' and any(value['installed'] is not True for value in preview.get('runtime_setup', {}).get('observations', {}).values()):
                    raise ValueError('selected private runtime is absent, changed or unverified')
                if preview['blockers'] or preview['assessment'] is None:
                    raise ValueError('selected stack is not executable')
                plan, source = Path(preview['assessment']['plan_path']), Path(preview['assessment']['source_path'])
                backend_review = preview['assessment']['backend_review']
            else:
                if args.operation == 'prepare' and args.write_plan is not None:
                    raise ValueError('canonical preparation requires an explicit v2 workflow')
                preview, plan, source = prepare(args.workflow, args.configuration)
                preview['workflow_accounting'] = meter.describe() if meter else {'coverage': 'NOT_RECORDED'}
                backend_review = preview['backend_review']
            if args.operation in {'plan', 'prepare'}:
                print(json.dumps(preview, indent=2))
                return
            if args.reviewed_digest != preview['review_sha256']:
                raise ValueError('exact selected workflow review required')
            from aeep.assessment.models import AssessmentPlan

            from .cli import read_plan_bytes
            from .managed import main as managed_main
            from .workflow_accounting import bind_workflow_plan

            if preview.get('scanner') is not None:
                from .workflow_security import require_scan
                if meter is None or meter.repository is None or args.scan_report is None:
                    raise ValueError('selected scanner needs a canonical scan report and workflow accounting')
                scan_record = require_scan(meter.repository, args.scan_report, args.workflow, args.configuration)
                meter.component_refs['skill-scanner'] = args.scan_report
                meter.component_observations['skill-scanner'] = {
                    'scan_ref': args.scan_report, 'receipt_ref': scan_record.receipt_ref,
                    'execution_evidence_ref': scan_record.execution_evidence_ref,
                    'candidate_sha256': scan_record.candidate_sha256, **scan_record.observations}
            elif args.scan_report is not None:
                raise ValueError('unselected scanner evidence cannot be attached')
            bind_workflow_plan(AssessmentPlan.model_validate_json(read_plan_bytes(plan)), args.manifest)

            # This fixed argv delegates all execution/export and recovery to the existing path.
            delegated = [args.operation, '--plan', str(plan), '--source', str(source),
                         '--manifest', str(args.manifest), '--output', str(args.output)]
            if 'scheduler' in preview:
                delegated += ['--scheduler', preview['scheduler']['path']]
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
    except (ValueError, OSError, ConfigurationError, sqlite3.Error):
        parser.exit(2, 'Workflow inputs or exact review are invalid. No automatic retry.\n')


if __name__ == '__main__':
    main()
