"""Exact cached offline docs tooling; retain its owned reusable runtime."""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def sha(path):
    assert path.is_file() and not path.is_symlink() and path.stat().st_nlink == 1
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(review):
    assert sha(Path(__file__)) == review['runner_sha256']
    for name, value in review['configs'].items():
        assert sha(ROOT / name) == value
    assert sha(HERE/'sandbox-template.sb') == review['sandbox_template_sha256']
    assert sha(HERE/'sandbox-preflight.py') == review['preflight_program_sha256']
    assert sha(HERE/'sandbox-preflight.json') == review['preflight_sha256']
    assert sha(Path(review['node'])) == review['node_sha256']
    assert sha(Path(review['archive'])) == review['archive_sha256']
    source = Path(review['node_modules'])
    for name, value in review['module_files'].items():
        assert sha(source/name) == value
    # The pinned Makefile expands filenames, never instructions from Markdown.
    planned = subprocess.run(['make','-n','docs-check'],cwd=ROOT,capture_output=True,
                             text=True,timeout=10,check=True).stdout.splitlines()
    lint = shlex.split(planned[0])
    assert lint[:7] == ['npx','--yes','markdownlint-cli2@0.23.3','--config','.markdownlint-cli2.jsonc','--no-globs',review['documents'][0]]
    assert lint[6:] == review['documents']


def tools_state(runtime):
    files={}
    for directory in ('bin','node_modules'):
        for path in (runtime/directory).rglob('*'):
            if path.is_file(): files[str(path.relative_to(runtime))]=sha(path)
    for name in ('operation.json','profile.sb'):
        files[name]=sha(runtime/name)
    return files


def setup(review, identity):
    journal=HERE/'runtime.json'
    if journal.exists():
        state=json.loads(journal.read_text());runtime=Path(state['runtime'])
        assert state['review_sha256']==identity and tools_state(runtime)==state['files']
        return runtime,state
    assert not (HERE/'setup-started.json').exists(), 'interrupted setup requires inspection'
    (HERE/'setup-started.json').write_text(json.dumps({'review_sha256':identity})+'\n')
    runtime=Path(tempfile.mkdtemp(prefix='aeep-stack-docs-',dir='/private/tmp')).resolve()
    for name in ('home','tmp','bin','node_modules'):(runtime/name).mkdir(mode=0o700)
    (runtime/'operation.json').write_text(json.dumps({'review_sha256':identity,'purpose':'retained offline documentation tools'})+'\n')
    for name in review['module_files']:
        target=runtime/'node_modules'/name;target.parent.mkdir(parents=True,exist_ok=True)
        with (Path(review['node_modules'])/name).open('rb') as src,target.open('xb') as dst:
            shutil.copyfileobj(src,dst)
        assert sha(target)==review['module_files'][name]
    with tarfile.open(review['archive'],'r:gz') as archive:
        member=archive.getmember(review['binary_member'])
        assert member.isfile() and member.size==review['binary_bytes']
        raw=archive.extractfile(member).read()
    assert hashlib.sha256(raw).hexdigest()==review['binary_sha256']
    binary=runtime/'bin/lychee';binary.write_bytes(raw);binary.chmod(0o500)
    profile=(HERE/'sandbox-template.sb').read_text()
    for key,value in {'HOME':runtime/'home','TMP':runtime/'tmp','ROOT':ROOT,'AEEP':ROOT/'.aeep',
                      'GIT':ROOT/'.git','CODEX':ROOT/'.codex'}.items():
        profile=profile.replace('@'+key+'@',json.dumps(str(value)))
    (runtime/'profile.sb').write_text(profile)
    prefix=['/usr/bin/sandbox-exec','-f',str(runtime/'profile.sb')]
    environment={'PATH':'/usr/bin:/bin','HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),
                 'LC_ALL':'en_US.UTF-8'}
    def wrapper(name, argv, expected=None):
        code='#!'+sys.executable+'\nimport subprocess,sys\n'
        if expected is not None:
            code+='assert sys.argv[1:] == '+repr(expected)+'\n'
            code+='args='+repr(argv)+'\n'
        else:code+='args='+repr(argv)+'+sys.argv[1:]\n'
        code+='raise SystemExit(subprocess.run('+repr(prefix)+'+args,env='+repr(environment)+',timeout=60).returncode)\n'
        target=runtime/'bin'/name;target.write_text(code);target.chmod(0o500)
    arguments=['--config','.markdownlint-cli2.jsonc','--no-globs',*review['documents']]
    wrapper('npx',[review['node'],str(runtime/'node_modules/markdownlint-cli2/markdownlint-cli2-bin.mjs'),*arguments],
            ['--yes','markdownlint-cli2@0.23.3',*arguments])
    wrapper('lychee-sandbox',[str(binary)])
    state={'review_sha256':identity,'runtime':str(runtime),'files':tools_state(runtime)}
    journal.write_text(json.dumps(state,indent=2)+'\n')
    return runtime,state


def main():
    review=json.loads((HERE/'operation-review.json').read_text());verify(review)
    identity=sha(HERE/'operation-review.json')
    if len(sys.argv)==1:
        print(json.dumps({'review_sha256':identity,'documents':len(review['documents']),
                          'executed':False,'runtime_created':False}));return
    assert sys.argv[1:]==['--execute-approved',identity]
    approval=json.loads((HERE/'operator-approval.json').read_text())
    assert approval['approved'] is True and approval['review_sha256']==identity
    assert not (HERE/'withdrawn.json').exists() and not (HERE/'complete.json').exists()
    assert shutil.disk_usage(ROOT).free>50*1024**3+review['reserve_bytes']
    assert json.loads((HERE/'sandbox-preflight.json').read_text())['passed']
    prior=sorted(HERE.glob('attempt-*.json'))
    assert len(prior)<3
    # Finite retries cover listed Markdown edits only. Binary/config/profile
    # changes need fresh authority. Every attempt and failed log remains.
    attempt=len(prior)+1;path=HERE/f'attempt-{attempt}.json'
    record={'review_sha256':identity,'attempt':attempt,'models':0,'network':False,
            'input_hashes':{name:sha(ROOT/name) for name in review['documents']}}
    with path.open('x') as handle:json.dump(record,handle,indent=2)
    began=time.monotonic()
    try:
        runtime,state=setup(review,identity)
        environment={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin',
                     'HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'en_US.UTF-8'}
        with (HERE/f'attempt-{attempt}.log').open('x') as log:
            result=subprocess.run(['make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],
                                  cwd=ROOT,env=environment,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        record.update(returncode=result.returncode,passed=result.returncode==0,
                      runtime=str(runtime),runtime_retained=True,tools_unchanged=tools_state(runtime)==state['files'])
        assert record['tools_unchanged']
        assert all(sha(ROOT/name)==value for name,value in record['input_hashes'].items())
    except BaseException as error:
        record.update(passed=False,error_type=type(error).__name__)
    finally:
        record['wall_seconds']=time.monotonic()-began
        path.write_text(json.dumps(record,indent=2)+'\n')
        if record.get('passed'):
            (HERE/'complete.json').write_text(json.dumps({'attempt':attempt,'review_sha256':identity})+'\n')
        print(json.dumps({key:value for key,value in record.items() if key!='input_hashes'}))


if __name__=='__main__':main()
