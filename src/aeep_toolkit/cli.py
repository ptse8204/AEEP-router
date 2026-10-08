"""Local toolkit commands; parsing a preview never initializes legacy services."""

from __future__ import annotations

import argparse
import json
import os
import stat
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from .installation import PROFILES, InstalledObservation, PreviewPolicy, preview
from .models import ExtensionRegistry


def read_json(path: Path) -> Any:
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
        if not stat.S_ISREG(os.fstat(handle.fileno()).st_mode):
            raise ValueError('metadata must be a regular file')
        raw = handle.read(1024 * 1024 + 1)
    if len(raw) > 1024 * 1024:
        raise ValueError('metadata exceeds the 1 MiB limit')
    return json.loads(raw)


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
    args = parser.parse_args(argv)
    try:
        registry = ExtensionRegistry.model_validate(read_json(args.registry)) if args.registry else ExtensionRegistry(extensions=())
        if args.command == 'list':
            roles = PROFILES[args.profile]['roles']
            known = json.loads(Path(__file__).with_name('catalog.json').read_text())
            data = {'profile': PROFILES[args.profile]['name'], 'selected': [],
                    'catalog': [item for item in known if item['role'] in roles],
                    'provided_manifests': [item.model_dump(mode='json') for item in registry.extensions if item.role in roles],
                    'notice': 'Source-reviewed catalog only. Installed/enabled state is unknown; artifact manifests and runtime qualification remain required.'}
            print(json.dumps(data, indent=2))
            return 0
        observations = tuple(InstalledObservation.model_validate(item) for item in read_json(args.observations)) if args.observations else ()
        result = preview(registry, tuple(args.select), PreviewPolicy.model_validate(read_json(args.policy)),
                         profile=args.profile, observations=observations)
        print(result.model_dump_json(indent=2))
        return 2 if result.blockers else 0
    except (OSError, ValueError, TypeError, KeyError, ValidationError):
        # Parse errors can contain secret-bearing user values; do not echo them.
        parser.exit(2, 'Cannot read or validate toolkit metadata; check the supplied files and schemas.\n')


if __name__ == '__main__':
    raise SystemExit(main())
