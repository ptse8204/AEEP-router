"""Fixed offline website fixture with an operator-owned independent verifier."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import stat
import sys
from datetime import timedelta
from pathlib import Path

from aeep.assessment.models import RecipeDefinition
from aeep.assessment.repository import AssessmentRepository
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService, MCPProtocolApp
from aeep.models import (
    ActionConstraints,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    PolicyConfig,
    SideEffect,
    TaskScope,
    ValidationKind,
    ValidationSpec,
    utc_now,
)
from aeep.router import Router
from aeep.validators import ValidationContext

NAME = 'operator.website.fixed.v1'
TOOL = 'aeep_recipe_' + hashlib.sha256(b'local.website.fixed@1').hexdigest()[:12]
HTML = '<!doctype html><html lang="en"><head><title>Fixture</title><link rel="stylesheet" href="style.css"></head><body><h1>Draft</h1><aside>Preserve literal content</aside></body></html>'
STYLE = 'body { color: #222; background: #fff; }\n'
NOTE = 'Keep this unrelated operator note.\n'
LATER_NOTE = 'Added after build; keep.\n'


def sha(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ConfigurationError('website pinned file must be regular')
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def prepare(root: Path, codex: Path, python: Path) -> dict[str, str]:
    """Create a new fixture and INERT scope; review and activation stay operator actions."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=False)
    data = root / 'data'
    data.mkdir()
    (root / '.aeep').mkdir()
    files = {'index.html': HTML, 'style.css': STYLE, 'note.txt': NOTE}
    for name, text in files.items():
        (data / name).write_text(text)
    expected = {op: {**files, 'index.html': HTML.replace('<h1>Draft</h1>', '<h1>' + title + '</h1>')}
                for op, title in [('build', 'Verified local website'), ('edit', 'Verified updated website')]}
    oracle = root / '.aeep' / 'website-oracle.json'
    oracle.write_text(json.dumps(expected, sort_keys=True) + '\n')
    boundary = NativeSandboxConfig(binary=str(codex.resolve()), binary_sha256='sha256:' + sha(codex.resolve()),
        project_root=str(root), read_roots=[str(python.resolve().parents[1]), str(data)],
        write_roots=[str(data)], deny_roots=[str(root / '.aeep')], single_process=True,
        python_binary=str(python.resolve()), python_sha256='sha256:' + sha(python.resolve()))
    program = ('import json,sys;from pathlib import Path;x=json.load(sys.stdin);p=Path('
        + repr(str(data / 'index.html')) + ');text=p.read_text();old,new={"build":'
        + '("<h1>Draft</h1>","<h1>Verified local website</h1>"),"edit":'
        + '("<h1>Verified local website</h1>","<h1>Verified updated website</h1>")}[x["operation"]];'
        + 'assert text.count(old)==1;p.write_text(text.replace(old,new));'
        + 'print(json.dumps({"operation":x["operation"],"updated":"index.html"}))')
    spec = ExecutorSpec(id='local.website.fixed', capability='local.website.fixed@1',
        kind=ExecutorKind.COMMAND, description='Fixed offline website build/edit fixture; no publishing.',
        side_effect=SideEffect.WRITE, idempotent=False, input_schema={'type': 'object', 'required': ['operation'],
            'additionalProperties': False, 'properties': {'operation': {'enum': ['build', 'edit']}}},
        output_schema={'type': 'object', 'required': ['operation', 'updated'], 'additionalProperties': False,
            'properties': {'operation': {'enum': ['build', 'edit']}, 'updated': {'const': 'index.html'}}},
        config={'argv': [str(python.resolve()), '-I', '-c', program], 'argv_literal': True,
            'stdin_json': True, 'output': {'type': 'json'}, 'timeout_seconds': 15,
            'native_sandbox': boundary.model_dump(mode='json')},
        validators=[ValidationSpec(kind=ValidationKind.CALLBACK,
            config={'name': NAME, 'module_sha256': sha(Path(__file__)), 'oracle_sha256': sha(oracle)})])
    manifest = root / 'aeep.json'
    manifest.write_text(Manifest(database=str(root / '.aeep' / 'state.db'), executors=[spec],
        policies={'balanced': PolicyConfig(constraints=ActionConstraints(max_side_effect=SideEffect.WRITE))}).model_dump_json())
    router = Router.from_manifest(manifest)
    try:
        scope = TaskScope(scope_id='website-build-edit', project_root=str(root),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, approval_ceiling=SideEffect.WRITE,
            max_attempts=2, max_attempt_seconds=15, expires_at=utc_now() + timedelta(hours=1))
        repository = AssessmentRepository(router.store)
        recipe = RecipeDefinition(recipe_id='website-fixed-task-declaration', capability=spec.capability,
            description=spec.description, input_schema=spec.input_schema, output_schema=spec.output_schema,
            generator='record_template:1', grader='exact_match:1', extractor='structural_json:1',
            variations=['fixed'], exclusions=['Task-tool declaration only; not qualification or a website benchmark.'])
        recipe_digest = repository.put('recipe', recipe.recipe_id, recipe)
        digest = repository.put('task_scope', scope.scope_id, scope)
        return {'manifest': str(manifest), 'scope_id': scope.scope_id, 'scope_digest': digest,
                'module_sha256': sha(Path(__file__)), 'oracle_sha256': sha(oracle),
                'recipe_digest': recipe_digest, 'reviewed': 'false'}
    finally:
        router.store.close()


