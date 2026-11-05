"""Pinned public source/module data only; never run their programs or installers."""
from __future__ import annotations
import argparse,base64,concurrent.futures,hashlib,io,json,os,re,shutil,stat,tarfile,threading,time,urllib.error,urllib.parse,urllib.request,zipfile
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,indent=2)+'\n')

def safe(path):
    p=PurePosixPath(path)
    if not path or p.is_absolute() or any(c in path for c in '\\\x00\r\n') or '..' in p.parts:
        raise ValueError('UnsafeArchivePath')
    return p

def h1(entries):
    digest=hashlib.sha256()
    for name,value in sorted(entries.items()):
        safe(name);digest.update((hashlib.sha256(value).hexdigest()+'  '+name+'\n').encode())
    return 'h1:'+base64.b64encode(digest.digest()).decode()

class Budget:
    def __init__(self,work,download_limit,unpacked_limit):
        self.work=work;self.download_limit=download_limit;self.unpacked_limit=unpacked_limit
        self.download=0;self.unpacked=0;self.lock=threading.Lock();self.stop=threading.Event()
    def check(self,amount=0,*,unpacked=False):
        with self.lock:
            if self.stop.is_set():raise RuntimeError('SharedStop')
            if shutil.disk_usage(ROOT).free<50*1024**3:self.stop.set();raise RuntimeError('HostReserveCrossed')
            if unpacked:self.unpacked+=amount
            else:self.download+=amount
            if self.download>self.download_limit or self.unpacked>self.unpacked_limit:
                self.stop.set();raise RuntimeError('ArtifactByteCeiling')

ALLOWED={'codeload.github.com','proxy.golang.org','storage.googleapis.com'}
class Redirect(urllib.request.HTTPRedirectHandler):
    max_redirections=5
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        u=urllib.parse.urlsplit(newurl)
        if u.scheme!='https' or u.hostname not in ALLOWED or u.port not in (None,443) or u.username or u.password:
            raise ValueError('UnreviewedRedirect')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

def fetch(asset,destination,budget):
    budget.check()
    u=urllib.parse.urlsplit(asset['url']);assert u.scheme=='https' and u.hostname in ALLOWED and u.port in (None,443) and not u.query and not u.username and not u.password
    destination.parent.mkdir(parents=True,exist_ok=True)
    # An interrupted or failed asset is retained, not silently overwritten/retried.
    partial=destination.with_name(destination.name+'.partial');count=0
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),Redirect())
    with partial.open('xb') as out:
        with opener.open(urllib.request.Request(asset['url'],headers={'User-Agent':'AEEP-pinned-artifact-inspection'}),timeout=20) as response:
            assert response.status==200
            while block:=response.read(1024**2):
                count+=len(block);budget.check(len(block))
                if count>asset['maximum_bytes']:raise ValueError('SingleArtifactByteCeiling')
                out.write(block)
    os.chmod(partial,0o600);partial.rename(destination)
    return count

def verify_source(archive,tree,work,budget):
    expected={x['path']:x for x in tree['tree'] if x['type']=='blob'}
    assert len(expected)==2877
    assert len({p.casefold() for p in expected})==len(expected)
    root=work/'source';root.mkdir();observed={};links=[]
    with tarfile.open(archive,'r:gz') as tar:
        for member in tar:
            parts=safe(member.name).parts
            assert parts[0]=='toolhive-33ba170aad633e20520f380500a45cd158f24aed'
            if member.isdir():continue
            relative='/'.join(parts[1:]);safe(relative)
            assert relative in expected and relative not in observed,relative
            record=expected[relative]
            if member.issym():
                assert record['mode']=='120000';body=member.linkname.encode();safe(member.linkname)
                target=(root/relative).parent/member.linkname
                assert target.resolve().is_relative_to(root.resolve())
                links.append((relative,member.linkname))
            else:
                assert member.isfile() and record['mode'] in ('100644','100755')
                assert member.size==record['size'] and member.size<=64*1024**2
                body=tar.extractfile(member).read(member.size+1);assert len(body)==member.size
            budget.check(len(body),unpacked=True)
            blob=hashlib.sha1(b'blob '+str(len(body)).encode()+b'\0'+body).hexdigest()
            assert blob==record['sha'],relative
            observed[relative]=hashlib.sha256(body).hexdigest()
            if not member.issym():
                target=root/relative;target.parent.mkdir(parents=True,exist_ok=True)
                with target.open('xb') as f:f.write(body)
                target.chmod(0o444)
    assert set(observed)==set(expected)
    for relative,target in links:(root/relative).symlink_to(target)
    # AGENTS.md/CLAUDE.md are upstream data, never coordinator instructions.
    return {'git_blobs_verified':len(observed),'source_file_sha256':observed,'source_symlinks':links,'archive_sha256':sha(archive),'upstream_instructions_applied':False}

