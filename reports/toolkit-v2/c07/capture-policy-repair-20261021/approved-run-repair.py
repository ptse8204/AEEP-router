"""Execute an explicitly approved COPY-only repair, then fresh gated diagnostics once."""
import hashlib
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, ConformanceProbeRequest
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[3]
OLD = OUT.parent / 'capture-repair-20261019'
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (OUT / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def run_script(name, *arguments):
    with (OUT / (name + '.log')).open('x') as stream:
        result = subprocess.run([sys.executable, str(OUT / name), *arguments], cwd=ROOT,
                                stdout=stream, stderr=subprocess.STDOUT, timeout=1500)
    assert result.returncode == 0, name


def main():
    assert len(sys.argv) == 2 and sha(OUT / 'operation-review.json') == sys.argv[1]
    review = json.loads((OUT / 'operation-review.json').read_text())
    approval = json.loads((OUT / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert verification_source_digest(ROOT) == review['source_digest']
    for name, digest in review['inputs'].items():
        assert sha(ROOT / name) == digest, name
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3 + review['maximum_build_growth_bytes']
    assert not (OUT / 'execution-started.json').exists()
    assert json.loads((OLD / 'collector-result.json').read_text())['passed'] is False
    assert not (OLD / 'diagnostics-started.json').exists()
    save('execution-started.json', {'review_sha256': sys.argv[1], 'automatic_retry': False})
    router = Router.from_manifest(BASE / 'aeep.json')
    repo = AssessmentService(router, BASE / '.aeep/assessments').repository
    request = ConformanceProbeRequest.model_validate(json.loads((OLD / 'collector-definitions.json').read_text())['requests'][0])
    operation = request.plan_id + ':copy-only-collector-local-parent-20261021'
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=360), stage='collector_image_repair')
    began = time.monotonic()
    result = {'parent_review_sha256': sys.argv[1], 'images': {}, 'model_turns_in_build': 0,
              'installs': 0, 'pulls': 0, 'run_instructions': 0}
    try:
        for role, item in review['builds'].items():
            context = OUT / ('image-' + role)
            local = json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', '--format', '{"id":{{json .Id}},"onbuild":{{json (index .Config "OnBuild")}}}', item['parent_reference']], text=True, timeout=20))
            assert local['onbuild'] in (None, []), 'Parent ONBUILD instructions are not authorized.'
            assert local['id'] == item['parent'], 'The named local parent is missing or changed; no build may start.'
            assert item['parent_reference'].endswith('@' + item['parent'])
            assert {p.name for p in context.iterdir()} == {'Dockerfile', 'codex_metrics.py'}
            assert (context / 'Dockerfile').read_text() == (
                'FROM ' + item['parent_reference'] + '\nCOPY --chown=0:0 --chmod=0444 codex_metrics.py /opt/aeep/codex_metrics.py\n')
            exists = subprocess.run([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', item['tag']],
                                    capture_output=True, timeout=20)
            assert exists.returncode != 0, 'The new tag already exists; do not replace it.'
        for role, item in review['builds'].items():
            assert shutil.disk_usage(ROOT).free > 51 * 1024**3
            context = OUT / ('image-' + role)
            with (OUT / (role + '-build.log')).open('x') as log:
                built = subprocess.run([*DOCKER, 'build', '--pull=false', '--network=none',
                                        '--provenance=false', '--sbom=false', '--tag', item['tag'],
                                        '--file', str(context / 'Dockerfile'), str(context)],
                                       stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=150)
            assert built.returncode == 0, role + ' build failed; retain output, no retry'
            identity = subprocess.check_output([*DOCKER, 'image', 'inspect', '--format', '{{.Id}}', item['tag']], text=True, timeout=20).strip()
            assert identity.startswith('sha256:') and len(identity) == 71 and identity != item['parent']
            result['images'][role] = dict(item, id=identity)
            save(role + '-built-image.json', result['images'][role])
        result['passed'] = True
    except BaseException as exc:
        result.update(passed=False, error_type=type(exc).__name__, error=str(exc)[:300])
    finally:
        result['wall_seconds'] = time.monotonic() - began
        repo.finish_operation(operation, elapsed_seconds=result['wall_seconds'])
        result['grant_after_build'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        save('build-result.json', result)
        router.store.close()
    assert result['passed'], 'Build did not pass; dependent execution remains blocked.'
    run_script('prepare-collector.py')
    definitions = json.loads((OUT / 'collector-definitions.json').read_text())
    derived = json.loads((OLD / 'collector-operation-review.json').read_text())
    derived.update(source_commit=review['source_commit'], source_digest=review['source_digest'],
                   collector_sha256=review['collector_sha256'], images={role: item['id'] for role, item in result['images'].items()},
                   definitions_sha256=sha(OUT / 'collector-definitions.json'),
                   runner_sha256=sha(OUT / 'run-collector.py'),
                   diagnostics_runner_sha256=sha(OUT / 'run-diagnostics.py'),
                   boundary_assembly_runner_sha256=sha(OUT / 'assemble-collector-boundary.py'),
                   diagnostic_tasks_sha256=sha(OUT / 'diagnostic-tasks.json'),
                   parent_repair_review_sha256=sys.argv[1], build_result_sha256=sha(OUT / 'build-result.json'),
                   approval_record=str(OUT / 'collector-operator-approval.json'))
    assert definitions['source_digest'] == review['source_digest']
    save('collector-operation-review.json', derived)
    digest = sha(OUT / 'collector-operation-review.json')
    save('collector-operator-approval.json', dict(approval, review_sha256=digest,
                                               parent_review_sha256=sys.argv[1],
                                               rule='Parent approval covers precisely these two COPY-only outputs and fresh bounded checks.'))
    run_script('run-collector.py', digest)
    collector = json.loads((OUT / 'collector-result.json').read_text())
    assert collector['passed'] and collector['proxy_restored_stopped'] and collector['source_unchanged']
    run_script('assemble-collector-boundary.py')
    run_script('run-diagnostics.py', digest)
    diagnostic = json.loads((OUT / 'diagnostic-result.json').read_text())
    save('execution-result.json', {'build_passed': True, 'collector_passed': True,
                                 'diagnostics_passed': diagnostic.get('passed'),
                                 'diagnostic_records': len(diagnostic.get('records', {})),
                                 'source_digest': verification_source_digest(ROOT),
                                 'proxy_restored_stopped': diagnostic.get('proxy_restored_stopped'),
                                 'qualification': False, 'admission': False, 'original_study_replayed': False})


if __name__ == '__main__':
    main()
