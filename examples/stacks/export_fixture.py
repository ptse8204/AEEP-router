"""Write an isolated offline fixture for the stack CLI; never overwrite files."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from aeep.examples.stack_fixtures import fixture


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('family', choices=['media', 'data', 'research'])
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=False)
    manifest, goal, inputs = fixture(args.family, database=str((args.directory / 'state.db').resolve()))
    for name, value in [('manifest', manifest.model_dump(mode='json')),
                        ('goal', goal.model_dump(mode='json')), ('inputs', inputs)]:
        (args.directory / f'{name}.json').write_text(json.dumps(value, indent=2) + '\n')


if __name__ == '__main__':
    main()
