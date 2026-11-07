"""Run one protected React reference in the retained upstream environment."""

import contextlib
import hashlib
import importlib
import importlib.metadata
import json
import os
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from urllib.request import ProxyHandler, build_opener

PROTECTED = Path('/opt/aeep-react-reference')
ROOT = Path('/tmp/aeep-react-reference')
SITE = ROOT / 'site'
ENV = {'PATH':'/usr/local/bin:/usr/bin:/bin', 'HOME':str(ROOT), 'TMPDIR':'/tmp',
       'LC_ALL':'C', 'EXTERNAL_API_URL':'http://localhost:3001',
       'PLAYWRIGHT_BROWSERS_PATH':'/root/.cache/ms-playwright', 'NEXT_TELEMETRY_DISABLED':'1',
       'npm_config_offline':'true', 'npm_config_audit':'false', 'npm_config_fund':'false',
       'UV_THREADPOOL_SIZE':'2', 'PYTHONDONTWRITEBYTECODE':'1'}
CLIENT = build_opener(ProxyHandler({}))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def boundary():
    assert os.geteuid()==0 and not os.access('/var/run/docker.sock',os.F_OK)
    status = dict(line.split(':',1) for line in Path('/proc/self/status').read_text().splitlines())
    assert status['NoNewPrivs'].strip()=='1' and int(status['CapEff'],16)==0 and status['Seccomp'].strip()=='2'
    ipv4=Path('/proc/net/route').read_text().splitlines()
    assert ipv4[0].split()[0]=='Iface' and all(row.split()[0]=='lo' for row in ipv4[1:] if row.strip())
    ipv6=Path('/proc/net/ipv6_route').read_text().splitlines()
    assert all(row.split()[-1]=='lo' for row in ipv6 if row.strip())
    assert all(not fd.readlink().as_posix().startswith('socket:')
               for fd in Path('/proc/self/fd').iterdir() if fd.exists())


def ready(url, proc):
    deadline=time.monotonic()+20
    while time.monotonic()<deadline:
        if proc.poll() is not None:
            raise RuntimeError('owned service exited')
        try:
            with CLIENT.open(url,timeout=2) as response:
                if response.status==200:
                    return
        except OSError:
            pass
        time.sleep(.2)
    raise TimeoutError('owned service readiness')


@contextlib.contextmanager
def service(argv, cwd, log):
    with log.open('xb') as output:
        proc=subprocess.Popen(argv,cwd=cwd,env=ENV,start_new_session=True,
                              stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT)
        try:
            yield proc
        finally:
            try:
                os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=4)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid,signal.SIGKILL)
                proc.wait(timeout=2)


def check(pins, name):
    path=PROTECTED/name
    assert sha(path.read_bytes())==pins['protected'][name]
    return path


def run(result):
    result['phase']='boundary'
    boundary()
    pins=json.loads((PROTECTED/'pins.json').read_bytes())
    for name in pins['protected']:
        check(pins,name)
    for pkg, version in pins['python_packages'].items():
        assert importlib.metadata.version(pkg)==version
    assert subprocess.check_output(['node','--version'],env=ENV,timeout=10,text=True).strip()=='v20.18.1'
    assert any(Path(ENV['PLAYWRIGHT_BROWSERS_PATH']).glob('chromium-*/chrome-linux/chrome'))
    assert Path('/app/node_modules/next/package.json').is_file()
    assert Path('/services/api-simulator/node_modules/tsx/package.json').is_file()
    ROOT.mkdir(mode=0o700)
    SITE.mkdir()
    for name, expected in pins['app_files'].items():
        src=Path('/app')/name
        assert src.is_file() and not src.is_symlink() and sha(src.read_bytes())==expected
        dst=SITE/name
        dst.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dst)
    (SITE/'node_modules').symlink_to('/app/node_modules',target_is_directory=True)
    (SITE/'output').mkdir()
    for name, digest in pins['patches'].items():
        assert name.startswith('src/') and '..' not in Path(name).parts
        path=PROTECTED/'patches'/name
        assert sha(path.read_bytes())==digest
        shutil.copyfile(path,SITE/name)
    result['solver_replayed']=False
    result['phase']='hidden loopback simulator'
    with service(['npm','start'],Path('/services/api-simulator'),ROOT/'simulator.log') as api:
        ready('http://localhost:3001/health',api)
        result['phase']='offline reference build'
        with (ROOT/'build.log').open('xb') as output:
            code=subprocess.run(['npm','run','build'],cwd=SITE,env=ENV,timeout=145,
                 stdin=subprocess.DEVNULL,stdout=output,stderr=subprocess.STDOUT).returncode
        result['build_exit_code']=code
        if code:
            return
        result['phase']='protected reference verifier'
        with service(['npm','start'],SITE,ROOT/'site.log') as app:
            ready('http://localhost:3000',app)
            os.environ.clear()
            os.environ.update(ENV)
            sys.path.insert(0,str(PROTECTED))
            import pytest
            from repository_suite_native_capture import NativeCapture

            os.environ['PYTEST_DISABLE_PLUGIN_AUTOLOAD']='1'
            plugins=[importlib.import_module(name) for name in pins['pytest_plugins']]
            capture=NativeCapture()
            pytest_log=ROOT/'pytest.log'
            with pytest_log.open('x') as log, contextlib.redirect_stdout(log), contextlib.redirect_stderr(log):
                code=int(pytest.main(['-p','no:cacheprovider','--asyncio-mode=auto',
                  '--base-url=http://localhost:3000','--rootdir='+str(PROTECTED),
                  str(PROTECTED/'test_outputs.py'),'-q'],plugins=[capture,*plugins]))
            statuses=capture.export()['statuses']
            expected=set(pins['test_ids'])
            result.update(verifier_exit_code=code,required_test_statuses={
                name:statuses[name] for name in sorted(expected & statuses.keys())},
                missing_collected=sorted(expected-set(capture.selected_ids)),
                unexpected_collected_count=len(set(capture.selected_ids)-expected))
            with pytest_log.open('rb') as log:
                sample=log.read(16384).lower()
            result['verifier_log_categories']=[label for label, marker in {
                'unrecognized_arguments':b'unrecognized arguments', 'import_failure':b'importerror',
                'missing_module':b'modulenotfounderror', 'browser_launch':b'browsertypelaunch',
                'asyncio_plugin':b'asyncio', 'timeout':b'timeout',
            }.items() if marker in sample]
            assert set(capture.selected_ids)==expected and set(statuses)==expected
            assert set(statuses.values())<={'PASSED','FAILED'}
            failed='FAILED' in statuses.values()
            assert code==int(failed)
            result.update(upstream_binary_reward=int(not failed),test_statuses=statuses,
                          verifier_exit_code=code,passed=not failed,phase='complete')


if __name__=='__main__':
    result={'passed':False,'models':0,'network':'loopback only','official_reproduction':False}
    try:
        run(result)
    except Exception as error:
        import traceback
        result['error_type']=type(error).__name__
        result['local_frames']=[{'line':f.lineno,'function':f.name}
             for f in traceback.extract_tb(error.__traceback__) if f.filename==__file__]
    for name in ('simulator','build','site','pytest'):
        file=ROOT/(name+'.log')
        if file.is_file():
            with file.open('rb') as stream:
                result[name+'_log_sha256']=hashlib.file_digest(stream,'sha256').hexdigest()
    print(json.dumps(result,allow_nan=False))
    raise SystemExit(not result['passed'])
