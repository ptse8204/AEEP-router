"""Tighten an unapproved profile; preserve old first-party proof, no SDK execution."""
from __future__ import annotations
import importlib.util,json,sys,tempfile
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import content_digest
from aeep_toolkit.install_runtime import snapshot,file_digest
spec=importlib.util.spec_from_file_location('sdk_native_profile',HERE/'native-profile.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
assert not (HERE/'operator-approval.json').exists() and not (HERE/'execution-started.json').exists()
context=json.loads((HERE/'context.json').read_bytes());authority=json.loads((HERE/'authority.json').read_bytes())
old={name:Path(path).read_text() for name,path in context['profiles'].items()}
backup=HERE/('inert-profile-snapshot-'+str(len(list(HERE.glob('inert-profile-snapshot-*.json')))+1)+'.json')
with backup.open('x') as f:json.dump({'evidence_kind':'superseded_before_upstream_execution','profiles':old,'SDK_calls':0},f,indent=2);f.write('\n')
for name,path in context['profiles'].items():
 work=Path(context['specs'][name]['config']['cwd'])
 Path(path).write_text(m.profile(Path(context['runtime']),Path(context['native_payload']['git_wrapper']).parents[1],work,HERE/'native-boundary.py'))
fd,path=tempfile.mkstemp(prefix='aeep-sdk-outside-canary-',suffix='.txt');import os
with os.fdopen(fd,'w') as f:f.write('first-party-outside-tmp-canary\n')
context['native_payload']['outside_tmp_canary']=path
for target in [HERE/'native-boundary.py',*(Path(v) for k,v in context['profiles'].items() if k!='preparation')]:context['executable_dependencies'][str(target)]=file_digest(target)
context['executable_dependencies'][path]=file_digest(Path(path))
context['executable_dependencies'][context['native_payload']['outside_canary']]=file_digest(Path(context['native_payload']['outside_canary']))
old_env=authority['request']['environment_digest'];environment=dict(authority['definitions'].pop(old_env))
environment['profiles']={k:file_digest(Path(v)) for k,v in context['profiles'].items() if k!='preparation'}
new_env=content_digest(environment);authority['definitions'][new_env]=environment
request=authority['request'];request['environment_digest']=request['worker_digest']=new_env;request['definition_digests']=[new_env if ref==old_env else ref for ref in request['definition_digests']]
amendment=authority['scope_amendment'];amendment['environment_digests']=[new_env];amendment['reviewed_digests']=[new_env if ref==old_env else ref for ref in amendment['reviewed_digests']]
context['profile_scope']='Existing native SDK boundary with explicit denial of all user homes, mounted volumes and shared temp data; allow the retained SDK/tools and own current case. OS file access outside those protected roots remains broader. This does not qualify model workers or all native process behavior.'
(HERE/'authority.json').write_text(json.dumps(authority,indent=2)+'\n');(HERE/'context.json').write_text(json.dumps(context,indent=2)+'\n')
print(json.dumps({'profiles_tightened_before_approval':True,'SDK_calls':0,'grant_changes':0,'new_tmp_canary':path}))
