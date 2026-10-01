"""Frozen-resource baseline: stdlib-only coordinator; no AEEP imports/service."""
import asyncio,base64,hashlib,json,os,signal,subprocess,sys,time
async def main(p):
    assert hashlib.sha256(open(p['binary'],'rb').read()).hexdigest()==p['binary_sha256']
    assert hashlib.sha256(open(p['python'],'rb').read()).hexdigest()==p['python_sha256']
    assert hashlib.sha256(p['guard'].encode()).hexdigest()==p['guard_sha256']
    process=None;pending={};next_id=0;target=None;stdout=bytearray();stderr_bytes=0;ready=asyncio.Event();prefix=bytearray();fatal=None;read_task=None;drain_task=None
    def identity(pid):
        value=subprocess.run(['/bin/ps','-p',str(pid),'-o','lstart=','-o','ppid='],capture_output=True,text=True,check=True,timeout=1).stdout.strip()
        assert value;return value
    async def send(value):
        process.stdin.write(json.dumps(value,separators=(',',':')).encode()+b'\n');await process.stdin.drain()
    async def request(method,params):
        nonlocal next_id
        next_id+=1;future=asyncio.get_running_loop().create_future();pending[next_id]=future
        await send({'id':next_id,'method':method,'params':params});return await asyncio.wait_for(asyncio.shield(future),32)
    async def read():
        nonlocal fatal,target
        try:
            while line:=await process.stdout.readline():
                if len(line)>2097152:raise RuntimeError('protocol_size')
                m=json.loads(line)
                if 'id' in m:
                    if 'method' in m:raise RuntimeError('unexpected_server_request')
                    future=pending.pop(m['id'],None)
                    if future:
                        if 'error' in m:future.set_exception(RuntimeError('protocol_rejection'))
                        else:future.set_result(m.get('result',{}))
                elif m.get('method')=='command/exec/outputDelta':
                    x=m['params'];assert x['processId']=='aeep-command' and type(x['capReached']) is bool and not x['capReached']
                    chunk=base64.b64decode(x['deltaBase64'],validate=True)
                    if x['stream']=='stdout':
                        if not ready.is_set():
                            prefix.extend(chunk);assert len(prefix)<=200128
                            if b'\n' not in prefix:continue
                            line,chunk=bytes(prefix).split(b'\n',1);assert line.startswith(b'aeep-single-process-ready:');pid=int(line.split(b':')[1]);assert os.getpgid(pid)==pid and os.getsid(pid)==pid
                            stamp=identity(pid);ancestor=pid
                            for _ in range(20):
                                parent=int(identity(ancestor).split()[-1])
                                if parent==process.pid:break
                                assert parent>1;ancestor=parent
                            else:raise RuntimeError('ownership')
                            target=(pid,stamp);ready.set()
                        stdout.extend(chunk);assert len(stdout)<=200000
                    elif x['stream']!='stderr':raise RuntimeError('invalid_stream')
        except Exception as exc:
            fatal=type(exc).__name__
            for future in pending.values():
                if not future.done():future.set_exception(RuntimeError('stream_failure'))
    async def drain():
        nonlocal stderr_bytes
        while chunk:=await process.stderr.read(4096):stderr_bytes+=len(chunk)
    result={'baseline_aeep_modules_imported':False,'model_turns':0}
    started=time.perf_counter()
    try:
        async with asyncio.timeout(40):
            process=await asyncio.create_subprocess_exec(p['binary'],'app-server','--stdio',*p['permission_overrides'],cwd=p['root'],env={k:os.environ[k] for k in ('HOME','CODEX_HOME','PATH') if k in os.environ},stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,limit=2097153)
            read_task=asyncio.create_task(read());drain_task=asyncio.create_task(drain())
            await request('initialize',{'clientInfo':{'name':'native-resource-baseline','version':'1'},'capabilities':{'experimentalApi':True}});await send({'method':'initialized','params':{}})
            command=asyncio.create_task(request('command/exec',{'command':[p['python'],'-I','-c',p['guard'],json.dumps(p['environment'],separators=(',',':')),*p['argv']],'processId':'aeep-command','permissionProfile':'aeep-native-task','cwd':p['root'],'streamStdin':True,'streamStdoutStderr':True,'outputBytesCap':200128,'timeoutMs':30000}))
            while not ready.is_set() and not command.done():await asyncio.sleep(.01)
            assert ready.is_set()
            await request('command/exec/write',{'processId':'aeep-command','deltaBase64':base64.b64encode(b'\0'+json.dumps(p['input']).encode()).decode(),'closeStdin':True})
            response=await command;assert response['exitCode']==0 and response['stdout']=='' and response['stderr']=='' and fatal is None
            result['output']=json.loads(stdout);result['guard_ready']=True
    finally:
        if process:
            process.stdin.close()
            try:await asyncio.wait_for(process.wait(),3)
            except TimeoutError:process.kill();await process.wait()
            if read_task:await read_task
            if drain_task:await drain_task
        if target:
            try:
                if identity(target[0])==target[1]:
                    os.kill(target[0],signal.SIGKILL);result['target_cleanup_intervention']=True
            except subprocess.CalledProcessError:pass
        result.update(elapsed_seconds=time.perf_counter()-started,cleanup_confirmed=process is None or process.returncode is not None,stderr_bytes=stderr_bytes,transport_fatal_type=fatal,aeep_modules_present=any(x=='aeep' or x.startswith('aeep.') for x in sys.modules))
    assert not result['aeep_modules_present'];print(json.dumps(result))
asyncio.run(main(json.load(sys.stdin)))
