"""Opt-in release validation against an explicitly selected local container image."""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import replace

import pytest

from aeep.assessment.containment import ContainerExecutor, container_name
from aeep.assessment.models import AssessmentEnvironment
from aeep.executors.base import ExecutionContext
from aeep.models import ActionRequest, ExecutionStatus, ExecutorSpec, new_id

pytestmark = [pytest.mark.assessment_boundary, pytest.mark.real_container, pytest.mark.skipif(not os.environ.get("AEEP_CONTAINER_IMAGE"), reason="requires an explicitly configured local release container")]


async def test_real_container_boundaries_timeout_and_cleanup():
    environment = AssessmentEnvironment(environment_id="release-container", kind="container", identity={"purpose": "release-validation"}, container_image=os.environ["AEEP_CONTAINER_IMAGE"], container_runtime=os.environ["AEEP_CONTAINER_RUNTIME"], container_socket=os.environ["AEEP_CONTAINER_SOCKET"], memory_mb=256, process_limit=32)
    executor = ContainerExecutor(environment)
    code = '''import json,os,pathlib,socket
checks={"uid":os.getuid(),"pids":pathlib.Path("/sys/fs/cgroup/pids.max").read_text().strip(),"memory":pathlib.Path("/sys/fs/cgroup/memory.max").read_text().strip()}
try:
 pathlib.Path("/forbidden-write").write_text("denied")
 checks["filesystem_denied"]=False
except OSError:
 checks["filesystem_denied"]=True
sock=socket.socket();sock.settimeout(.2)
try:
 sock.connect(("1.1.1.1",443));checks["network_denied"]=False
except OSError:
 checks["network_denied"]=True
finally:
 sock.close()
print(json.dumps(checks))
'''
    spec = ExecutorSpec(id="contained-check", capability="container.check@1", kind="command", description="Release containment check", config={"argv": ["python3", "-c", code], "output": {"type": "json"}, "timeout_seconds": 10})
    context = ExecutionContext(spec=spec, request=ActionRequest(capability=spec.capability), estimate=spec.estimate, attempt=1, attempt_id=new_id("real-container"))
    result = await executor.execute(context)
    assert result.status == ExecutionStatus.SUCCESS, result.model_dump_json()
    assert result.output == {"uid": 65534, "pids": "32", "memory": "268435456", "filesystem_denied": True, "network_denied": True}
    assert result.resources.cpu_ms == 0 and result.metadata["container_resource_usage"] == "unavailable"
    slow = spec.model_copy(deep=True)
    slow.config["argv"] = ["python3", "-c", "import time; time.sleep(60)"]
    slow.config["timeout_seconds"] = 0.2
    timeout = await executor.execute(replace(context, spec=slow, attempt_id=new_id("real-timeout")))
    assert timeout.status == ExecutionStatus.TIMEOUT
    assert timeout.resources.latency_ms > 0
    cancelled_id = new_id("real-cancel")
    task = asyncio.create_task(executor.execute(replace(context, spec=spec.model_copy(update={"config": {**spec.config, "argv": ["python3", "-c", "import time; time.sleep(60)"]}}), attempt_id=cancelled_id)))
    await asyncio.sleep(0.5)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    process = await asyncio.create_subprocess_exec(str(environment.container_runtime), "--host", f"unix://{environment.container_socket}", "ps", "--filter", "name=" + container_name(cancelled_id), "--format", "{{.ID}}", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    stdout, _stderr = await asyncio.wait_for(process.communicate(), 5)
    assert process.returncode == 0 and not stdout.strip(), json.dumps(result.metadata)


async def test_real_worker_crash_retains_attempt_and_recovery_removes_container(tmp_path):
    import sqlite3
    import sys
    from datetime import timedelta

    from aeep.assessment.models import AssessmentAuthorization, AssessmentLimits, content_digest
    from aeep.assessment.onboarding import reference_spec
    from aeep.assessment.recovery import recover
    from aeep.assessment.service import AssessmentService
    from aeep.models import Manifest, SideEffect, utc_now
    from aeep.qualification import RouteCandidate, behavior_fingerprint
    from aeep.router import Router

    root = tmp_path.resolve()
    manifest = root / "aeep.json"
    manifest.write_text(Manifest(database=str(root / "main.sqlite3"), executors=[reference_spec("csv")]).model_dump_json())
    router = Router.from_manifest(manifest)
    service = AssessmentService(router, root / "assessments")
    plugin = root / "plugin.txt"
    plugin.write_text("Reviewed crash fixture")
    subject = service.inspect_local(plugin)
    candidate = ExecutorSpec(id="crash-candidate", capability="assessment.csv@1", kind="command", description="Controlled crash fixture", enabled=False, idempotent=True, side_effect=SideEffect.READ, estimate=reference_spec("csv").estimate, config={"argv": ["python3", "-c", "import time; time.sleep(60)"], "timeout_seconds": 60, "output": {"type": "json"}})
    router.store.save_route_candidate(RouteCandidate(executor_id=candidate.id, source_id="reviewed-crash-fixture", capability=candidate.capability, behavior_fingerprint=behavior_fingerprint(candidate), spec=candidate))
    environment = AssessmentEnvironment(environment_id="release-container", kind="container", identity={}, container_image=os.environ["AEEP_CONTAINER_IMAGE"], container_runtime=os.environ["AEEP_CONTAINER_RUNTIME"], container_socket=os.environ["AEEP_CONTAINER_SOCKET"])
    plan = service.propose(subject_id=subject.subject_id, family="csv", candidate_id=candidate.id, baseline_id="reference.csv", authorization_id="crash-grant", environment=environment)
    for digest in plan.definition_digests:
        service.repository.review(digest)
    service.repository.grant(AssessmentAuthorization(authorization_id="crash-grant", subject_digests=[content_digest(subject)], recipe_digests=[plan.recipe_digest], environment_digests=[plan.environment_digest], limits=AssessmentLimits(max_operations=1000, max_elapsed_seconds=1000), expires_at=utc_now() + timedelta(hours=1)))
    assessment_id = service.enqueue(plan.plan_id)
    worker = await asyncio.create_subprocess_exec(sys.executable, "-m", "aeep.assessment.worker", "--manifest", str(manifest), "--directory", str(service.directory), "--assessment", assessment_id, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
    target = None
    try:
        async with asyncio.timeout(20):
            while target is None:
                await asyncio.sleep(0.1)
                for database in (service.directory / plan.plan_id / "attempts").glob("*.sqlite3"):
                    connection = sqlite3.connect(database)
                    try:
                        row = connection.execute("SELECT attempt_id FROM execution_attempts WHERE executor_id=? AND state='INVOKING'", (candidate.id,)).fetchone()
                    except sqlite3.OperationalError:
                        row = None
                    finally:
                        connection.close()
                    if row:
                        target = row[0]
                        break
        await asyncio.sleep(1)
        worker.kill()
        await worker.wait()
        assert service.status(assessment_id)["state"] == "indeterminate"
        record = await recover(service, assessment_id)
        assert target in record.retained_attempt_ids
        process = await asyncio.create_subprocess_exec(str(environment.container_runtime), "--host", f"unix://{environment.container_socket}", "ps", "--filter", "name=" + container_name(target), "--format", "{{.ID}}", stdout=asyncio.subprocess.PIPE)
        output, _ = await process.communicate()
        assert not output.strip()
        assert service.status(assessment_id)["state"] == "indeterminate"
        assert not router.store.list_receipts()
        assert await asyncio.to_thread(lambda: list((service.directory / plan.plan_id / "attempts").glob("*.sqlite3")))
    finally:
        if worker.returncode is None:
            worker.kill()
            await worker.wait()
        if target:
            await ContainerExecutor(environment).cleanup(target)
        await router.close()


async def test_real_trial_mount_excludes_future_cases_and_other_arm(tmp_path):
    fixture_root = tmp_path.resolve() / 'fixtures'
    current = fixture_root / 'trial-inputs' / ('a' * 64)
    other = fixture_root / 'trial-inputs' / ('b' * 64)
    future = fixture_root / 'holdout-0'
    for root in (current, other, future):
        root.mkdir(parents=True)
        (root / 'input.txt').write_text('synthetic fixture')
    environment = AssessmentEnvironment(environment_id='private-fixture', kind='container', identity={},
        container_image=os.environ['AEEP_CONTAINER_IMAGE'], container_runtime=os.environ['AEEP_CONTAINER_RUNTIME'],
        container_socket=os.environ['AEEP_CONTAINER_SOCKET'])
    code = '''import json,pathlib,sys
p=json.load(sys.stdin); root=pathlib.Path(p['root'])
print(json.dumps({'current':(root/'input.txt').read_text(), 'other':pathlib.Path(p['other']).exists(), 'future':pathlib.Path(p['future']).exists()}))
'''
    spec = ExecutorSpec(id='private-fixture', capability='test', kind='command', description='Controlled private-fixture probe',
        config={'argv':['python3','-c',code], 'stdin_json':True, 'output':{'type':'json'}, 'timeout_seconds':10})
    context = ExecutionContext(spec=spec, request=ActionRequest(capability='test', input={'root':str(current),'other':str(other),'future':str(future)}),
        estimate=spec.estimate, attempt=1, attempt_id=new_id('fixture'))
    result = await ContainerExecutor(environment, fixture_root=fixture_root).execute(context)
    assert result.status == ExecutionStatus.SUCCESS, result.model_dump_json()
    assert result.output == {'current':'synthetic fixture', 'other':False, 'future':False}


async def test_real_worker_artifact_transfer_rejects_escapes_and_shared_state():
    import base64
    import hashlib

    from aeep.errors import ConfigurationError
    from aeep.hosts.workers import ManagedWorkerBinding

    worker = ManagedWorkerBinding(worker_id='artifact-fixture',runtime=os.environ['AEEP_CONTAINER_RUNTIME'],
        socket=os.environ['AEEP_CONTAINER_SOCKET'],image=os.environ['AEEP_CONTAINER_IMAGE'],
        platform='linux/arm64' if os.uname().machine == 'arm64' else 'linux/amd64',binary='/usr/local/bin/python3',
        binary_sha256='a'*64,configuration_digest='b'*64,dependencies_digest='c'*64)
    ids = [new_id('artifact-case'), new_id('artifact-other')]
    docker = [worker.runtime,'--host','unix://'+worker.socket]
    async def command(*argv):
        process = await asyncio.create_subprocess_exec(*argv,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await asyncio.wait_for(process.communicate(),10)
        assert process.returncode == 0, stderr.decode()[-1000:]
        return stdout
    names = ['aeep-'+hashlib.sha256(identity.encode()).hexdigest()[:32] for identity in ids]
    try:
        for name in names:
            await command(*docker,'run','--pull=never','--rm','-d','--name',name,'--network=none','--read-only',
                '--user','65534:65534','--cap-drop=ALL','--security-opt=no-new-privileges','--pids-limit=16','--memory=128m',
                '--tmpfs','/workspace:rw,nosuid,nodev,size=8m,uid=65534,gid=65534,mode=700',
                '--entrypoint','python3',worker.image,'-c','import time; time.sleep(60)')
        payload = base64.b64encode(b'current task only').decode()
        written = await worker.artifact(ids[0],name='input.xlsx',limit=100,data=payload)
        result = await worker.artifact(ids[0],name='input.xlsx',limit=100)
        assert result['data'] == payload and result['sha256'] == written['sha256']
        await command(*docker,'exec',names[0],'python3','-c',
            "import os; os.symlink('/etc/passwd','/workspace/link.xlsx'); os.mkfifo('/workspace/fifo.xlsx'); os.link('/workspace/input.xlsx','/workspace/hard.xlsx')")
        for name, limit in [('link.xlsx',100),('fifo.xlsx',100),('hard.xlsx',100),('../etc/passwd',100),('input.xlsx',2)]:
            with pytest.raises(ConfigurationError,match='artifact transfer failed'):
                await worker.artifact(ids[0],name=name,limit=limit)
        for name, data in [('input.xlsx',payload),('other.xlsx','not base64'),('large.xlsx',base64.b64encode(b'x'*101).decode())]:
            with pytest.raises(ConfigurationError,match='artifact transfer failed'):
                await worker.artifact(ids[0],name=name,limit=100,data=data)
        with pytest.raises(ConfigurationError,match='artifact transfer failed'):
            await worker.artifact(ids[1],name='input.xlsx',limit=100)
    finally:
        for identity in ids:
            assert await worker.cleanup(identity)
