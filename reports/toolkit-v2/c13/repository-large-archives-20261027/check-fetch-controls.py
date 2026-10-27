"""Run first-party control fixtures with all network/build/subject dispatch replaced."""
import asyncio
import contextlib
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch
import urllib.request

from aeep.assessment.models import content_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    checks=[];script=(HERE/'fetch-reviewed-wheel.py').read_text()
    for mode in ('pass','hash_mismatch','short','oversize','wrong_directory','existing','wrong_host','not_approved','redirect'):
        with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-fetch-only-',dir=ROOT/'.aeep') as temp:
            base=Path(temp);cache=base/'cache';cache.mkdir();body=b'SYNTHETIC WHEEL DATA; NEVER IMPORT'
            plan={'source_url':'https://files.pythonhosted.org/SYNTHETIC-NOT-A-REAL-ARTIFACT','size_bytes':len(body),'sha256':hashlib.sha256(body).hexdigest()}
            if mode=='wrong_host':plan['source_url']='https://example.invalid/no'
            if mode=='hash_mismatch':plan['sha256']='0'*64
            review=base/'runtime-review.json';review.write_text(json.dumps({'pending_wheel_fetch':plan,'fetch_cache':str(cache)}))
            (base/'operator-approval.json').write_text(json.dumps({'approved':mode!='not_approved','review_sha256':sha(review),'SYNTHETIC_FIXTURE_ONLY':True,'authority_granted':False}))
            destination=(base if mode=='wrong_directory' else cache)/'attempt-1.partial'
            if mode=='existing':destination.write_bytes(b'preserve')
            data=body[:-1] if mode=='short' else body+b'!' if mode=='oversize' else body
            calls=[]
            def opener(*handlers):
                assert isinstance(handlers[0],urllib.request.ProxyHandler) and handlers[0].proxies=={}
                def open_data(request,timeout):
                    calls.append(request.full_url);assert timeout==30
                    if mode=='redirect':handlers[1].redirect_request(None,None,None,None,None,None)
                    return io.BytesIO(data)
                return SimpleNamespace(open=open_data)
            scope={'__file__':str(base/'fetch-reviewed-wheel.py'),'__name__':'SYNTHETIC_FIXTURE_ONLY'}
            with patch.object(sys,'argv',['synthetic',str(destination)]),patch.object(urllib.request,'build_opener',opener),contextlib.redirect_stdout(io.StringIO()):
                try:exec(compile(script,str(HERE/'fetch-reviewed-wheel.py'),'exec'),scope)
                except (AssertionError,ValueError):assert mode!='pass'
                else:assert mode=='pass'
            assert len(calls)==(0 if mode in ('wrong_directory','existing','wrong_host','not_approved') else 1)
            if mode=='existing':assert destination.read_bytes()==b'preserve'
            if mode=='pass':assert destination.read_bytes()==body
            if mode=='oversize':assert destination.stat().st_size==len(body)+1
            checks.append({'fixture':mode,'passed':True})
        assert not base.exists()
    # Execute the actual parent control path; replace all subprocesses and the
    # live assessment store. Both failed fetch reservations must be retained.
    original=json.loads((HERE/'runtime-review.json').read_text())
    for mode in ('two_timeouts','two_hash_failures'):
        with tempfile.TemporaryDirectory(prefix='aeep-SYNTHETIC-fetch-ledger-',dir=ROOT/'.aeep') as temp:
            base=Path(temp);review=copy.deepcopy(original);review['fetch_cache']=str(base/'cache');review['assets']={}
            review_path=base/'runtime-review.json';review_path.write_text(json.dumps(review));digest=sha(review_path)
            (base/'operator-approval.json').write_text(json.dumps({'approved':True,'review_sha256':digest,'SYNTHETIC_FIXTURE_ONLY':True,'authority_granted':False}))
            records=[];current=[100,20,1000.,'0.0']
            class Repo:
                def put(self,kind,identity,value):return content_digest(value)
                def approve_bundle(self,*args):pass
                def current_grant(self,*args):return SimpleNamespace(limits=SimpleNamespace(max_operations=50000,max_elapsed_seconds=604800))
                def reserve(self,request,name,limits,**kwargs):
                    records.append({'operation_id':name,'reserved':limits.max_elapsed_seconds,'completed':False});current[0]+=1;current[2]+=limits.max_elapsed_seconds
                def finish_operation(self,name,elapsed_seconds):
                    record=next(r for r in records if r['operation_id']==name);assert not record['completed'];record['completed']=True;current[2]+=elapsed_seconds-record['reserved']
                def operation_ledger(self,*args):return SimpleNamespace(model_dump=lambda **kwargs:{'operations':records})
            repo=Repo();connection=SimpleNamespace(execute=lambda *args:SimpleNamespace(fetchone=lambda:current.copy()))
            closed=[]
            async def close():closed.append(True)
            router=SimpleNamespace(store=SimpleNamespace(_connection=connection),close=close)
            m=load('synthetic_fetch_parent_'+mode,HERE/'run-bundle.py');m.HERE=base
            # Only the first-party budget helper is needed by this fake parent.
            (base/'review-budget.py').write_bytes((HERE/'review-budget.py').read_bytes())
            m.Router=SimpleNamespace(from_manifest=lambda *args:router);m.AssessmentService=lambda *args:SimpleNamespace(repository=repo)
            m.inspect=lambda *args:{'Id':review['parent_image'],'Config':{}}
            dispatch=[]
            def fake_run(argv,**kwargs):
                if '-I' not in argv:return SimpleNamespace(returncode=1)
                dispatch.append(argv);assert kwargs['timeout']==90 and kwargs['env']['PATH']
                if mode=='two_timeouts':raise subprocess.TimeoutExpired(argv,90)
                return SimpleNamespace(returncode=1,stdout='',stderr='SYNTHETIC hash failure')
            m.subprocess=SimpleNamespace(run=fake_run,check_output=lambda *args,**kwargs:b'SYNTHETIC Docker inventory; no actual call',DEVNULL=subprocess.DEVNULL,STDOUT=subprocess.STDOUT,TimeoutExpired=subprocess.TimeoutExpired)
            with patch.object(sys,'argv',['SYNTHETIC-no-authority',digest]):
                try:asyncio.run(m.main())
                except AssertionError as exc:assert 'Exact data fetch unavailable' in str(exc)
                else:raise AssertionError('Failed synthetic fetch reached build')
            result=json.loads((base/'build-result.json').read_text());ledger=json.loads((base/'build-operation-ledger.json').read_text())
            assert not result['passed'] and result['download_attempts']==2 and result['verified_downloaded_artifacts']==0
            assert len(dispatch)==len(records)==len(ledger['operations'])==2 and all(r['completed'] for r in records)
            assert result['grant_after'][0]-result['grant_before'][0]==2 and closed==[True]
            assert not (base/'image-build.log').exists()
            checks.append({'fixture':mode,'passed':True,'charges_retained':2,'builds':0})
        assert not base.exists()
    value={'passed':True,'first_party_fixtures':checks,'network_docker_installs_models_or_upstream_execution':0,'all_external_dispatch_replaced':True,'synthetic_resources_removed':True,'fixture_is_not_execution_authority_or_benchmark':True}
    (HERE/'fetch-control-check.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))

if __name__=='__main__':main()
