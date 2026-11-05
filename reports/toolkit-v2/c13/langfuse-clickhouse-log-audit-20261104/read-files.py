"""Docker cp from a stopped owned container; bounded transient parsing only."""
import argparse,hashlib,json,re,subprocess,tarfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('--review',required=True);args=parser.parse_args()
p=HERE/'operation-review.json';assert hashlib.sha256(p.read_bytes()).hexdigest()==args.review
r=json.loads(p.read_bytes());env={'PATH':'/usr/bin:/bin','HOME':r['work'],'DOCKER_CONFIG':r['docker_config'],'DOCKER_HOST':'unix://'+r['docker_socket'],'LC_ALL':'C'}
categories=("couldn't get",'global thread pool','backgroundschedulepool','resource temporarily unavailable','cannot allocate memory','permission denied','fatal','read-only file system','not enough threads','os_thread_priority')
settings=('background_schedule_pool_size','background_buffer_flush_schedule_pool_size','background_distributed_schedule_pool_size','background_message_broker_schedule_pool_size','max_thread_pool_size')
results=[]
class Bounded:
    def __init__(self,stream):self.stream=stream;self.count=0
    def read(self,n=-1):
        assert self.count<r['maximum_archive_bytes_per_file'];value=self.stream.read(min(n if n>=0 else 65536,r['maximum_archive_bytes_per_file']-self.count));self.count+=len(value);return value
for file in r['files']:
    command=[r['docker'],'--config',r['docker_config'],'--host',env['DOCKER_HOST'],'cp',r['container_id']+':'+file,'-']
    process=subprocess.Popen(command,env=env,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    row={'path':file,'raw_content_retained':False}
    try:
        with tarfile.open(fileobj=Bounded(process.stdout),mode='r|') as archive:
            member=next(iter(archive));assert member.isfile() and member.size<=r['maximum_archive_bytes_per_file']-1024
            body=archive.extractfile(member).read(member.size);assert len(body)==member.size;text=body.decode('utf-8',errors='replace');lower=text.lower()
            row.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),categories=[word for word in categories if word in lower],error_codes=sorted({int(x) for x in re.findall(r'\bCode:\s*(\d+)',text)}),thread_counts=sorted({int(x) for x in re.findall(r'\b(\d+)\s+threads\b',text)}),public_pool_settings={key:[int(x) for x in re.findall('<'+key+r'>\s*(\d+)\s*</'+key+'>',text)] for key in settings},read=True)
    except (tarfile.TarError,AssertionError,StopIteration,OSError) as error:row.update(read=False,error_type=type(error).__name__)
    finally:
        if process.poll() is None:process.terminate()
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait()
        process.stdout.close()
    results.append(row)
print(json.dumps({'files':results,'raw_content_retained':False,'guest_or_service_programs_executed':False}))
