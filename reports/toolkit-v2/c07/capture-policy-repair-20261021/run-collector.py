"""One explicitly approved collector boundary inspection; no model turns or installs."""
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.hosts import codex_pair_inspection as inspection
from aeep.hosts.workers import binding_from_config
from aeep.router import Router

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
PORTS = '''import json,pathlib
ports=[]
for line in pathlib.Path('/proc/net/tcp').read_text().splitlines()[1:]:
 fields=line.split()
 address,port=fields[1].split(':')
 if address=='0100007F' and fields[3]=='0A':ports.append(int(port,16))
print(json.dumps({'loopback_listener_ports':ports}))
'''
DENIED = '''import json,socket
denied=False
try:
 connection=socket.create_connection(('127.0.0.1',PORT),timeout=2)
 connection.close()
except PermissionError:
 denied=True
print(json.dumps({'collector_connection_denied':denied}))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*args):
    return subprocess.check_output(['/usr/local/bin/docker','--host',
        'unix:///Users/edwintse/.docker/run/docker.sock',*args],text=True,stderr=subprocess.DEVNULL,timeout=25).strip()


async def main():
    review_path = OUT / 'collector-operation-review.json'
    assert len(sys.argv)==2 and sha(review_path)==sys.argv[1]
    review = json.loads(review_path.read_text())
    approval = json.loads((OUT / 'collector-operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256']==sys.argv[1]
    assert sha(Path(__file__))==review['runner_sha256']
    assert sha(OUT / 'collector-definitions.json')==review['definitions_sha256']
    assert verification_source_digest(ROOT)==review['source_digest']
    validation=json.loads((OUT.parent/'capture-policy-repair-20261021/validation/source-stability.json').read_text())
    assert validation['all_passed'] and validation['source_digest']==review['source_digest']
    assert shutil.disk_usage(ROOT).free > 51*1024**3
    proposal = json.loads((OUT / 'collector-definitions.json').read_text())
    assert not (OUT / 'collector-started.json').exists()
    before = json.loads(docker('inspect','--format',review['proxy_inspect_format'],review['proxy_name']))
    assert not before['Running'] and before['Id']==review['proxy_id'] and before['Image']==review['proxy_image']
    assert before['Memory']==before['MemorySwap']==review['proxy_memory_bytes']
    assert review['network_id'] in [v['NetworkID'] for v in before['Networks'].values()]
    with (OUT / 'collector-started.json').open('x') as stream:
        json.dump({'review_sha256':sys.argv[1],'replay_allowed':False},stream)
    router=Router.from_manifest(BASE/'aeep.json')
    service=AssessmentService(router,BASE/'.aeep/assessments')
    repo=service.repository
    request=ConformanceProbeRequest.model_validate(proposal['requests'][0])
    operation=request.plan_id+':collector-proxy-lifecycle'
    result={'review_sha256':sys.argv[1],'source_digest':review['source_digest'],
        'model_turns':0,'images_created':0,'installations':0,'raw_payloads_retained':False,
        'telemetry_boundary_observations':{},'replay_allowed':False,'full_conformance':False}
    original_collect=inspection.collect
    reserved=False
    started_proxy=False
    began=time.monotonic()

    async def collect(adapter, config, journal, recheck):
        facts=await original_collect(adapter,config,journal,recheck)
        result.setdefault('initial_inspection', {})[config.adapter_id] = facts
        assert facts.get('inspection_complete') and facts.get('identity_digest')
        recheck()
        worker=binding_from_config(config.managed_worker)
        container='aeep-'+hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
        ports=json.loads(await inspection.docker(worker,'exec','-i','--user','65534:65534',
            container,'python3','-I','-c',PORTS))['loopback_listener_ports']
        assert len(ports)==1 and type(ports[0]) is int and 0<ports[0]<65536
        program=DENIED.replace('PORT',str(ports[0]))
        digest=hashlib.sha256(program.encode()).hexdigest()
        journal.append('action.started','collector-access-start',action_digest=digest)
        observed=await inspection.command(adapter,program,timeout_ms=5000)
        assert observed=={'collector_connection_denied':True}, 'Collector must be unreachable from trial code.'
        journal.append('action.completed','collector-access-complete',action_digest=digest)
        journal.append('artifact.created','collector-denied-result',evidence_ref=content_digest(observed))
        result['telemetry_boundary_observations'][worker.digest()]={
            'collector_connection_denied':True,'scope_sha256':hashlib.sha256(adapter.transport.metrics_scope.encode()).hexdigest(),
            'program_sha256':digest,'native_command_path':True,'port_is_private_ephemeral':True}
        facts['collector_boundary']=result['telemetry_boundary_observations'][worker.digest()]
        return facts

    try:
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(proposal['amendment']),proposal['definitions'])
        repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,
            max_elapsed_seconds=600,max_cash_usd=0),stage='collector_proxy_lifecycle')
        reserved=True
        repo.authorize(request)
        started_proxy=True
        docker('start',review['proxy_name'])
        inspection.collect=collect
        async with asyncio.timeout(420):
            result['pair']=await inspection.execute_pair(service,*proposal['request_ids'])
        result['passed']=bool(result['pair'].get('probes_match')) and len(result['telemetry_boundary_observations'])==2
        assert result['passed']
    except BaseException as exc:
        result.update(passed=False,error_type=type(exc).__name__)
    finally:
        inspection.collect=original_collect
        if started_proxy:
            try:
                docker('stop','--time','5',review['proxy_name'])
                result['proxy_restored_stopped']=docker('inspect','--format','{{.State.Running}}',review['proxy_name'])=='false'
            except Exception as exc:
                result.update(proxy_restored_stopped=False,cleanup_error_type=type(exc).__name__)
        if reserved:
            repo.finish_operation(operation,elapsed_seconds=time.monotonic()-began)
        result['source_unchanged']=verification_source_digest(ROOT)==review['source_digest']
        result['grant_after']=list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        (OUT / 'collector-result.json').write_text(json.dumps(result,indent=2)+'\n')
        await router.close()
        print(json.dumps({k:v for k,v in result.items() if k!='pair'}))


if __name__=='__main__':
    asyncio.run(main())
