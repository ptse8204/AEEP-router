"""Prepare exact retained-runtime SDK checks. No ASE import, grant write or install."""
from __future__ import annotations
import ast,hashlib,importlib.util,json,os,shutil,sqlite3,sys,tempfile
from datetime import UTC,datetime
from pathlib import Path
from threading import RLock
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3];sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.models import AssessmentAuthorization,AssessmentBudgetAmendment,AssessmentScopeAmendment,ConformanceProbeRequest,content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from aeep_toolkit.ase_contract import ASE_SOURCE_FILES,ASE_REVISION,ASE_ARTIFACT
from aeep_toolkit.candidate import inspect
from aeep_toolkit.install_runtime import snapshot,file_digest

RUNTIME=ROOT/'.aeep/upstream-stack-runtimes-20261102/corrected-composed-runtime'
WORK=ROOT/'.aeep/ase-engineering-work-20261103/scheduler'
TOOLS=ROOT/'.aeep/ase-engineering-tools-20261103'
CACHE=ROOT/'.aeep/workflow-scanner-20261102/candidate'
AUDIT=HERE.parent/'next-stack-integration-audit-20261103'
CANARY=ROOT/'.aeep/ase-engineering-outside-canary-20261103.txt'
OUTSIDE=ROOT/'.aeep/ase-engineering-outside-write-20261103.txt'
SOURCE=verification_source_digest(ROOT)
assert SOURCE=='c2eb4a3dab740304934e9a590892ff5db18fcfe0c998dc303e15ead5c238c839'
assert shutil.disk_usage(ROOT).free>=50*1024**3+16*1024**2
assert not (HERE/'context.json').exists(),'Inspect existing prepared context; never overwrite it'
assert not WORK.exists() and not TOOLS.exists() and not CANARY.exists() and not OUTSIDE.exists()
WORK.mkdir(mode=0o700,parents=True);(TOOLS/'bin').mkdir(mode=0o700,parents=True)
wrapper=TOOLS/'bin/git';shutil.copyfile(AUDIT/'ase-git-wrapper.py',wrapper);wrapper.chmod(0o555)
CANARY.write_text('first-party-native-sdk-boundary-canary\n');CANARY.chmod(0o600)
fd,tmp_canary=tempfile.mkstemp(prefix='aeep-sdk-outside-canary-',suffix='.txt')
with os.fdopen(fd,'w') as f:f.write('first-party-outside-tmp-canary\n')
profile_spec=importlib.util.spec_from_file_location('sdk_native_profile',HERE/'native-profile.py')
profile_builder=importlib.util.module_from_spec(profile_spec);profile_spec.loader.exec_module(profile_builder)
site=RUNTIME/'lib/python3.13/site-packages'
for name,expected in ASE_SOURCE_FILES.items():assert file_digest(site/name)==expected,name
current_child={}
for name in ['ase_child.py','ase_contract.py']:
 assert (site/'aeep_toolkit'/name).read_bytes()==(ROOT/'src/aeep_toolkit'/name).read_bytes()
 current_child[name]=file_digest(site/'aeep_toolkit'/name)
old_cli=(site/'aeep_toolkit/cli.py').read_text();current_cli=(ROOT/'src/aeep_toolkit/cli.py').read_text()
def function(source,name):return ast.dump(next(n for n in ast.parse(source).body if isinstance(n,ast.FunctionDef) and n.name==name),include_attributes=False)
assert function(old_cli,'read_bytes')==function(current_cli,'read_bytes')

