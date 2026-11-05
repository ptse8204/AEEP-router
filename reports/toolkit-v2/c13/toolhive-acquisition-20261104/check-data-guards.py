"""First-attempt first-party malicious-data fixtures; no network or Go execution."""
import importlib.util,json,stat,tempfile,urllib.request,zipfile
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('pinned_artifact_data',HERE/'acquire.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
checks=[]
for value in ('../escape','/absolute','a/../../escape','a\\escape','a\nfile'):
    try:m.safe(value)
    except ValueError:pass
    else:raise AssertionError('unsafe name accepted')
checks.append('absolute/traversal/control-character archive paths rejected')
with tempfile.TemporaryDirectory(prefix='aeep-toolhive-data-control-') as directory:
    root=Path(directory);notices=root/'licenses';notices.mkdir();budget=m.Budget(root,1024,1024)
    for number,name,mode in [(1,'example.invalid/p@v1.0.0/../escape',0),(2,'wrong.module@v1.0.0/LICENSE',0),(3,'example.invalid/p@v1.0.0/LICENSE',stat.S_IFLNK|0o777)]:
        path=root/(str(number)+'.zip')
        with zipfile.ZipFile(path,'w') as archive:
            item=zipfile.ZipInfo(name);item.external_attr=mode<<16;archive.writestr(item,b'FIRST_PARTY_ONLY')
        try:m.verify_zip(path,{'module':'example.invalid/p','version':'v1.0.0','go_h1':'h1:wrong'},budget,notices)
        except (AssertionError,ValueError):pass
        else:raise AssertionError('untrusted zip accepted')
    assert not list(notices.iterdir()) and not (root/'escape').exists()
    checks.append('traversal/foreign module/symlink ZIPs cannot create license records or outside files')
    budget=m.Budget(root,1,1)
    try:budget.check(2)
    except RuntimeError:pass
    else:raise AssertionError('quota was ignored')
    assert budget.stop.is_set()
    try:budget.check()
    except RuntimeError as error:assert str(error)=='SharedStop'
    else:raise AssertionError('dispatch continued after common stop')
    checks.append('quota breach sets shared stop before subsequent fetch')
redirect=m.Redirect();request=urllib.request.Request('https://proxy.golang.org/')
for address in ('http://proxy.golang.org/file','https://unreviewed.invalid/file','https://user:password@proxy.golang.org/file'):
    try:redirect.redirect_request(request,None,302,'',{},address)
    except ValueError:pass
    else:raise AssertionError('unreviewed redirect accepted')
checks.append('nonHTTPS/foreign/auth-bearing redirects rejected')
result={'passed':True,'evidence_kind':'NEW_FIRST_PARTY_DATA_GUARDS_NOT_UPSTREAM_EXECUTION','checks':checks,'network':False,'go_executed':False,'models':0}
(HERE/'data-controls.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
