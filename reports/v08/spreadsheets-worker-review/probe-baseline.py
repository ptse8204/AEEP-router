import asyncio, hashlib, json, subprocess, tempfile
from pathlib import Path
from aeep.hosts.workers import ManagedWorkerBinding
from aeep.hosts.codex_app_server import CodexAppServerTransport

async def main():
 if Path('reports/v08/plain-worker-review-rerun.json').exists(): raise FileExistsError("retain previous diagnostic evidence; choose a new output path")
 c=Path('/tmp/aeep-plain-worker-review')
 worker=ManagedWorkerBinding(schema_version='execution.worker.v2',worker_id='plain-review',runtime='/usr/local/bin/docker',socket='/Users/edwintse/.docker/run/docker.sock',image=(c/'image-id').read_text().strip(),platform='linux/arm64',binary='/opt/codex/codex',binary_sha256=hashlib.sha256((c/'codex').read_bytes()).hexdigest(),configuration_digest=hashlib.sha256((c/'worker-config.json').read_bytes()).hexdigest(),dependencies_digest=hashlib.sha256(b'no selected plugin').hexdigest(),seccomp_profile=json.loads(Path('integrations/managed-worker/nested-sandbox-seccomp.example.json').read_text()),permissions_profile='aeep')
 report={'schema_version':'aeep.worker-dependency-review.v1','policy_approved':False,'environment_verified':False,'model_turns':0,'worker':worker.model_dump(mode='json'),'observations':{}}
 code="import pathlib,json; assert not pathlib.Path('/opt/dependencies/plugin').exists(); assert not pathlib.Path('/opt/dependencies/runtime/node_modules/@oai/artifact-tool').exists(); print(json.dumps({'selected_plugin_absent': True, 'artifact_tool_absent': True}))"
 with tempfile.TemporaryDirectory(prefix='aeep-skill-review-') as temp:
  security=worker.prepare_security(Path(temp))
  result=subprocess.run(worker.argv(('sandbox','-P','aeep','--include-managed-config','--','python3','-c',code),execution_id='plain-runtime-review',security_path=security),capture_output=True,timeout=40)
  report['observations']['runtime']={'exit_code':result.returncode,'stdout':result.stdout.decode()[-2000:],'stderr':result.stderr.decode()[-2000:]}
  transport=CodexAppServerTransport(worker.argv(('app-server',),execution_id='plain-inventory-review',security_path=security),request_timeout=30,max_message_bytes=4194304)
  try:
   result=await transport.request('skills/list',{'cwds':['/workspace'],'forceReload':True})
   report['observations']['skills']=result
  except Exception as exc:
   report['observations']['inventory_error']=type(exc).__name__
  finally:
   await transport.close()
   report['observations']['cleanup_confirmed']=await worker.cleanup('plain-inventory-review')
 Path('reports/v08/plain-worker-review-rerun.json').write_text(json.dumps(report,indent=2)+'\n')
 print(json.dumps(report['observations'],indent=2))
asyncio.run(main())
