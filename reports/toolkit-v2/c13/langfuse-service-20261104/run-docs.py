"""One independent current-doc check with the unchanged cached offline tools."""
import argparse,hashlib,json,os,shutil,subprocess,time
from datetime import UTC,datetime
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
def load(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def validate(review):
    assert datetime.now(UTC)<datetime.fromisoformat(review['expires_at'].replace('Z','+00:00'))
    assert shutil.disk_usage(ROOT).free>=50*1024**3
    for p,h in review['docs_assets'].items():assert sha(p)==h,p
    docs=review['docs'];runtime=Path(docs['runtime']);state=load(docs['runtime_record'])
    actual=['README.md','AGENTS.md','CLAUDE.md','CONTRIBUTING.md','CODE_OF_CONDUCT.md','ARCHITECTURE.md','SPEC.md','SECURITY.md','docs/media/README.md']
    actual += [str(p.relative_to(ROOT)) for p in (ROOT/'docs').glob('*.md') if p.name not in ('ASSESSMENT_TESTING.md','ROADMAP_0.7.md')]
    for pattern in ('docs/protocol/*.md','docs/aeep-toolkit/*.md','examples/*/README.md','integrations/*/README.md'):
        actual += [str(p.relative_to(ROOT)) for p in ROOT.glob(pattern)]
    assert sorted(actual)==sorted(docs['documents']),'Makefile input expansion differs from exact reviewed scope'
    files={str(p.relative_to(runtime)):sha(p) for folder in ('bin','node_modules') for p in (runtime/folder).rglob('*') if p.is_file()}
    for name in ('operation.json','profile.sb'):files[name]=sha(runtime/name)
    assert files==state['files']
    if (HERE/'service-started.json').exists():
        assert (HERE/'service-execution/summary.json').exists(),'Reconcile started service first'
        result=load(HERE/'service-execution/summary.json')
        assert not result['cleanup_uncertain'] and not result['accounting_uncertain']

def execute(review,identity):
    validate(review);docs=review['docs'];runtime=Path(docs['runtime'])
    result={'review_sha256':identity,'passed':False,'models':0,'network':False,
            'input_hashes':{name:sha(ROOT/name) for name in docs['documents']}}
    with (HERE/'docs-attempt-1.json').open('x') as f:json.dump(result,f,indent=2)
    clock=time.monotonic()
    try:
        env={'PATH':str(runtime/'bin')+':/usr/local/bin:/usr/bin:/bin','HOME':str(runtime/'home'),'TMPDIR':str(runtime/'tmp'),'LC_ALL':'C'}
        with (HERE/'docs-attempt-1.log').open('x') as log:
            completed=subprocess.run(['/usr/bin/make','docs-check','LYCHEE='+str(runtime/'bin/lychee-sandbox')],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=180)
        result.update(passed=completed.returncode==0,exit_code=completed.returncode)
        validate(review);result['tools_and_inputs_unchanged']=True
    except BaseException as failure:result.update(passed=False,error_type=type(failure).__name__)
    finally:
        result['wall_seconds']=time.monotonic()-clock
        (HERE/'docs-attempt-1.json').write_text(json.dumps(result,indent=2)+'\n')
    return result

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute-approved');args=p.parse_args()
    review=load(HERE/'operation-review.json');identity=sha(HERE/'operation-review.json');validate(review)
    if args.execute_approved is None:print(json.dumps({'execution':False,'review_sha256':identity,'component':'docs'}));raise SystemExit(0)
    approval=load(HERE/'operator-approval.json');assert args.execute_approved==identity==approval['review_sha256'] and approval['approved'] is True
    result=execute(review,identity);print(json.dumps({k:v for k,v in result.items() if k!='input_hashes'}))
    if not result['passed']:raise SystemExit(1)