def verify_zip(path,asset,budget,licenses):
    summary=hashlib.sha256();notices=[]
    prefix=asset['module']+'@'+asset['version']+'/'
    with zipfile.ZipFile(path) as archive:
        entries=archive.infolist();assert len(entries)<=100000 and len({e.filename for e in entries})==len(entries)
        assert sum(e.file_size for e in entries)<=256*1024**2
        for item in sorted(entries,key=lambda x:x.filename):
            safe(item.filename);assert item.filename.startswith(prefix)
            assert stat.S_IFMT(item.external_attr>>16) in (0,stat.S_IFREG,stat.S_IFDIR)
            relative=item.filename[len(prefix):];safe(relative)
            digest=hashlib.sha256();body=bytearray()
            notice=len(PurePosixPath(relative).parts)==1 and re.match(r'(?i)^(license|licence|copying|notice)(\.|$)',PurePosixPath(relative).name)
            with archive.open(item) as stream:
                while block:=stream.read(1024**2):
                    budget.check(len(block),unpacked=True);digest.update(block)
                    if notice and len(body)<1024**2:body.extend(block[:1024**2-len(body)])
            summary.update((digest.hexdigest()+'  '+item.filename+'\n').encode())
            if notice:notices.append({'path':relative,'sha256':digest.hexdigest(),'bytes':item.file_size,'text':bytes(body).decode('utf-8',errors='replace'),'complete_text':item.file_size<=1024**2})
    actual='h1:'+base64.b64encode(summary.digest()).decode();assert actual==asset['go_h1'],asset['module']
    identity=hashlib.sha256((asset['module']+'@'+asset['version']).encode()).hexdigest()
    write(licenses/(identity+'.json'),{'module':asset['module'],'version':asset['version'],'notices':notices,'clearance':'NOT_INFERRED'})
    # Same exact checksum that the offline Go cache must consume.
    path.with_name(path.name+'hash').write_text(actual)
    return {'go_h1_verified':actual,'root_notices':len(notices),'license_record':identity+'.json','license_clearance':'NOT_INFERRED'}

def execute(plan):
    work=Path(plan['work']);work.mkdir(mode=0o700,parents=True,exist_ok=True)
    licenses=work/'licenses';licenses.mkdir(mode=0o700)
    budget=Budget(work,plan['maximum_download_bytes'],plan['maximum_uncompressed_bytes'])
    result={'passed':False,'models':0,'compiler_executed':False,'upstream_programs_executed':False,'comparisons':'PAUSED','assets':[]}
    # No fixture, verifier, model or benchmark is executed here.
    source=plan['source'];archive=work/'source.tar.gz'
    try:
        downloaded=fetch(source,archive,budget)
        result['source']=verify_source(archive,load(plan['source_tree']),work,budget)
        result['source']['body_bytes']=downloaded
    except BaseException as error:
        result['source_error_type']=type(error).__name__
        write(HERE/'acquisition-result.json',result);raise

    def one(asset):
        destination=work/'mod-cache/cache/download'/asset['cache_path'];start=time.perf_counter()
        row={k:asset[k] for k in ('kind','module','version','url')}
        try:
            row['body_bytes']=fetch(asset,destination,budget)
            if asset['kind']=='zip':row.update(verify_zip(destination,asset,budget,licenses))
            elif asset['kind']=='mod':assert h1({'go.mod':destination.read_bytes()})==asset['go_h1'];row['go_h1_verified']=asset['go_h1']
            else:assert load(destination)['Version']==asset['version']
            row.update(passed=True,sha256=sha(destination))
        except BaseException as error:row.update(passed=False,error_type=type(error).__name__,http_status=error.code if isinstance(error,urllib.error.HTTPError) else None)
        row['wall_seconds']=time.perf_counter()-start;return row

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures=[pool.submit(one,asset) for asset in plan['assets']]
        for number,future in enumerate(concurrent.futures.as_completed(futures),1):
            result['assets'].append(future.result())
            if number%100==0:print(json.dumps({'completed':number,'total':len(futures),'data_only':True}),flush=True)
    result.update(passed=all(a['passed'] for a in result['assets']),download_body_bytes=budget.download,uncompressed_hashed_bytes=budget.unpacked,
                  free_bytes_after=shutil.disk_usage(ROOT).free,licenses_cleared=False)
    write(HERE/'acquisition-result.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ('assets','source')}),flush=True)
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--review-sha256',required=True);args=parser.parse_args()
    review=load(HERE/'operation-review.json');assert sha(HERE/'operation-review.json')==args.review_sha256
    for p,h in review['assets'].items():assert sha(p)==h,p
    authority=load(ROOT/'reports/toolkit-v2/c13/pipeline-standing-authority-20261104.json')
    assert authority['first_attempts'] and not (HERE/'acquisition-result.json').exists()
    result=execute(load(HERE/'plan.json'))
    if not result['passed']:raise SystemExit(1)
