"""Independent cached offline documentation check; preserve tools and failures."""
from __future__ import annotations
import argparse,hashlib,json,os,re,shlex,shutil,subprocess,sys,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
sys.path.insert(0,str(ROOT/'src'))
from aeep.assessment.identity import verify_dependencies
from aeep.assessment.verification import verification_source_digest
from aeep_toolkit.install_runtime import file_digest as sha

def blank_line_digest(raw):
    """Only repeated blank lines outside fenced/indented code may be removed."""
    output=[];fence=None;indented=False;previous_blank=False
    for line in raw.splitlines(keepends=True):
      blank=not line.strip();match=re.match(br' {0,3}(`{3,}|~{3,})',line)
      if blank and not fence and not indented and previous_blank:continue
      output.append(line)
      if match:
        marker=match[1]
        if fence is None:fence=marker
        elif marker[:1]==fence[:1] and len(marker)>=len(fence):fence=None
      if not blank:indented=bool(line.startswith((b'    ',b'\t'))) and not match
      previous_blank=blank and not fence and not indented
    return hashlib.sha256(b''.join(output)).hexdigest()

def tools_state(runtime):
    files={}
    for folder in ('bin','node_modules'):
      for p in (runtime/folder).rglob('*'):
        if p.is_file():files[str(p.relative_to(runtime))]=sha(p)
    for name in ('operation.json','profile.sb'):files[name]=sha(runtime/name)
    return files

def verify():
    review=json.loads((HERE/'operation-review.json').read_bytes());docs=review['docs']
    assert verification_source_digest(ROOT)==review['source'],'Common source changed; preserve the current checkout'
    for name,expected in review['bound_files'].items():
      if sha(ROOT/name)==expected:continue
      first=HERE/'docs-attempt-1.json'
      assert name in docs['normalized_input_hashes'] and first.exists() and not json.loads(first.read_bytes())['passed'] and not (HERE/'docs-complete.json').exists()
      assert blank_line_digest((ROOT/name).read_bytes())==docs['normalized_input_hashes'][name],name
    runtime=Path(docs['runtime']);state=json.loads(Path(docs['runtime_record']).read_bytes())
    assert tools_state(runtime)==state['files']
    verify_dependencies(docs['executable_dependencies'])
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    command=subprocess.run(['/usr/bin/make','-n','docs-check'],cwd=ROOT,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'},capture_output=True,text=True,timeout=10,check=True)
    assert shlex.split(command.stdout.splitlines()[0])==['npx','--yes','markdownlint-cli2@0.23.3','--config','.markdownlint-cli2.jsonc','--no-globs',*docs['documents']]
    return review

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--execute-approved');args=parser.parse_args()
    review=verify();identity=sha(HERE/'operation-review.json')
    if args.execute_approved is None:print(json.dumps({'review_sha256':identity,'execution':False,'tools_match':True,'documents':len(review['docs']['documents'])}));return
    approval=json.loads((HERE/'operator-approval.json').read_bytes());assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    attempts=list(HERE.glob('docs-attempt-*.json'));assert len(attempts)<2 and not (HERE/'docs-complete.json').exists()
    number=len(attempts)+1;docs=review['docs'];runtime=Path(docs['runtime']);record={'review_sha256':identity,'attempt':number,'passed':False,'models':0,'network':False,'input_hashes':{name:sha(ROOT/name) for name in docs['documents']}}
    path=HERE/f'docs-attempt-{number}.json'
    with path.open('x') as f:json.dump(record,f,indent=2)
    clock=time.monotonic()
    try:
      env={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin','HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'C'}
      with (HERE/f'docs-attempt-{number}.log').open('x') as log:
        result=subprocess.run(['/usr/bin/make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
      record.update(passed=result.returncode==0,exit_code=result.returncode)
      assert tools_state(runtime)==json.loads(Path(docs['runtime_record']).read_bytes())['files']
      assert all(sha(ROOT/name)==value for name,value in record['input_hashes'].items())
      record['tools_unchanged']=True
    except BaseException as error:record.update(passed=False,error_type=type(error).__name__)
    finally:
      record['seconds']=time.monotonic()-clock;path.write_text(json.dumps(record,indent=2)+'\n')
      if record['passed']:(HERE/'docs-complete.json').write_text(json.dumps({'review_sha256':identity,'attempt':number})+'\n')
    print(json.dumps({k:v for k,v in record.items() if k!='input_hashes'}))

if __name__=='__main__':main()
