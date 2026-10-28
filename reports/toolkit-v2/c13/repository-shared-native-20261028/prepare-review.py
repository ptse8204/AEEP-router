"""Pin one upstream Git component, one new local image and the frozen task/control scope."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

from aeep.assessment.models import RecipeMaterializationRequest
from aeep.assessment.verification import verification_source_digest
from git_component import DOCKERFILE, NEEDED, OBJDUMP, SHA256, SIZE, URL

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    template = json.loads((HERE / 'template-operation-review.json').read_text())
    assert template['source_digest'] == verification_source_digest(ROOT)
    request = RecipeMaterializationRequest.model_validate(template['request'])
    parent = json.loads((ROOT / template['parent_review']).read_text())
    inventory = json.loads((HERE / 'image-package-inventory.json').read_text())
    assert inventory['git_absent'] and inventory['unchanged_owned_export_removed']
    assert inventory['oci_manifest_config_and_all_layer_digests_verified']
    image = json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', template['parent_image']], timeout=20))[0]
    assert image['Id'] == inventory['image_id'] == template['parent_image']
    assert image['RootFS']['Layers'] == inventory['layers'] and image['Architecture'] == 'arm64'
    assert image['Config'].get('OnBuild') in (None, []) and image['Config']['User'] == '65534:65534'
    reference = 'aeep-toolkit-v2/repository-grader:py313-multifile-20261027'
    assert json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', reference], timeout=20))[0]['Id'] == image['Id']
    tag = 'aeep-toolkit-v2/repository-grader:py313-shared-native-git-20261028'
    assert subprocess.run([*DOCKER, 'image', 'inspect', tag], capture_output=True, timeout=20).returncode != 0
    packages = inventory['packages']
    assert all(n in packages for n in ('libc6', 'libpcre2-8-0', 'zlib1g', 'libc-bin'))
    metadata = json.loads((HERE / 'upstream-metadata.json').read_text())
    assert (metadata['binary_package_url'], metadata['binary_package_bytes'], metadata['binary_package_sha256']) == (URL, SIZE, SHA256)
    assert sha(OBJDUMP) == metadata['objdump_sha256']
    assert sha(HERE / 'upstream-copyright.txt') == metadata['copyright_sha256']
    for name in ('component-check.json', 'template-preparation-checks.json'):
        assert json.loads((HERE / name).read_text())['passed']
    stable = HERE.parent / 'repository-stable-workspace-20261028'
    actual = json.loads((stable / 'completion-audit.json').read_text())
    assert actual['physical_receipt_integrity_passed'] and actual['canonical_receipts_reopened'] == 17
    assert actual['eligible_cases'] and actual['all_owned_containers_absent']
    for name in ('observer-operator.py', 'observer-default.py'):
        assert (HERE / name).read_bytes() == (stable / name).read_bytes()
    assert len(template['active_case_ids']) == 1 and 'asottile__dead-204' in template['active_case_ids'][0]
    inspection = HERE / 'parent-image-inspection.json'
    if inspection.exists():
        saved = json.loads(inspection.read_text())
        assert all(saved[k] == image[k] for k in ('Id', 'RootFS', 'Config', 'Architecture', 'Os'))
    else:
        save(inspection, image)
    assets = dict(template['assets'])
    for path in [*HERE.glob('*.py'), *HERE.glob('*.txt'), HERE / 'upstream-metadata.json',
                 HERE / 'component-check.json', HERE / 'parent-image-inspection.json',
                 HERE / 'template-operation-review.json', HERE / 'template-preparation-checks.json',
                 stable / 'completion-audit.json', stable / 'provisional-pool.json']:
        assets[str(path.resolve())] = sha(path)
        if path.suffix == '.py':
            ast.parse(path.read_text())
    for path in (HERE / 'runtime-execution').glob('*.py'):
        ast.parse(path.read_text())
        assets[str(path.resolve())] = sha(path)
    assert all(Path(p).is_file() and not Path(p).is_symlink() and sha(Path(p)) == h for p, h in assets.items())
    context = ROOT / '.aeep/repository-shared-native-runtime-20261028/context'
    component_cache = ROOT / '.aeep/repository-shared-native-git-component-20261028'
    assert not context.exists() and not component_cache.exists()
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + 128 * 1024**2
    documents = {**parent['documents'], **template['new_documents']}
    review = {'purpose': 'Provide the real upstream Git local-command component needed by Dead204, then validate all38required obligations. No model comparison or general Git deployment.',
        'source_digest': template['source_digest'], 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'authorization_digest': template['authorization_digest'], 'assets': assets,
        'template_review_sha256': sha(HERE / 'template-operation-review.json'),
        'parent_reference': reference, 'parent_image': image['Id'], 'target_tag': tag,
        'build_context': str(context.relative_to(ROOT)), 'component_cache': str(component_cache.relative_to(ROOT)),
        'dockerfile_sha256': hashlib.sha256(DOCKERFILE.encode()).hexdigest(), 'dockerfile': DOCKERFILE,
        'upstream_metadata': metadata, 'required_ELF_NEEDED_set': sorted(NEEDED),
        'inherited_library_packages': {n: packages[n] for n in ('libc6', 'libpcre2-8-0', 'zlib1g', 'libc-bin')},
        'build_request': request.model_dump(mode='json'), 'build_documents': documents,
        'build_amendment': template['amendment'], 'host_canary': template['host_canary'],
        'maximum_builds': 1, 'maximum_build_growth_bytes': 16 * 1024**2,
        'maximum_new_filesystem_layers': 3, 'maximum_download_attempts': 2,
        'maximum_download_bytes_per_attempt': SIZE, 'initial_contained_calls': 19,
        'maximum_contained_calls': 21, 'maximum_operations': 26,
        'maximum_reserved_seconds': 1335, 'maximum_model_turns': 0, 'cash_usd': 0,
        'automatic_retry': False, 'bounded_control_repairs': template['bounded_control_repairs'],
        'permissions': ['Download only the pinned8665568-byte Debian Git archive from the exactdeb.debian.org URL,at most two network attempts. Size/hash mismatch stops before extraction/build. No credentials or task-data disclosure.',
            'Read package data with trusted system ar/tar and pinned Apple LLVM objdump;never execute Linux Git on the Mac,Debian maintainer scripts,setup.py or a resolver. Require the exact three-library NEEDED set and retained publisher copyright before building.',
            'Select only unmodified usr/bin/git,git-core templates and publisher copyright. One private COPY-only local image build,networknone,pullfalse,from the checked retained tag/image. No other packages,helpers,Perl/Curl stack,OS/host/project installation,source build or environment changes. This is a local-command component,not a complete Debian Git package installation.',
            'Before calls,bind output image digest,all selected file hashes and exact recipe/environment through the frozen derivation. Require unchanged inherited configuration,exact parent layers and three COPY layers,at most16MiB growth. Keep the new image and all old images.',
            'Both stable profiles each run four fresh boundary/state/transport probes and two native-event fixtures. One real Git version/linker/init/add/ls-files/Identify-origin probe,one collection,reference/original pair and raw reference follow. All38obligations remain;all original source/assertion/reference/fault bytes and expansion rule remain.',
            'At most21offline calls/26existing-grant operations/1335reservedseconds cumulative,including one300-second download/preparation/build operation,two possible150-second setup/analysis phases and21times35seconds. Initial maximum19calls/22operations/1115seconds. Existing counters/failed attempts remain.',
            'Remove only new owned containers and unchanged canary. Keep the component cache,prepared context,new image,all old images and evidence. Keep50GiB host free. No blanket pruning or retained-resource deletion.'],
        'no_authority_for': ['Models,cash,credentials,external services/new model destinations,activation,publication/release,old-image/volume/backup deletion,uncertain replay,allowance refunds or budget resets.',
            'No source/assertion/required-test/scope/observer changes after collection or body outcomes;no metadata fabrication,no fake Git,no unsupported-case admission. Isort and Sopel remain excluded for actual runtime metadata/dependency blockers.',
            'No automatic second build,expanded library closure,changed component selection or extra downloads. A new shared library or changed software needs its own review;first-party report controls cannot expand software authority.'],
        'failure_policy': 'Initial execution once. Static closure/copyright/build/configuration mismatch stops runtime. Known completed and cleaned-up case failures stay excluded. Common authority,identity,accounting or cleanup uncertainty stops all dispatch. Two optional immutable-payload report controls require an exact recorded first-party amendment within cumulative ceilings;no automatic retries.',
        'evidence_reuse': 'New shared source passes its own13gates. Its raw program is byte-equal to the source-M1 profile,which is partial applicability evidence only. Fresh new-source/image checks and frozen171-test controls remain required. Old package3791d8f7 does not qualify the corrected wheel.',
        'approval_reason': 'The user continuation reserves untrusted installation/execution and CONTINUATION.md requires applicable provisioning/large-download authority. Terminalae6a0f9f covered no download,build or new Git bytes. Routine finite definitions/budget amendments are delegated;no architecture or budget decision.'}
    save(HERE / 'runtime-review.json', review)
    save(HERE / 'preparation-audit.json', {'passed': True, 'assets_bound': len(assets),
        'runtime_review_sha256': sha(HERE / 'runtime-review.json'),
        'actual_image_inventory_verified_without_container': True,
        'source13_and_installed20_checks_reused': True,
        'component_fixture_checks': len(json.loads((HERE / 'component-check.json').read_text())['checks']),
        'required_test_obligations': 38, 'actual_package_download_build_or_execution': False})
    print(json.dumps({'prepared': True, 'review_sha256': sha(HERE / 'runtime-review.json'),
        'assets_bound': len(assets), 'actual_execution': False}))


if __name__ == '__main__':
    main()
