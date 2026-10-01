#!/usr/bin/env python3
"""Exploratory native-command/AEEP calibration. No model calls or release verdict."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.metadata
import json
import platform
import statistics
import sys
import tempfile
import time
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path

# The subprocess starts without AEEP imports in the native baseline arm.
PROGRAM = 'import csv,io,json,sys; v=json.load(sys.stdin); print(json.dumps({"records":list(csv.DictReader(io.StringIO(v["text"]), delimiter=v["delimiter"]))}))'
INPUT = {'text': 'name\nAda\n', 'delimiter': ','}


async def child(configuration, arm, scenario):
    count = 5 if scenario == 'warm' else 1
    activation = time.perf_counter()
    observations = []
    output = {'scenario': scenario, 'arm': arm, 'task_ms': []}
    if arm == 'aeep':
        from aeep.assessment.onboarding import reference_spec
        from aeep.assessment.repository import AssessmentRepository
        from aeep.economic.prepared import executor_fingerprint
        from aeep.mcp.server import AEEPToolService
        from aeep.models import ExecutorKind, Manifest, TaskScope
        from aeep.router import Router
        from aeep.tasks import activate, change_state, inspect
        spec = reference_spec('csv').model_copy(update={'kind': ExecutorKind.COMMAND,
            'config': configuration['config']})
        root = Path(configuration['config']['native_sandbox']['project_root'])
        manifest_path = root / 'aeep.json'
        manifest_path.write_text(Manifest(database=str(root / '.aeep' / 'state.db'),
            executors=[spec]).model_dump_json())
        output['manifest_bytes'] = manifest_path.stat().st_size
        host_config = root / '.codex' / 'config.toml'
        host_before = host_config.read_bytes() if host_config.exists() else None
        router = Router.from_manifest(manifest_path)
        repo = AssessmentRepository(router.store)
        scope = TaskScope(scope_id='calibration', project_root=str(root),
            executor_fingerprints={spec.id: executor_fingerprint(spec)}, max_attempts=5,
            max_attempt_seconds=10, expires_at=datetime.now(UTC) + timedelta(minutes=5))
        repo.review(repo.put('task_scope', scope.scope_id, scope))
        record = activate(router, scope.scope_id)
        host_applied = host_config.read_bytes() if host_config.exists() else None
        output['project_host_config_bytes_after_activation'] = len(host_applied or b'')
        service = AEEPToolService(router, profile='task', task_activation=record.activation_id)
        output['schema_bytes'] = len(json.dumps(service.list_tools()).encode())
        output['instructions_bytes'] = len(service.instructions.encode())
        output['activation_ms'] = (time.perf_counter() - activation) * 1000
        try:
            if scenario == 'idle':
                await asyncio.sleep(0.25)
            else:
                for _ in range(count):
                    started = time.perf_counter()
                    reply = await service.call('aeep_csv', INPUT)
                    output['task_ms'].append((time.perf_counter() - started) * 1000)
                    result = reply['structuredContent']
                    observations.append(result['ok'])
                    if scenario != 'failure':
                        assert result['output'] == {'records': [{'name': 'Ada'}]}
                    output['sample_summary'] = result['summary']
            lifecycle_started = time.perf_counter()
            change_state(router, record.activation_id, 'pause')
            blocked = await service.call('aeep_csv', INPUT)
            assert blocked['isError']
            change_state(router, record.activation_id, 'resume')
            change_state(router, record.activation_id, 'uninstall')
            state = inspect(router, record.activation_id)
            assert state['overlay'] == 'absent' and state['attempts_used'] == len(observations)
            host_after = host_config.read_bytes() if host_config.exists() else None
            output['project_host_config_bytes_after_uninstall'] = len(host_after or b'')
            output['project_host_config_mutations'] = int(host_before != host_applied) + int(host_applied != host_after)
            output['project_host_entry_after_uninstall'] = state['codex_mcp_entry'] != 'absent'
            output['retained_project_lock_files'] = len(state['retained_artifacts'])
            output['retained_project_lock_bytes'] = await asyncio.to_thread(
                lambda: sum(Path(path).stat().st_size for path in state['retained_artifacts']))
            assert output['project_host_config_mutations'] == 2
            assert output['project_host_entry_after_uninstall'] is False
            assert output['retained_project_lock_files'] == 1
            output['pause_resume_uninstall_ms'] = (time.perf_counter()-lifecycle_started)*1000
            output['pause_rejected_dispatch'] = True
            output['evidence_bytes_before_close'] = sum(path.stat().st_size for path in (root / '.aeep').rglob('*') if path.is_file())
        finally:
            await router.close()
        output['evidence_bytes_after_close'] = sum(path.stat().st_size for path in (root / '.aeep').rglob('*') if path.is_file())
    else:
        output['activation_ms'] = None  # No AEEP activation in the baseline.
        output['schema_bytes'] = output['instructions_bytes'] = 0
        if scenario == 'idle':
            await asyncio.sleep(0.25)
        else:
            for _ in range(count):
                started = time.perf_counter()
                process = await asyncio.create_subprocess_exec(*configuration['native_argv'],
                    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                stdout, _ = await process.communicate(json.dumps(INPUT).encode())
                output['task_ms'].append((time.perf_counter() - started) * 1000)
                observations.append(process.returncode == 0)
                if scenario != 'failure':
                    assert json.loads(stdout) == {'records': [{'name': 'Ada'}]}
    assert all(success == (scenario != 'failure') for success in observations)
    output['verified_tasks'] = sum(observations)
    output['expected_failures'] = sum(not success for success in observations)
    print(json.dumps(output))


async def measure(binary, repetitions):
    import psutil

    from aeep.executors.command import _monitor_process
    from aeep.hosts.codex_sandbox import NativeSandboxConfig
    samples = []
    with binary.open('rb') as stream:
        pin = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    for scenario in ('idle', 'cold', 'warm', 'failure'):
        for repetition in range(repetitions):
            # Alternate paired order; calibration only, no claim of a scored trial.
            for arm in (('native', 'aeep') if repetition % 2 == 0 else ('aeep', 'native')):
                with tempfile.TemporaryDirectory(prefix='aeep-calibration-') as directory:
                    root = await asyncio.to_thread(Path(directory).resolve)
                    boundary = NativeSandboxConfig(binary=str(binary), binary_sha256=pin,
                        project_root=str(root), read_roots=[str(await asyncio.to_thread(Path(sys.prefix).resolve))])
                    argv = [sys.executable, '-I', '-c', 'raise SystemExit(2)' if scenario == 'failure' else PROGRAM]
                    configuration = {'native_argv': boundary.argv(argv), 'config': {
                        'argv': argv, 'argv_literal': True, 'stdin_json': True, 'timeout_seconds': 10,
                        'output': {'type': 'json'}, 'native_sandbox': boundary.model_dump(mode='json')}}
                    started = time.perf_counter()
                    process = await asyncio.create_subprocess_exec(sys.executable, __file__, '--child', arm, scenario,
                        stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                    stop = asyncio.Event()
                    monitor = asyncio.create_task(_monitor_process(process.pid, stop))
                    try:
                        stdout, stderr = await asyncio.wait_for(process.communicate(json.dumps(configuration).encode()), 60)
                    finally:
                        if process.returncode is None:
                            process.kill()
                            await process.wait()
                        stop.set()
                        metrics = await monitor
                    if process.returncode:
                        raise RuntimeError(stderr.decode()[:2000])
                    sample = json.loads(stdout)
                    sample.update(repetition=repetition, process_wall_ms=(time.perf_counter()-started)*1000,
                                  sampled_process_tree=asdict(metrics))
                    samples.append(sample)
    pairs = {}
    for scenario in ('idle', 'cold', 'warm', 'failure'):
        rows = [item for item in samples if item['scenario'] == scenario]
        medians = {arm: statistics.median(item['process_wall_ms'] for item in rows if item['arm'] == arm)
                   for arm in ('native', 'aeep')}
        pairs[scenario] = {'median_process_wall_ms': medians, 'incremental_ms': medians['aeep'] - medians['native']}
    return {
        'schema_version': 'aeep.footprint-calibration.v3', 'recorded_at': datetime.now(UTC).isoformat(),
        'purpose': 'exploratory calibration; no release or benefit verdict',
        'reference': {'os': platform.platform(), 'architecture': platform.machine(),
            'python': platform.python_version(), 'logical_cpus': psutil.cpu_count(),
            'physical_memory_bytes': psutil.virtual_memory().total, 'codex_sha256': pin,
            'dependencies': {name: importlib.metadata.version(name) for name in ('psutil', 'pydantic', 'jsonschema')}},
        'boundary': 'Fresh Python coordinator plus its Codex sandbox and command descendants. Supervisor and existing desktop/host are shared and excluded.',
        'measurement_limits': [
            '10ms process sampling can miss short-lived children and their CPU; CPU is a sampled lower bound.',
            'RSS sums can count shared pages more than once; these are sampled resident sums, not unique whole-machine memory.',
            'Idle is a 250ms local coordinator sample, not complete Codex host idle memory.',
            'Compilation/pinning in the harness is excluded from baseline; AEEP checks at activation/dispatch are included.',
            'AEEP arm includes manifest write, owned overlay and project MCP entry creation, pause/rejected dispatch/resume/uninstall, retained lock and accounting. Native arm needs none of these controls.',
            'Synthetic CSV only. Assessment lab, workbook workload, actual host context and recovery footprint remain unmeasured.',
            'No amortization or speculative savings are subtracted. No acceptance budgets or holdouts are evaluated.'],
        'production': {'samples': samples, 'comparisons': pairs},
        'assessment': None,
        'unknown': ['whole-host startup and peak memory', 'OS cache usage', 'exact context tokens', 'network telemetry',
                    'installation/dependency disk increment', 'human effort', 'long-term retention growth', 'crash/recovery footprint'],
        'operations': {'model_calls': 0, 'reviewer_calls': 0, 'downloads': 0, 'optional_integrations': [],
            'project_host_config_mutations_per_aeep_sample': sorted({item['project_host_config_mutations'] for item in samples if item['arm'] == 'aeep'}),
            'project_host_entry_after_uninstall': any(item['project_host_entry_after_uninstall'] for item in samples if item['arm'] == 'aeep'),
            'retained_project_lock_files_per_aeep_sample': sorted({item['retained_project_lock_files'] for item in samples if item['arm'] == 'aeep'}),
            'owned_overlay_files_per_activation': 1,
            'hooks': 0, 'services': 0, 'ports': 0, 'retries': 0,
            'network_policy': 'disabled for command children; coordinator network activity not instrumented',
            'cleanup': 'disposable synthetic stores removed after normal close; not production evidence cleanup'},
    }


if __name__ == '__main__':
    if sys.argv[1:2] == ['--child']:
        asyncio.run(child(json.load(sys.stdin), *sys.argv[2:]))
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--codex', type=Path, required=True)
        parser.add_argument('--output', type=Path, required=True)
        parser.add_argument('--repetitions', type=int, choices=range(1, 11), default=3)
        args = parser.parse_args()
        report = asyncio.run(measure(args.codex.resolve(), args.repetitions))
        args.output.write_text(json.dumps(report, indent=2) + '\n')
        print(args.output)
