"""Two read-only save streams per approved image; no disk archive or guest code."""
from __future__ import annotations
import gzip,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile,threading,time
from pathlib import Path,PurePosixPath

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
review=json.loads((HERE/'operation-review.json').read_bytes())
SOURCE=Path(review['coordinator_source_snapshot']);sys.path.insert(0,str(SOURCE/'src'))
from aeep.assessment.models import AssessmentLimits,RecipeMaterializationRequest
from aeep.assessment.repository import AssessmentRepository
from aeep.models import ExecutionReceipt,ResourceVector,utc_now
from aeep.store import ReceiptStore

OUT=HERE/'image-audit';OUT.mkdir(mode=0o700,exist_ok=True)
PRIVATE=Path(review['acquisition']['work'])/'image-notices';PRIVATE.mkdir(mode=0o700,exist_ok=True)
NAMESET={'bin','lib','lib64','sbin','sh','bash','busybox','coreutils','mkdir','chown','mc','minio',
 'node','dumb-init','postgres','redis-server','clickhouse','entrypoint.sh','docker-entrypoint.sh'}
NOTICE=re.compile(r'^(license|copying|notice|copyright)([._-].*)?$',re.I)


def load(path):return json.loads(Path(path).read_bytes())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,indent=2)+'\n')


class Digesting:
    def __init__(self,stream):self.stream=stream;self.digest=hashlib.sha256();self.count=0
    def read(self,n):
        assert 0<=n<=16*1024**2
        raw=self.stream.read(n);self.count+=len(raw);assert self.count<=16*1024**3
        self.digest.update(raw);return raw


def first_pass(archive,config_digest):
    config_name=config_digest.removeprefix('sha256:');found={};members=0
    for member in archive:
        members+=1;assert members<=10000
        if member.name in {'manifest.json','index.json',config_name+'.json','blobs/sha256/'+config_name}:
            assert member.isfile() and member.size<=2*1024**2
            raw=archive.extractfile(member).read(member.size)
            found[member.name]={'sha256':hashlib.sha256(raw).hexdigest(),'value':json.loads(raw)}
    manifest=found['manifest.json']['value'];assert isinstance(manifest,list) and len(manifest)==1
    manifest=manifest[0];config=found[manifest['Config']]
    assert config['sha256']==config_name
    assert len(manifest['Layers'])==len(config['value']['rootfs']['diff_ids'])
    return {'manifest':manifest,'config':config['value'],'outer_headers':members,'config_digest_verified':True}


