"""Build a source-bound proposal-only overlay without changing planner methods."""

import ast
import hashlib
import importlib.util
import json
import sys
from collections import deque
from pathlib import Path
from zipfile import ZipFile

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
ROOT = PARENT.parents[3]
SOURCE = json.loads((PARENT/'source-result.json').read_bytes())
WORK = ROOT / '.aeep' / PARENT.name
ORIGINAL = Path(SOURCE['source_root'])
OVERLAY = WORK / 'proposal-overlay'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read(name):
    data = (ORIGINAL/name).read_bytes()
    assert sha(data) == SOURCE['source_sha256'][name]
    return data.decode()


def replace(text, original, updated):
    assert text.count(original) == 1
    return text.replace(original, updated, 1)


def tools(text):
    assert text.splitlines()[0].replace(' ', '') == 'from.toolimportTool,Toolkit'
    return '"""Core tool types for the isolated proposal runtime."""\nfrom .tool import Tool, Toolkit\n\n__all__ = ["Tool", "Toolkit"]\n'


def storage(text):
    for line in ('from .graph_stores import GraphStoreFactory, GraphStoreBase\n',
                 'from .vectore_stores import VectorStoreFactory, VectorStoreBase\n'):
        text = replace(text, line, '')
    for kind, module in (('vector', 'vectore_stores'), ('graph', 'graph_stores')):
        base = kind.title() + 'StoreBase'
        factory = kind.title() + 'StoreFactory'
        text = replace(text, f'Optional[Union[{base}, Any]]', 'Optional[Any]')
        line = f'        if {kind}_config is not None:\n'
        text = replace(text, line, line + f'            from .{module} import {factory}\n')
    return text


def operators(text):
    for line in ('from ..benchmark.benchmark import Benchmark\n',
                 'from ..benchmark.humaneval import AFlowHumanEval\n',
                 'from ..benchmark.mbpp import AFlowMBPP\n',
                 'TEST_SUPPORTED_BENCHMARKS = (AFlowHumanEval, AFlowMBPP)\n'):
        text = replace(text, line, '')
    assert text.count('benchmark: Benchmark') == 2
    text = text.replace('benchmark: Benchmark', 'benchmark: "Benchmark"')
    marker = '        if any(isinstance(benchmark, benchmark_type)'
    local = ('        from ..benchmark.humaneval import AFlowHumanEval\n'
             '        from ..benchmark.mbpp import AFlowMBPP\n'
             '        TEST_SUPPORTED_BENCHMARKS = (AFlowHumanEval, AFlowMBPP)\n\n')
    return replace(text, marker, local + marker)


def memory_package(text):
    text = replace(text, 'from .long_term_memory import LongTermMemory\n', '')
    text = replace(text, 'from .memory_manager import MemoryManager\n', '')
    return replace(text, ', "LongTermMemory", "MemoryManager"', '')


def agent(text):
    text = replace(text, 'from typing import Any, Dict, List, Optional, Tuple, Type, Union',
                   'from typing import Any, Dict, List, Literal, Optional, Tuple, Type, Union')
    text = replace(text, 'from ..memory.long_term_memory import LongTermMemory\n', '')
    text = replace(text, 'from ..memory.memory_manager import MemoryManager\n', '')
    text = replace(text, 'use_long_term_memory: Optional[bool] = False',
                   'use_long_term_memory: Literal[False] = False')
    text = replace(text, 'long_term_memory: Optional[LongTermMemory] = None', 'long_term_memory: None = None')
    text = replace(text, 'long_term_memory_manager: Optional[MemoryManager] = None',
                   'long_term_memory_manager: None = None')
    start = text.index('    def init_long_term_memory(self):')
    end = text.index('    def init_context_extractor(self):', start)
    return text[:start] + (
        '    def init_long_term_memory(self):\n'
        '        raise RuntimeError("Persistent memory is disabled in the proposal-only runtime")\n\n'
    ) + text[end:]


def nested_imports(body):
    for node in body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            yield node
        elif isinstance(node, (ast.If, ast.With, ast.Try, ast.For)):
            yield from nested_imports(node.body)
            yield from nested_imports(getattr(node, 'orelse', []))


def import_closure(changed):
    files, packages = {}, set()
    for file in (ORIGINAL/'evoagentx').rglob('*.py'):
        name = '.'.join(file.relative_to(ORIGINAL).with_suffix('').parts)
        if name.endswith('.__init__'):
            name = name.removesuffix('.__init__')
            packages.add(name)
        files[name] = file.relative_to(ORIGINAL).as_posix()
    supplied = set(sys.stdlib_module_names)
    for file in (WORK/'wheelhouse').glob('*.whl'):
        with ZipFile(file) as archive:
            supplied.update(part for name in archive.namelist()
                            if (part := name.split('/')[0].split('.', 1)[0]).isidentifier())
    queue = deque(['evoagentx.workflow.workflow_generator', 'evoagentx.actions.task_planning'])
    checked, missing = set(), set()
    while queue:
        name = queue.popleft()
        if name in checked:
            continue
        checked.add(name)
        segments = name.split('.')
        queue.extend(parent for depth in range(1, len(segments))
                     if (parent := '.'.join(segments[:depth])) in packages)
        path = files[name]
        tree = ast.parse(changed[path] if path in changed else read(path))
        package = name if name in packages else name.rpartition('.')[0]
        for node in nested_imports(tree.body):
            if isinstance(node, ast.Import):
                imports = [alias.name for alias in node.names]
            else:
                base = (importlib.util.resolve_name('.' * node.level + (node.module or ''), package)
                        if node.level else node.module)
                imports = [base, *(f'{base}.{alias.name}' for alias in node.names
                                   if f'{base}.{alias.name}' in files)]
            for item in imports:
                if item in files:
                    queue.append(item)
                elif item.split('.')[0] not in supplied and not item.startswith('evoagentx'):
                    missing.add(item.split('.')[0])
    return {'visited_upstream_modules': len(checked), 'missing_static_modules': sorted(missing)}


edits = {
    'evoagentx/tools/__init__.py': tools,
    'evoagentx/memory/__init__.py': memory_package,
    'evoagentx/agents/agent.py': agent,
    'evoagentx/storages/base.py': storage,
    'evoagentx/workflow/operators.py': operators,
}
changed = {name: edit(read(name)) for name, edit in edits.items()}
before, after = import_closure({}), import_closure(changed)
assert 'docker' in before['missing_static_modules']
assert after['missing_static_modules'] == [], after
assert not OVERLAY.exists()
for name, text in changed.items():
    dst = OVERLAY / name
    dst.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    with dst.open('x') as stream:
        stream.write(text)
report = {
    'source_revision': SOURCE['revision'], 'before': before, 'after': after,
    'changed_support_files': {name: {'original_sha256': SOURCE['source_sha256'][name],
                                     'overlay_sha256': sha(text.encode())}
                              for name, text in changed.items()},
    'planner_and_graph_source_unchanged': True,
    'purpose': 'Keep optional toolkit, storage and benchmark imports out of the proposal-only path.',
    'offline_runtime_executed': False, 'models': 0,
}
with (HERE/'overlay-report.json').open('x') as stream:
    stream.write(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
