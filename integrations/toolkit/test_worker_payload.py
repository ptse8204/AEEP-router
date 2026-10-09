import base64
import importlib.util
import sys
import types
from pathlib import Path
from unittest.mock import patch

import pytest

from aeep_toolkit.candidate import identity


def worker():
    spec=importlib.util.spec_from_file_location('controlled_fixture_worker',Path(__file__).with_name('controlled_fixture_worker.py'))
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'agent_skill_eval.harnesses':types.SimpleNamespace(FakeHarness=object)}):
        spec.loader.exec_module(module)
    return module


def test_worker_stages_exact_candidate_resources_and_control_gets_none(tmp_path):
    files={'SKILL.md':b'synthetic','resources/table.csv':b'a,b\n1,2\n'}
    payload={'name':'fixture','sha256':identity(files),'files':{n:base64.b64encode(raw).decode() for n,raw in files.items()}}
    module=worker()
    assert module.stage(tmp_path,payload)
    root=tmp_path/'.fake/skills/fixture'
    assert {str(p.relative_to(root)):p.read_bytes() for p in root.rglob('*') if p.is_file()}==files
    control=tmp_path/'control'
    control.mkdir()
    assert not module.stage(control,None)
    assert not list(control.iterdir())


@pytest.mark.parametrize('name',['../escape','/outside','fixture/other'])
def test_unsafe_worker_skill_names_never_write(tmp_path,name):
    files={'SKILL.md':b'synthetic'}
    with pytest.raises(ValueError):
        worker().stage(tmp_path,{'name':name,'sha256':identity(files),'files':{'SKILL.md':base64.b64encode(b'synthetic').decode()}})
    assert not list(tmp_path.iterdir())


def test_bad_hash_or_included_oracle_never_writes(tmp_path):
    payload={'name':'fixture','sha256':'a'*64,'files':{'SKILL.md':'c3ludGhldGlj'}}
    with pytest.raises(ValueError):
        worker().stage(tmp_path,payload)
    payload['files']['resources/evals/answer.txt']='eA=='
    with pytest.raises(ValueError):
        worker().stage(tmp_path,payload)
    assert not list(tmp_path.iterdir())