def second_pass(archive,first):
    chosen=set(first['manifest']['Layers']);layers={};texts=0
    for member in archive:
        if member.name not in chosen:continue
        assert member.isfile() and member.name not in layers
        buffered=io.BufferedReader(archive.extractfile(member))
        source=gzip.GzipFile(fileobj=buffered) if buffered.peek(2)[:2]==b'\x1f\x8b' else buffered
        hashed=Digesting(source);entries={};whiteouts=[];headers=0;notices={}
        with tarfile.open(fileobj=hashed,mode='r|') as inner:
            for item in inner:
                headers+=1;assert headers<=500000
                name=item.name.removeprefix('./').rstrip('/');path=PurePosixPath(name)
                assert not path.is_absolute() and '..' not in path.parts and '\x00' not in name
                if path.name=='.wh..wh..opq':whiteouts.append((str(path.parent),True));continue
                if path.name.startswith('.wh.'):
                    whiteouts.append((str(path.parent/path.name.removeprefix('.wh.')),False));continue
                notice=bool(NOTICE.fullmatch(path.name))
                package=name in {'app/web/package.json','app/worker/package.json','lib/apk/db/installed','var/lib/dpkg/status'} or name.endswith('.spdx.json')
                if not(notice or package or path.name in NAMESET):continue
                assert len(entries)<20000
                record={'kind':'file' if item.isfile() else 'symlink' if item.issym() else 'hardlink' if item.islnk() else 'directory' if item.isdir() else 'other',
                    'mode':oct(item.mode&0o7777),'uid':item.uid,'gid':item.gid,'bytes':item.size}
                if item.issym() or item.islnk():record['target']=item.linkname
                if item.isfile():
                    digest=hashlib.sha256();head=bytearray();body=inner.extractfile(item)
                    while True:
                        raw=body.read(1024**2)
                        if not raw:break
                        digest.update(raw)
                        limit=8*1024**2 if package else 65536 if notice and not(item.mode&0o111) else 0
                        if len(head)<limit:head.extend(raw[:limit-len(head)])
                    record['sha256']=digest.hexdigest()
                    if head:
                        try:text=head.decode('utf-8')
                        except UnicodeDecodeError:text=None
                        if text is not None and not text.startswith('#!'):
                            texts+=len(head);assert texts<=64*1024**2
                            notices[name]={'text':text,'truncated':len(head)<item.size,'sha256':record['sha256']}
                entries[name]=record
        while hashed.read(1024**2):pass
        layers[member.name]={'diff_id':'sha256:'+hashed.digest.hexdigest(),'uncompressed_bytes':hashed.count,'headers':headers,'entries':entries,'whiteouts':whiteouts,'notices':notices}
    assert set(layers)==chosen
    final={}
    for name,expected in zip(first['manifest']['Layers'],first['config']['rootfs']['diff_ids'],strict=True):
        layer=layers[name];assert layer['diff_id']==expected
        for target,opaque in layer['whiteouts']:
            prefix='' if target=='.' else target+'/'
            final={path:value for path,value in final.items() if not(path.startswith(prefix) or (not opaque and path==target))}
        final.update(layer['entries'])
    retained={}
    for name in first['manifest']['Layers']:
        retained.update({path:value for path,value in layers[name]['notices'].items()
                         if path in final and value['sha256']==final[path].get('sha256')})
    return {'final_entries':final,'notice_data':retained,
        'layers':[{'name':name,**{key:layers[name][key] for key in ('diff_id','uncompressed_bytes','headers')}} for name in first['manifest']['Layers']]}


def stream(repo,request,image,phase,consume):
    for path,expected in review['component_assets']['acquisition'].items():assert sha(path)==expected,path
    from aeep.assessment.verification import verification_source_digest
    assert verification_source_digest(SOURCE)==review['source']
    assert sha(review['acquisition']['docker'])==review['assets'][review['acquisition']['docker']]
    assert image in review['acquisition']['images']
    repo.authorize(request);assert shutil.disk_usage(ROOT).free>=50*1024**3
    operation=request.plan_id+':static-audit:'+image['key']+':'+phase
    repo.reserve(request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=210),stage='static_image_header_audit')
    clock=time.perf_counter();started=utc_now();child=None;failure=None;value=None;stop=threading.Event();violation=[]
    argv=[review['acquisition']['docker'],'--config',review['acquisition']['docker_config'],'--host',
        'unix://'+review['acquisition']['docker_socket'],'image','save',image['reference']]
    def monitor():
        while not stop.wait(.5):
            if shutil.disk_usage(ROOT).free<50*1024**3 or time.perf_counter()-clock>190:
                violation.append('reserve_or_timeout')
                if child is not None and child.poll() is None:child.terminate()
                return
    try:
        child=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            env={'PATH':'/usr/bin:/bin','HOME':review['acquisition']['work']})
        watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
        with tarfile.open(fileobj=child.stdout,mode='r|*') as archive:value=consume(archive)
        child.stdout.close();error=child.stderr.read(16385)
        assert len(error)<=16384 and child.wait(timeout=10)==0 and not violation
    except BaseException as error:failure=type(error).__name__
    finally:
        stop.set()
        if child is not None:
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait(timeout=5)
            for pipe in (child.stdout,child.stderr):
                if pipe is not None:pipe.close()
        elapsed=time.perf_counter()-clock
        receipt=ExecutionReceipt(decision_id=operation,action_id=operation,capability='toolkit.upstream-engineering@1',
            executor_id='langfuse.static-image-audit',executor_kind='command',status='failed' if failure else 'success',
            started_at=started,ended_at=utc_now(),estimated={},actual_resources=ResourceVector(latency_ms=elapsed*1000),
            execution_success=failure is None,error_type=failure,metadata={'image':image['reference'],'phase':phase,
                'driver_sha256':sha(Path(__file__)),'observed_resource_dimensions':['latency_ms'],
                'no_guest_execution_or_disk_archive':True,'legacy_vector_defaults_are_not_observations':True})
        repo.store.save_receipt(receipt);repo.finish_operation(operation,elapsed_seconds=elapsed,resources=receipt.actual_resources)
        write(OUT/(image['key']+'-'+phase+'-receipt.json'),receipt.model_dump(mode='json'))
    return value,failure,elapsed


