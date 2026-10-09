"""Candidate bytes copied to a worker must be exactly the bytes in its identity."""
import json
import os
import sys

import pytest

from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main

pytestmark = pytest.mark.skipif(sys.platform == 'win32', reason='candidate reader requires POSIX no-follow file support')


def test_nested_excluded_bytes_never_enter_staged_payload(tmp_path):
    root = tmp_path/'skill'
    root.mkdir()
    (root/'SKILL.md').write_text('Synthetic instructions')
    (root/'resources').mkdir()
    (root/'resources/data.txt').write_text('included')
    (root/'resources/evals').mkdir()
    (root/'resources/evals/answer.txt').write_text('excluded oracle canary')
    first = inspect(root)
    (root/'resources/evals/answer.txt').write_text('changed excluded bytes')
    assert inspect(root).sha256 == first.sha256
    (root/'resources/data.txt').write_text('changed included bytes')
    assert inspect(root).sha256 != first.sha256
    first.stage(tmp_path/'staged')
    assert (tmp_path/'staged/resources/data.txt').read_text() == 'included'
    assert not (tmp_path/'staged/resources/evals').exists()
    assert inspect(tmp_path/'staged').sha256 == first.sha256
    with pytest.raises(ValueError):
        first.stage(tmp_path/'staged')


@pytest.mark.parametrize('kind',['symlink','hardlink','fifo','credentials','case_collision','missing_skill'])
def test_unsafe_payload_stops_before_staging(tmp_path,kind):
    (tmp_path/'SKILL.md').write_text('fixture')
    if kind == 'symlink':
        (tmp_path/'link').symlink_to(tmp_path/'SKILL.md')
    elif kind == 'hardlink':
        os.link(tmp_path/'SKILL.md',tmp_path/'linked')
    elif kind == 'fifo':
        os.mkfifo(tmp_path/'pipe')
    elif kind == 'credentials':
        (tmp_path/'auth.json').write_text('never read')
    elif kind == 'case_collision':
        # Also rejects a single noncanonical Skill.md spelling on case-insensitive hosts.
        (tmp_path/'SKILL.md').rename(tmp_path/'Skill.md')
    else:
        (tmp_path/'SKILL.md').unlink()
    with pytest.raises(ValueError):
        inspect(tmp_path)


def test_cli_has_only_hashes_and_captured_mutation_is_rejected(tmp_path,capsys):
    (tmp_path/'SKILL.md').write_text('private skill text')
    assert main(['candidate',str(tmp_path/'SKILL.md')]) == 0
    data = capsys.readouterr().out
    assert 'private skill text' not in data and json.loads(data)['executed'] is False
    payload = inspect(tmp_path)
    payload.files['../escape'] = b'bad'
    with pytest.raises(ValueError):
        payload.stage(tmp_path/'destination')
    assert not (tmp_path/'destination').exists()
