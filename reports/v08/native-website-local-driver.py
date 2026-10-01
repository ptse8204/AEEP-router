"""Fixed offline local website lifecycle; no model, server, deployment, or campaign."""
import asyncio, hashlib, json, subprocess, sys
from datetime import timedelta
from pathlib import Path
from aeep.assessment.models import RecipeDefinition
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.hosts.codex_sandbox import NativeSandboxConfig
from aeep.mcp.server import AEEPToolService
from aeep.models import ExecutorSpec, Manifest, SideEffect, TaskScope, utc_now
from aeep.router import Router
from aeep.tasks import activate, change_state, inspect
ROOT=Path(__file__).resolve().parents[2]
REPORTS=ROOT/'reports/v08'
STATE=REPORTS/'native-website-local-definition.json'
RESULT=REPORTS/'native-website-local-result.json'
SOURCE='f55ebe5ca0764a8ebfbcfa653c49ee39cced7e85b0a78515d6bbbb6b2f0a1cc4'
PYTHON=Path('/Users/edwintse/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/bin/python3').resolve()
CODEX=Path('/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex').resolve()
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
async def main():
    assert verification_source_digest(ROOT)==SOURCE
    if sys.argv[1]=='prepare':
        assert not STATE.exists()
        root=ROOT/'.aeep/native-website-local'; root.mkdir()
        data=root/'data'; data.mkdir()
        (data/'unrelated.txt').write_text('Preserve this operator note.\n')
        (data/'index.html').write_text('<!doctype html><html lang="en"><head><title>Local fixture</title><link rel="stylesheet" href="style.css"></head><body><h1>Draft</h1><aside>Preserved content</aside></body></html>')
        (data/'style.css').write_text('body { color: #222; background: #fff; }\n')
        config=root/'.codex/config.toml';config.parent.mkdir();config.write_text('model = "operator-preserved"\n')
        prefix=subprocess.run([str(PYTHON),'-I','-c','import sys;print(sys.prefix)'],capture_output=True,text=True,check=True).stdout.strip()
        boundary=NativeSandboxConfig(binary=str(CODEX),binary_sha256='sha256:'+sha(CODEX),project_root=str(root),read_roots=[str(Path(prefix).resolve())],write_roots=[str(data)],single_process=True,python_binary=str(PYTHON),python_sha256='sha256:'+sha(PYTHON))
        program="import json,sys;from pathlib import Path;x=json.load(sys.stdin);p=Path("+repr(str(data/'index.html'))+");text=p.read_text();old,new={'build':('<h1>Draft</h1>','<h1>Local website</h1>'),'edit':('<h1>Local website</h1>','<h1>Updated local website</h1>')}[x['operation']];assert text.count(old)==1;p.write_text(text.replace(old,new));print(json.dumps({'operation':x['operation'],'updated':'index.html'}))"
        inp={'type':'object','properties':{'operation':{'enum':['build','edit']}},'required':['operation'],'additionalProperties':False}
        out={'type':'object','properties':{'operation':{'enum':['build','edit']},'updated':{'const':'index.html'}},'required':['operation','updated'],'additionalProperties':False}
        spec=ExecutorSpec(id='local.website.fixed',capability='local.website.fixed@1',kind='command',description='Two fixed local static HTML edits; no deployment.',input_schema=inp,output_schema=out,side_effect=SideEffect.WRITE,idempotent=False,config={'argv':[str(PYTHON),'-I','-c',program],'native_sandbox':boundary.model_dump(mode='json'),'env':{'TMPDIR':str(data)},'timeout_seconds':15,'max_output_bytes':10000})
        recipe=RecipeDefinition(recipe_id='local-website-offline-lifecycle',capability=spec.capability,description=spec.description,input_schema=inp,output_schema=out,generator='record_template:1',grader='exact_match:1',extractor='structural_json:1',variations=['fixed'],exclusions=['Not an assessment recipe or qualification; task tool declaration only.'])
        manifest=root/'aeep.json';manifest.write_text(Manifest(database=str(root/'.aeep/state.db'),executors=[spec]).model_dump_json())
        router=Router.from_manifest(manifest)
        try:
            repo=AssessmentRepository(router.store);rd=repo.put('recipe',recipe.recipe_id,recipe);repo.review(rd)
            scope=TaskScope(scope_id='local-website-fixed-two-edits',project_root=str(root),executor_fingerprints={spec.id:executor_fingerprint(spec)},approval_ceiling=SideEffect.WRITE,max_attempts=2,max_attempt_seconds=15,expires_at=utc_now()+timedelta(hours=1))
            sd=repo.put('task_scope',scope.scope_id,scope);repo.review(sd)
            state={'source_digest':SOURCE,'driver_sha256':sha(Path(__file__)),'root':str(root),'manifest':str(manifest),'scope_id':scope.scope_id,'scope_digest':sd,'recipe_digest':rd,'executor_fingerprint':executor_fingerprint(spec),'binary':str(CODEX),'binary_sha256':sha(CODEX),'python':str(PYTHON),'python_sha256':sha(PYTHON),'before':{p.name:sha(p) for p in data.iterdir()},'original_config':config.read_text(),'attempts':2,'seconds_per_attempt':15,'authority':'Standing September25/27 finite exact-definition delegation; separate production task allowance, no assessment grant amendment','classification':'Offline synthetic local lifecycle; no live agent, value, arbitrary website readiness, or deployment evidence'}
            STATE.write_text(json.dumps(state,indent=2)+'\n');print(json.dumps(state))
        finally: await router.close()
        return
    state=json.loads(STATE.read_text());assert sha(Path(__file__))==state['driver_sha256'];assert not RESULT.exists()
    root=Path(state['root']);data=root/'data';router=Router.from_manifest(state['manifest']);evidence={'definition_sha256':sha(STATE),'source_digest':SOURCE,'phases':[],'classification':state['classification'],'assessment_ledger':'Separate production task allowance; no assessment operations','model_tokens':'Unknown for authoring collaboration; no model invocation in lifecycle'}
    def save(): RESULT.write_text(json.dumps(evidence,indent=2)+'\n')
    try:
        activation=activate(router,state['scope_id']);evidence['activation_id']=activation.activation_id
        service=AEEPToolService(router,profile='task',task_activation=activation.activation_id,approved_side_effect=SideEffect.WRITE)
        tool=service.list_tools()[0]['name'];assert len(service.list_tools())==1
        for operation,heading in [('build','Local website'),('edit','Updated local website')]:
            if operation=='edit':
                (data/'operator-note.txt').write_text('Added between tasks; preserve.\n')
                evidence['later_operator_note_digest']=sha(data/'operator-note.txt')
            view=(await service.call(tool,{'operation':operation}))['structuredContent'];evidence['phases'].append({'operation':operation,'response':view});save();assert view['ok']
            text=(data/'index.html').read_text();assert '<h1>'+heading+'</h1>' in text and '<aside>Preserved content</aside>' in text and 'href="style.css"' in text
            assert sha(data/'style.css')==state['before']['style.css'] and sha(data/'unrelated.txt')==state['before']['unrelated.txt']
            evidence['phases'].append({'operation':'independent_verify_'+operation,'valid':True,'index_sha256':sha(data/'index.html'),'limit':'Fixed literal HTML, stylesheet linkage and preservation; no browser rendering or accessibility audit'});save()
        denied=await service.call('aeep_website_publish',{'destination':'https://example.invalid'})
        assert denied.get('isError') is True
        evidence['phases'].append({'operation':'attempted_publish','response':denied,'permitted_route':False,'destination_authority':False,'network_invoked':False});save()
        change_state(router,activation.activation_id,'pause')
        paused=(await service.call(tool,{'operation':'edit'}))['structuredContent'];assert not paused.get('ok',False)
        evidence['phases'].append({'operation':'paused_dispatch','response':paused});save()
        change_state(router,activation.activation_id,'resume');before=inspect(router,activation.activation_id);assert before['attempts_used']==2
        restored=change_state(router,activation.activation_id,'uninstall');assert restored['overlay']=='absent'
        assert (root/'.codex/config.toml').read_text()==state['original_config']
        assert sha(data/'operator-note.txt')==evidence['later_operator_note_digest']
        evidence['phases'].append({'operation':'uninstall_restoration','inspection':restored,'project_config_restored':True,'later_user_edit_preserved':True})
        evidence['receipt_ids']=[p['response']['receipts'][0]['receipt_id'] for p in evidence['phases'] if p['operation'] in ('build','edit')]
        assert all(router.store.get_receipt(x) is not None for x in evidence['receipt_ids'])
        evidence.update(complete=True,source_unchanged=verification_source_digest(ROOT)==SOURCE,publish_gate_complete=False,model_turns=0);save()
    except Exception as exc:
        evidence.update(complete=False,failure_type=type(exc).__name__,failure=str(exc));save();raise
    finally: await router.close()
    print(json.dumps({'result':str(RESULT),'complete':True}))
asyncio.run(main())
