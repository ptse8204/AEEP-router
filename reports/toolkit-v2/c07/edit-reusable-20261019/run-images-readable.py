"""Build only the two approved COPY derivatives and inspect their public files."""
import asyncio
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, AssessmentPlan, content_digest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

ROOT = Path(__file__).resolve().parents[4]
OUT = Path(__file__).parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
CHECK = '''import hashlib,json,pathlib,stat
result={}
for name in ('tool.py','USAGE.txt'):
 p=pathlib.Path('/opt/dependencies/reusable')/name
 s=p.lstat()
 assert stat.S_ISREG(s.st_mode) and s.st_uid==0 and s.st_nlink==1
 assert stat.S_IMODE(s.st_mode)==0o444
 result[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
p=pathlib.Path('/opt/dependencies/reusable');s=p.lstat()
assert stat.S_ISDIR(s.st_mode) and s.st_uid==0 and not s.st_mode & 0o022
print(json.dumps(result))
'''


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def docker(*args, timeout=30):
    return subprocess.check_output(DOCKER + list(args), text=True, timeout=timeout,
                                   stderr=subprocess.DEVNULL).strip()


def image(identity):
    # Image metadata only, never container environment or protected volumes.
    return json.loads(docker('image', 'inspect', identity))[0]


def absent(identity):
    result = subprocess.run(DOCKER + ['image', 'inspect', identity],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=20)
    return result.returncode != 0


async def main():
    assert len(sys.argv) == 2 and sha(OUT / 'copy-permission-correction-review.json') == sys.argv[1]
    review = json.loads((OUT / 'copy-permission-correction-review.json').read_text())
    approval = json.loads((OUT / 'copy-permission-correction-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert sha(Path(__file__))==review['runner_sha256']
    assert verification_source_digest(ROOT) == review['source_digest']
    assert sha(OUT / 'generated-source.py.txt') == review['source_sha256']
    scope = review['image_scope']
    context = OUT / 'image-context-readable'
    assert {p.name: sha(p) for p in context.iterdir()} == scope['context_hashes']
    assert not (OUT / 'images-readable-started.json').exists()
    assert not (OUT / 'images-readable-result.json').exists()
    before_free = shutil.disk_usage(ROOT).free
    assert before_free >= 52 * 1024**3
    usage_before = docker('system', 'df')
    bases = {role: image(identity) for role, identity in scope['base_images'].items()}
    for role in bases:
        assert bases[role]['Id'] == scope['base_images'][role]
        assert bases[role]['Config']['User'] == '65534:65534'
        assert absent(scope['output_tags'][role])
        if not absent(scope['base_tags'][role]):
            assert image(scope['base_tags'][role])['Id']==scope['base_images'][role]
    router = Router.from_manifest(BASE / 'aeep.json')
    service = AssessmentService(router, BASE / '.aeep/assessments')
    repo = service.repository
    result = {'review_sha256': sys.argv[1], 'runner_sha256': sha(Path(__file__)),
              'source_digest': review['source_digest'], 'images': {},
              'files': scope['worker_files'], 'free_before_bytes': before_free,
              'docker_usage_before': usage_before, 'generated_source_executed': False,
              'model_turns': 0, 'replay_allowed': False}
    owned = []
    try:
        plan = AssessmentPlan.model_validate(repo.get('plan', review['plan_id']))
        proposed = json.loads((OUT / 'training-review.json').read_text())
        assert content_digest(plan) == content_digest(proposed['plan'])
        repo.authorize(plan)
        with (OUT / 'images-readable-started.json').open('x') as marker:
            json.dump(result, marker)
        for role, base in bases.items():
            assert shutil.disk_usage(ROOT).free >= 52 * 1024**3
            operation = plan.plan_id + ':copy_image:' + role
            repo.reserve(plan, operation, AssessmentLimits(max_operations=1,
                         max_elapsed_seconds=600), stage='reusable_image_build')
            started = time.monotonic()
            try:
                repo.authorize(plan)
                if absent(scope['base_tags'][role]):docker('tag', base['Id'], scope['base_tags'][role])
                command = DOCKER + ['build', '--pull=false', '--network=none',
                                   '--file', str(context / ('Dockerfile.' + role)),
                                   '--tag', scope['output_tags'][role], str(context)]
                with (OUT / ('image-readable-' + role + '-build.log')).open('x') as log:
                    subprocess.run(command, stdout=log, stderr=subprocess.STDOUT,
                                   timeout=300, check=True)
                built = image(scope['output_tags'][role])
                assert built['RootFS']['Layers'][:-2] == base['RootFS']['Layers']
                assert len(built['RootFS']['Layers']) == len(base['RootFS']['Layers']) + 2
                assert built['Config'] == base['Config']
                assert built['Os'] == base['Os'] and built['Architecture'] == base['Architecture']
                name = 'aeep-edit-generated-readable-check-' + role + '-3360c74f'
                assert not docker('ps', '-aq', '--filter', 'name=^/' + name + '$')
                owned.append(name)
                files = json.loads(docker(
                    'run', '--name', name, '--network=none', '--read-only',
                    '--cap-drop=ALL', '--security-opt=no-new-privileges',
                    '--pids-limit=32', '--memory=128m', '--cpus=1',
                    '--user=65534:65534', '--entrypoint=python3', built['Id'], '-c', CHECK,
                    timeout=40))
                assert files == scope['worker_files']
                docker('rm', name)
                owned.remove(name)
                result['images'][role] = built['Id']
                result.setdefault('checks', {})[role] = {
                    'base_image': base['Id'], 'base_layers_preserved': True,
                    'copy_and_directory_permission_layers_only': True, 'image_config_unchanged': True,
                    'public_file_hashes_and_modes_passed': True,
                    'created_tag': scope['output_tags'][role],
                    'created_base_alias': scope['base_tags'][role],
                }
            finally:
                repo.finish_operation(operation, elapsed_seconds=time.monotonic() - started)
        result['passed'] = True
    except BaseException as exc:
        result.update(passed=False, error_type=type(exc).__name__)
    finally:
        for name in owned:
            # Exact names checked absent before creation; no older object is touched.
            try:
                docker('stop', '--time', '1', name, timeout=10)
                docker('rm', name)
            except Exception as exc:
                result.setdefault('cleanup_errors', {})[name] = type(exc).__name__
        result['source_unchanged'] = verification_source_digest(ROOT) == review['source_digest']
        result['free_after_bytes'] = shutil.disk_usage(ROOT).free
        result['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        await router.close()
        (OUT / 'images-readable-result.json').write_text(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result))


asyncio.run(main())
