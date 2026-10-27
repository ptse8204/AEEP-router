"""Build one approved offline dependency image, then finite independent reproduction."""
import asyncio
from email.parser import BytesParser
import os
import zipfile
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

from aeep.assessment.models import (AssessmentEnvironment, AssessmentLimits, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest, RecipeRuntimeBinding)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')
DOCKER = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def inspect(reference):
    return json.loads(subprocess.check_output([*DOCKER, 'image', 'inspect', reference], timeout=20))[0]


def run_script(path, *arguments):
    with (HERE / (path.parent.name + '-' + path.name + '.log')).open('x') as log:
        result = subprocess.run([sys.executable, str(path), *arguments], cwd=ROOT,
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=json.loads((HERE / 'runtime-review.json').read_text())['maximum_reserved_seconds'] + 60)
    assert result.returncode == 0, 'Dependent reviewed script failed; do not retry.'


async def main():
    assert len(sys.argv) == 2 and sha(HERE / 'runtime-review.json') == sys.argv[1]
    bundle = json.loads((HERE / 'runtime-review.json').read_text())
    approval = json.loads((HERE / 'operator-approval.json').read_text())
    assert approval['approved'] and approval['review_sha256'] == sys.argv[1]
    assert verification_source_digest(ROOT) == bundle['source_digest']
    for path, expected in bundle['assets'].items():
        assert not Path(path).is_symlink() and sha(Path(path)) == expected
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3 + bundle['maximum_build_growth_bytes']
    parent = inspect(bundle['parent_reference'])
    assert parent['Id'] == bundle['parent_image'] and parent['Config'].get('OnBuild') in (None, [])
    exists = subprocess.run([*DOCKER, 'image', 'inspect', bundle['target_tag']], capture_output=True, timeout=20)
    assert exists.returncode != 0, 'Target already exists; do not replace it.'
    context = ROOT / bundle['build_context']
    # The sole approved pending wheel is populated after its metered data fetch.
    save(HERE / 'execution-started.json', {'review_sha256': sys.argv[1], 'automatic_retry': False})
    (HERE / 'docker-usage-before.txt').write_bytes(subprocess.check_output([*DOCKER, 'system', 'df'], timeout=20))
    router = Router.from_manifest(BASE / 'aeep.json')
    repo = AssessmentService(router, BASE / '.aeep/assessments').repository
    request = RecipeMaterializationRequest.model_validate(bundle['build_request'])
    build = {'passed': False, 'parent_review_sha256': sys.argv[1], 'parent_image': bundle['parent_image'],
             'target_tag': bundle['target_tag'], 'model_turns': 0, 'download_attempts': 0, 'verified_downloaded_artifacts': 0, 'retained_image': True}
    reserved, began = False, None
    try:
        build['grant_before'] = list(router.store._connection.execute(
            "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
        import importlib.util
        budget_spec = importlib.util.spec_from_file_location('exact_review_budget', HERE / 'review-budget.py')
        budget = importlib.util.module_from_spec(budget_spec); budget_spec.loader.exec_module(budget)
        budget.install(repo, router.store._connection, build['grant_before'], bundle)
        grant = repo.current_grant('onboarding')
        assert build['grant_before'][0] + bundle['maximum_operations'] <= grant.limits.max_operations
        assert build['grant_before'][2] + bundle['maximum_reserved_seconds'] <= grant.limits.max_elapsed_seconds
        models = {'subject': AssessmentSubject, 'recipe': RecipeDefinition, 'environment': AssessmentEnvironment,
            'recipe_runtime': RecipeRuntimeBinding, 'recipe_materialization_request': RecipeMaterializationRequest}
        for digest, item in bundle['build_documents'].items():
            assert repo.put(item['kind'], item['id'], models[item['kind']].model_validate(item['document'])) == digest
        repo.approve_bundle(AssessmentScopeAmendment.model_validate(bundle['build_amendment']),
                            {key: item['document'] for key, item in bundle['build_documents'].items()})
        fetch = bundle['pending_wheel_fetch']
        cache = Path(bundle['fetch_cache']); cache.mkdir(exist_ok=False)
        fetch_records = []; verified = None
        for index in range(bundle['maximum_fetch_attempts']):
            identity = request.plan_id + '-wheel-fetch-' + str(index + 1)
            repo.reserve(request, identity, AssessmentLimits(max_operations=1, max_elapsed_seconds=120), stage='reviewed_native_wheel_fetch')
            fetch_began = time.perf_counter(); target = cache / ('attempt-' + str(index + 1) + '.partial')
            record = {'operation_id':identity, 'attempt':index + 1, 'verified':False, 'partial_retained':str(target)}
            try:
                result = subprocess.run([sys.executable, '-I', '-B', str(HERE/'fetch-reviewed-wheel.py'), str(target)],
                    cwd=ROOT, env={'PATH':os.defpath,'HOME':str(cache)}, stdin=subprocess.DEVNULL,
                    capture_output=True, text=True, timeout=90)
                record['returncode'] = result.returncode
                if result.returncode == 0:
                    facts=json.loads(result.stdout)
                    assert facts['verified'] and facts['bytes']==fetch['size_bytes'] and sha(target)==fetch['sha256']
                    record.update(verified=True,bytes=target.stat().st_size,sha256=sha(target));verified=target
            except (subprocess.TimeoutExpired, ValueError) as exc:
                record['error_type']=type(exc).__name__
            finally:
                repo.finish_operation(identity, elapsed_seconds=time.perf_counter()-fetch_began)
                fetch_records.append(record)
                build['download_attempts'] = len(fetch_records)
                with (HERE/'wheel-fetch-progress.json').open('w') as stream:json.dump(fetch_records,stream,indent=2)
            if verified is not None:break
        build['verified_downloaded_artifacts'] = int(verified is not None)
        assert verified is not None, 'Exact data fetch unavailable; retain attempts and stop without installation'
        licenses=[]
        with zipfile.ZipFile(verified) as archive:
            metadata=next(n for n in archive.namelist() if n.endswith('.dist-info/METADATA'))
            assert archive.getinfo(metadata).file_size<1_000_000
            fields=BytesParser().parsebytes(archive.read(metadata))
            assert fields['Name'].casefold()=='scipy' and fields['Version']==fetch['version']
            requires=[r for r in fields.get_all('Requires-Dist',[]) if 'extra ==' not in r]
            assert requires==[fetch['required_runtime_dependency']]
            for name in archive.namelist():
                if '.dist-info/' not in name or 'license' not in name.casefold() or archive.getinfo(name).is_dir():continue
                assert archive.getinfo(name).file_size<=1_000_000
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
                data=archive.read(name);path=cache/('license-'+str(len(licenses))+'.txt');path.write_bytes(data)
                licenses.append({'wheel_path':name,'retained':str(path),'sha256':sha(path),'bytes':len(data)})
        assert licenses, 'Retain wheel license evidence before any install'
        destination=context/fetch['filename'];assert not destination.exists();shutil.copyfile(verified,destination)
        assert sha(destination)==fetch['sha256']
        save(HERE/'wheel-fetch-result.json',{'verified':True,'artifact':str(destination),'sha256':sha(destination),'bytes':destination.stat().st_size,'licenses':licenses,'attempts':fetch_records,'executed_or_imported':False})
        assert {str(path.relative_to(context)) for path in context.rglob('*') if path.is_file()}==set(bundle['context_files'])
        operation = request.plan_id + '-runtime-build'
        repo.reserve(request, operation, AssessmentLimits(max_operations=1, max_elapsed_seconds=180), stage='repository_runtime_image_build')
        reserved, began = True, time.perf_counter()
        with (HERE / 'image-build.log').open('x') as log:
            done = subprocess.run([*DOCKER, 'build', '--pull=false', '--network=none', '--provenance=false', '--sbom=false',
                '--tag', bundle['target_tag'], '--file', str(context / 'Dockerfile'), str(context)],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT, timeout=120)
        assert done.returncode == 0, 'Build failed; retain logs and stop without retry.'
        current_parent, image = inspect(bundle['parent_reference']), inspect(bundle['target_tag'])
        assert current_parent['Id'] == bundle['parent_image'] and image['Id'] != current_parent['Id']
        assert image['RootFS']['Layers'][:len(parent['RootFS']['Layers'])] == parent['RootFS']['Layers']
        assert len(image['RootFS']['Layers']) == len(parent['RootFS']['Layers']) + 2
        assert image['Config'] == parent['Config'], 'Execution configuration must remain exactly inherited.'
        assert 0 < image['Size'] - parent['Size'] <= bundle['maximum_build_growth_bytes']
        assert shutil.disk_usage(ROOT).free > 50 * 1024**3
        build.update(passed=True, image_id=image['Id'], inherited_config_verified=True, parent_layers_verified=True,
                     image_growth_bytes=image['Size'] - parent['Size'])
    except BaseException as exc:
        build['error_type'] = type(exc).__name__
        raise
    finally:
        try:
            if reserved:
                repo.finish_operation(operation, elapsed_seconds=time.perf_counter() - began)
            save(HERE / 'build-operation-ledger.json', repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            build['grant_after'] = list(router.store._connection.execute(
                "SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
            save(HERE / 'build-result.json', build)
        finally:
            await router.close()
    run_script(HERE / 'derive-execution.py')
    out = HERE / 'runtime-execution'
    canary = ROOT / bundle['host_canary']
    assert not canary.exists()
    marker = b'AEEP reviewed runtime host-only canary; no secret.\n'
    with canary.open('xb') as stream:
        stream.write(marker)
    try:
        run_script(out / 'run.py', sha(out / 'operation-review.json'))
        run_script(out / 'audit-execution.py')
    finally:
        assert canary.is_file() and not canary.is_symlink() and canary.read_bytes() == marker
        canary.unlink()
        save(HERE / 'canary-cleanup.json', {'unchanged_owned_canary_removed': True})
    audit = json.loads((out / 'completion-audit.json').read_text())
    save(HERE / 'execution-result.json', {'batch_completed': audit['batch_completed'], 'build_passed': True,
        'image_id': build['image_id'], 'image_tag': bundle['target_tag'], 'image_retained_for_remaining_work': True,
        'receipt_integrity_passed': audit['physical_receipt_integrity_passed'], 'eligible_cases': audit['eligible_cases'],
        'canonical_operations': 1 + len(fetch_records) + audit['canonical_operations'], 'grant_before': build['grant_before'],
        'grant_after': audit['grant_after'], 'cash_delta': 0, 'model_turns': 0,
        'source_unchanged': verification_source_digest(ROOT) == bundle['source_digest'], 'human_gate': 'OPEN',
        'qualification': False, 'comparative_usefulness': False, 'selection_improvement': False})


if __name__ == '__main__':
    asyncio.run(main())
