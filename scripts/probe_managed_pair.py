#!/usr/bin/env python3
"""Offline paired-worker boundary observations; never sign in or invoke a model."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

from aeep.assessment.identity import file_digest
from aeep.assessment.models import content_digest
from aeep.assessment.verification import verification_source_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_pair_inspection import CHECK, DEPENDENCY, SEED, command, docker
from aeep.hosts.workers import binding_from_config, validate_worker_pair
from aeep.models import ExecutorSpec

ROOT = Path(__file__).resolve().parents[1]



def offline_specs(path: Path) -> tuple[list[ExecutorSpec], str]:
    digest = file_digest(path.absolute())  # Reject authentication paths and symlinks before reading.
    with path.open('rb') as stream:
        data = stream.read(262145)
    if len(data) > 262144:
        raise ValueError('worker fixture definitions exceed the input bound')
    if hashlib.sha256(data).hexdigest() != digest:
        raise ValueError("worker fixture changed during review")
    raw = json.loads(data)
    if not isinstance(raw, list) or len(raw) != 2:
        raise ValueError('two offline worker definitions required, control then treatment')
    specs = [ExecutorSpec.model_validate(item) for item in raw]
    workers = []
    for spec in specs:
        config = spec.managed_host_config()
        worker = binding_from_config(config.managed_worker)
        if (worker is None or any((worker.credential_volume, worker.network_id, worker.model_proxy_url))
                or config.argv != (worker.binary, 'app-server')):
            raise ValueError('probe refuses credentials, networking and alternate entrypoints')
        workers.append(worker)
    validate_worker_pair(workers[0], workers[1])
    return specs, digest




async def probe(path: Path) -> dict[str, Any]:
    specs, fixture_digest = await asyncio.to_thread(offline_specs, path)
    source = await asyncio.to_thread(verification_source_digest, ROOT)
    suffix = uuid.uuid4().hex
    names = ['control-'+suffix, 'treatment-'+suffix]
    canary = 'aeep-synthetic-'+suffix
    result: dict[str, Any] = dict(purpose='offline paired-worker boundary fixture',
        authenticated=False, model_turns=0, full_conformance=False, source_digest=source,
        fixture_digest=fixture_digest, workers={}, passed=False)
    active = []
    pending: asyncio.Task[dict[str, Any]] | None = None
    stage = 'start'
    try:
        with tempfile.TemporaryDirectory(prefix='aeep-external-answer-') as directory:
            answer = Path(directory)/'synthetic-answer'
            answer.write_text('coordinator-only synthetic answer')
            for index, spec in enumerate(specs):
                worker = binding_from_config(spec.managed_host_config().managed_worker)
                assert worker is not None
                adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=b'offline-pair-fixture')
                active.append((worker, adapter))
                await command(adapter, 'import json;print(json.dumps({"started":True}))')
                identity = adapter._worker_process_id
                assert identity is not None
                await worker.artifact(identity, name=names[index], limit=100, data='c3ludGhldGlj')
                await worker.artifact(identity, name='case-tree', limit=100000,
                    files=[{'path':'nested/λ.txt','text':'current case\n'}])
                container = 'aeep-'+hashlib.sha256(identity.encode()).hexdigest()[:32]
                cgroups = json.loads(await docker(worker, 'exec', '-i', '--user', '65534:65534',
                    container, 'python3', '-I', '-c', SEED, payload={'name': canary}))
                metadata = json.loads(await docker(worker, 'inspect', '--format',
                    '{"running":{{json .State.Running}},"image":{{json .Image}},"mounts":{{json .Mounts}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"network":{{json .HostConfig.NetworkMode}}}', container))
                if (not metadata['running'] or metadata['image'] != worker.image or not metadata['readonly']
                        or metadata['network'] != 'none' or any(item['Type'] in {'bind','volume'} for item in metadata['mounts'])):
                    raise ValueError('running worker differs from the offline boundary')
                quota, period = map(int, cgroups['cpu.max'].split())
                if (quota/period != worker.cpu_count or int(cgroups['memory.max']) != worker.memory_mb*1024*1024
                        or int(cgroups['pids.max']) != worker.process_limit):
                    raise ValueError('actual cgroup limits differ from the binding')
                result['workers'][names[index].split('-')[0]] = dict(worker_digest=worker.digest(),
                    image=worker.image, cgroups=cgroups, private_mounts=True, cleanup_confirmed=False)
            stage = 'paired_observations'
            await command(active[0][1], "import pathlib,json;pathlib.Path('/workspace/case-tree/nested/λ.txt').write_text('control changed');print('{}')")
            for index, (_worker, adapter) in enumerate(active):
                paths = {'own_workspace':'/workspace/'+names[index], 'other_workspace':'/workspace/'+names[1-index],
                         'credential_canary':'/worker/auth/'+canary, 'external_answer':str(answer)}
                observed = await command(adapter, CHECK.replace('PATHS', repr(paths)))
                role = names[index].split('-')[0]
                result['workers'][role]['observed'] = observed
                tree = await command(adapter, "import pathlib,json;print(json.dumps({'text':pathlib.Path('/workspace/case-tree/nested/λ.txt').read_text()}))")
                if tree != {'text':'current case\n' if index else 'control changed'}:
                    raise ValueError('private input tree delivery or independence failed')
                observed['private_input_tree'] = True
                if (observed['own_workspace'] != 'readable' or observed['other_workspace'] != 'absent'
                        or observed['credential_canary'] not in {'denied','absent'}
                        or observed['external_answer'] not in {'denied','absent'}
                        or observed['shared_workbook_roundtrip'] is not True):
                    raise ValueError('private fixture or shared dependency boundary failed')
                if any(bool(observed[key]) != bool(index) for key in
                       ('candidate_skill_sha256','candidate_alias','candidate_runtime')):
                    raise ValueError('candidate availability differs from control/treatment assignment')
            control = result['workers']['control']['observed']
            treatment = result['workers']['treatment']['observed']
            if any(control[key] != treatment[key] for key in ('pandas','openpyxl')):
                raise ValueError('shared library versions differ')
            stage = 'candidate_dependencies'
            dependency = await command(active[-1][1], DEPENDENCY, timeout_ms=30000)
            result['workers']['treatment']['dependency_execution'] = dependency
            if dependency != {'authoring_helper': True, 'artifact_tool_csv': True}:
                raise ValueError('candidate dependency execution failed')
            stage = 'interruption'
            worker, adapter = active[-1]
            pending = asyncio.create_task(command(adapter,
                "import pathlib,time;pathlib.Path('/workspace/interruption-ready').write_text('ready');time.sleep(60)", timeout_ms=60000))
            for _ in range(100):
                await asyncio.sleep(.05)
                try:
                    await worker.artifact(adapter._worker_process_id, name='interruption-ready', limit=100)
                    break
                except Exception:
                    if pending.done():
                        raise RuntimeError('interruption probe ended before its ready marker') from None
            else:
                raise RuntimeError('interruption probe did not become ready')
            if not await worker.cleanup(adapter._worker_process_id):
                raise RuntimeError('worker removal was not confirmed')
            try:
                await asyncio.wait_for(pending, timeout=10)
            except Exception as exc:
                result['interrupted_request_error_type'] = type(exc).__name__
            else:
                raise ValueError('removed worker returned a successful command result')
            result['passed'] = True
    except Exception as exc:
        result.update(failed_stage=stage, error_type=type(exc).__name__)
    finally:
        if pending is not None:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
        for index, (worker, adapter) in enumerate(active):
            cleaned = False
            try:
                await asyncio.wait_for(adapter.transport.close(), timeout=5)
            except Exception:
                pass
            finally:
                try:
                    if adapter._worker_process_id:
                        cleaned = await worker.cleanup(adapter._worker_process_id)
                except Exception as exc:
                    result['passed'] = False
                    result.setdefault('cleanup_errors', []).append(type(exc).__name__)
                finally:
                    if adapter._worker_security:
                        adapter._worker_security.cleanup()
            role = names[index].split('-')[0]
            result['workers'].setdefault(role, {})['cleanup_confirmed'] = cleaned
            result['passed'] &= cleaned
        result['source_unchanged'] = await asyncio.to_thread(verification_source_digest, ROOT) == source
        result['passed'] &= result['source_unchanged']
    result['observation_digest'] = content_digest(result['workers'])
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workers', type=Path, required=True, help='two explicit credential-free executor specs, control then treatment')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists; preserve previous observations')
    result = asyncio.run(probe(args.workers))
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    if not result['passed']:
        raise SystemExit('offline pair probe failed; inspect the sanitized record')


if __name__ == '__main__':
    main()
