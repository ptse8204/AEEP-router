"""Grade a bounded React source patch using the original protected assertions."""

import contextlib
import json
import re
import runpy
import sys
from pathlib import Path, PurePosixPath

ROOT = Path('/opt/aeep-react-reference')
TASK = 'react-performance-debugging'
SOURCE_PATH = re.compile(r'src/(?:[A-Za-z0-9_-]+/)*[A-Za-z0-9_.-]+\.(?:ts|tsx|css)\Z')
FORBIDDEN = {'test', 'tests', '__tests__', 'node_modules'}


def checked_changes(output, base_digest, original_paths, decode):
    patch = decode(output)
    if patch.base_sha256 != base_digest:
        raise ValueError('patch belongs to another task archive')
    combined = {path.casefold(): path for path in original_paths}
    if any(not SOURCE_PATH.fullmatch(path) or set(PurePosixPath(path.casefold()).parts) & FORBIDDEN
           for path in patch.files):
        raise ValueError('patch may change only application source files')
    for path in patch.files:
        prior = combined.setdefault(path.casefold(), path)
        if prior != path:
            raise ValueError('patch contains a case-insensitive path conflict')
    if any(str(parent).casefold() in combined for path in combined.values()
           for parent in PurePosixPath(path).parents):
        raise ValueError('patch has a file and directory conflict')
    return patch.files


def grade(example, pins, *, decode, run):
    expected = pins['task_archive_sha256']
    if (example['input']['task_id'] != TASK
            or example['input']['task_archive_sha256'] != expected
            or example['expected'] != {'task_archive_sha256': expected}):
        raise RuntimeError('protected task binding differs')
    try:
        changes = checked_changes(example['output'], expected, pins['app_files'], decode)
    except (ValueError, TypeError):
        return False, 'output_contract'

    observed = {}
    with contextlib.redirect_stdout(sys.stderr):
        run(observed, changes)
    if observed.get('phase') != 'complete' or len(observed.get('test_statuses', ())) != 11:
        raise RuntimeError('protected assertions did not complete')
    reward = observed['upstream_binary_reward']
    if type(reward) is not int or reward not in {0, 1}:
        raise RuntimeError('protected verifier returned an invalid reward')
    return bool(reward), None if reward == 1 else 'upstream_rejected'


def main():
    if len(sys.argv) != 2 or not Path(sys.argv[1]).is_absolute():
        raise ValueError('reviewed AEEP source mount is required')
    sys.path.append(sys.argv[1])
    from aeep.assessment.repository_suites import decode_patch

    payload = json.load(sys.stdin)
    example, = payload['examples']
    pins = json.loads((ROOT / 'pins.json').read_bytes())
    run = runpy.run_path(str(ROOT / 'verifier-driver.py'))['run']
    valid, detail = grade(example, pins, decode=decode_patch, run=run)
    print(json.dumps({'valid': [valid], 'failure_codes': [detail]}))


if __name__ == '__main__':
    main()
