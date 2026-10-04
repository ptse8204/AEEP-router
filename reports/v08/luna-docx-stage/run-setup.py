"""Run one bounded, offline build of the matched SkillsBench DOCX images."""
import hashlib
import json
import shutil
import sys
import subprocess
import time
import urllib.parse
import urllib.request
from pathlib import Path
from aeep.router import Router
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.models import AssessmentLimits, AssessmentScopeAmendment, ConformanceProbeRequest, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CONTEXT = OUT / 'image-context'
SOURCE = '060fbefd55ff1c73256520a0c1e3d0de0e029755b75437cf7a93d7b68335e293'
MIN_FREE = 53687091200
MAX_GROWTH = 3000000000
TOTAL_SECONDS = 600
PER_ARM_SECONDS = 180

def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def docker_df() -> str:
    return subprocess.run(['docker', 'system', 'df'], check=True, capture_output=True, text=True, timeout=15).stdout.strip()

def important_capacity() -> int:
    values = dict((line.split('=', 1) for line in subprocess.check_output([sys.executable, str(OUT / 'storage_probe.py')], text=True, timeout=10).splitlines()))
    return int(values['NSURLVolumeAvailableCapacityForImportantUsageKey_bytes'])

def check_disk(initial_free: int) -> int:
    free = shutil.disk_usage(ROOT).free
    if important_capacity() < MIN_FREE + MAX_GROWTH:
        raise RuntimeError('macOS available capacity below reserve plus setup allowance')
    if initial_free - free > MAX_GROWTH:
        raise RuntimeError('host disk growth exceeded the 3 GB cap')
    return free

def image_exists(tag: str) -> bool:
    result = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True, text=True, timeout=10)
    if result.returncode == 0:
        return True
    if 'no such image' in result.stderr.lower() or 'not found' in result.stderr.lower():
        return False
    raise RuntimeError(f'could not verify image tag: {tag}')

def verify_stage(hashes: dict[str, str]) -> None:
    files = {'prepare-setup.py': OUT / 'prepare-setup.py', 'run-setup.py': OUT / 'run-setup.py', 'image-build-plan.json': OUT / 'image-build-plan.json', 'Dockerfile.docx': CONTEXT / 'Dockerfile.docx', 'requirements-docx.lock': CONTEXT / 'requirements-docx.lock', 'docx/SKILL.md': CONTEXT / 'docx' / 'SKILL.md', 'LICENSE': OUT / 'LICENSE', 'NOTICE': OUT / 'NOTICE', 'provenance.json': OUT / 'provenance.json', 'storage_probe.py': OUT / 'storage_probe.py'}
    if set(hashes) != set(files):
        raise ValueError('setup review has an unexpected staged-file inventory')
    for name, path in files.items():
        if sha256(path) != hashes[name]:
            raise RuntimeError(f'staged setup input changed: {name}')

