"""Pinned Waza mock-engine conformance. Review only unless specifically approved."""
import argparse
import asyncio
import hashlib
import io
import json
import shutil
import stat
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from aeep.executors.base import ExecutionContext
from aeep.executors.command import CommandExecutor
from aeep.models import ActionRequest, ExecutionReceipt, ExecutorSpec, SideEffect, utc_now
from aeep_toolkit.external import PINS, import_result, render_import
from aeep_toolkit.install_runtime import digest

ROOT=Path(__file__).resolve().parents[4]; HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'integrations/toolkit'))
from stack import command, probe, sandbox

SPEC={'schemaVersion':'1.4','name':'aeep-waza-mock','skill':'aeep-fixture','version':'1.0',
      'config':{'executor':'mock','model':'mock','trials_per_task':1,'timeout_seconds':10,'parallel':False,
                'max_attempts':1,'skill_directories':['skill']},
      'graders':[{'name':'fixed-echo','type':'text','config':{'contains':['Mock response for:']}}],
      'tasks':['tasks/*.yaml']}
SKILL='---\nname: aeep-fixture\ndescription: Synthetic Waza engineering fixture; no candidate code.\n---\nUse the ordinary tools.\n'


async def run(review):
    assert shutil.disk_usage(HERE).free > 50*1024**3+1024**3
    output=HERE/'execution';output.mkdir(mode=0o700)
    artifact=urllib.request.urlopen(review['archive_url'],timeout=60).read(review['archive_bytes']+1)
    assert len(artifact)==review['archive_bytes'] and hashlib.sha256(artifact).hexdigest()==review['archive_sha256']
    with tempfile.TemporaryDirectory(prefix='aeep-waza-reviewed-') as temp:
        root=Path(temp).resolve()
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            members=[i for i in archive.infolist() if not i.is_dir() and Path(i.filename).name in {'microsoft-azd-waza-darwin-arm64'}]
            assert len(members)==1 and members[0].file_size<=400*1024**2
            member=members[0];assert not stat.S_ISLNK(member.external_attr>>16)
            binary=root/'waza';binary.write_bytes(archive.read(member));binary.chmod(0o700)
            (output/'archive-inventory.json').write_text(json.dumps({'entries':[i.filename for i in archive.infolist()],
                'selected':member.filename,'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},indent=2)+'\n')
        runtime=Path('/private/tmp/aeep-ase-c04-tt14mj6r/rebuild')
        prefix,env=sandbox(root,runtime)
        boundary=probe(prefix,env,root)
        (output/'boundary.json').write_text(json.dumps(boundary,indent=2)+'\n')
        (root/'skill').mkdir();(root/'skill/SKILL.md').write_text(SKILL)
        (root/'tasks').mkdir()
        for index in range(3):
            (root/f'tasks/case-{index}.yaml').write_text(json.dumps({'id':f'case-{index}','name':f'case-{index}',
                'inputs':{'prompt':f'synthetic fixture {index}'}}))
        (root/'eval.yaml').write_text(json.dumps(SPEC))
        # Use the same enforced sandbox prefix without launching the Python interpreter.
        launch=prefix[:3]+[str(binary)]
        version=command([*launch,'--version'],cwd=root,env=env,timeout=30)
        (output/'version.txt').write_text(version)
        spec=ExecutorSpec(id='toolkit.waza.mock',capability='toolkit.evaluation.mock',kind='command',
            description='Exact pinned Waza mock engine, three cases with baseline; no model or remote graders',side_effect='write',
            config={'argv':[*launch,'run',str(root/'eval.yaml'),'--baseline','--no-cache','--output',str(root/'results.json')],
                    'argv_literal':True,'inherit_env':False,'env':env,'cwd':str(root),'timeout_seconds':90,'max_output_bytes':65536})
        action=ActionRequest(capability=spec.capability,input={});started=utc_now();executor=CommandExecutor()
        try:
            raw=await (await executor.start(ExecutionContext(request=action,spec=spec,estimate=spec.estimate,attempt=1,
                                                            approved_side_effect=SideEffect.WRITE))).task
        finally:
            await executor.close()
        receipt=ExecutionReceipt(decision_id='reviewed-waza-mock',action_id=action.action_id,capability=spec.capability,
            executor_id=spec.id,executor_kind=spec.kind,status=raw.status,started_at=started,ended_at=utc_now(),
            estimated=spec.estimate,actual_resources=raw.resources,accounting=raw.accounting,execution_success=raw.status.value=='success',
            error_type=raw.error_type,metadata={'review_sha256':digest(review),'evidence_kind':'synthetic','scope':'whole mock evaluator process'})
        (output/'receipt.json').write_text(receipt.model_dump_json(indent=2)+'\n')
        (output/'stdout.txt').write_text(raw.stdout or '')
        (output/'stderr.txt').write_text(raw.stderr or '')
        (output/'failure.json').write_text(json.dumps({'status':raw.status.value,'error_type':raw.error_type,'error_message':raw.error_message},indent=2)+'\n')
        assert raw.status.value=='failed' and raw.error_type=='CommandExitError' and raw.error_message=='command exited with status 1'
        assert (raw.stderr or '').strip()=='baseline comparison: skills have negative/neutral impact (100.0% vs 100.0%)'
        result=(root/'results.json').read_bytes();(output/'results.json').write_bytes(result)
        data=json.loads(result)
        assert data['config']['engine_type']=='mock'
        for arm in (data,data['baseline_outcome']):
            assert len(arm['tasks'])==3
            assert all(task['status']=='passed' and len(task['runs'])==1 and task['runs'][0]['status']=='passed' for task in arm['tasks'])
        imported=import_result(result,'waza',revision=PINS['waza'],candidate_sha256=hashlib.sha256(SKILL.encode()).hexdigest())
        for format in ('json','markdown','html'):
            (output/('normalized.'+{'json':'json','markdown':'md','html':'html'}[format])).write_text(render_import(imported,format))
        assert imported['observations']['actual_cash'] is None
        assert all(run['reported_usage'] is None for run in imported['observations']['runs'])
        (output/'checks.json').write_text(json.dumps({'expected_runs':6,'passed_runs':6,'process_exit_code':1,'neutral_comparison':True,'source_revision_asserted':PINS['waza'],
            'binary_source_correspondence_verified':False,'model_calls':0,'evidence_kind':'synthetic',
            'paired_agent_worker_conformance':False,'raw_report_not_verified_benefit':True},indent=2)+'\n')
    (output/'cleanup.json').write_text(json.dumps({'private_directory':str(root),'removed':not root.exists()})+'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-reviewed-digest');args=parser.parse_args()
    review=json.loads((HERE/'operation-review.json').read_text())
    assert hashlib.sha256(Path(__file__).read_bytes()).hexdigest()==review['driver_sha256']
    assert digest(SPEC)==review['spec_sha256']
    if args.execute_reviewed_digest is None:
        print(json.dumps({'review_sha256':digest(review),'execution':False}));return
    assert args.execute_reviewed_digest==digest(review)
    asyncio.run(run(review))


if __name__=='__main__':main()