def main():
    assert sha(HERE/'operation-review.json')=='d7f05c3f6c0e726cee3b499c1bd185038a16c369dc64781b559fbe3eae66086c'
    approval=load(HERE/'operator-approval.json');assert approval['approved'] and approval['review_sha256']==sha(HERE/'operation-review.json')
    assert load(HERE/'runtime-execution/summary.json')['passed']
    prepared=load(HERE/'acquisition-preparation.json');request=RecipeMaterializationRequest.model_validate(prepared['request'])
    record={'evidence_kind':'STATIC_IMAGE_LICENSE_HEADER_AUDIT_NOT_EXECUTION','images':[],
        'models':0,'guest_programs_executed':0,'services_started':0,'disk_archives_written':0,'host_executables_extracted':0}
    with ReceiptStore(prepared['ledger']) as store:
        repo=AssessmentRepository(store)
        overhead_request=request.model_copy(update={'plan_id':request.plan_id+':static-audit-overhead'})
        operation=request.plan_id+':static-audit-overhead'
        repo.reserve(overhead_request,operation,AssessmentLimits(max_operations=1,max_model_turns=0,max_elapsed_seconds=60),stage='static_audit_driver_overhead')
        clock=time.perf_counter();nested=0.
        try:
            for image in review['acquisition']['images']:
                first,error,elapsed=stream(repo,request,image,'manifest',lambda archive:first_pass(archive,image['config_digest']));nested+=elapsed
                row={'image':image['reference'],'key':image['key'],'passed':False}
                if error:row['manifest_error']=error
                else:
                    second,error,elapsed=stream(repo,request,image,'layers',lambda archive:second_pass(archive,first));nested+=elapsed
                    if error:row['layer_error']=error
                    else:
                        notices=PRIVATE/(image['key']+'.json');write(notices,second.pop('notice_data'));notices.chmod(0o600)
                        detail={'image':image['reference'],'config_digest':image['config_digest'],'config':first['config']['config'],**second,
                            'license_notices_private_file':str(notices),'license_notices_sha256':sha(notices),'guest_execution':False}
                        write(OUT/(image['key']+'-headers.json'),detail)
                        row.update(passed=True,selected_entries=len(second['final_entries']),verified_layers=len(second['layers']),
                            notice_records=len(load(notices)),detail=str(OUT/(image['key']+'-headers.json')))
                record['images'].append(row);write(OUT/'summary.json',record)
                if shutil.disk_usage(ROOT).free<50*1024**3:raise RuntimeError('Reserve crossed')
        finally:
            elapsed=max(0.,time.perf_counter()-clock-nested)
            repo.finish_operation(operation,elapsed_seconds=elapsed,resources=ResourceVector(latency_ms=elapsed*1000))
            record['grant_counters']=list(store._connection.execute('SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?',(request.authorization_id,)).fetchone())
            record['accounting_uncertain']=store._connection.execute("SELECT 1 FROM assessment_operations WHERE grant_id=? AND state='reserved'",(request.authorization_id,)).fetchone() is not None
            record['passed']=len(record['images'])==6 and all(row['passed'] for row in record['images'])
            record['free_bytes_after']=shutil.disk_usage(ROOT).free;write(OUT/'summary.json',record)
            write(OUT/'operation-ledger.json',repo.operation_ledger(request.plan_id).model_dump(mode='json'))
            write(OUT/'overhead-ledger.json',repo.operation_ledger(overhead_request.plan_id).model_dump(mode='json'))
    print(json.dumps(record))


if __name__=='__main__':main()
