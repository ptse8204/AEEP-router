"""Prepare the changed wheel review from the integrated build; never install or download."""
import hashlib
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import RuntimeInstallation, Wheel, digest
from aeep_toolkit.installation import PreviewPolicy, preview
from aeep_toolkit.models import ExtensionRegistry

HERE=Path(__file__).parent
ROOT=HERE.parents[3]
OLD=HERE.parent/'package-review-shared-native-20261028'
CAPTURE=ROOT/'reports/toolkit-v2/c13/repository-codec-preflight-20261029'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    assert not (HERE/'operation-review.json').exists()
    checks=json.loads((CAPTURE/'validation/source-stability.json').read_text())
    assert checks['all_passed'] and checks['source_digest']==verification_source_digest(ROOT)
    assert shutil.disk_usage(ROOT).free>51*1024**3
    built=list((CAPTURE/'validation/artifacts').glob('*.whl'))
    assert len(built)==1
    wheel=built[0]
    prior=RuntimeInstallation.model_validate_json((OLD/'installation.json').read_text())
    registry=ExtensionRegistry.model_validate_json((OLD/'registry.json').read_text())
    manifest=next(m for m in registry.extensions if m.extension_id=='aeep-agent-router')
    manifest.source.revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip()
    manifest.source.artifact_sha256=sha(wheel)
    with zipfile.ZipFile(wheel) as archive:
        for member in ('aeep/assessment/repository_tasks.py','aeep/assessment/repository_suites.py','aeep/assessment/adapters.py','aeep/assessment/containment.py','aeep/assessment/container_worker.py','aeep_toolkit/selection.py','aeep_toolkit/cli.py','aeep/router.py','aeep/hosts/registry.py','aeep/hosts/codex_app_server.py','aeep/assessment/service.py'):
            assert hashlib.sha256(archive.read(member)).hexdigest()==sha(ROOT/'src'/member)
        for name in ('repository_suite_program.py','repository_suite_plugins_program.py','swe_rebench_pytest_parser.py','swe-rebench-provenance.json','LICENSE.swe-rebench','repository_suite_native_capture.py','repository_suite_native_program.py'):
            member='aeep_agent_router-0.8.2.data/data/share/aeep/integrations/assessment-runtime/'+name
            assert hashlib.sha256(archive.read(member)).hexdigest()==sha(ROOT/'integrations/assessment-runtime'/name)
        assert 'aeep/hosts/codex_metrics.py' in archive.namelist()
        assert hashlib.sha256(archive.read('aeep/hosts/codex_metrics.py')).hexdigest()==sha(ROOT/'src/aeep/hosts/codex_metrics.py')
        manifest.disk_bytes=sum(m.file_size for m in archive.infolist())+wheel.stat().st_size
    policy=prior.policy.model_copy(deep=True)
    policy.free_disk_bytes=shutil.disk_usage(ROOT).free
    policy.reviewed_dependency_manifests=tuple(digest(m) for m in registry.extensions)
    policy=PreviewPolicy.model_validate(policy.model_dump(mode='json'))
    proposed=preview(registry,('aeep-agent-router',),policy,profile='essentials')
    wheelhouse=Path(tempfile.mkdtemp(prefix='aeep-repository-wheel-review-',dir='/private/tmp')).resolve()
    shutil.copyfile(wheel,wheelhouse/wheel.name)
    wheels=tuple(Wheel.model_validate(w.model_dump(mode='json')|{'filename':wheel.name,'sha256':sha(wheel)})
        if w.extension_id=='aeep-agent-router' else w for w in prior.wheels)
    plan=RuntimeInstallation(preview=proposed,policy=policy,destination=str(wheelhouse/'runtime'),
        wheelhouse=str(wheelhouse),interpreter=prior.interpreter,interpreter_sha256=prior.interpreter_sha256,
        python_version=prior.python_version,system=prior.system,machine=prior.machine,wheels=wheels)
    cache_records=[]
    for item in prior.wheels:
        if item.extension_id=='aeep-agent-router':continue
        cached=Path(prior.wheelhouse)/item.filename
        available=cached.is_file() and not cached.is_symlink() and sha(cached)==item.sha256
        assert available, 'Exact retained dependency wheel is unavailable; do not download during preparation.'
        shutil.copyfile(cached,wheelhouse/item.filename)
        cache_records.append({'filename':item.filename,'sha256':item.sha256,'retained_exact_cache_reused':available})
    (HERE/'dependency-cache.json').write_text(json.dumps(cache_records,indent=2)+'\n')
    for name,value in (('registry.json',registry),('policy.json',policy),('review.json',proposed),('installation.json',plan)):
        (HERE/name).write_text(value.model_dump_json(indent=2)+'\n')
    codec_check=str((HERE/'installed-codec-check.py').relative_to(ROOT))
    inputs={codec_check:sha(HERE/'installed-codec-check.py')}
    review={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT).decode().strip(),'source_digest':verification_source_digest(ROOT),
        'installation_sha256':digest(plan),'driver_sha256':sha(HERE/'run_review.py'),
        'wheel_sha256':sha(wheel),'wheel_bytes':wheel.stat().st_size,
                'inputs':inputs,'codec_check':codec_check,
        'installed_module_hashes':{n:sha(ROOT/'src'/Path(n.replace('.','/')+'.py')) for n in ('aeep.assessment.repository_suites','aeep.assessment.service')},
        'effects':'Install the changed AEEP wheel with exactly32 unchanged cached dependency wheels in one new private runtime. Run three focused offline checks: CLI entry point, installed source identity/router-free import, and first-party codec preflight. Reuse historical unchanged-feature evidence without replaying its20 checks. Network and other host-home access are denied. Remove only the unchanged owned runtime and scratch; retain evidence and inert wheel cache.',
        'limits':{'maximum_download_bytes':0,'maximum_download_seconds_each':60,
                  'maximum_offline_check_seconds_each':60,'minimum_host_reserve_bytes':50*1024**3,
                  'dependency_wheels':32,'first_party_wheels':1,'cash_usd':0},
        'permissions':{'models':False,'workers':False,'new_services':False,'credentials':False,'host_activation':False,
            'download_destinations':[],'network_during_install_and_checks':False,
            'installation':'New private runtime only','cleanup':'Unchanged task runtime and its new scratch only; preserve old work, backups, images and volumes'},
        'change':'Adds early validation that standard managed-worker patch fields match every scheduled repository task encoding. The installed check accepts matching plain/gzip profiles and rejects mixed or mismatched profiles before budget reservation. No task decoder, observer, schema, third-party package, model, image or historical evidence changes. Source and installed behavior checks are engineering evidence only.',
        'execution_started':False}
    (HERE/'operation-review.json').write_text(json.dumps(review,indent=2)+'\n')
    print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'argument_policy_digest':digest(review),
        'wheel_sha256':sha(wheel),'wheels':len(wheels),'execution_started':False}))


if __name__=='__main__':
    main()
