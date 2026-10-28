"""Bounded public source sizing and inert triage; no installer or subject runs."""
import ast
import concurrent.futures
import gzip
import hashlib
import io
import json
from pathlib import Path,PurePosixPath
import re
import shutil
import tarfile
import time
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
CACHE=ROOT/'.aeep/repository-multifile-source-review-20261027'
QUEUE=ROOT/'reports/toolkit-v2/c13/repository-worker-input-20261027/next-multifile-metadata-queue.json'
SELECTED=json.loads(QUEUE.read_text())
IDENTITIES={x['id'] for x in SELECTED['candidates']}
REPOSITORIES={x['repository'] for x in SELECTED['candidates']}
BOUND=3_500_000


def sha(data):return hashlib.sha256(data).hexdigest()

def main():
    assert shutil.disk_usage(ROOT).free>50*1024**3+200*1024**2
    CACHE.mkdir(exist_ok=False)
    meta_path=ROOT/'reports/toolkit-v2/c13/repository-cohort-20261022/union-candidate-metadata.json';meta=json.loads(meta_path.read_text())
    inv=json.loads((ROOT/'reports/toolkit-v2/c13/repository-suite-integration-20261022/cohort-inventory.json').read_text());eligible={x['instance_id']:x for x in inv['rows'] if not x['metadata_blockers']}
    selected=[];excluded=[]
    for item in meta['sources']:
        path=ROOT/item['private_cache'];assert sha(path.read_bytes())==item['sha256']
        for record in json.loads(path.read_text())['rows']:
            row=record['row']
            if row['instance_id'] not in IDENTITIES or row['instance_id'] not in eligible:continue
            nodes=row['FAIL_TO_PASS']+row['PASS_TO_PASS'];roots=set();reason=[]
            for node in nodes:
                parts=node.split('::')[0].split('/');index=next((i for i,x in enumerate(parts[:-1]) if x in ('test','tests','testing')),None)
                if index is None:reason.append('unsupported_test_root')
                else:roots.add('/'.join(parts[:index+1]))
                terminal=node.rsplit('::',1)[-1]
                if any(c.isspace() for c in node) or ('[' in terminal and not terminal.endswith(']')):reason.append('incomplete_or_whitespace_identity')
            if not nodes or len(roots)!=1:reason.append('non_single_root_metadata')
            if reason:excluded.append({'id':row['instance_id'],'reasons':sorted(set(reason))});continue
            selected.append(row)
    selected.sort(key=lambda x:x['instance_id']);assert len(selected)<=16
    pool=json.loads((ROOT/'reports/toolkit-v2/c13/repository-worker-input-20261027/provisional-pool.json').read_text())
    existing=json.loads((ROOT/pool['cases_file']).read_text());origins={(c['source_repository'].removeprefix('https://github.com/').casefold(),c['source_revision']) for c in existing}
    assert not {(x['repo'].casefold(),x['base_commit']) for x in selected}&origins
    queue={'dataset_revision':meta['revision_before_and_after'],'metadata_sha256':sha(meta_path.read_bytes()),'selection_basis':'The previously pinned14-row multi-file metadata queue,chosen before these source outcomes. Existing56 pool origins excluded;prior failed/compact-cap exclusions stay recorded for review. No future stage or capability-value claim.', 'metadata_queue_sha256':sha(QUEUE.read_bytes()),'repositories':sorted(REPOSITORIES),'identities':[r['instance_id'] for r in selected],'metadata_exclusions':excluded,'maximum_compressed_read_each':BOUND+1,'maximum_total_read_bytes':len(selected)*(BOUND+1),'source_cap_is_operational_not_scientific':True,'models':0,'subjects_executed':0,'cases_adopted':0}
    (HERE/'source-queue.json').write_text(json.dumps(queue,indent=2)+'\n')
    def collect(row):
        began=time.monotonic();repo,revision,identity=row['repo'],row['base_commit'],row['instance_id']
        assert re.fullmatch(r'[A-Za-z0-9_.-]+__[A-Za-z0-9_.-]+-[0-9]+',identity)
        assert re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repo) and re.fullmatch(r'[a-f0-9]{40}',revision)
        directory=CACHE/identity;directory.mkdir();(directory/'row.json').write_text(json.dumps(row,indent=2)+'\n')
        url='https://codeload.github.com/'+repo+'/tar.gz/'+revision
        result={'instance_id':identity,'repository':repo,'revision':revision,'url':url,'private_cache':str(directory.relative_to(ROOT)),'metadata_family_hint':eligible[identity]['family_hint'],'declared_python':row['install_config']['python'],'code_executed':False,'stage':None,'proposed_audit':False,'requires_actual_multifile_semantic_review':True,'previous_queue_recorded':next(x for x in SELECTED['candidates'] if x['id']==identity)['previous_queue_recorded']}
        try:
            opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open(urllib.request.Request(url,headers={'User-Agent':'AEEP-source-size-review/1'}),timeout=25) as response:
                assert urllib.parse.urlparse(response.geturl()).hostname=='codeload.github.com';data=response.read(BOUND+1)
            (directory/'source.tar.gz').write_bytes(data);result.update(downloaded_bytes=len(data),archive_sha256=sha(data))
            if len(data)>BOUND:
                result.update(status='NEEDS_SOURCE_SCOPE_REVIEW',reason='Partial bytes exceed explicit larger-profile cap;not parsed.');return result
            with gzip.GzipFile(fileobj=io.BytesIO(data)) as compressed:raw=compressed.read(24_000_001)
            if len(raw)>24_000_000:raise ValueError('raw_tar_bound')
            files={};total=0;prefix=None;violations=[]
            with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as archive:
                for member in archive:
                    name=PurePosixPath(member.name);assert name.parts and not name.is_absolute() and '..' not in name.parts
                    prefix=prefix or name.parts[0];assert name.parts[0]==prefix
                    if member.isdir():continue
                    if not member.isfile():violations.append('nonregular_member');continue
                    total+=member.size
                    if total>20_000_000 or len(files)>=5000:violations.append('expanded_or_member_bound');break
                    relative=PurePosixPath(*name.parts[1:]).as_posix();assert relative not in files and len(relative)<=240 and '\\' not in relative and relative.isprintable()
                    if any(p in {'.git','.codex','.agents'} for p in PurePosixPath(relative).parts) or PurePosixPath(relative).name in {'AGENTS.md','auth.json','.env','credentials.json'}:violations.append('protected_instruction_or_secret_path')
                    files[relative]=archive.extractfile(member).read()
            licenses=[];configs=[];imports=set()
            for name,body in files.items():
                if '/' not in name and name.upper().startswith(('LICENSE','COPYING','NOTICE')):
                    (directory/name).write_bytes(body);licenses.append({'file':name,'sha256':sha(body),'bytes':len(body)})
                if name in ('pyproject.toml','setup.cfg','setup.py','requirements.txt','conftest.py','tests/conftest.py'):
                    path=directory/'review-files'/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(body);configs.append({'file':name,'sha256':sha(body),'bytes':len(body)})
                if name.endswith('.py'):
                    try:
                        tree=ast.parse(body);imports.update((n.module or '').split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.ImportFrom) and not n.level);imports.update(a.name.split('.')[0] for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names)
                    except (SyntaxError,ValueError):pass
            result.update(status='EXCLUDED' if violations else 'STATIC_REVIEW_REQUIRED',reason=';'.join(sorted(set(violations))) or 'License,source semantics,runtime closure and actual reproduction still require review.',regular_files=len(files),unpacked_bytes=total,raw_tar_bytes=len(raw),licenses=licenses,config_files=configs,static_import_roots=sorted(imports-{''}),old_compact_source_fit=len(data)<=650_000 and total<=4_000_000 and len(files)<=1000)
        except Exception as exc:result.update(status='UNRESOLVED',error_type=type(exc).__name__,error=str(exc)[:180])
        finally:result['read_and_triage_seconds']=time.monotonic()-began
        return result
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:results=list(executor.map(collect,selected))
    report={**queue,'sources':results,'downloaded_bytes':sum(r.get('downloaded_bytes',0) for r in results),'external_code_executed':False,'installers':0,'tests':0,'source_normalization_or_case_preparation':False}
    (HERE/'source-size-review.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'rows':len(results),'bytes':report['downloaded_bytes'],'statuses':{s:sum(r['status']==s for r in results) for s in sorted({r['status'] for r in results})}}))


if __name__=='__main__':main()
