"""Stage an offline AMD64 COPY-only carrier and private ordinary-grader cases."""

import base64
import hashlib
import json
import shutil
import stat
from pathlib import Path, PurePosixPath
from zipfile import ZipFile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import patch_artifact
from aeep.assessment.repository_tasks import RepositoryPatch
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WORK = ROOT/'.aeep'/HERE.name
CONTEXT = WORK/'context'
CALIBRATION = ROOT/'.aeep/skillsbench-react-nonroot-calibration-20261108'
REACT = ROOT/'.aeep/skillsbench-react-reference-20261106'
POSITIVE = REACT/'browser-id-continuation/protected'
RIGHTS = ROOT/'.aeep/skillsbench-react-managed-preparation-20261107'
TASK = 'react-performance-debugging'
PARENT_TAG = 'aeep-skillsbench-react:retained-amd64-6f04cf16'


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def read(path):
    return json.loads(path.read_bytes())


def write(path,value):
    with path.open('x') as stream:
        json.dump(value,stream,indent=2);stream.write('\n')


def unpack():
    dependency_root=CONTEXT/'python'
    dependency_root.mkdir()
    rows=read(HERE/'wheel-lock.json')['wheels']
    result=read(HERE/'acquisition-continuation-result.json')
    assert result['passed'] and len(result['new_artifacts'])==5
    assert len(rows)==32
    for row in rows:
        path=Path(row['path']) if row['origin']=='retained' else WORK/'wheelhouse'/row['filename']
        assert not path.is_symlink() and sha(path)==row['sha256'] and path.stat().st_size==row['bytes']
        with ZipFile(path) as archive:
            items=archive.infolist()
            assert len(items)==len({entry.filename for entry in items})<=20_000
            assert sum(entry.file_size for entry in items)<=256*1024**2
            for entry in items:
                name=PurePosixPath(entry.filename)
                assert str(name)==entry.filename.rstrip('/') and not name.is_absolute()
                assert '..' not in name.parts and '\\' not in entry.filename
                assert not entry.filename.endswith('.pth') and '.data' not in name.parts[0]
                assert not stat.S_ISLNK(entry.external_attr>>16)
                if entry.is_dir():
                    continue
                target=dependency_root.joinpath(*name.parts)
                target.parent.mkdir(parents=True,exist_ok=True)
                with archive.open(entry) as source,target.open('xb') as output:
                    shutil.copyfileobj(source,output)
                target.chmod(0o444)


def stage_protected():
    protected=CONTEXT/'protected'
    protected.mkdir()
    pins=read(POSITIVE/'pins.json')
    for name,expected in pins['protected'].items():
        assert Path(name).name==name and sha(POSITIVE/name)==expected
        shutil.copyfile(POSITIVE/name,protected/name)
    driver=CALIBRATION/'nonroot-reference.py'
    reviewed=read(HERE.parent/'skillsbench-react-nonroot-calibration-20261108/operation-review.json')
    assert sha(driver)==reviewed['assets'][str(driver)]
    text=driver.read_text()
    old="""    for name, digest in pins['patches'].items():
        assert name.startswith('src/') and '..' not in Path(name).parts
        path=PROTECTED/'patches'/name
        assert sha(path.read_bytes())==digest
        shutil.copyfile(path,SITE/name)
"""
    new="""    for name, value in changes.items():
        target = SITE / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(value, encoding='utf-8')
"""
    assert text.count(old)==1 and text.count('def run(result):')==1
    text=text.replace(old,new).replace('def run(result):','def run(result, changes):')
    text=text[:text.index("\n\nif __name__")]
    compile(text,str(protected/'verifier-driver.py'),'exec')
    (protected/'verifier-driver.py').write_text(text)
    pack=BenchmarkPack.model_validate(read(RIGHTS/f'{TASK}-bound-pack.json'))
    payload=task_input(pack,ROOT/'.aeep/skillsbench-stack-9a1f4dd5',TASK)
    original=read(HERE.parent/'skillsbench-react-managed-preparation-20261107/operation-review.json')
    assert payload['task_archive_sha256']==original['tasks'][0]['public_archive_sha256']
    pins.pop('patches')
    pins['task_archive_sha256']=payload['task_archive_sha256']
    write(protected/'pins.json',pins)
    return payload


def stage_controls(payload):
    protected=[
        ('reference',POSITIVE,True,None),
        ('incomplete',REACT/'negative-controls/incomplete/protected',False,'upstream_rejected'),
        ('destructive',REACT/'negative-controls/destructive/protected',False,'upstream_rejected'),
    ]
    examples=[]
    for name,location,valid,failure in protected:
        patches=read(location/'pins.json')['patches']
        files={}
        for key,expected in patches.items():
            path=location/'patches'/key
            assert sha(path)==expected
            files[key]=path.read_text()
        patch=RepositoryPatch(base_sha256=payload['task_archive_sha256'],files=files)
        examples.append({'name':name,'artifact':patch_artifact(patch),'valid':valid,'failure_code':failure})
    bad=RepositoryPatch(base_sha256=payload['task_archive_sha256'],files={'package.json':'{}'})
    examples.append({'name':'outside_source','artifact':patch_artifact(bad),'valid':False,'failure_code':'output_contract'})
    write(WORK/'controls.json', {'input':payload,'variants':examples})


def inventory():
    assert not any(path.is_symlink() for path in CONTEXT.rglob('*'))
    return {str(path.relative_to(CONTEXT)):sha(path) for path in sorted(CONTEXT.rglob('*')) if path.is_file()}


def main():
    assert shutil.disk_usage(ROOT).free>=54*1024**3
    CONTEXT.mkdir(mode=0o700)
    browser=read(CALIBRATION/'browser-extraction.json')
    path=Path(browser['browser_path'])
    assert not any(item.is_symlink() for item in path.rglob('*'))
    assert {str(item.relative_to(path)):sha(item) for item in path.rglob('*') if item.is_file()}=={
        name:entry['sha256'] for name,entry in browser['files'].items()}
    shutil.copytree(path,CONTEXT/'browser')
    unpack()
    payload=stage_protected()
    stage_controls(payload)
    shutil.copyfile(HERE/'grade.py',CONTEXT/'protected/grade.py')
    (CONTEXT/'aeep-assessment.pth').write_text('/opt/aeep-assessment-python\n')
    (CONTEXT/'Dockerfile').write_text(f"""FROM {PARENT_TAG}
COPY browser/ /opt/aeep-react-browser/
COPY python/ /opt/aeep-assessment-python/
COPY aeep-assessment.pth /usr/local/lib/python3.12/dist-packages/aeep-assessment.pth
COPY protected/ /opt/aeep-react-reference/
USER 65534:65534
""")
    items=inventory()
    write(WORK/'context-inventory.json',items)
    write(HERE/'carrier-preparation.json', {
        'context_sha256':content_digest(items),'files':len(items),'parent_tag':PARENT_TAG,
        'controls_sha256':sha(WORK/'controls.json'),'original_verifier_assertions':11,
        'protected_reference_patches_in_image':False,'offline_build_unstarted':True,'models':0,
        'scratch_mib':160,'scratch_basis':'111.3 MiB sampled in the approved nonroot reference',
    })


if __name__=='__main__':
    main()
