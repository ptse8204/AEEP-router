"""Inspect protected verifier entry points; never import or execute upstream code."""
import ast
import hashlib
import json
import sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep_toolkit.benchmarks import BenchmarkPack,asset_path,inspect_pack
pack=BenchmarkPack.model_validate_json((HERE/'task-only-pack.json').read_bytes())
root=ROOT/'.aeep/skillsbench-stack-9a1f4dd5'
rows=[]
for task in pack.tasks:
 inspect_pack(pack,root,(task.task_id,))
 verifiers=[];shells=[]
 for asset in task.assets:
  if asset.role!='verifier':continue
  path=asset_path(root,asset)
  if path.suffix=='.py':
   tree=ast.parse(path.read_text());imports=set();tests=[];params=[];skips=[]
   for node in ast.walk(tree):
    if isinstance(node,ast.Import):imports.update(alias.name for alias in node.names)
    elif isinstance(node,ast.ImportFrom) and node.module:imports.add(node.module)
    elif isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name.startswith('test_'):
     tests.append({'name':node.name,'line':node.lineno,'async':isinstance(node,ast.AsyncFunctionDef)})
     for deco in node.decorator_list:
      if isinstance(deco,ast.Call) and isinstance(deco.func,ast.Attribute) and deco.func.attr in {'parametrize','skip','skipif','xfail'}:
       params.append({'function':node.name,'line':deco.lineno,'decorator':ast.unparse(deco.func)})
    elif isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in {'skip','importorskip','xfail'}:
     skips.append({'line':node.lineno,'call':ast.unparse(node.func)})
   verifiers.append({'path':asset.path,'sha256':asset.sha256,'imports':sorted(imports),
    'static_functions':tests,'decorators_requiring_collection':params,'runtime_skip_or_xfail_sites':skips,
    'actual_collected_test_ids':None,'actual_required_test_ids':None,'collection_status':'NOT_EXECUTED'})
  elif path.name=='test.sh':
   script=path.read_text()
   shells.append({'path':asset.path,'sha256':asset.sha256,
    'raw_reward_path':'/logs/verifier/reward.txt','raw_score_semantics':'Original binary0/1 chosen from pytest exit',
    'raw_shell_exit_is_a_grader_verdict':False,
    'contains_mutable_installer':any(token in script for token in ('apt-get','pip install','uvx','install.sh')),
    'requires_private_service_lifecycle':task.task_id=='react-performance-debugging',
    'requires_java_and_maven_runtime':task.task_id=='spring-boot-jakarta-migration'})
 rows.append({'task_id':task.task_id,'domain':task.domain,'upstream_score':task.upstream_score,
  'verifiers':verifiers,'original_shells':shells,
  'protected_reference_asset_hashes':{a.path:a.sha256 for a in task.assets if a.role=='oracle'},
  'launch_adaptation_status':'PENDING exact runtime artifacts and asset-rights determinations',
  'reference_success':None,'incomplete_output_rejected':None,'destructive_output_rejected':None,
  'intentional_skip_classification':None,'infrastructure_error_classification':None})
assert len(rows)==6 and sum(row['domain']=='document-data' for row in rows)==3
result={'pack_revision':pack.source.revision,'task_only_manifest_sha256':hashlib.sha256((HERE/'task-only-pack.json').read_bytes()).hexdigest(),
 'evidence':'First-party AST and original-byte inspection only. No upstream import, reference, verifier, runtime or model execution.',
 'rows':rows,'execution_prerequisites':[
 'Exact task-specific asset-use determinations and reviewed runtime closure before any reference/task program executes.',
 'Original assertions and oracle bytes stay protected; freeze actual pytest identities after valid reference collection, never derive them from function counts.',
 'Record original reward independently from AEEP observation validity. Missing collection, all-skipped tests, xfails, collection errors or absent reward cannot establish success.',
 'Treat grader infrastructure failures as indeterminate observations, not negative capability scores. Preserve original reward and error data where available.',
 'Replace mutable shell provisioning with reviewed finite setup; document changed launch commands without editing upstream assertions.',
 'Keep any React service/port/process cleanup inside new owned verifier containers; never execute the upstream broad kill commands on the operator host.',
 'Reference success, incomplete/destructive counterexamples, intentional skips and infrastructure failures each need actual protected observations before model dispatch.'],
 'rights_cleared':False,'runtime_ready':False,'functional_pack_ready':False,'comparisons':'PAUSED'}
(HERE/'verifier-contracts.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'tasks':len(rows),'verifier_modules':sum(len(r['verifiers']) for r in rows),'protected_reference_assets':sum(len(r['protected_reference_asset_hashes']) for r in rows),'upstream_executed':False,'functional_pack_ready':False}))