def compose(manifest: Path, activation: str) -> AEEPToolService:
    """Fixed composition; no callback import or evaluated-agent registration interface."""
    router = Router.from_manifest(manifest)
    try:
        spec, = router.manifest.executors
        check, = spec.validators
        oracle = manifest.parent / '.aeep' / 'website-oracle.json'
        if oracle.is_symlink() or not oracle.is_file() or oracle.stat().st_size > 64_000:
            raise ConfigurationError('website verifier oracle is unavailable or unsafe')
        expected_config = {'name': NAME, 'module_sha256': sha(Path(__file__)), 'oracle_sha256': sha(oracle)}
        if check.kind != ValidationKind.CALLBACK or check.config != expected_config:
            raise ConfigurationError('website verifier module or oracle differs from reviewed declaration')
        expected = json.loads(oracle.read_bytes())
        fixed = {op: {'index.html': HTML.replace('<h1>Draft</h1>', '<h1>' + title + '</h1>'),
                      'style.css': STYLE, 'note.txt': NOTE}
                 for op, title in [('build', 'Verified local website'), ('edit', 'Verified updated website')]}
        if expected != fixed:
            raise ConfigurationError('website fixture oracle differs from the fixed task contract')
        data = manifest.parent / 'data'

        def verify(context: ValidationContext) -> bool:
            op = context.input.get('operation')
            if (context.input != {'operation': op} or op not in {'build', 'edit'}
                    or context.output != {'operation': op, 'updated': 'index.html'}
                    or sha(Path(__file__)) != check.config['module_sha256']
                    or sha(oracle) != check.config['oracle_sha256']):
                return False
            files = dict(expected[op])
            if op == 'edit':
                files['later-note.txt'] = LATER_NOTE
            for name, text in files.items():
                path = data / name
                if path.is_symlink() or not path.is_file() or path.stat().st_size > 64_000 or path.read_text() != text:
                    return False
            return True

        router.validator_callbacks[NAME] = verify
        return AEEPToolService(router, profile='task', task_activation=activation,
                               approved_side_effect=SideEffect.WRITE)
    except BaseException:
        router.store.close()
        raise


async def run(args: argparse.Namespace) -> None:
    service = compose(args.manifest.resolve(), args.activation)
    try:
        if args.mode == 'call':
            print(json.dumps(await service.call(service.list_tools()[0]['name'], {'operation': args.operation})))
        else:
            app = MCPProtocolApp(service)
            while line := await asyncio.to_thread(sys.stdin.buffer.readline, 65_537):
                if len(line) > 65_536:
                    raise ConfigurationError('website fixture protocol message exceeds its bound')
                response = await app.handle(json.loads(line))
                if response is not None:
                    print(json.dumps(response), flush=True)
    finally:
        await service.router.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='mode', required=True)
    setup = sub.add_parser('prepare')
    for name in ('root', 'codex', 'python'):
        setup.add_argument('--' + name, type=Path, required=True)
    for mode in ('call', 'mcp'):
        command = sub.add_parser(mode)
        command.add_argument('--manifest', type=Path, required=True)
        command.add_argument('--activation', required=True)
        if mode == 'call':
            command.add_argument('operation', choices=('build', 'edit'))
    args = parser.parse_args()
    if args.mode == 'prepare':
        print(json.dumps(prepare(args.root, args.codex, args.python)))
    else:
        asyncio.run(run(args))


if __name__ == '__main__':
    main()
