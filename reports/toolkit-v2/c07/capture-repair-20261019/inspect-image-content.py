"""Read only reviewed public image files, without creating or starting containers."""
import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import time
from pathlib import Path

from aeep.assessment.models import AssessmentLimits, ConformanceProbeRequest
from aeep.assessment.service import AssessmentService
from aeep.router import Router

OUT = Path(__file__).parent
ROOT = OUT.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
FILES = {'opt/aeep/worker-launch', 'opt/aeep/codex_metrics.py', 'opt/aeep/worker-config.json'}


def main():
    review = json.loads((OUT / 'collector-operation-review.json').read_text())
    definitions = json.loads((OUT / 'collector-definitions.json').read_text())
    assert not (OUT / 'image-content-result.json').exists()
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3 + 700 * 1024**2
    audit = {'authority': 'Read-only audit authority and September25/27 finite diagnostic definition delegation.',
             'purpose': 'Explain the terminal collector startup failure without retrying it.',
             'images': review['images'], 'public_paths': sorted(FILES),
             'models': 0, 'containers_created': 0, 'software_executed_in_images': False,
             'maximum_operations': 1, 'maximum_seconds': 120,
             'maximum_archive_bytes': 700 * 1024**2,
             'driver_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (OUT / 'image-content-review.json').write_text(json.dumps(audit, indent=2) + '\n')
    router = Router.from_manifest(BASE / 'aeep.json')
    repo = AssessmentService(router, BASE / '.aeep/assessments').repository
    request = ConformanceProbeRequest.model_validate(definitions['requests'][0])
    operation = request.plan_id + ':public-image-content-audit'
    repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='public_image_content_audit')
    began = time.monotonic()
    result = dict(audit, images={})
    try:
        with tempfile.TemporaryDirectory(prefix='aeep-public-image-audit-') as scratch:
            archive = Path(scratch) / 'images.tar'
            with archive.open('xb') as stream:
                run = subprocess.run(['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock',
                                      'image', 'save', *review['images'].values()], stdout=stream,
                                     stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, timeout=90)
            assert run.returncode == 0
            assert archive.stat().st_size <= audit['maximum_archive_bytes']
            result['archive_bytes'] = archive.stat().st_size
            with tarfile.open(archive) as outer:
                manifests = json.load(outer.extractfile('manifest.json'))
                for manifest in manifests:
                    config = outer.extractfile(manifest['Config']).read()
                    identity = 'sha256:' + hashlib.sha256(config).hexdigest()
                    assert identity in review['images'].values()
                    found = {}
                    for layer in manifest['Layers']:
                        with tarfile.open(fileobj=outer.extractfile(layer), mode='r|*') as contents:
                            for member in contents:
                                name = member.name.removeprefix('./')
                                if name not in FILES:
                                    continue
                                assert member.isfile() and member.size < 65536
                                payload = contents.extractfile(member).read()
                                found[name] = {'sha256': hashlib.sha256(payload).hexdigest(),
                                               'bytes': len(payload), 'mode': oct(member.mode)}
                                target = OUT / 'image-public-files' / identity.removeprefix('sha256:') / name
                                target.parent.mkdir(parents=True, exist_ok=True)
                                target.write_bytes(payload)
                    result['images'][identity] = {'files': found, 'missing_paths': sorted(FILES - found.keys())}
            result['archive_removed_with_owned_scratch'] = True
            result['private_scratch'] = scratch
        result['private_scratch_removed'] = not Path(scratch).exists()
        result['passed'] = len(result['images']) == 2
    except BaseException as exc:
        result.update(passed=False, error_type=type(exc).__name__)
    finally:
        result['wall_seconds'] = time.monotonic() - began
        repo.finish_operation(operation, elapsed_seconds=result['wall_seconds'])
        result['grant_after'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        (OUT / 'image-content-result.json').write_text(json.dumps(result, indent=2) + '\n')
        router.store.close()
        print(json.dumps(result))


if __name__ == '__main__':
    main()
