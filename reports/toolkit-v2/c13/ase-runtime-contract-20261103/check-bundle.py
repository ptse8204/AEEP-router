"""First-party bundle/Markdown controls; no external tool or upstream SDK runs."""
from __future__ import annotations
import hashlib,importlib.util,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
HERE=Path(__file__).resolve().parent

def load(name,path):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m

d=load('ase_docs_review',HERE/'run-docs.py');b=load('ase_bundle_review',HERE/'run-bundle.py')
assert d.blank_line_digest(b'# H\n\n\nText\n')==d.blank_line_digest(b'# H\n\nText\n')
assert d.blank_line_digest(b'# H\n\nText\n')!=d.blank_line_digest(b'# H\n\nChanged\n')
assert d.blank_line_digest(b'```python\nx=1\n\n\n```\n')!=d.blank_line_digest(b'```python\nx=1\n\n```\n')
assert d.blank_line_digest(b'    command\n\n\nText\n')!=d.blank_line_digest(b'    command\n\nText\n')
results=[]
for status,measurement,expect_docs in [(True,0.1,True),(False,0.1,True),(False,None,False)]:
 with tempfile.TemporaryDirectory(prefix='aeep-bundle-fixture-') as tmp:
  root=Path(tmp);review=root/'operation-review.json';review.write_text('{}\n');identity=hashlib.sha256(review.read_bytes()).hexdigest()
  (root/'operator-approval.json').write_text(json.dumps({'approved':True,'review_sha256':identity}))
  calls=[]
  def substitute(argv,**kwargs):
   calls.append(Path(argv[1]).name)
   if calls[-1]=='run-review.py':
    (root/'execution').mkdir();(root/'execution/summary.json').write_text(json.dumps({'passed':status,'operation_ledger':{'operations':[{'elapsed_seconds':measurement}]}}))
   else:(root/'docs-complete.json').write_text('{}')
   return SimpleNamespace(returncode=0)
  with patch.object(b,'HERE',root),patch.object(b.subprocess,'run',substitute),patch.object(b.sys,'argv',['run-bundle.py','--execute-approved',identity]):b.main()
  assert ('run-docs.py' in calls) is expect_docs
  results.append({'SDK_fixture_passed':status,'accounting_settled':measurement is not None,'independent_docs_ran':expect_docs})
print(json.dumps({'passed':True,'blank_line_only_correction_preserves_code':True,'bundle_controls':results,'actual_ASE_imports':0,'actual_docs_tool_calls':0,'actual_grant_changes':0}))
