"""Acquire and inspect exact release archives as data; execute no archived file."""
import argparse,hashlib,json,shutil,stat,tarfile,urllib.parse,urllib.request,zipfile
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')
def safe(name):
    p=PurePosixPath(name)
    assert name and not p.is_absolute() and '..' not in p.parts and '\\' not in name and '\x00' not in name
    return p
def allowed(url):
    p=urllib.parse.urlsplit(url)
    assert p.scheme=='https' and p.hostname in {'github.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}
    assert p.port in (None,443) and p.username is None and p.password is None
class Redirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,url):
        allowed(url);count=getattr(req,'reviewed_redirects',0)+1;assert count<=4
        out=super().redirect_request(req,fp,code,msg,headers,url);out.reviewed_redirects=count;return out
def acquire(plan):
    work=Path(plan['work']);work.mkdir(mode=0o700,parents=True,exist_ok=True)
    result={'passed':False,'assets':[],'compiler_executed':False,'upstream_programs_executed':False,'models':0,'comparisons':'PAUSED','licenses_cleared':False}
    total=unpacked=count=0
    try:
        opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),Redirect())
        for row in plan['assets']:
            allowed(row['url']);archive=work/row['name'];size=0
            req=urllib.request.Request(row['url'],headers={'User-Agent':'AEEP-retained-native-artifact-review'})
            with opener.open(req,timeout=90) as response,archive.open('xb') as out:
                allowed(response.url);assert response.status==200
                while block:=response.read(1024**2):
                    assert shutil.disk_usage(ROOT).free>=plan['minimum_free_bytes']
                    size+=len(block);total+=len(block)
                    assert size<=row['size'] and total<=plan['maximum_download_bytes']
                    out.write(block)
            assert size==row['size'] and sha(archive)==row['sha256'];archive.chmod(0o444)
            destination=work/row['component'];destination.mkdir(mode=0o700)
            entries=[];seen=set()
            archive_handle=zipfile.ZipFile(archive) if row['kind']=='zip' else tarfile.open(archive,'r:gz')
            with archive_handle as handle:
                items=handle.infolist() if row['kind']=='zip' else handle.getmembers()
                for item in items:
                    name=item.filename if row['kind']=='zip' else item.name
                    rel=safe(name);assert name not in seen;seen.add(name)
                    count+=1;assert count<=plan['maximum_file_count']
                    isdir=item.is_dir() if row['kind']=='zip' else item.isdir()
                    mode=item.external_attr>>16 if row['kind']=='zip' else item.mode
                    if isdir:continue
                    regular=stat.S_IFMT(mode) in (0,stat.S_IFREG) if row['kind']=='zip' else item.isfile()
                    # Links are retained as metadata only. They cannot redirect extraction.
                    if not regular:
                        entries.append({'path':name,'extracted':False,'type':'nonregular','target':getattr(item,'linkname',None)})
                        continue
                    target=destination.joinpath(*rel.parts);assert target.resolve().is_relative_to(destination.resolve())
                    target.parent.mkdir(parents=True,exist_ok=True)
                    stream=handle.open(item) if row['kind']=='zip' else handle.extractfile(item)
                    digest=hashlib.sha256();actual=0;header=b''
                    with stream,target.open('xb') as out:
                        while block:=stream.read(1024**2):
                            if not header:header=block[:8]
                            actual+=len(block);unpacked+=len(block)
                            assert unpacked<=plan['maximum_uncompressed_bytes'] and shutil.disk_usage(ROOT).free>=plan['minimum_free_bytes']
                            digest.update(block);out.write(block)
                    expected=item.file_size if row['kind']=='zip' else item.size;assert actual==expected
                    executable=bool(mode&0o111);target.chmod(0o555 if executable else 0o444)
                    entries.append({'path':name,'sha256':digest.hexdigest(),'bytes':actual,'extracted':True,'executable':executable,'first8_hex':header.hex()})
            result['assets'].append({'component':row['component'],'archive_sha256':row['sha256'],'body_bytes':size,'files':entries})
        result['passed']=True
    except BaseException as error:result['error_type']=type(error).__name__
    result.update(download_body_bytes=total,uncompressed_hashed_bytes=unpacked,archive_files=count,free_bytes_after=shutil.disk_usage(ROOT).free)
    write(HERE/'acquisition-result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='assets'}),flush=True)
    return result
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--review-sha256',required=True);args=parser.parse_args()
    review=load(HERE/'operation-review.json');assert sha(HERE/'operation-review.json')==args.review_sha256
    for p,h in review['assets'].items():assert sha(p)==h,p
    assert load(HERE.parent/'pipeline-standing-authority-20261104.json')['first_attempts'] and not (HERE/'acquisition-result.json').exists()
    if not acquire(load(HERE/'plan.json'))['passed']:raise SystemExit(1)
