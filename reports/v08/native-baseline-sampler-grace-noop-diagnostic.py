"""One zero-effect initialization diagnostic; no command/model dispatch."""
import asyncio,ast,hashlib,json,subprocess,sys,tempfile,time,shutil
from pathlib import Path
from aeep.assessment.models import AssessmentPlanningRequest,AssessmentLimits
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.models import StrictModel
from aeep.router import Router
from aeep.executors.command import _monitor_process
from dataclasses import asdict
import psutil
ROOT=Path(__file__).resolve().parents[2];R=ROOT/'reports/v08';SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
B=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex');P=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve();CHILD=R/'native-no-aeep-baseline-child-v2.py'
class Definition(StrictModel):
 source_digest:str
 driver_sha256:str
 child_sha256:str
 sampler_sha256:str
 binary_sha256:str
 python_sha256:str
 maximum_seconds:int=20
 maximum_model_turns:int=0
 maximum_operations:int=1
 classification:str='guard-only no-op handshake diagnosis; one native read-only Python print; no workbook/tool/model dispatch; not failed-workbook replay'
async def main():
 assert verification_source_digest(ROOT)==SOURCE
 router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json');repo=AssessmentRepository(router.store);old=AssessmentPlanningRequest.model_validate(repo.get('planning_request','planning_8e8a10fdfd7f49b891cf9f3f44c35228'))
 definition=Definition(source_digest=SOURCE,driver_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),child_sha256=hashlib.sha256(CHILD.read_bytes()).hexdigest(),sampler_sha256=hashlib.sha256((R/'native-resource-full-path-pair-v4.py').read_bytes()).hexdigest(),binary_sha256=hashlib.sha256(B.read_bytes()).hexdigest(),python_sha256=hashlib.sha256(P.read_bytes()).hexdigest());mapping=repo.put('native_initialization_diagnostic','baseline-sampler-grace-noop',definition);repo.review(mapping);req=old.model_copy(update={'plan_id':'planning_native_baseline_sampler_grace_noop','mapping_digest':mapping,'definition_digests':[*old.definition_digests,mapping]});digest=repo.put('planning_request',req.plan_id,req);repo.review(digest);repo.authorize(req);(R/'native-baseline-sampler-grace-noopialization-review.json').write_text(json.dumps({'authority':'standing finite exact delegation; parent authorized zero-effect harness setup diagnostic','definition':definition.model_dump(),'mapping_digest':mapping,'request_digest':digest},indent=2));op='native-init:'+req.plan_id;repo.reserve(req,op,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=20),stage='native_baseline_sampler_grace_noopialization_diagnosis');started=time.perf_counter();root=Path(tempfile.mkdtemp(prefix='aeep-baseline-sampler-grace-noop-',dir=ROOT));(root/'scratch').mkdir();record={}
 try:
  prefix=subprocess.run([str(P),'-I','-c','import sys;print(sys.prefix)'],capture_output=True,text=True,check=True,timeout=2).stdout.strip();cfg=NativeSandboxConfig(binary=str(B),binary_sha256='sha256:'+definition.binary_sha256,project_root=str(root),read_roots=[str(Path(prefix).resolve()),str(ROOT/'AGENTS.md')],write_roots=[str(root/'scratch')],single_process=True,python_binary=str(P),python_sha256='sha256:'+definition.python_sha256)
  node=next(x.value for x in ast.parse((ROOT/'src/aeep/hosts/codex_native_process.py').read_text()).body if isinstance(x,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='SINGLE_PROCESS_GUARD' for t in x.targets));guard=ast.literal_eval(node)
  payload={'diagnostic_only':False,'retain_diagnostics':True,'timeout':8,'argv':[str(P),'-I','-c','import json;print(json.dumps({}))'],'environment':{},'input':{},'binary':str(B),'binary_sha256':definition.binary_sha256,'python':str(P),'python_sha256':definition.python_sha256,'guard':guard,'guard_sha256':hashlib.sha256(guard.encode()).hexdigest(),'permission_overrides':['-c','features.apps=false',*cfg.permission_overrides()],'root':str(root)}
  node=next(x for x in ast.parse((R/'native-resource-full-path-pair-v4.py').read_text()).body if isinstance(x,ast.AsyncFunctionDef) and x.name=='monitored');exec(compile(ast.Module(body=[node],type_ignores=[]),str(R/'native-resource-full-path-pair-v4.py'),'exec'),globals())
  result,metrics=await monitored([sys.executable,'-I',str(CHILD)],json.dumps(payload).encode(),12)
  result.pop('output',None);record={'baseline_metadata':result,'metrics':metrics}
 except BaseException as error:record={'error_type':type(error).__name__,'safe_metadata':getattr(error,'safe_metadata',None),'stack':[{'file':Path(x.filename).name,'line':x.lineno,'function':x.name} for x in __import__('traceback').extract_tb(error.__traceback__)[-8:]]}
 finally:
  shutil.rmtree(root);elapsed=time.perf_counter()-started;repo.finish_operation(op,elapsed_seconds=elapsed);await router.close();record.update(elapsed_seconds=elapsed,model_turns=0,source_unchanged=verification_source_digest(ROOT)==SOURCE);(R/'native-baseline-sampler-grace-noopialization-result.json').write_text(json.dumps(record,indent=2)+'\n');print(json.dumps(record))
asyncio.run(main())
