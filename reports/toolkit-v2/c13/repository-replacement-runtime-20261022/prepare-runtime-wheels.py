"""Read official wheel metadata as data; never install or import downloaded code."""
from concurrent.futures import ThreadPoolExecutor
from email.parser import BytesParser
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request
import zipfile

from packaging.requirements import Requirement
from packaging.tags import compatible_tags, cpython_tags
from packaging.utils import canonicalize_name, parse_wheel_filename
from packaging.version import Version

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CACHE = ROOT / '.aeep/repository-replacement-runtime-20261022-wheels'
PINS = {'pytest':'8.3.5','iniconfig':'2.1.0','packaging':'25.0','pluggy':'1.6.0',
    'pytest-mock':'3.15.0','PyGithub':'2.8.1','semver':'3.0.4','requests':'2.32.5',
    'urllib3':'2.5.0','certifi':'2025.10.5','idna':'3.11','charset-normalizer':'3.4.4',
    'PyJWT':'2.10.1','PyNaCl':'1.6.0','cffi':'2.0.0','pycparser':'2.23',
    'typing-extensions':'4.15.0','cryptography':'46.0.3','PyYAML':'6.0.2',
    'numpy':'2.2.6','aioshutil':'1.5','pyparsing':'3.2.3','orjson':'3.11.3','tqdm':'4.67.1','psutil':'7.1.0'}
ENV = {'implementation_name':'cpython','implementation_version':'3.13.15',
    'os_name':'posix','platform_machine':'aarch64','platform_python_implementation':'CPython',
    'platform_release':'','platform_system':'Linux','platform_version':'',
    'python_full_version':'3.13.15','python_version':'3.13','sys_platform':'linux'}
PLATFORMS = [f'manylinux_2_{minor}_aarch64' for minor in range(41,16,-1)] + ['manylinux2014_aarch64']
TAGS = list(cpython_tags((3,13),abis=['cp313'],platforms=PLATFORMS))
TAGS += list(compatible_tags((3,13),interpreter='cp313',platforms=PLATFORMS))
RANK = {value:index for index,value in enumerate(TAGS)}


def sha(data): return hashlib.sha256(data).hexdigest()


def read(url, ceiling):
    assert url.startswith(('https://pypi.org/','https://files.pythonhosted.org/'))
    with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'AEEP-read-only-source-review/2'}),timeout=45) as stream:
        assert stream.geturl().startswith(('https://pypi.org/','https://files.pythonhosted.org/'))
        data=stream.read(ceiling+1)
    assert len(data)<=ceiling
    return data


def prepare(item):
    project,version=item
    metadata_url=f'https://pypi.org/pypi/{project}/{version}/json'
    raw=read(metadata_url,4*1024**2); metadata=json.loads(raw)
    choices=[]
    for entry in metadata['urls']:
        if entry['packagetype']!='bdist_wheel' or entry['yanked']: continue
        _,wheel_version,_,tags=parse_wheel_filename(entry['filename'])
        assert wheel_version==Version(version)
        overlap=set(tags)&RANK.keys()
        if overlap:
            # Prefer portable wheels, avoiding an unnecessary native extension.
            choices.append((0 if any(tag.platform=='any' for tag in tags) else 1,
                            min(RANK[tag] for tag in overlap),entry,tags))
    assert choices,project
    _,_,entry,tags=min(choices,key=lambda value:value[:2])
    assert entry['size']<25*1024**2
    path=CACHE/entry['filename']
    wheel=path.read_bytes() if path.exists() else read(entry['url'],25*1024**2)
    assert len(wheel)==entry['size'] and sha(wheel)==entry['digests']['sha256']
    if not path.exists(): path.write_bytes(wheel)
    (CACHE/(canonicalize_name(project)+'.pypi.json')).write_bytes(raw)
    with zipfile.ZipFile(path) as archive:
        names=archive.namelist()
        message=BytesParser().parsebytes(archive.read(next(name for name in names if name.endswith('.dist-info/METADATA'))))
        assert canonicalize_name(message['Name'])==canonicalize_name(project) and Version(message['Version'])==Version(version)
        licenses=[]
        for name in names:
            if archive.getinfo(name).is_dir(): continue
            if ('.dist-info/' in name or name.lower().startswith(canonicalize_name(project)+'/')) and ('license' in name.lower() or 'licence' in name.lower() or 'copying' in name.lower() or name.lower().endswith('/notice')):
                data=archive.read(name);assert len(data)<1024**2
                assert not Path(name).is_absolute() and '..' not in Path(name).parts
                destination=HERE/'licenses'/canonicalize_name(project)/name
                destination.parent.mkdir(parents=True,exist_ok=True)
                if destination.exists(): assert destination.read_bytes()==data
                else: destination.write_bytes(data)
                licenses.append({'wheel_path':name,'retained':str(destination.relative_to(ROOT)),'sha256':sha(data)})
        assert licenses,project
        return {'project':project,'version':version,'filename':entry['filename'],'sha256':sha(wheel),
            'size_bytes':len(wheel),'private_cache':str(path.relative_to(ROOT)),
            'source_url':entry['url'],'metadata_url':metadata_url,'metadata_sha256':sha(raw),
            'wheel_tags':sorted(map(str,tags)),'requires_python':message.get('Requires-Python'),
            'requires_dist':message.get_all('Requires-Dist',[]),'license_expression':message.get('License-Expression'),
            'license_metadata':message.get('License'),'licenses':licenses,
            'uploaded_utc':entry['upload_time_iso_8601'],'target':'CPython3.13.15 Linux aarch64 Debian trixie; static wheel tags only'}


def main():
    assert shutil.disk_usage(ROOT).free>50*1024**3+100*1024**2
    CACHE.mkdir(exist_ok=True)
    with ThreadPoolExecutor(max_workers=6) as pool: records=list(pool.map(prepare,PINS.items()))
    by_name={canonicalize_name(row['project']):row for row in records}
    extras={name:set() for name in by_name}
    changed=True
    while changed:
        changed=False
        for name,row in by_name.items():
            if row['requires_python']: assert Version(ENV['python_full_version']) in Requirement('python'+row['requires_python']).specifier
            for text in row['requires_dist']:
                requirement=Requirement(text)
                if requirement.marker and not any(requirement.marker.evaluate({**ENV,'extra':extra}) for extra in {'',*extras[name]}): continue
                target=canonicalize_name(requirement.name)
                assert target in by_name,(name,text)
                assert Version(by_name[target]['version']) in requirement.specifier,(name,text)
                before=len(extras[target]);extras[target].update(requirement.extras)
                changed |= before!=len(extras[target])
    result={'pins':records,'target_marker_environment':ENV,'extras':{key:sorted(value) for key,value in extras.items()},
        'complete_static_dependency_closure':True,'wheels':len(records),'total_bytes':sum(row['size_bytes'] for row in records),
        'installed':False,'downloaded_code_imported':False,'runtime_compatibility':'UNVERIFIED; exact offline image build and probes require separate approval',
        'deviation':'Repository requirements pin pytest8.4.2/PyYAML6.0.2. AEEP retains pytest8.3.5/parser contract and PyYAML6.0.2; lint/type/coverage tools excluded from task execution. No claim of official benchmark-runtime equivalence.',
        'redistribution':'Local private unmodified wheels with retained license texts; no image/package publication authorized. PyGithub LGPL applies independently of task source Apache2.'}
    (HERE/'runtime-wheel-review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ('wheels','total_bytes','complete_static_dependency_closure','installed')}))


if __name__=='__main__': main()
