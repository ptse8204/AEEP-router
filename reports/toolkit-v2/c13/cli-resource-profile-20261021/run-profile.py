"""Measure the current local CLI and shared host; no model or acceptance verdict."""
import asyncio
import hashlib
import importlib.metadata
import json
import os
import platform
import resource
import shutil
import sys
import tempfile
import time
from dataclasses import asdict
from pathlib import Path

import psutil

from aeep.assessment.models import AssessmentLimits, AssessmentPlan
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.executors.command import _monitor_process
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def host():
    vm = psutil.virtual_memory()
    net = psutil.net_io_counters()
    return {'monotonic': time.monotonic(), 'cpu_percent': psutil.cpu_percent(interval=None),
            'memory_available_bytes': vm.available, 'memory_used_bytes': vm.used,
            'network_sent_bytes': net.bytes_sent, 'network_received_bytes': net.bytes_recv,
            'disk_free_bytes': shutil.disk_usage(ROOT).free}


async def main():
    review = json.loads((OUT / 'operation-review.json').read_text())
    assert sha(Path(__file__)) == review['runner_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    assert not (OUT / 'execution-started.json').exists()
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    evidence = ROOT / review['evidence_fixture']
    assert sha(evidence) == review['evidence_sha256']
    router = Router.from_manifest(BASE / 'aeep.json')
    repo = AssessmentService(router, BASE / '.aeep/assessments').repository
    prior = json.loads((ROOT / 'reports/toolkit-v2/c07/capture-explicit-profile-20261021/positive-check-result.json').read_text())
    plan = AssessmentPlan.model_validate(repo.get('plan', prior['plans'][0]['plan_id']))
    operation = plan.plan_id + ':local-cli-resource-characterization-20261021'
    repo.reserve(plan, operation, AssessmentLimits(max_operations=26, max_elapsed_seconds=300), stage='cli_resource_characterization')
    began = time.monotonic()
    home = Path(tempfile.mkdtemp(prefix='aeep-cli-resource-', dir='/private/tmp')).resolve()
    save('execution-started.json', {'operation': operation, 'scratch': str(home), 'models': 0, 'automatic_retry': False})
    result = {'source_digest': review['source_digest'], 'samples': [], 'host_samples': [],
              'model_calls': 0, 'candidate_execution': False, 'resource_acceptance': False,
              'scope': 'Darwin arm64 source-checkout CLI, existing Framework Python dependencies. Not installed-wheel or model/worker performance.',
              'environment': {'python': sys.version, 'executable': sys.executable, 'platform': platform.platform(),
                              'logical_cpus': psutil.cpu_count(), 'memory_total_bytes': psutil.virtual_memory().total,
                              'versions': {name: importlib.metadata.version(name) for name in ('psutil', 'pydantic', 'jsonschema')}}}
    immutable = {}
    expected = set()
    try:
        shutil.copyfile(evidence, home / 'evidence.json')
        (home / 'operation.json').write_text(json.dumps({'operation': operation, 'owner': 'AEEP Toolkit V2 resource characterization'}) + '\n')
        profile = home / 'profile.sb'
        profile.write_text('(version 1)\n(allow default)\n(deny network*)\n(deny file-write*)\n'
            + '(allow file-write* (subpath ' + json.dumps(str(home)) + '))\n(allow file-write* (literal "/dev/null"))\n'
            + '(deny file-read* (subpath ' + json.dumps(str(Path.home().resolve())) + '))\n'
            + '(allow file-read* (subpath ' + json.dumps(str(ROOT / 'src')) + '))\n')
        for index, size in enumerate(review['skill_payload_sizes']):
            directory = home / ('candidate-' + str(index)); directory.mkdir()
            prefix = '---\nname: footprint-' + str(index) + '\ndescription: Synthetic inert metadata, never executed.\n---\n'
            (directory / 'SKILL.md').write_text(prefix + 'x' * size)
        immutable = {str(p.relative_to(home)): sha(p) for p in home.rglob('*') if p.is_file()}
        expected = set(immutable)
        psutil.cpu_percent(interval=None)
        for _ in range(50):
            result['host_samples'].append({'phase': 'before', **host()}); await asyncio.sleep(.1)
        program = 'import sys;sys.path.insert(0,' + repr(str(ROOT / 'src')) + ');from aeep_toolkit.cli import main;raise SystemExit(main(sys.argv[1:]))'
        environment = {'PATH': '/usr/bin:/bin', 'HOME': str(home), 'TMPDIR': str(home),
                       'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1', 'LC_ALL': 'C'}
        for index, size in enumerate(review['skill_payload_sizes']):
            commands = [('candidate', ['candidate', str(home / ('candidate-' + str(index)))]),
                        ('list', ['list', 'essentials']),
                        ('report', ['report', '--evidence', str(home / 'evidence.json'), '--format', 'json'])]
            for label, arguments in commands:
                assert shutil.disk_usage(ROOT).free > 50 * 1024**3
                stdout = home / f'{index}-{label}.stdout'; stderr = home / f'{index}-{label}.stderr'
                expected.update((stdout.name, stderr.name))
                started = time.monotonic()
                with stdout.open('xb') as output, stderr.open('xb') as errors:
                    process = await asyncio.create_subprocess_exec('/usr/bin/sandbox-exec', '-f', str(profile),
                        sys.executable, '-I', '-B', '-c', program, *arguments, cwd=home, env=environment,
                        stdin=asyncio.subprocess.DEVNULL, stdout=output, stderr=errors)
                    stop = asyncio.Event(); monitor = asyncio.create_task(_monitor_process(process.pid, stop))
                    try:
                        while process.returncode is None:
                            result['host_samples'].append({'phase': 'cli', 'case': index, 'command': label, **host()})
                            await asyncio.wait_for(asyncio.shield(process.wait()), timeout=10)
                    finally:
                        if process.returncode is None:
                            process.kill(); await process.wait()
                        stop.set(); metrics = await monitor
                result['samples'].append({'case': index, 'payload_padding_bytes': size, 'command': label,
                    'returncode': process.returncode, 'wall_seconds': time.monotonic()-started,
                    'sampled_process_tree': asdict(metrics), 'stdout_bytes': stdout.stat().st_size,
                    'stdout_sha256': sha(stdout), 'stderr_bytes': stderr.stat().st_size,
                    'kernel_cumulative_children_ru_maxrss_native': resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss})
                save('partial-result.json', result)
                assert process.returncode == 0, 'CLI failed; preserve logs/scratch, no retry.'
                value = json.loads(stdout.read_text())
                if label == 'candidate': assert value['executed'] is False
                if label == 'report': assert value['outcome'] == 'NOT_ASSESSED'
        for _ in range(50):
            result['host_samples'].append({'phase': 'after', **host()}); await asyncio.sleep(.1)
        result['commands_completed'] = len(result['samples']); assert result['commands_completed'] == 24
        result['characterization_complete'] = True
    except BaseException as exc:
        result.update(characterization_complete=False, error_type=type(exc).__name__, error_message=str(exc)[:300])
    finally:
        result['wall_seconds'] = time.monotonic()-began
        actual = {str(p.relative_to(home)) for p in home.rglob('*') if p.is_file()}
        unchanged = bool(immutable) and actual == expected and not any(p.is_symlink() for p in home.rglob('*')) and all(sha(home/name)==pin for name,pin in immutable.items())
        if unchanged and result.get('characterization_complete'):
            shutil.rmtree(home); result['scratch_removed'] = not home.exists()
        else: result.update(scratch_removed=False, scratch_preserved=str(home))
        result['source_unchanged'] = verification_source_digest(ROOT)==review['source_digest']
        result['limits'] = ['Observed process samples can miss short children and peaks; CPU is a sampled lower bound.',
            'Shared-host CPU/memory/network include this coordinator and unrelated user work; differences are not attributable CLI costs.',
            'Only the child CLI has network denied. Host network byte deltas are not CLI traffic or model usage.',
            'Kernel ru_maxrss is retained in native platform units and cumulative across these children; it is not a per-case memory figure.',
            'Synthetic inert metadata and report fixtures; no evaluation worker, candidate code, model or service is exercised.',
            'No predeclared production workload/acceptance budget or held-out resource trial; this cannot close the production resource gate.',
            'Energy, whole Codex workload and long-term evidence growth remain unknown. No money, token or time savings claim.']
        repo.finish_operation(operation, elapsed_seconds=result['wall_seconds'])
        result['grant_after'] = list(router.store._connection.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        save('result.json', result); await router.close()
        print(json.dumps({k:result.get(k) for k in ('characterization_complete','commands_completed','scratch_removed','error_type','error_message','grant_after')}))


if __name__ == '__main__':
    asyncio.run(main())
