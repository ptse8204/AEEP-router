"""Current-thread CLI agent-use evidence; not discovery, autonomy, or isolation."""
import asyncio, hashlib, json, runpy, subprocess, sys, tempfile, time
from datetime import timedelta
from pathlib import Path
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.assessment.workbook_native import implementation_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService
from aeep.models import Manifest, SideEffect, TaskScope, ValidationKind, ValidationSpec, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'reports/v08'
SOURCE='288e082274cf22631398ca404180f6b58cb27ed7d5654fec0420d1ee6a0a2782'
STATE=REPORTS/('native-sol61-agent-use-fault-start-288e.json' if sys.argv[1] in ('prepare-fault','verify-fault','uninstall-fault','invoke-fault') else 'native-sol61-agent-use-start-288e.json')
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3')
CODEX=Path('/Users/edwintse/.local/bin/codex').resolve()
ASSETS=ROOT/'integrations/assessment-runtime'
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    if sys.argv[1] in ('prepare','prepare-fault'):
        assert not STATE.exists()
        root=Path(tempfile.mkdtemp(prefix='aeep-sol61-agent-use-')).resolve()
        scratch=root/'scratch'; scratch.mkdir()
        fixtures=runpy.run_path(str(REPORTS/'workbook-footprint-calibration-288e.py'))['cases']()
        source=(ASSETS/'workbook_program.py').read_text()
        prefix=subprocess.run([str(PYTHON),'-I','-c','import sys; print(sys.prefix)'],capture_output=True,text=True,check=True).stdout.strip()
        boundary=NativeSandboxConfig(binary=str(CODEX),binary_sha256='sha256:'+hashlib.sha256(CODEX.read_bytes()).hexdigest(),project_root=str(root),read_roots=[str(Path(prefix).resolve())],write_roots=[str(scratch)])
        recipe=workbook_recipe(); spec=recipe.extension.reference.model_copy(deep=True)
        spec.id='native.workbook.sol61-agent-use'; spec.input_schema=recipe.input_schema; spec.output_schema=recipe.output_schema
        program="import json,sys; ns={'__name__':'reference'}; exec("+repr(source)+",ns); print(json.dumps(ns['reference'](json.load(sys.stdin))))"
        if sys.argv[1]=='prepare-fault':
            fault=scratch/'fault.json'; fault.write_text(json.dumps(json.loads((ASSETS/'workbook-faults.json').read_text())['stale_value']))
            program='import json; print(json.dumps(json.load(open('+repr(str(fault))+'))))'
        spec.config={**spec.config,'argv':[str(PYTHON),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(scratch)},'max_output_bytes':200000}
        spec.validators=[ValidationSpec(kind=ValidationKind.CALLBACK,config={'name':'aeep.workbook.native.v1','implementation_digest':implementation_digest()})]
        manifest=root/'aeep.json'; manifest.write_text(Manifest(database=str(root/'.aeep/state.db'),executors=[spec]).model_dump_json())
        router=Router.from_manifest(manifest)
        try:
            repo=AssessmentRepository(router.store); recipe_digest=repo.put('recipe',recipe.recipe_id,recipe); repo.review(recipe_digest)
            scope=TaskScope(scope_id='sol61-current-source-agent-use',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.READ,max_attempts=1 if sys.argv[1]=='prepare-fault' else 2,max_attempt_seconds=30,expires_at=utc_now()+timedelta(minutes=30))
            scope_digest=repo.put('task_scope',scope.scope_id,scope); repo.review(scope_digest)
            activation=activate(router,scope.scope_id)
            service=AEEPToolService(router,profile='task',task_activation=activation.activation_id)
            tools=service.list_tools(); assert len(tools)==1
            state={'source_digest':SOURCE,'root':str(root),'manifest':str(manifest),'activation':activation.activation_id,'tool':tools[0]['name'],'recipe_digest':recipe_digest,'scope_digest':scope_digest,'executor_fingerprint':executor_fingerprint(spec),'schema_bytes':len(json.dumps(tools).encode()),'instructions_bytes':len(service.instructions.encode()),'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'maximum_attempts':scope.max_attempts,'maximum_attempt_seconds':30,'classification':'current-thread GPT-6.1 Sol test-author-orchestrated CLI task use; shared filesystem; no model discovery, isolated comparison, or scored autonomy','assessment_ledger':'not used; separate production task allowance','model_tokens':'unknown; this collaboration turn has no AEEP-measured model accounting','fixtures':{}}
            for name,case in fixtures.items():
                inp=scratch/(name+'-input.json'); inp.write_text(json.dumps(case['input']))
                state['fixtures'][name]={'input':str(inp),'input_sha256':hashlib.sha256(inp.read_bytes()).hexdigest(),'expected':case['expected']}
            STATE.write_text(json.dumps(state,indent=2)+'\n')
            print(json.dumps({k:v for k,v in state.items() if k!='fixtures'}))
        finally: await router.close()
    else:
        state=json.loads(STATE.read_text())
        if sys.argv[1] in ('invoke','invoke-fault'):
            name=sys.argv[2]; case=sys.argv[3]; expected_code=int(sys.argv[4])
            argv=[sys.executable,'-m','aeep','tool-call',state['tool'],'--profile','task','--task-activation',state['activation'],'--manifest',state['manifest'],'--arguments','@'+state['fixtures'][case]['input'],'--compact']
            started=time.perf_counter(); r=subprocess.run(argv,capture_output=True,text=True,timeout=45)
            output=Path(state['root'])/(name+'-result.json'); output.write_text(r.stdout)
            record={'argv':argv,'exit_code':r.returncode,'wall_seconds':time.perf_counter()-started,'result_file':str(output),'stderr_bytes':len(r.stderr.encode()),'stdout_bytes':len(r.stdout.encode()),'stdout_sha256':hashlib.sha256(r.stdout.encode()).hexdigest()}
            if r.returncode: record['stop_response']={k:v for k,v in json.loads(r.stdout).items() if k!='output'}
            target=REPORTS/('native-sol61-agent-use-'+name+'-command-288e.json'); assert not target.exists(); target.write_text(json.dumps(record,indent=2)+'\n'); print(json.dumps(record)); assert r.returncode==expected_code
            return
        router=Router.from_manifest(state['manifest'])
        try:
            if sys.argv[1] in ('pause','resume','uninstall','uninstall-fault'):
                change_state(router,state['activation'],sys.argv[1].replace('-fault','')); print(json.dumps(inspect(router,state['activation'])))
            elif sys.argv[1] in ('verify','verify-fault'):
                name=sys.argv[2]; result=json.loads(Path(sys.argv[3]).read_text()); grader=runpy.run_path(str(ASSETS/'workbook_grader.py'))['grade']
                inp=json.loads(Path(state['fixtures'][name]['input']).read_text())
                receipt=result['receipts'][0]
                valid=grader({'input':inp,'output':result['output'],'expected':state['fixtures'][name]['expected']}) is True
                if sys.argv[1]=='verify-fault':
                    assert not result['ok'] and receipt['task_valid'] is False and not valid
                else:
                    assert result['ok'] and receipt['task_valid'] is True and valid
                summary={'case':name,'source_digest':SOURCE,'receipt_id':receipt['receipt_id'],'summary':result['summary'],'required_checks':receipt['checks'],'resources':receipt['recorded_resources'],'recovery_state':result['recovery_state'],'independent_grader_valid':valid,'input_json_bytes':Path(state['fixtures'][name]['input']).stat().st_size,'output_json_bytes':len(json.dumps(result['output']).encode())}
                target=REPORTS/('native-sol61-agent-use-'+name+('-fault' if sys.argv[1]=='verify-fault' else '')+'-288e.json'); assert not target.exists(); target.write_text(json.dumps(summary,indent=2)+'\n'); print(json.dumps(summary))
        finally: await router.close()
asyncio.run(main())
