import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from definition import Suite, prepare

from aeep_toolkit.candidate import inspect
from aeep_toolkit.models import SourcePin


def inputs(tmp_path):
    root=tmp_path/'fixture'
    root.mkdir()
    (root/'SKILL.md').write_text('---\nname: fixture\ndescription: synthetic\n---\nNo model execution.')
    source=SourcePin(repository='https://example.org/fixture',revision='a'*40,artifact_sha256=inspect(root).sha256,
                     license_expression='MIT',data_rights='synthetic test input')
    suite=tmp_path/'suite.json'
    suite.write_text(json.dumps({'skill_name':'fixture','evals':[{'id':'easy','prompt':'A task',
                         'expected_output':'checked externally','assertions':['The output contains `ok`']}]}))
    return root,suite,source


def test_prepare_has_no_process_network_or_write_and_keeps_contents_out_of_preview(tmp_path):
    args=inputs(tmp_path)
    before={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    with patch('subprocess.Popen',side_effect=AssertionError('process forbidden')),patch('socket.socket',side_effect=AssertionError('network forbidden')),patch.object(Path,'write_bytes',side_effect=AssertionError('write forbidden')),patch.object(Path,'write_text',side_effect=AssertionError('write forbidden')):
        result=prepare(*args)
    result.verify()
    assert 'A task' not in json.dumps(result.binding())
    assert before=={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in tmp_path.rglob('*') if p.is_file()}
    assert result.binding()['trials']==2 and result.binding()['model_turns']==0


def test_captured_mutation_and_source_mismatch_rejected(tmp_path):
    args=inputs(tmp_path)
    result=prepare(*args)
    result.candidate.files['SKILL.md']=b'changed'
    with pytest.raises(ValueError):
        result.worker_payload()
    args[2].artifact_sha256='b'*64
    with pytest.raises(ValueError):
        prepare(*args)


def test_duplicate_cases_prompts_and_nonliteral_grading_rejected(tmp_path):
    args=inputs(tmp_path)
    raw=json.loads(args[1].read_text())
    with pytest.raises(ValueError):
        Suite.model_validate(raw|{'evals':raw['evals']*2})
    other=raw['evals'][0]|{'id':'other'}
    with pytest.raises(ValueError):
        Suite.model_validate(raw|{'evals':[*raw['evals'],other]})
    for assertion in ['Run a model judge','The output contains ``','The output contains `a` and `b`']:
        with pytest.raises(ValueError):
            Suite.model_validate(raw|{'evals':[raw['evals'][0]|{'assertions':[assertion]}]})


def test_candidate_resources_are_captured_and_nested_evals_excluded(tmp_path):
    root,suite,source=inputs(tmp_path)
    (root/'resources/evals').mkdir(parents=True)
    (root/'resources/evals/answers.txt').write_text('future answers')
    (root/'resources/data.txt').write_text('support')
    source.artifact_sha256=inspect(root).sha256
    result=prepare(root,suite,source)
    assert set(result.worker_payload()['files'])=={'SKILL.md','resources/data.txt'}
    (root/'resources/data.txt').write_text('later edit')
    assert result.worker_payload()['files']['resources/data.txt']=='c3VwcG9ydA=='
