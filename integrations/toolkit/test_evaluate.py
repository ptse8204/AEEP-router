import asyncio
import json
from unittest.mock import AsyncMock

import controlled
import pytest
from definition import prepare
from evaluate import UpstreamFixtureAdapter
from test_definition import inputs

from aeep.assessment.models import AssessmentEnvironment


def adapter(tmp_path,monkeypatch):
    selected=prepare(*inputs(tmp_path))
    environment=AssessmentEnvironment(environment_id='fixture',kind='container',identity={},container_image='sha256:'+'a'*64,
                                      container_runtime='/unused/docker',container_socket='/unused/socket')
    monkeypatch.setattr(controlled,'manifest',lambda:{})
    monkeypatch.setattr(controlled,'verify_runtime',lambda *a:{'synthetic-test':True})
    monkeypatch.setattr(controlled,'read_bytes',lambda path:b'synthetic adapter source')
    return UpstreamFixtureAdapter(tmp_path/'runtime',tmp_path/'results',environment,selected)


def test_adapter_preview_has_no_task_contents_or_execution(tmp_path,monkeypatch):
    execute=AsyncMock(side_effect=AssertionError('no dispatch'))
    monkeypatch.setattr(controlled,'execute',execute)
    selected=adapter(tmp_path,monkeypatch)
    assert 'A task' not in json.dumps(selected.plan)
    assert selected.capabilities.hosts==('fake',)
    assert selected.capabilities.containment=='unverified'
    with pytest.raises(ValueError,match='review'):
        asyncio.run(selected.evaluate('b'*64))
    execute.assert_not_called()
    assert not selected.output.exists()


def test_changed_candidate_cannot_dispatch_under_prior_review(tmp_path,monkeypatch):
    selected=adapter(tmp_path,monkeypatch)
    selected.inputs.candidate.files['SKILL.md']=b'changed after review'
    with pytest.raises(ValueError,match='changed'):
        asyncio.run(selected.evaluate(selected.capabilities.implementation_sha256))
    assert not selected.output.exists()
