"""Capture only the pinned proposer and optimizer integration contracts."""

import ast
import hashlib
import json
import shutil
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
PRIVATE = ROOT / '.aeep' / HERE.name
TARGETS = {
    'evoagentx': {
        'repository': 'ANative-Lab/EvoAgentX',
        'revision': 'd77fd6b9a3e76c8dd83bebe3374c53a3f5d16f54',
        'files': (
            'LICENSE', 'pyproject.toml', 'evoagentx/__init__.py',
            'evoagentx/workflow/workflow_generator.py', 'evoagentx/workflow/workflow_graph.py',
            'evoagentx/actions/task_planning.py', 'evoagentx/agents/task_planner.py',
            'evoagentx/models/base_model.py', 'evoagentx/models/__init__.py',
        ),
    },
    'aflow': {
        'repository': 'FoundationAgents/AFlow',
        'revision': '3f457218fc716093fe53f6df8a5d5e6379d66346',
        'files': (
            'LICENSE', 'requirements.txt', 'run.py', 'scripts/optimizer.py',
            'scripts/async_llm.py', 'scripts/evaluator.py',
            'scripts/optimizer_utils/evaluation_utils.py', 'scripts/optimizer_utils/graph_utils.py',
            'scripts/optimizer_utils/data_utils.py', 'scripts/optimizer_utils/experience_utils.py',
        ),
    },
}


def get(url, limit):
    req = urllib.request.Request(url, headers={'User-Agent': 'AEEP source contract inspection'})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read(limit + 1)
    assert len(data) <= limit
    return data


def blob_digest(data):
    return hashlib.sha1(f'blob {len(data)}\0'.encode() + data).hexdigest()


assert shutil.disk_usage(ROOT).free >= 50 * 1024**3
PRIVATE.mkdir(mode=0o700)
result = {'scope': 'read_only_upstream_contracts', 'executed': False, 'models': 0, 'components': {}}
for component, task in TARGETS.items():
    name, rev = task['repository'], task['revision']
    tree = json.loads(get(f'https://api.github.com/repos/{name}/git/trees/{rev}?recursive=1', 4_000_000))
    assert tree['sha'] == rev and not tree['truncated']
    by_path = {row['path']: row for row in tree['tree'] if row['type'] == 'blob'}
    missing = [path for path in task['files'] if path not in by_path]
    assert not [path for path in missing if path not in ('requirements.txt', 'scripts/async_llm.py')]
    selected = [path for path in task['files'] if path in by_path]
    if 'scripts/async_llm.py' in missing:
        selected.extend(path for path in ('scripts/async_llm/__init__.py', 'scripts/async_llm/llm.py') if path in by_path)
    if 'requirements.txt' in missing:
        selected.extend(path for path in ('pyproject.toml', 'setup.py') if path in by_path)
    assert sum(by_path[path]['size'] for path in selected) <= 400_000
    files = {}
    for path in selected:
        entry = by_path[path]
        url = f'https://raw.githubusercontent.com/{name}/{rev}/{path}'
        data = get(url, entry['size'])
        assert blob_digest(data) == entry['sha'] and len(data) == entry['size']
        saved = PRIVATE / component / path
        saved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with saved.open('xb') as output:
            output.write(data)
        saved.chmod(0o444)
        row = {'git_blob': entry['sha'], 'sha256': hashlib.sha256(data).hexdigest(),
               'bytes': len(data), 'source_url': url}
        if path.endswith('.py'):
            code = ast.parse(data)
            row['public_top_level_definitions'] = [
                node.name for node in code.body
                if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                and not node.name.startswith('_')
            ]
        files[path] = row
    result['components'][component] = {'repository': name, 'revision': rev, 'files': files}
with (HERE / 'source-contracts.json').open('x') as stream:
    json.dump(result,stream,indent=2)
    stream.write('\n')
print({key:len(row['files']) for key,row in result['components'].items()})
