"""Finish the unstarted offline host checks on the retained resolver output."""
import ast
import hashlib
import importlib.util
import json
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent


def load(path):
    return json.loads(path.read_bytes())


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def write(path, data):
    with path.open('x') as stream:
        json.dump(data, stream, indent=2)
        stream.write('\n')


review = load(HERE/'operation-review.json')
result = load(HERE/'execution/summary.json')
assert not result['passed'] and result['error_type']=='UnboundLocalError'
assert not result['cleanup_uncertain'] and not result['accounting_uncertain']
assert result['containers']['resolver']['terminal']=={'Status':'exited','ExitCode':0,'OOMKilled':False}
assert result['containers']['relay']['terminal']['Status']=='exited'
receipt = load(HERE/'execution/resolve.json')
assert receipt['execution_success'] and receipt['metadata']['exit_code']==0
assert receipt['metadata']['review_sha256']==sha(HERE/'operation-review.json')
with sqlite3.connect('file:'+review['ledger']+'?mode=ro',uri=True) as connection:
    settled = connection.execute(
        'SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', (HERE.name,)
    ).fetchone()
    assert list(settled)==result['grant_counters']
    assert not connection.execute(
        "SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'", (HERE.name,)
    ).fetchone()

driver = ast.parse((HERE/'run.py').read_bytes())
run = next(node for node in driver.body if isinstance(node,ast.AsyncFunctionDef) and node.name=='run')
body = next(node for node in ast.walk(run) if isinstance(node,ast.Try) and any(
    isinstance(item,ast.Assign) and isinstance(item.targets[0],ast.Name) and item.targets[0].id=='cache'
    for item in node.body
)).body
assignment = next(node for node in body if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name)
                  and node.targets[0].id=='cache')
read = next(node for node in ast.walk(run) if isinstance(node,ast.Call)
            and isinstance(node.func,ast.Attribute) and node.func.attr=='verify_graph')
assert assignment.lineno>read.lineno and isinstance(read.args[1],ast.Name) and read.args[1].id=='cache'
work = Path(review['work'])
cache = work/'maven-cache'
graph_path = work/'selected.tgf'
seed = load(work/'cache-lock.json')
assert sha(work/'cache-lock.json')==review['pins'][str(work/'cache-lock.json')]
assert sha(HERE/'verify-cache.py')==review['pins'][str(HERE/'verify-cache.py')]
spec = importlib.util.spec_from_file_location('pinned_cache_verifier',HERE/'verify-cache.py')
verifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verifier)
graph = verifier.verify_graph(graph_path.read_text().strip(),cache,review['surefire_provider_files'])
inventory = []
for path in sorted(cache.rglob('*')):
    assert not path.is_symlink()
    if path.is_file():
        inventory.append({'path':path.relative_to(cache).as_posix(),'bytes':path.stat().st_size,'sha256':sha(path)})
total = sum(row['bytes'] for row in inventory)
assert inventory and total<=256*1024**2
current = {row['path']:row['sha256'] for row in inventory}
assert all(current.get(path)==digest for path,digest in seed.items()
           if not path.endswith(('_remote.repositories','resolver-status.properties')))
new = [row for row in inventory if row['path'] not in seed and row['path'].endswith(('.pom','.jar'))]
methods = {}
for row in new:
    path = cache/row['path']
    data = path.read_bytes()
    sidecar = path.with_suffix(path.suffix+'.sha1')
    if sidecar.is_file():
        algorithm = 'sha1'
        digest = hashlib.sha1(data).hexdigest()
    else:
        algorithm = 'md5'
        sidecar = path.with_suffix(path.suffix+'.md5')
        digest = hashlib.md5(data,usedforsecurity=False).hexdigest()
    assert sidecar.is_file() and digest==sidecar.read_text().strip(), path
    methods[algorithm] = methods.get(algorithm,0)+1
assert any(row['path'].endswith('/spring-boot-starter-web-3.2.0.jar') for row in inventory)
write(HERE/'retained-dependency-graph.json',graph)
write(work/'verified-cache-lock.json',current)
write(HERE/'retained-cache-audit.json',{
    'passed':True,'parent_execution_passed':False,'parent_failure':'UnboundLocalError from a later local cache assignment',
    'parent_result_sha256':sha(HERE/'execution/summary.json'),'parent_review_sha256':sha(HERE/'operation-review.json'),
    'resolver_receipt_sha256':sha(HERE/'execution/resolve.json'),'retained_tgf_sha256':sha(graph_path),
    'selected_graph_nodes':graph['selected_nodes'],'required_graph_files':graph['required_files'],
    'cache_files':len(inventory),'cache_bytes':total,'new_verified_artifacts':len(new),
    'published_checksum_counts':methods,'cache_lock_sha256':sha(work/'verified-cache-lock.json'),
    'selected_graph_file_sha256':sha(HERE/'retained-dependency-graph.json'),
    'settled_counters':list(settled),'guest_invocations':0,'models':0,'task_executed':False,
})
print((HERE/'retained-cache-audit.json').read_text())
