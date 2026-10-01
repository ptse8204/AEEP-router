#!/usr/bin/env python3
"""Unauthenticated review probe for pinned Codex workers and a Squid image.

Run only with locally reviewed images. Creates temporary Docker networks and
containers, probes synthetic data, and removes those resources in finally.
It neither logs in nor invokes a model; results are supporting evidence only.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

from aeep.hosts.workers import ManagedWorkerBinding


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--workers', type=Path, required=True)
    parser.add_argument('--proxy-image', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not __import__('re').fullmatch(r'sha256:[a-f0-9]{64}', args.proxy_image):
        parser.error('proxy image must be an immutable local sha256 image')
    workers = {role: ManagedWorkerBinding.model_validate(entry['binding'])
               for role, entry in json.loads(args.workers.read_text())['workers'].items()}
    if set(workers) != {'control','treatment'} or any(worker.credential_volume for worker in workers.values()):
        parser.error('probe requires exactly two unauthenticated worker bindings')
    first = workers['control']
    docker = [first.runtime,'--host','unix://'+first.socket]
    if any((worker.runtime,worker.socket) != (first.runtime,first.socket) for worker in workers.values()):
        parser.error('workers must use the same explicit local runtime')
    suffix = __import__('uuid').uuid4().hex[:12]
    proxy = 'aeep-proxy-probe-'+suffix
    networks: list[str] = []
    report: dict[str, object] = {'model_turns':0,'authenticated':False,'approved':False,
        'proxy_image':args.proxy_image,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def run(*argv: str) -> str:
        result = subprocess.run([*docker,*argv],capture_output=True,text=True,timeout=30)
        if result.returncode:
            raise RuntimeError('local container probe command failed')
        return result.stdout.strip()

    try:
        private = run('network','create','--internal','aeep-private-'+suffix)
        networks.append(private)
        outbound = run('network','create','aeep-outbound-'+suffix)
        networks.append(outbound)
        run('create','--name',proxy,'--network',private,'--read-only','--cap-drop=ALL',
            '--security-opt=no-new-privileges','--tmpfs','/tmp:rw,nosuid,nodev,size=8m',
            '--pids-limit=32','--memory=128m',args.proxy_image)
        run('network','connect',outbound,proxy)
        run('start',proxy)
        address = json.loads(run('inspect',proxy))[0]['NetworkSettings']['Networks']['aeep-private-'+suffix]['IPAddress']
        observations = {}
        for role, original in workers.items():
            worker = ManagedWorkerBinding.model_validate({**original.model_dump(),'network_id':private,'model_proxy_url':f'http://{address}:3128'})
            code = '''import json,pathlib,socket
result={}
try:pathlib.Path('/worker/auth/synthetic-canary').read_text();result['credential_canary']='readable'
except PermissionError:result['credential_canary']='denied'
for name,endpoint in [('proxy',(ADDRESS,3128)),('direct',('1.1.1.1',443))]:
 sock=None
 try:
  sock=socket.socket();sock.settimeout(1);sock.connect(endpoint);result[name]='permitted'
 except OSError:result[name]='denied'
 finally:
  if sock:sock.close()
pathlib.Path('/workspace/allowed.txt').write_text('synthetic')
result['workspace_write']=True
print(json.dumps(result))
'''.replace('ADDRESS',repr(address))
            with tempfile.TemporaryDirectory(prefix='aeep-probe-policy-') as directory:
                argv = list(worker.argv(('sandbox','--permission-profile','aeep','--include-managed-config','python3','-c',code),
                    execution_id=suffix+role,security_path=worker.prepare_security(Path(directory))))
                index = argv.index('--entrypoint')
                launch = ['/opt/aeep/worker-launch',*argv[index+3:]]
                wrapper = "import os,pathlib; pathlib.Path('/worker/auth/synthetic-canary').write_text('synthetic-only'); os.execv('/opt/aeep/worker-launch',"+repr(launch)+")"
                argv[index:] = ['--entrypoint','python3',worker.image,'-c',wrapper]
                result = subprocess.run(argv,capture_output=True,text=True,timeout=30)
                observed = json.loads(result.stdout) if result.returncode == 0 else None
                observations[role] = {'worker_digest':worker.digest(),'exit_code':result.returncode,'observed':observed}
        report['workers'] = observations
    finally:
        for name in [proxy,*['aeep-'+hashlib.sha256((suffix+role).encode()).hexdigest()[:32] for role in workers]]:
            subprocess.run([*docker,'rm','-f',name],capture_output=True,timeout=10)
        for network in reversed(networks):
            subprocess.run([*docker,'network','rm',network],capture_output=True,timeout=10)
        args.output.write_text(json.dumps(report,indent=2)+'\n')
    expected = {'credential_canary':'denied','proxy':'denied','direct':'denied','workspace_write':True}
    if any(item['observed'] != expected for item in observations.values()):
        raise SystemExit('worker boundary probe failed; inspect the sanitized record')


if __name__ == '__main__':
    main()