profiles={};specs={};conditions={};prepared={}
for name in ['preparation','native-boundary','positive','negative']:
 work=WORK/name;work.mkdir(mode=0o700)
 for part in ['home','tmp','responses','candidate']:(work/part).mkdir(mode=0o700)
 if name in {'positive','negative'}:
  payload=inspect(CACHE);payload.stage(work/'candidate/format-json')
  evals=work/'candidate/format-json/evals';evals.mkdir()
  (evals/'evals.json').write_text(json.dumps({'skill_name':'format-json','evals':[{'id':'0','prompt':'0','expected_output':'First-party grade-certificate fixture, not task truth','assertions':[{'type':'json_path','json_path':'canonical_valid','equals':True}]}]},indent=2)+'\n')
 profile=HERE/(name+'.sb')
 text=profile_builder.profile(RUNTIME,TOOLS,work,HERE/'native-boundary.py')
 profile.write_text(text);profiles[name]=str(profile)
 env={'PATH':str(TOOLS/'bin')+':/usr/bin:/bin','HOME':str(work/'home'),'TMPDIR':str(work/'tmp'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONNOUSERSITE':'1','LC_ALL':'C'}
 argv=['/usr/bin/sandbox-exec','-f',str(profile),str(RUNTIME/'bin/python'),'-I','-B']
 argv+=['-m','aeep_toolkit.ase_child'] if name in {'positive','negative'} else [str(HERE/'native-boundary.py')]
 spec=ExecutorSpec(id='toolkit.ase-sdk-'+name,capability='toolkit.upstream-engineering@1',kind='command',description='Reviewed actual ASE scheduler/grader contract check with first-party certificates; no model worker or benefit claim' if name in {'positive','negative'} else 'First-party native sandbox/Git boundary; no upstream import',side_effect='write',config={'argv':argv,'argv_literal':True,'inherit_env':False,'stdin_json':True,'cwd':str(work),'env':env,'timeout_seconds':40 if name in {'positive','negative'} else 25,'max_output_bytes':65536,'output':{'type':'jsonl','match':{'kind':'done'}} if name in {'positive','negative'} else {'type':'json'}})
 specs[name]=spec.model_dump(mode='json')
 prepared[name]=snapshot(work)
 if name in {'positive','negative'}:
  valid=name=='positive';certificate=content_digest({'kind':'first_party_grade_certificate_fixture','condition':name,'canonical_valid':valid})
  conditions[name]={'canonical_valid':valid,'certificate_fixture_sha256':certificate,'input':{'slots':['0'],'run_token':content_digest({'source':SOURCE,'condition':name,'purpose':'SDK_conformance_only'}),'skill_name':'format-json','response_timeout':15.0},'prepared_tree_sha256':prepared[name]}

# Read the real shared ledger without schema writes or credential access.
database=Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3')
c=sqlite3.connect(database.as_uri()+'?mode=ro',uri=True)
repo=AssessmentRepository(SimpleNamespace(_connection=c,_lock=RLock()))
original=AssessmentAuthorization.model_validate(repo.get('authorization','onboarding'));effective=repo.effective_grant('onboarding')
previous=c.execute("SELECT digest FROM assessment_records WHERE kind='budget_amendment' AND json_extract(payload_json,'$.authorization_id')='onboarding' ORDER BY rowid DESC LIMIT 1").fetchone()[0]
baseline=dict(zip(('revoked','operations','model_turns','elapsed_seconds','cash_usd'),c.execute("SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone(),strict=True))
old_unsettled=[row[0] for row in c.execute("SELECT id FROM assessment_operations WHERE grant_id='onboarding' AND state='reserved'")];c.close()
assert not baseline['revoked']
assert effective.limits.max_operations-baseline['operations']>=3
assert effective.limits.max_elapsed_seconds-baseline['elapsed_seconds']>=120
budget=AssessmentBudgetAmendment(amendment_id='aeep-ase-sdk-expiry-20261103',authorization_id='onboarding',authorization_digest=content_digest(original),previous_amendment_digest=previous,limits=effective.limits,expires_at=datetime(2026,11,5,12,tzinfo=UTC))
subject={'schema_version':'toolkit.sdk-subject.v1','purpose':'Public first-party grade-certificate fixtures; no capability benchmark','candidate_files':inspect(CACHE).describe()['files']}
recipe={'schema_version':'toolkit.sdk-contract.v1','upstream_revision':ASE_REVISION,'artifact_sha256':ASE_ARTIFACT,'specs':{k:v for k,v in specs.items() if k!='preparation'},'conditions':conditions,'models':0}
environment={'schema_version':'toolkit.sdk-runtime.v1','runtime':str(RUNTIME),'runtime_tree_sha256':snapshot(RUNTIME),'profiles':{k:file_digest(Path(v)) for k,v in profiles.items() if k!='preparation'},'current_child_files':current_child,'read_bytes_function_equivalent':True}
definitions={content_digest(value):value for value in [subject,recipe,environment]}
scope=ConformanceProbeRequest(plan_id='conformance_probe_ase_sdk_contract_20261103',subject_digest=content_digest(subject),recipe_digest=content_digest(recipe),mapping_digest=content_digest(recipe),environment_digest=content_digest(environment),authorization_id='onboarding',definition_digests=list(definitions),worker_digest=content_digest(environment),executable_dependencies={str(wrapper):file_digest(wrapper)})
amendment=AssessmentScopeAmendment(amendment_id='aeep-ase-sdk-scope-20261103',authorization_id='onboarding',authorization_digest=content_digest(original),subject_digests=[scope.subject_digest],recipe_digests=[scope.recipe_digest],environment_digests=[scope.environment_digest],reviewed_digests=list(definitions))
authority={'authority':'Standing routine scope and finite-budget delegation in AGENTS.md and docs/ASSESSMENT_TESTING.md; no new model/disclosure/cash authority. Apply only with the exact upstream-execution review.','request':scope.model_dump(mode='json'),'definitions':definitions,'scope_amendment':amendment.model_dump(mode='json'),'budget_amendment':budget.model_dump(mode='json'),'grant_baseline':baseline,'effective_grant_before':{'limits':effective.limits.model_dump(mode='json'),'expires_at':effective.expires_at.isoformat()},'old_unsettled_operations':old_unsettled,'old_operations_are_not_replayed_or_settled':True}
(HERE/'authority.json').write_text(json.dumps(authority,indent=2)+'\n')
context={'source':SOURCE,'runtime':str(RUNTIME),'runtime_tree_sha256':environment['runtime_tree_sha256'],'runtime_current_child_files':current_child,'read_bytes_function_equivalent':True,'database':str(database),'profiles':profiles,'specs':specs,'conditions':conditions,'prepared_trees':prepared,'native_payload':{'outside_canary':str(CANARY),'outside_tmp_canary':tmp_canary,'outside_write':str(OUTSIDE),'git_wrapper':str(wrapper)},'executable_dependencies':{str(wrapper):file_digest(wrapper),str(Path('/Applications/Xcode.app/Contents/Developer/usr/bin/git')):file_digest(Path('/Applications/Xcode.app/Contents/Developer/usr/bin/git')),str(Path(sys.executable).resolve()):file_digest(Path(sys.executable).resolve()),**{str(site/name):expected for name,expected in ASE_SOURCE_FILES.items()}}}
for target in [HERE/'native-boundary.py',*(Path(v) for k,v in profiles.items() if k!='preparation'),site/'aeep_toolkit/ase_child.py',site/'aeep_toolkit/ase_contract.py']:
 context['executable_dependencies'][str(target)]=file_digest(target)
context['executable_dependencies']['/usr/bin/sandbox-exec']=file_digest(Path('/usr/bin/sandbox-exec'))
context['executable_dependencies'][tmp_canary]=file_digest(Path(tmp_canary))
context['executable_dependencies'][str(CANARY)]=file_digest(CANARY)
(HERE/'context.json').write_text(json.dumps(context,indent=2)+'\n')
print(json.dumps({'prepared':True,'source':SOURCE,'ASE_source_files_verified':16,'runtime_unchanged':True,'models':0,'upstream_imports':0,'grant_mutations':0,'main_grant_expiry_amendment_prepared':True}))
