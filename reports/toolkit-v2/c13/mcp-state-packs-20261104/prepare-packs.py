"""Bind cached original MCP task bytes; never run task setup, SQL or verifiers."""
import hashlib,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep_toolkit.benchmarks import inspect_pack,stage_agent_assets
from aeep_toolkit.install_runtime import digest
from aeep_toolkit.state_benchmarks import MCPStatePack

def load(path):return json.loads(Path(path).read_bytes())
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')
source=load(HERE.parent/'next-stack-integration-audit-20261103/mcp-security-source-bindings.json')['sources']
licenses=load(HERE.parent/'next-stack-integration-audit-20261103/mcp-security-license-bindings.json')
cache=ROOT/'.aeep/mcp-stack-protected-candidate-20261103'
for item in licenses['files']:
 source.append({'repository':'SalesforceAIResearch/MCP-Universe','revision':licenses['source_revision'],
  'cache':str(cache/'SalesforceAIResearch__MCP-Universe'/item['path']),**item})
source_by_repo={name:[item for item in source if item['repository']==name] for name in ('eval-sys/mcpmark','SalesforceAIResearch/MCP-Universe')}
workspace=ROOT/'.aeep/mcp-state-packs-20261104';workspace.mkdir(mode=0o700)
results=[]
for repository,pack_id in [('eval-sys/mcpmark','mcpmark'),('SalesforceAIResearch/MCP-Universe','mcp-universe')]:
 entries=source_by_repo[repository];asset_root=cache/repository.replace('/','__');assets=[];bindings={}
 for entry in entries:
  path=Path(entry['cache']);relative=path.relative_to(asset_root).as_posix();raw=path.read_bytes()
  assert len(raw)==entry['bytes'] and hashlib.sha256(raw).hexdigest()==entry['sha256']
  assert hashlib.sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()==entry['git_blob']
  if relative.endswith(('LICENSE','LICENSE.txt','license_info.md')):role='license'
  elif relative.endswith('description.md') or (pack_id=='mcp-universe' and relative.endswith('user_permission_audit.json')):role='instruction'
  elif relative.endswith('ground_truth.sql'):role='oracle'
  elif relative.endswith('verify.py'):role='verifier'
  elif relative.endswith('prepare_environment.py'):role='environment'
  elif relative.endswith('meta.json'):role='input'
  else:raise AssertionError('Unclassified original task asset: '+relative)
  assets.append({'path':relative,'sha256':entry['sha256'],'bytes':len(raw),'role':role});bindings[relative]=entry['sha256']
 revision=entries[0]['revision'];assert all(entry['revision']==revision for entry in entries)
 task={'task_id':'postgres.security.user_permission_audit','difficulty':'unknown','assets':assets,
  'oracle_layout':'separate_asset' if pack_id=='mcpmark' else 'embedded_in_verifier','upstream_score':'binary',
  'state_outputs':[{'backend_id':'owned-postgres-audit','table_name':name} for name in ('security_audit_results','security_audit_details')],
  'adaptations':['Original asset bytes are unchanged. Runtime, private database mapping, protected grader invocation and cleanup remain unreviewed.',
   'The backend alias is inert metadata, not a database URL, credential or permission. No state is synthesized as a file artifact.',
   'Keep pack-specific prompts and verifier assertions separate. The two packs reuse a related underlying task and are not independent usefulness cases.']}
 if pack_id=='mcp-universe':
  task['instruction_json_key']='question'
  task['adaptations'].append('Original question remains in its original JSON asset. It omits explicit table-schema deliverables present in MCPMark; this difference is preserved and requires task-contract review before model trials.')
 pack=MCPStatePack.model_validate({'pack_id':pack_id,'source':{'repository':'https://github.com/'+repository,'revision':revision,
  'artifact_sha256':digest(bindings),'license_expression':'Apache-2.0','data_rights':'Pinned repository notices only; exact task-use determination and runtime authority remain pending. No execution, provider disclosure or redistribution clearance inferred.'},'tasks':[task]})
 write(HERE/(pack_id+'-pack.json'),pack.model_dump(mode='json'))
 facts=inspect_pack(pack,asset_root,(task['task_id'],));write(HERE/(pack_id+'-inspection.json'),facts)
 public=workspace/pack_id
 stage_agent_assets(pack,asset_root,task['task_id'],public)
 staged={p.relative_to(public).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in public.rglob('*') if p.is_file()}
 expected={a['path']:a['sha256'] for a in assets if a['role'] in {'instruction','input'}}
 assert staged==expected
 results.append({'pack':pack_id,'source_revision':revision,'original_assets':len(assets),'asset_root':str(asset_root),
  'public_staging':str(public),'staged_sha256':staged,'protected_roles_not_staged':['oracle','verifier','environment','license'],
  'state_tables':[output['table_name'] for output in task['state_outputs']],'rights_reviewed':False,'runtime_qualified':False,
  'task_executed':False,'functional_gate_pass':False})
write(HERE/'preparation.json',{'evidence_kind':'pinned_source_binding_and_local_input_separation_only','packs':results,
 'models':0,'services_started':False,'upstream_programs_executed':False,'comparisons':'PAUSED'})
print(json.dumps({'prepared_packs':len(results),'assets':sum(r['original_assets'] for r in results),'executed':False,'models':0}))
