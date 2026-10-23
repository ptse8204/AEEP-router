"""Read bounded pinned public source archives as data only; no installer/test/import."""
import concurrent.futures
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import tarfile
import urllib.request

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).parent
CACHE=ROOT/'.aeep/repository-workload-expansion-20261022-audit-source'
MAX_BYTES=650_000


def main():
    assert shutil.disk_usage(ROOT).free>50*1024**3+10*1024**2
    CACHE.mkdir(exist_ok=False)
    metadata=json.loads((ROOT/'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json').read_text())
    inventory=json.loads((ROOT/'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json').read_text())
    eligible={row['instance_id']:row for row in inventory['rows'] if not row['metadata_blockers']}
    rows=[]
    for entry in metadata['sources']:
        path=ROOT/entry['private_cache'];assert hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']
        rows.extend(item['row'] for item in json.loads(path.read_text())['rows'])
    repositories=['iluvcapra/pycmx']
    selected=[]
    for repository in repositories:
        options=[row for row in rows if row['repo'].casefold()==repository.casefold() and row['instance_id'] in eligible and all(name.startswith('tests/') for name in row['FAIL_TO_PASS']+row['PASS_TO_PASS'])]
        assert options
        # This is a static curation queue, not stage assignment or an outcome-driven sample.
        options.sort(key=lambda row:(row['install_config']['python'] not in ('3.13','3.13.1'),
            eligible[row['instance_id']]['family_hint']!='multi-file-repair',row['instance_id']))
        selected.append(options[0])
    (CACHE/'queue.json').write_text(json.dumps(selected,indent=2)+'\n')
    def collect(row):
        repository,revision=row['repo'],row['base_commit']
        assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository) and re.fullmatch(r'[a-f0-9]{40}',revision)
        directory=CACHE/row['instance_id'];directory.mkdir()
        (directory/'row.json').write_text(json.dumps(row,indent=2)+'\n')
        url='https://codeload.github.com/'+repository+'/tar.gz/'+revision
        record={'instance_id':row['instance_id'],'repo':repository,'base_commit':revision,'url':url,
            'family_hint':eligible[row['instance_id']]['family_hint'],'declared_python':row['install_config']['python'],
            'private_cache':str(directory.relative_to(ROOT)),'adopted':False,'code_executed':False,'stage':None}
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(url,headers={'User-Agent':'AEEP-source-review/2'}),timeout=30) as response:
                assert urllib.parse.urlparse(response.geturl()).hostname=='codeload.github.com'
                data=response.read(MAX_BYTES+1)
            record.update(downloaded_bytes=len(data),archive_sha256=hashlib.sha256(data).hexdigest())
            path=directory/'source.tar.gz';path.write_bytes(data)
            if len(data)>MAX_BYTES:
                record.update(status='EXCLUDED',reason='Compressed archive exceeds current650000-byte reviewed transport bound; partial bytes retained, never parsed or executed.')
                return record
            files={};total=0;prefix=None;violations=[]
            with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as archive:
                for member in archive:
                    name=PurePosixPath(member.name)
                    assert not name.is_absolute() and '..' not in name.parts
                    prefix=prefix or name.parts[0];assert name.parts[0]==prefix
                    if member.isdir():continue
                    if not member.isfile():
                        violations.append('non_regular_member');continue
                    assert member.size>=0
                    total+=member.size
                    if total>4_000_000 or len(files)>=1000:
                        violations.append('unpacked_archive_bound');break
                    relative=PurePosixPath(*name.parts[1:]).as_posix()
                    if relative in files:violations.append('duplicate_path');continue
                    if set(PurePosixPath(relative).parts)&{'.git','.codex','.agents','AGENTS.md','auth.json'}:
                        violations.append('protected_or_embedded_agent_path')
                    files[relative]=archive.extractfile(member).read()
            licenses=[]
            for name,content in files.items():
                if len(PurePosixPath(name).parts)==1 and name.upper().startswith(('LICENSE','COPYING','NOTICE')):
                    (directory/name).write_bytes(content)
                    licenses.append({'file':name,'bytes':len(content),'sha256':hashlib.sha256(content).hexdigest()})
            configs=[]
            for name in ('pyproject.toml','setup.cfg','setup.py','requirements.txt','requirements-dev.txt','conftest.py','tests/conftest.py'):
                if name in files:
                    target=directory/'review-files'/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(files[name])
                    configs.append({'file':name,'sha256':hashlib.sha256(files[name]).hexdigest(),'bytes':len(files[name])})
            record.update(status='STATIC_REVIEW_REQUIRED' if not violations else 'EXCLUDED',
                reason='Source is inert. License text, dependencies, runtime compatibility and baseline/reference reproduction are not yet approved or verified.' if not violations else ';'.join(sorted(set(violations))),
                regular_files=len(files),unpacked_bytes=total,licenses=licenses,config_files=configs)
        except Exception as exc:
            record.update(status='UNRESOLVED',error_type=type(exc).__name__)
        return record
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(collect,selected))
    result={'source_dataset_revision':metadata['revision_before_and_after'],'purpose':'Additional pinned multi-file source review as inert data; no adopted cases or stage freeze.',
        'maximum_bytes_each':MAX_BYTES+1,'maximum_total_bytes':len(selected)*(MAX_BYTES+1),
        'external_code_executed':False,'tests_run':0,'installers_run':0,'models':0,'cases_adopted':0,'holdouts_frozen':0,'sources':results}
    (HERE/'audit-source-review.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'sources':len(results),'statuses':{name:sum(item.get('status')==name for item in results) for name in ('STATIC_REVIEW_REQUIRED','EXCLUDED','UNRESOLVED')},'downloaded_bytes':sum(item.get('downloaded_bytes',0) for item in results),'executed_external_code':False}))


if __name__=='__main__':main()
