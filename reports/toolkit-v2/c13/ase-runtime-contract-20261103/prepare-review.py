"""Freeze a component-scoped SDK/docs review; no third-party execution or grant write."""
from __future__ import annotations
import ast,hashlib,importlib.util,json,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.identity import file_digest as executable_digest
from aeep_toolkit.install_runtime import snapshot,file_digest
spec=importlib.util.spec_from_file_location('docs_review_preparation',HERE/'run-docs.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
context=json.loads((HERE/'context.json').read_bytes());assert verification_source_digest(ROOT)==context['source']
assert snapshot(Path(context['runtime']))==context['runtime_tree_sha256']
for name,c in context['conditions'].items():assert snapshot(Path(context['specs'][name]['config']['cwd']))==c['prepared_tree_sha256']
parent=json.loads((HERE.parent/'scanner-storage-review-20261103/operation-review.json').read_bytes())
docs=dict(parent['docs']);docs.pop('executed',None)
docs['normalized_input_hashes']={name:module.blank_line_digest((ROOT/name).read_bytes()) for name in docs['documents'] if not name.startswith('integrations/')}
docs['permitted_correction']='At most two attempts; only repeated blank lines outside fenced or indented code may be removed after a failed first attempt. All nonblank bytes, code, input list, config, tools and sandbox remain exact. No fingerprinted integration-document changes.'
docs['runtime_retained']=True
tools=Path(docs['runtime']);state=json.loads(Path(docs['runtime_record']).read_bytes());assert module.tools_state(tools)==state['files']
parsed=ast.parse((tools/'bin/npx').read_text());assignment=next(n for n in parsed.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='args' for t in n.targets));node=Path(assignment.value.elts[0].value)
docs['executable_dependencies']={str(p):executable_digest(p) for p in [node,Path('/usr/bin/make'),Path('/Applications/Xcode.app/Contents/Developer/usr/bin/make'),Path('/usr/bin/sandbox-exec'),Path(sys.executable).resolve()]}
names={str(p.relative_to(ROOT)) for p in HERE.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name not in {'operation-review.json','preflight.json','docs-preflight.json'}}
names.update(docs['documents'])
names.update(['Makefile','.markdownlint-cli2.jsonc','.lychee.toml','reports/v08/plan-coverage.md','reports/toolkit-v2/c13/coverage-completion-20261103/verification/checks.json','reports/toolkit-v2/c13/coverage-completion-20261103/completion-result.json',str(Path(docs['runtime_record']).relative_to(ROOT))])
review={
 'purpose':'Actual ASE0.7 scheduler/deterministic grader contract check through production AgentHarness over explicit positive/negative first-party grade certificates, plus independent current-input offline docs. Not controlled-worker, benchmark, qualification or usefulness evidence.',
 'source':context['source'],'source_checks':str(HERE.parent/'coverage-completion-20261103/verification/checks.json'),
 'runtime':context['runtime'],'runtime_tree_sha256':context['runtime_tree_sha256'],
 'runtime_scope':'Installed child and contract byte-identical to current source; read_bytes helper AST-equivalent. Other installed AEEP code retains older runtime scope. No installation or current-source suite replay.',
 'ASE_source_revision':'59de161f657b82bfaf8f6abe83dfff38552deb21','ASE_artifact_sha256':'5e29aff9fc354475c7e3e652659475e89cbb438603ee55d0392f0c845dbcf07f',
 'database':context['database'],'executable_dependencies':context['executable_dependencies'],
 'prepared_native_tree_sha256':context['prepared_trees']['native-boundary'],
 'specs':{k:v for k,v in context['specs'].items() if k!='preparation'},'conditions':context['conditions'],'native_payload':context['native_payload'],
 'maximum_operations':3,'maximum_reserved_seconds':120,'maximum_model_turns':0,'cash_usd':0,
 'expires_at':'2026-11-04T23:00:00Z',
 'authority':'Apply the prepared routine scope amendment and finite expiry extension under standing September27 authority only after this exact upstream-execution approval. Preserve current ceilings/counters; use current budget predecessor, record exact amendment, or skip extension if already sufficient. No model, disclosure, credential or paid authority.',
 'attempts':'Pre-dispatch authority bookkeeping failures retain separate records and do not consume an unstarted SDK invocation; no grant counter is refunded. One native probe and one SDK invocation per positive/negative condition. Failed SDK conditions stop dependent SDK calls; retain costs and state, no automatic replay. Independent docs remain eligible after settled failure; unresolved SDK effects/accounting stop dispatch. Docs allow at most two attempts under the stated blank-line-only correction rule.',
 'docs':docs,
 'candidate':'The already-inspected repository-authored format-json engineering fixture only; no real task result or skill usefulness claim.',
 'measurements':'Native SDK process costs enter the original operation ledger. Upstream TimingData defaults and approximate stdout tokens are not measured model/candidate usage. Docs engineering timings remain separately reported; this does not pass whole-workflow accounting.',
 'cleanup':'Retain reusable runtimes, tools, case inputs, responses, result records, old operations, Docker resources and unrelated work. The pinned SDK may remove only its newly created scratch Git workspace after grading; changed/older prepared trees block dispatch. No other cleanup.',
 'downloads':False,'installs':False,'image_changes':False,'credentials':False,'services':False,'release':False,
 'comparisons':'PAUSED','all_stack_completion':False,'controlled_model_worker_verified':False,
 'bound_files':{name:file_digest(ROOT/name) for name in sorted(names)},
}
(HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
print(json.dumps({'review_sha256':file_digest(HERE/'operation-review.json'),'bound_files':len(names),'SDK_operations':3,'maximum_reserved_SDK_seconds':120,'docs_inputs':len(docs['documents']),'cached_docs_tool_files':len(state['files']),'models':0,'execution':False}))
