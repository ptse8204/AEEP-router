"""Private input delivery is not model conformance or plugin-quality evidence."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from test_v08_managed_workers import binding

from aeep.assessment.adapters import prepare_context
from aeep.errors import ConfigurationError
from aeep.execution import ExecutorCapabilities
from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts import HostProbe, HostProbeStatus, ManagedHostRegistry
from aeep.hosts.base import ManagedHostExecutionContext
from aeep.hosts.codex_exec import CodexExecAdapter
from aeep.hosts.workers import ARTIFACT_PROGRAM
from aeep.models import ActionRequest, ExecutionStatus, ExecutorSpec, RawExecution

pytestmark = pytest.mark.assessment_boundary


def route(root):
    return ExecutorSpec(id='search', capability='assessment.search@1', kind='host_managed', resource_pool='pool',
        description='Reviewed search tree fixture', config={'adapter_id':'fixture', 'argv':[binding().binary],
            'instructions':'Task {input}; action {action}', 'managed_worker':binding().model_dump(mode='json'),
            'input_tree':'local_search_tree:1', 'assessment_adapter':{'input_transform':'local_search_tree:2',
                'read_only_roots':[str(root)]}})


def mapped(approved_root, **changes):
    spec = route(approved_root)
    request = ActionRequest(capability=spec.capability, input={'root':str(approved_root), 'query':'λ', 'path':'.', **changes})
    return prepare_context(ExecutionContext(request=request, spec=spec, estimate=spec.estimate, attempt=1))[0]


async def test_mapping_keeps_search_work_in_worker_and_never_prompts_host_paths(tmp_path):
    (tmp_path/'nested').mkdir()
    (tmp_path/'nested'/'λ.txt').write_text('\u03b1\nλ\n', encoding='utf-8')
    ctx = mapped(tmp_path, path='../outside')
    assert ctx.request.input == {'query':'λ', 'path':'../outside', 'files':[{'path':'nested/λ.txt','text':'\u03b1\nλ\n'}]}
    assert ctx.spec.required_capabilities == ('input_tree',)
    class Fixture:
        def capabilities(self):
            return ExecutorCapabilities(adapter='fixture', features={'input_tree':'supported'})
        async def probe(self):
            return HostProbe(adapter_id='fixture', status=HostProbeStatus.READY)
        async def execute(self, context):
            assert str(tmp_path) not in context.instruction and '\u03b1' not in context.instruction
            assert '/workspace/case-tree' in context.instruction and '../outside' in context.instruction
            assert context.request.input['files'][0]['text'] == '\u03b1\nλ\n'
            return RawExecution(status=ExecutionStatus.SUCCESS, output={'error':'invalid_input'})
    registry = ManagedHostRegistry()
    registry.register('fixture', Fixture())
    raw = await ManagedHostExecutor(registry).execute(ctx)
    assert raw.output == {'error':'invalid_input'}
    host = CodexExecAdapter(ctx.spec)
    handle = await host.start(ManagedHostExecutionContext(request=ctx.request, instruction='fixture',
        config=ctx.spec.managed_host_config(), attempt=1, attempt_id='fixture'))
    assert (await handle.task).error_type == 'ARTIFACT_TRANSPORT_UNSUPPORTED'
    await host.close()
    registry._adapters['fixture'].capabilities = lambda: ExecutorCapabilities(adapter='fixture')
    with pytest.raises(ConfigurationError, match='input_tree'):
        await ManagedHostExecutor(registry).execute(ctx)
    with pytest.raises(ConfigurationError, match='outside reviewed'):
        mapped(tmp_path, root=str(tmp_path.parent))


def test_tree_review_is_required_and_legacy_serialization_stays_unchanged(tmp_path):
    spec = route(tmp_path)
    for change in ({'managed_worker':None}, {'assessment_adapter':None},
                   {'assessment_adapter':{'input_transform':'local_search_tree:1', 'read_only_roots':[str(tmp_path)]}}):
        with pytest.raises(ValueError, match='input tree requires'):
            ExecutorSpec.model_validate({**spec.model_dump(), 'config':{**spec.config, **change}})
    legacy = spec.model_dump()
    legacy['config'].pop('input_tree')
    legacy['config']['assessment_adapter']['input_transform'] = 'local_search_tree:1'
    legacy['required_capabilities'] = []
    old = ExecutorSpec.model_validate(legacy)
    assert 'input_tree' not in old.config and 'required_capabilities' not in old.model_dump()
    (tmp_path/'safe').write_text('ok')
    (tmp_path/'link').symlink_to(tmp_path/'safe')
    with pytest.raises(ConfigurationError, match='unsafe'):
        mapped(tmp_path)


def transfer(workspace: Path, files):
    # Exercise the exact child program; substitute only its fixed container root.
    program = ARTIFACT_PROGRAM.replace("'/workspace'", repr(str(workspace)))
    return subprocess.run([sys.executable, '-I', '-c', program], input=json.dumps({
        'operation':'tree','name':'case-tree','limit':100000,'files':files}),
        text=True, capture_output=True, timeout=5)


@pytest.mark.parametrize('files', [
    [{'path':'../escape','text':'x'}], [{'path':'/absolute','text':'x'}],
    [{'path':'a//b','text':'x'}], [{'path':'a\\b','text':'x'}],
    [{'path':'a\x00b','text':'x'}], [{'path':'.env','text':'synthetic'}],
    [{'path':'a','text':'x'}, {'path':'a','text':'y'}],
    [{'path':'a','text':'x'}, {'path':'a/b','text':'y'}],
    [{'path':'large','text':'λ'*50001}], [{'path':'a','text':1}],
    [{'path':'a','text':'x','extra':True}], [{'path':'a/'*33+'b','text':'x'}],
    [{'path':str(i),'text':''} for i in range(1001)],
])
def test_invalid_tree_is_rejected_before_any_write(tmp_path, files):
    assert transfer(tmp_path, files).returncode != 0
    assert list(tmp_path.iterdir()) == []


@pytest.mark.skipif(sys.platform == "win32", reason="native task integration requires POSIX; Windows uses WSL")
def test_tree_transfer_preserves_unicode_and_refuses_overwrite_or_symlink(tmp_path):
    files = [{'path':'nested/λ.txt','text':'\u03b1\nλ\n'}, {'path':'empty','text':''}]
    result = transfer(tmp_path, files)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {'size':6,'files':2}
    assert (tmp_path/'case-tree'/'nested'/'λ.txt').read_bytes() == '\u03b1\nλ\n'.encode()
    assert transfer(tmp_path, []).returncode != 0
    other = tmp_path/'other'
    other.mkdir()
    (other/'case-tree').symlink_to(tmp_path/'case-tree', target_is_directory=True)
    assert transfer(other, files).returncode != 0
    assert (tmp_path/'case-tree'/'empty').read_bytes() == b''
