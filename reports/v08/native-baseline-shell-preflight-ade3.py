"""Inert fixed ordinary-shell support probe; no model or task-success claim."""
import asyncio,base64,hashlib,json,os,runpy,shlex,shutil,sys,tempfile,time
from pathlib import Path
from aeep.assessment.models import AssessmentLimits,AssessmentPlanningRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerTransport,AppServerOptions
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import StrictModel
from aeep.router import Router
from contextlib import contextmanager
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/v08'
SOURCE='5fffda8a321005abc175e63f887f118b2297097542a5c1332560cb60f409f9bc'
BINARY=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
class Definition(StrictModel): facts:dict

def sha(path):
 with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
@contextmanager
def environment(values):
 previous={k:os.environ.get(k) for k in values}
 try:os.environ.update(values);yield
 finally:
  for k,v in previous.items():
   if v is None:os.environ.pop(k,None)
   else:os.environ[k]=v

def shell_command(scratch,explicit_prefix):
 script=('import json,tempfile;from pathlib import Path;from openpyxl import load_workbook;'
 'root=Path('+repr(str(scratch))+');book=load_workbook(root/"input.xlsx");'
 'book.save(root/'+repr('output-prefix.xlsx' if explicit_prefix else 'output-default.xlsx')+');'
 'print(json.dumps({"opened":True,"saved":True,"temp_root_matches":Path(tempfile.gettempdir())==root}))')
 prefix='TMPPREFIX='+shlex.quote(str(scratch/'zsh-owned-'))+'\n' if explicit_prefix else ''
 return prefix+shlex.quote(str(PYTHON))+" -I - <<'AEEP_FIXED_PROBE'\n"+script+'\nAEEP_FIXED_PROBE\n'

def categories(stderr):
 text=stderr.lower();return [name for marker,name in [('permission denied','permission_denied'),('operation not permitted','permission_denied'),('temporary file','shell_temporary_file'),('here-document','heredoc'),('no usable temporary directory','python_temp_unavailable'),('no module named','module_missing'),('no such file','missing_path')] if marker in text]
async def main(review_hash):
 path=OUT/'native-baseline-shell-preflight-ade3-review.json';assert sha(path)==review_hash;r=json.loads(path.read_text());assert r['execution_authorized'] is True and sha(__file__)==r['driver_sha256'] and verification_source_digest(ROOT)==SOURCE
 assert sha(PYTHON)==r['python_sha256']
 for name,digest in r['dependencies'].items():assert sha(ROOT/name)==digest
 native_prerequisite=runpy.run_path(str(OUT/'native-only-validation-prerequisite-5fff.py'))['validate'](ROOT,r,SOURCE)
 resultpath=OUT/'native-baseline-shell-preflight-ade3-result.json';assert not resultpath.exists()
 router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store);old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'));definition=Definition(facts=r);mapping=repo.put('native_host_diagnostic','baseline-shell-preflight-ade3',definition);repo.review(mapping);req=old.model_copy(update={'plan_id':'planning_native_baseline_shell_preflight_ade3','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]});repo.review(repo.put('planning_request',req.plan_id,req));repo.authorize(req)
 operation='native-shell-preflight:'+req.plan_id;repo.reserve(req,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=40),stage='native_shell_support_probe');started=time.perf_counter();directory=Path(tempfile.mkdtemp(prefix='aeep-owned-shell-probe-',dir=ROOT)).resolve();scratch=directory/'scratch';scratch.mkdir();transport=None;record={'source_digest':SOURCE,'operation_id':operation,'model_turns':0,'probes':[],'cleanup_confirmed':False}
 try:
  async with asyncio.timeout(25):
   fixture=json.loads((ROOT/'integrations/assessment-runtime/workbook-grader-fixtures.json').read_text())[0]['input']['workbook_b64'];(scratch/'input.xlsx').write_bytes(base64.b64decode(fixture,validate=True))
   boundary=NativeSandboxConfig(binary=str(BINARY),binary_sha256='sha256:'+r['binary_sha256'],project_root=str(directory),read_roots=[str(PYTHON.parents[1]),str(ROOT/'AGENTS.md')],write_roots=[str(scratch)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+r['python_sha256']);configured=boundary.validate_environment({'TMPDIR':str(scratch),'TMP':str(scratch),'TEMP':str(scratch)})
   transport=CodexAppServerTransport((str(BINARY),'app-server','-c','features.apps=false','-c','features.code_mode=true',*boundary.permission_overrides()),environment_allowlist=('HOME','CODEX_HOME','PATH','TMPDIR','TMP','TEMP'),cwd=str(directory),executable_sha256=boundary.binary_sha256,request_timeout=10,options=AppServerOptions(experimental_api=True))
   with environment(configured):await transport.start()
   for mode in (False,True):
    command=shell_command(scratch,mode);began=time.perf_counter();reply=await transport.request('command/exec',{'command':['/bin/zsh','-lc',command],'cwd':str(scratch),'permissionProfile':'aeep-native-task','timeoutMs':5000,'outputBytesCap':4096});stdout=reply.get('stdout','');stderr=reply.get('stderr','');facts={'explicit_scoped_TMPPREFIX':mode,'command_sha256':hashlib.sha256(command.encode()).hexdigest(),'exit_code':reply.get('exitCode'),'stdout_bytes':len(stdout.encode()),'stderr_bytes':len(stderr.encode()),'known_error_categories':categories(stderr),'elapsed_seconds':time.perf_counter()-began};record['probes'].append(facts)
    try:facts['known_result']=json.loads(stdout) if len(stdout.encode())<4096 else None
    except json.JSONDecodeError:facts['known_result']=None
    if not isinstance(facts['known_result'],dict) or set(facts['known_result'])!={'opened','saved','temp_root_matches'} or any(type(x)is not bool for x in facts['known_result'].values()):facts['known_result']=None
    expected=scratch/('output-prefix.xlsx' if mode else 'output-default.xlsx');facts['owned_output_exists']=expected.is_file() and not expected.is_symlink();facts['supported']=facts['exit_code']==0 and facts['known_result']=={'opened':True,'saved':True,'temp_root_matches':True} and facts['owned_output_exists']
    if facts['supported']:break
    if not {'permission_denied','shell_temporary_file','heredoc'}.intersection(facts['known_error_categories']):break
 except BaseException as exc:record['error_type']=type(exc).__name__
 finally:
  if transport:
   try:await asyncio.wait_for(transport.close(),5);record['cleanup_confirmed']=not transport.running
   except BaseException as exc:record['cleanup_error_type']=type(exc).__name__
  record.update(elapsed_seconds=time.perf_counter()-started,source_unchanged=verification_source_digest(ROOT)==SOURCE,scope='Synthetic shell/openpyxl read-save support only; no model, production task grader or acceptance claim',replay_allowed=False)
  repo.finish_operation(operation,elapsed_seconds=record['elapsed_seconds']);await router.close()
  if record['cleanup_confirmed']:shutil.rmtree(directory);record['owned_scratch_removed']=True
  else:record['owned_scratch_removed']=False
  resultpath.write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
if __name__=='__main__':
 if len(sys.argv)!=3 or sys.argv[1]!='--execute-reviewed':raise SystemExit('INERT: exact parent review required')
 asyncio.run(main(sys.argv[2]))