def main() -> None:
    review_path = OUT / 'setup-review.json'
    result_path = OUT / 'setup-result.json'
    if result_path.exists():
        raise RuntimeError('setup result already exists; blind retry denied')
    if not (len(sys.argv) == 2 and sha256(review_path) == sys.argv[1]):
        raise RuntimeError('exact review hash required')
    review = json.loads(review_path.read_text())
    if verification_source_digest(ROOT) != SOURCE or review['source_digest'] != SOURCE:
        raise RuntimeError('source changed; refresh review against the final source')
    verify_stage(review['stage_hashes'])
    request = ConformanceProbeRequest.model_validate(review['request'])
    if content_digest(request) != review['request_digest']:
        raise RuntimeError('reviewed request digest mismatch')
    if request.authorization_id != 'onboarding' or request.composed_model_turns != 0:
        raise ValueError('setup requires the reviewed onboarding zero-turn request')
    plan = json.loads((OUT / 'image-build-plan.json').read_text())
    bounds = review['resource_and_grant_bounds']
    if bounds != plan['resource_and_grant_bounds']:
        raise RuntimeError('setup bounds changed after review')
    base = subprocess.run(['docker', 'image', 'inspect', '--format', '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}}}', plan['common_base']['tag']], check=True, capture_output=True, text=True, timeout=15)
    base_info = json.loads(base.stdout)
    if base_info.get('Id') != review['base_image']['image_id'] or plan['common_base']['repo_digest'] not in base_info.get('RepoDigests', []):
        raise RuntimeError('pinned plain control base image changed')
    for tag in review['output_tags'].values():
        if image_exists(tag):
            raise RuntimeError(f'preserving existing output tag: {tag}')
    wheel_dir = CONTEXT / 'wheels'
    if [p.name for p in wheel_dir.iterdir() if p.name != '.keep']:
        raise RuntimeError('wheel directory contains prior or unreviewed files')
    with (OUT / 'setup-started.json').open('x') as started:
        json.dump({'review_sha256': sys.argv[1], 'request_digest': content_digest(request)}, started)
    initial_free = check_disk(shutil.disk_usage(ROOT).free)
    initial_important = important_capacity()
    docker_before = docker_df()
    router = Router.from_manifest(ROOT / '.aeep/live-review-v3/aeep.json')
    repository = AssessmentRepository(router.store)
    operation = request.plan_id + ':skillsbench_docx_image_setup'
    reserved = False
    began = time.monotonic()
    result = {'source_digest': SOURCE, 'request_digest': review['request_digest'], 'operation_id': operation, 'authorization_id': 'onboarding', 'model_turns': 0, 'cash_usd': 0, 'download_bytes': 0, 'images': {}, 'worker_or_model_started': False, 'cleanup_performed': False, 'retry_allowed': False, 'resource_measurements': {'wall_seconds': None, 'cpu_ms': None, 'memory_bytes': None}, 'host_free_bytes_before': initial_free, 'important_capacity_before': initial_important, 'docker_system_df_before': docker_before}
    stage = 'reserve'
    try:
        repository.approve_bundle(AssessmentScopeAmendment.model_validate(review['amendment']), review['definitions'])
        repository.authorize(request)
        verify_dependencies(request.executable_dependencies)
        repository.reserve(request, operation, AssessmentLimits(max_operations=1, max_model_turns=0, max_elapsed_seconds=TOTAL_SECONDS, max_cash_usd=0), stage='skillsbench_docx_image_setup')
        reserved = True

        def check() -> None:
            repository.authorize(request)
            if verification_source_digest(ROOT) != SOURCE:
                raise RuntimeError('source changed during setup')
            if time.monotonic() - began > TOTAL_SECONDS:
                raise TimeoutError('600 second total setup cap')
            check_disk(initial_free)
        stage = 'download'
        for package in plan['packages']:
            destination = wheel_dir / package['filename']
            if destination.exists():
                raise RuntimeError('preserving existing wheel file; no retry')
            url = urllib.parse.urlparse(package['url'])
            if url.scheme != 'https' or url.hostname != 'files.pythonhosted.org':
                raise ValueError('wheel URL is outside the pinned PyPI file host')
            digest = hashlib.sha256()
            downloaded = 0
            with urllib.request.urlopen(package['url'], timeout=30) as response, destination.open('xb') as target:
                final_host = urllib.parse.urlparse(response.geturl()).hostname
                if final_host != 'files.pythonhosted.org':
                    raise RuntimeError('wheel download redirected outside PyPI file host')
                while (chunk := response.read(256 * 1024)):
                    downloaded += len(chunk)
                    if downloaded > package['size']:
                        raise RuntimeError('wheel exceeded its pinned size')
                    target.write(chunk)
                    digest.update(chunk)
                    check()
            if downloaded != package['size'] or digest.hexdigest() != package['sha256']:
                raise RuntimeError('wheel size or SHA-256 mismatch; preserve partial file')
            result['download_bytes'] += downloaded
        if result['download_bytes'] != 5049844:
            raise RuntimeError('download total differs from reviewed exact byte count')
        for role in ('control', 'treatment'):
            check()
            stage = 'build_' + role
            tag = review['output_tags'][role]
            log_path = OUT / (role + '-build.log')
            iid_path = OUT / (role + '-image-id')
            if log_path.exists() or iid_path.exists() or image_exists(tag):
                raise RuntimeError('build output already exists; preserve and stop')
            remaining = TOTAL_SECONDS - (time.monotonic() - began)
            timeout = min(PER_ARM_SECONDS, max(1, int(remaining)))
            command = ['docker', 'build', '--network=none', '--pull=false', '--platform', 'linux/arm64', '--progress=plain', '--file', str((CONTEXT / 'Dockerfile.docx').resolve()), '--target', role, '--tag', tag, '--iidfile', str(iid_path.resolve()), str(CONTEXT.resolve())]
            with log_path.open('xb') as log:
                completed = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            if completed.returncode != 0:
                raise RuntimeError(f'offline {role} build failed; logs retained')
            image = subprocess.run(['docker', 'image', 'inspect', '--format', '{"Id":{{json .Id}},"RepoDigests":{{json .RepoDigests}}}', tag], check=True, capture_output=True, text=True, timeout=15)
            image_info = json.loads(image.stdout)
            result['images'][role] = {'tag': tag, 'image_id': image_info['Id'], 'repo_digests': image_info.get('RepoDigests', [])}
            check()
        result['setup_complete'] = True
    except BaseException as exc:
        result.update(setup_complete=False, failed_stage=stage, error_type=type(exc).__name__, error_summary=str(exc)[:200])
    finally:
        elapsed = time.monotonic() - began
        if reserved:
            repository.finish_operation(operation, elapsed_seconds=elapsed)
        result['resource_measurements']['wall_seconds'] = elapsed
        result['host_free_bytes_after'] = shutil.disk_usage(ROOT).free
        result['important_capacity_after'] = important_capacity()
        row = router.store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?', ('onboarding',)).fetchone()
        result['grant_after'] = dict(zip(('operations', 'model_turns', 'elapsed_seconds', 'cash_usd'), row))
        try:
            result['docker_system_df_after'] = docker_df()
        except Exception as exc:
            result['docker_system_df_after'] = None
            result['docker_after_error_type'] = type(exc).__name__
        result['source_unchanged'] = verification_source_digest(ROOT) == SOURCE
        result['result_hashes'] = review['stage_hashes']
        with result_path.open('x', encoding='utf-8') as stream:
            json.dump(result, stream, indent=2)
            stream.write('\n')
        print(json.dumps(result))
        router.store.close()
if __name__ == '__main__':
    main()
