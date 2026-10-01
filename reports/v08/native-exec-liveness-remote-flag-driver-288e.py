"""Bounded installed exec-server liveness probe, native sandbox no-fork command."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
import psutil
from aeep.hosts.codex_sandbox import NativeSandboxConfig
ROOT=Path(__file__).resolve().parent
OWNED=ROOT/'native-coordinator-death-owned-288e'
DEFINITION=json.loads((OWNED/'definition.json').read_text())
BINARY=DEFINITION['binary']
def worker(mode):
    data=OWNED/'data'
    boundary=NativeSandboxConfig(binary=BINARY,binary_sha256=DEFINITION['binary_sha256'],project_root=str(OWNED),read_roots=[str(Path(sys.prefix).resolve())],write_roots=[str(data)])
    program="import resource,pathlib,sys,time,os; resource.setrlimit(resource.RLIMIT_NPROC,(0,0)); pathlib.Path(sys.argv[1]).write_text(str(os.getpid())); time.sleep(2); pathlib.Path(sys.argv[2]).write_text('effect'); time.sleep(3)"
    log=open(OWNED/f'exec-{mode}-stderr.log','w')
    server=subprocess.Popen([BINARY,'exec-server','--listen','stdio','--exit-on-stdin-close'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,text=True)
    def send(v): server.stdin.write(json.dumps(v)+'\n');server.stdin.flush()
    def response(i):
        while True:
            line=server.stdout.readline()
            if not line: raise RuntimeError('native exec-server ended before response')
            v=json.loads(line)
            if v.get('id')==i:
                if 'error' in v: raise RuntimeError(json.dumps(v['error']))
                return v
    send({'id':1,'method':'initialize','params':{'clientName':'aeep-bounded-liveness-probe'}});response(1)
    send({'method':'initialized','params':{}})
    argv=boundary.argv([sys.executable,'-I','-c',program,str(data/f'{mode}-started'),str(data/f'{mode}-effect')])
    send({'id':2,'method':'process/start','params':{'processId':'owned-probe','argv':argv,'cwd':OWNED.as_uri(),'env':{'PATH':'/usr/bin:/bin'},'tty':False,'pipeStdin':False,'arg0':None}});response(2)
    (data/f'{mode}-server').write_text(str(server.pid))
    while not (data/f'{mode}-started').exists(): time.sleep(.01)
    if mode=='close': server.stdin.close();server.wait(timeout=4)
    elif mode=='terminate':
        send({'id':3,'method':'process/terminate','params':{'processId':'owned-probe'}});response(3);server.stdin.close();server.wait(timeout=4)
    else: time.sleep(8)
def supervisor():
    review={'source_digest':DEFINITION['source_digest'],'binary_sha256':DEFINITION['binary_sha256'],'authority':'parent September 30 finite native liveness feasibility instruction','cases':['close','kill','terminate'],'command':'sandboxed Python sets hard RLIMIT_NPROC=0 before writing started marker, waits2sec then writes effect','bounds':'max8sec wait to start; observe2.5sec; cleanup identity-bound observed children; no model/auth/global config','protocol_source':'https://github.com/openai/codex/blob/main/codex-rs/exec-server/README.md','driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'expected':'server exit on pipe closure and no command effect after owner closure, death or terminate'}
    (ROOT/'native-exec-liveness-review-288e.json').write_text(json.dumps(review,indent=2))
    results=[]
    for mode in review['cases']:
        t=time.monotonic(); p=subprocess.Popen([sys.executable,str(Path(__file__).resolve()),mode],stdout=subprocess.DEVNULL,stderr=open(OWNED/f'{mode}-driver-stderr.log','w'),env=dict(os.environ,PYTHONPATH=str(ROOT.parents[1]/'src')))
        owner=psutil.Process(p.pid); handles=[owner]; row={'mode':mode}
        try:
            deadline=time.monotonic()+8
            while not (OWNED/'data'/f'{mode}-started').exists() and p.poll() is None and time.monotonic()<deadline: time.sleep(.02)
            row['started']=(OWNED/'data'/f'{mode}-started').exists()
            handles.extend(owner.children(recursive=True)) if owner.is_running() else None
            if not row['started']: row['failure']='start failed';continue
            if mode=='kill': owner.kill();p.wait(timeout=2)
            else: p.wait(timeout=4)
            time.sleep(2.5)
            row['effect_after_stop']=(OWNED/'data'/f'{mode}-effect').exists()
            serverpid=int((OWNED/'data'/f'{mode}-server').read_text())
            row['server_still_live']=any(h.pid==serverpid and h.is_running() and h.status()!=psutil.STATUS_ZOMBIE for h in handles)
        finally:
            killed=[]
            for h in reversed(handles):
                try:
                    if h.is_running() and h.status()!=psutil.STATUS_ZOMBIE: h.kill();killed.append(h.pid)
                except psutil.NoSuchProcess: pass
            psutil.wait_procs(handles,timeout=2)
            row['cleanup_signalled_owned_pids']=killed;row['remaining_owned_live_pids']=[h.pid for h in handles if h.is_running() and h.status()!=psutil.STATUS_ZOMBIE];row['elapsed_seconds']=time.monotonic()-t;results.append(row)
    record={'review':review,'cases':results,'claim':'bounded native feasibility only; no adapter implementation or general containment qualification'}
    (ROOT/'native-exec-liveness-result-288e.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
if __name__=='__main__': supervisor() if len(sys.argv)==1 else worker(sys.argv[1])
