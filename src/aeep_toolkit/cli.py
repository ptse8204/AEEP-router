"""Local toolkit commands; parsing a preview never initializes legacy services."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import subprocess
import sys
import sysconfig
import zipfile
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .installation import PROFILES, InstalledObservation, PreviewPolicy, preview
from .models import EvidenceBundle, ExtensionRegistry

METADATA_BYTES = 1024 * 1024
INTEGRATION_PLAN_BYTES = 32 * METADATA_BYTES


def _read_bounded_bytes(path: Path, maximum_bytes: int) -> bytes:
    if path.is_symlink() or path.name.casefold() in {'auth.json', 'credentials.json'} or path.name.casefold().startswith('.env'):
        raise ValueError('credential files and metadata symlinks are excluded')
    resolved = path.resolve(strict=True)
    protected = Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).resolve()
    if resolved.is_relative_to(protected) or any(part.casefold() == '.codex' for part in resolved.parts):
        raise ValueError('Codex state is excluded from toolkit metadata')
    if protected.exists() and any(parent.samefile(protected) for parent in resolved.parents):
        raise ValueError('Codex state aliases are excluded from toolkit metadata')
    fd = os.open(resolved, os.O_RDONLY | os.O_NONBLOCK | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('metadata must be a regular file without hard links')
        if info.st_size > maximum_bytes:
            raise ValueError('input exceeds its bounded reader limit')
        raw = handle.read(maximum_bytes + 1)
    if len(raw) > maximum_bytes:
        raise ValueError('input exceeds its bounded reader limit')
    return raw


def read_bytes(path: Path) -> bytes:
    return _read_bounded_bytes(path, METADATA_BYTES)


def read_plan_bytes(path: Path) -> bytes:
    """Only explicit integration plans may exceed ordinary metadata limits.

    This envelope supports the initial six-task pack and its artifact transfers.
    Callers must still parse the complete AssessmentPlan and verify canonical
    identity and authority. This function never creates a service or job.
    """
    raw = _read_bounded_bytes(path, INTEGRATION_PLAN_BYTES)
    if len(raw) > METADATA_BYTES:
        value = json.loads(raw)
        if not isinstance(value, dict) or value.get('schema_version') not in {'assessment.plan.v7', 'assessment.plan.v8'}:
            raise ValueError('large plan files require the bounded v7 integration contract')
    return raw


def read_json(path: Path) -> Any:
    return json.loads(read_bytes(path))


def doctor(host: str, project: Path) -> dict[str, Any]:
    if host not in {'codex', 'claude', 'dsh', 'deepseek-api'}:
        raise ValueError('unsupported host')
    # check_setup initializes Router/store state; inventory only reads configuration.
    from aeep.errors import ConfigurationError
    from aeep.onboarding import inventory

    project = project.resolve(strict=True)
    if not project.is_dir():
        raise ValueError('doctor requires a project directory')
    try:
        observed = inventory(host, project)
    except (AttributeError, ConfigurationError) as exc:
        raise ValueError('invalid host inventory') from exc
    if len(observed) > 256:
        raise ValueError('host inventory exceeds the bounded view')
    connections = []
    for item in observed:
        name = item.get('name')
        if not isinstance(name, str) or not 0 < len(name) <= 200 or not name.isprintable():
            raise ValueError('invalid connection name')
        connections.append({'name': name, 'configured': True,
                            'enabled_in_configuration': item.get('enabled') if type(item.get('enabled')) is bool else None,
                            'installed': None, 'live_exposure': None, 'qualified': None})
    facts = {'host': host, 'project': str(project), 'connections': connections,
             'source': 'aeep.onboarding.inventory', 'status': 'configuration_only'}
    return {**facts, 'observation_sha256': hashlib.sha256(
        json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        'notice': 'Configuration only: no host process, network probe, authentication check or qualification ran. A configured connection does not prove installation or effective access.'}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog='aeep-toolkit')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('list', 'plan'):
        command = sub.add_parser(name)
        command.add_argument('profile', choices=PROFILES, nargs='?', default='essentials')
        command.add_argument('--registry', type=Path, help='Explicit extension manifests; reading them grants no trust')
        if name == 'plan':
            command.add_argument('--select', action='append', default=[])
            command.add_argument('--policy', type=Path, required=True)
            command.add_argument('--observations', type=Path)
    diagnostic = sub.add_parser('doctor', help='Read project connection metadata without starting services')
    diagnostic.add_argument('--host', choices=('codex', 'claude', 'dsh', 'deepseek-api'), required=True)
    diagnostic.add_argument('--project', type=Path, required=True)
    sub.add_parser('stack-status', help='Print all required integration checks; no readiness or execution is inferred')
    report = sub.add_parser('report', help='Summarize normalized records without executing an evaluator')
    report.add_argument('--evidence', type=Path, required=True)
    report.add_argument('--format', choices=('json', 'markdown', 'html'), default='markdown')
    report.add_argument('--accounting', type=Path, help='Digest-keyed receipt records; contents are not authenticated by this command')
    report.add_argument('--currency', default='USD')
    report.add_argument('--recurring-fee', type=Path, help='Explicit decimal amount/period/source_ref scenario; not an incurred charge')
    portable = sub.add_parser('export-preview', help='Prepare a minimized local sharing document; never publishes')
    portable.add_argument('--evidence', type=Path, required=True)
    portable.add_argument('--disclose-source', action='store_true', help='Include supplied public source metadata in the preview')
    portable.add_argument('--developer', type=Path, help='Exact-source developer assertion; requires --disclose-source and remains unverified')
    trace_preview = sub.add_parser('trace-preview', help='Prepare minimized OTLP/HTTP JSON from a receipt; no exporter or network')
    trace_preview.add_argument('--receipt', type=Path, required=True)
    install_plan = sub.add_parser('install-plan', help='Review a selected closure of local wheels; no writes or execution')
    install_plan.add_argument('--preview', type=Path, required=True)
    install_plan.add_argument('--policy', type=Path, required=True)
    install_plan.add_argument('--wheels', type=Path, required=True)
    install_plan.add_argument('--wheelhouse', type=Path, required=True)
    install_plan.add_argument('--destination', type=Path, required=True)
    for name in ('install', 'remove'):
        operation = sub.add_parser(name, help='Operator-only private runtime installation/removal')
        operation.add_argument('--installation', type=Path, required=True)
        operation.add_argument('--reviewed-digest', required=True)
    candidate = sub.add_parser('candidate', help='Inspect exact local skill payload without executing or installing it')
    candidate.add_argument('path', type=Path)
    candidate.add_argument('--stage', type=Path, help='Explicit new private copy of captured skill bytes; excludes evaluation answers')
    candidate.add_argument('--manifest', type=Path, help='Optionally record the staged subject and measured setup costs; no grant or execution')
    discovery = sub.add_parser('discover', help='Search explicitly configured sources and retain provenance; never install candidates')
    discovery.add_argument('--config', type=Path, required=True)
    discovery.add_argument('--store', type=Path, required=True, help='Discovery provenance database (this command writes records)')
    discovery.add_argument('--source', action='append', required=True)
    discovery.add_argument('--query', required=True, help='Public search phrase, never private task material')
    discovery.add_argument('--limit', type=int, default=20)
    upstream = sub.add_parser('import-report', help='Read upstream observations; never execute software or qualify claims')
    upstream.add_argument('backend', choices=('waza', 'cisco-skill-scanner'))
    upstream.add_argument('--input', type=Path, required=True)
    upstream.add_argument('--revision', required=True, help='Exact supported source revision asserted by the supplier')
    upstream.add_argument('--candidate-sha256', required=True, help='Supplied candidate binding, not independently verified')
    upstream.add_argument('--format', choices=('json', 'markdown', 'html'), default='json')
    evaluation = sub.add_parser('eval', help='Run an explicitly selected existing evaluation backend')
    evaluation.add_argument('backend', choices=('scripted', 'managed'))
    evaluation.add_argument('arguments', nargs=argparse.REMAINDER, help='Backend plan, run or report arguments')
    workflow = sub.add_parser('workflow', help='Select a hash-bound configuration through the existing managed evaluator')
    workflow.add_argument('arguments', nargs=argparse.REMAINDER)
    benchmark = sub.add_parser('benchmark', help='Inspect pinned benchmark packs and protected asset separation; no execution')
    benchmark.add_argument('arguments', nargs=argparse.REMAINDER)
    repository_recipe = sub.add_parser('repository-recipe', help='Export a reviewed repository recipe definition; never executes code')
    repository_recipe.add_argument('--cases', type=Path, required=True)
    repository_recipe.add_argument('--assessment', action='store_true', help='Require distinct curated 8/28/105 campaign cases')
    repository_suite = sub.add_parser('repository-suite-recipe', help='Export a hash-bound repository suite; no execution or installation')
    repository_suite.add_argument('--cases', type=Path, required=True, action='append', help='Repeat for bounded metadata files')
    repository_suite.add_argument('--assessment', action='store_true', help='Require distinct curated 8/28/105 campaign cases')
    selection_report = sub.add_parser('selection-report', help='Score supplied policy decisions; never grants admission')
    selection_report.add_argument('--evaluation', type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'workflow':
            from .workflow import main as workflow_main
            workflow_main(args.arguments)
            return 0
        if args.command == 'repository-suite-recipe':
            from aeep.assessment.repository_suites import (
                RepositorySuiteCase,
                repository_suite_recipe,
            )
            from aeep.errors import ConfigurationError

            try:
                suite_cases = [RepositorySuiteCase.model_validate(case) for path in args.cases for case in read_json(path)]
                recipe = repository_suite_recipe(suite_cases, assessment=args.assessment)
            except ConfigurationError as exc:
                raise ValueError('invalid repository suite metadata') from exc
            print(recipe.model_dump_json(indent=2))
            return 0
        if args.command == 'repository-recipe':
            from aeep.assessment.repository_tasks import RepositoryCase
            from aeep.assessment.repository_tasks import repository_recipe as export_recipe
            cases = [RepositoryCase.model_validate(case) for case in read_json(args.cases)]
            print(export_recipe(cases, assessment=args.assessment).model_dump_json(indent=2))
            return 0
        if args.command == 'selection-report':
            from .selection import SelectionEvaluation, summarize_selection
            print(json.dumps(summarize_selection(SelectionEvaluation.model_validate(read_json(args.evaluation))),
                             indent=2, allow_nan=False))
            return 0
        if args.command == 'trace-preview':
            from aeep.telemetry import receipt_otlp_preview
            print(json.dumps(receipt_otlp_preview(read_json(args.receipt)), indent=2, allow_nan=False))
            return 0
        if args.command == 'import-report':
            from .external import import_result, render_import
            print(render_import(import_result(read_bytes(args.input), args.backend, revision=args.revision,
                                              candidate_sha256=args.candidate_sha256), args.format))
            return 0
        if args.command == 'discover':
            from aeep.discovery import DiscoveryRequest
            from aeep.discovery_service import DiscoveryConfig, DiscoveryService
            from aeep.errors import AEEPError
            from aeep.store import ReceiptStore

            config = DiscoveryConfig.model_validate(read_json(args.config))
            request = DiscoveryRequest(public_query=args.query, source_ids=args.source, limit=args.limit)
            if not set(request.source_ids).issubset(source.source_id for source in config.sources):
                raise ValueError('discovery source is unavailable')
            store = ReceiptStore(args.store)
            try:
                service = DiscoveryService.from_config(store, config, base_directory=args.config.resolve().parent)
                result = asyncio.run(service.search(request))
                print(result.model_dump_json(indent=2))
                return 0 if all(record.status in {'complete', 'fallback'} for record in result.source_records) else 2
            except AEEPError as exc:
                raise ValueError('discovery unavailable or outside configured authority') from exc
            finally:
                store.close()
        if args.command == 'eval':
            if args.backend == 'managed':
                from .managed import main as managed_main
                managed_main(args.arguments)
                return 0
            script = Path(__file__).resolve().parents[2] / 'integrations/toolkit/evaluate.py'
            if not script.is_file():
                script = Path(sysconfig.get_path('data')) / 'share/aeep/integrations/toolkit/evaluate.py'
            if not script.is_file():
                parser.exit(2, 'The scripted backend assets are missing; it is unavailable in this installation.\n')
            # Keep the upstream development bridge's module namespace in its own process.
            return subprocess.run([sys.executable, '-B', str(script), *args.arguments], check=False).returncode
        if args.command == 'benchmark':
            from .benchmarks import main as benchmark_main
            benchmark_main(args.arguments)
            return 0
        if args.command == 'stack-status':
            from .stack_readiness import checklist
            print(json.dumps(checklist(), indent=2))
            return 0
        if args.command == 'candidate':
            from .candidate import inspect, stage_subject
            if args.manifest is not None and args.stage is None:
                raise ValueError('canonical candidate inspection requires an explicit new staged payload')
            candidate_result = (stage_subject(args.path.absolute(), args.stage.absolute(), args.manifest)
                      if args.stage is not None else inspect(args.path.absolute()).describe())
            print(json.dumps(candidate_result, indent=2))
            return 0
        if args.command in {'install-plan', 'install', 'remove'}:
            from aeep.errors import ConfigurationError

            from .install_runtime import RuntimeInstallation, Wheel, apply, digest, prepare, remove
            from .installation import InstallationPreview
            try:
                if args.command == 'install-plan':
                    installation = prepare(InstallationPreview.model_validate(read_json(args.preview)),
                                           PreviewPolicy.model_validate(read_json(args.policy)), args.destination,
                                           args.wheelhouse, tuple(Wheel.model_validate(w) for w in read_json(args.wheels)))
                    install_result = {'review_sha256': digest(installation), 'installation': installation.model_dump(mode='json')}
                else:
                    installation = RuntimeInstallation.model_validate(read_json(args.installation)['installation'])
                    install_result = (apply if args.command == 'install' else remove)(installation, args.reviewed_digest)
                print(json.dumps(install_result, indent=2))
                return 0
            except ConfigurationError as error:
                raise ValueError('installation safety check failed') from error
        if args.command == 'export-preview':
            from .models import DeveloperIdentity
            from .reporting import portable_summary
            exported = portable_summary(EvidenceBundle.model_validate(read_json(args.evidence)),
                                      disclose_source=args.disclose_source,
                                      developer=DeveloperIdentity.model_validate(read_json(args.developer)) if args.developer else None)
            print(json.dumps(exported, indent=2, allow_nan=False))
            return 0
        if args.command == 'report':
            from .reporting import render, summarize
            print(render(summarize(EvidenceBundle.model_validate(read_json(args.evidence)),
                                  accounting_records=read_json(args.accounting) if args.accounting else None,
                                  currency=args.currency, recurring_fee=read_json(args.recurring_fee) if args.recurring_fee else None), args.format), end='')
            return 0
        if args.command == 'doctor':
            print(json.dumps(doctor(args.host, args.project), indent=2))
            return 0
        registry = ExtensionRegistry.model_validate(read_json(args.registry)) if args.registry else ExtensionRegistry(extensions=())
        if args.command == 'list':
            roles = PROFILES[args.profile]['roles']
            known = json.loads(Path(__file__).with_name('catalog.json').read_text())
            data = {'profile': PROFILES[args.profile]['name'], 'selected': [],
                    'catalog': [item for item in known if item['role'] in roles],
                    'provided_manifests': [item.model_dump(mode='json') for item in registry.extensions if item.role in roles],
                    'notice': 'Catalog entries describe their recorded integration scope. Installed/enabled state is unknown; exact installation manifests and applicable runtime qualification remain required.'}
            print(json.dumps(data, indent=2))
            return 0
        observations = tuple(InstalledObservation.model_validate(item) for item in read_json(args.observations)) if args.observations else ()
        installation_preview = preview(registry, tuple(args.select), PreviewPolicy.model_validate(read_json(args.policy)),
                         profile=args.profile, observations=observations)
        print(installation_preview.model_dump_json(indent=2))
        return 2 if installation_preview.blockers else 0
    except (OSError, ValueError, TypeError, KeyError, ValidationError, subprocess.SubprocessError, zipfile.BadZipFile):
        if args.command == 'doctor':
            parser.exit(2, 'Cannot inspect project inventory; use macOS/Linux/WSL and valid regular project configuration files.\n')
        # Parse errors can contain secret-bearing user values; do not echo them.
        parser.exit(2, 'Cannot read or validate toolkit metadata; check the supplied files and schemas.\n')


if __name__ == '__main__':
    raise SystemExit(main())
