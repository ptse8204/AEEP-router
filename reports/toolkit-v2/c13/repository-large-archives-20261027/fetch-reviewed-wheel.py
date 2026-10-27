"""Fetch only the approved exact binary as data; never import or install it."""
import hashlib
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

HERE=Path(__file__).resolve().parent
review=json.loads((HERE/'runtime-review.json').read_text());approval=json.loads((HERE/'operator-approval.json').read_text())
assert approval['approved'] and approval['review_sha256']==hashlib.sha256((HERE/'runtime-review.json').read_bytes()).hexdigest()
plan=review['pending_wheel_fetch'];destination=Path(sys.argv[1]);assert destination.parent.resolve()==Path(review['fetch_cache']).resolve()
assert destination.name in ('attempt-1.partial','attempt-2.partial') and not destination.exists()
assert urllib.parse.urlparse(plan['source_url']).hostname=='files.pythonhosted.org'
class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('Wheel download redirects are not authorized')
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
count=0;digest=hashlib.sha256()
with opener.open(urllib.request.Request(plan['source_url'],headers={'User-Agent':'AEEP-reviewed-artifact-fetch/1'}),timeout=30) as stream,destination.open('xb') as output:
    while True:
        chunk=stream.read(min(1024*1024,plan['size_bytes']+1-count))
        if not chunk:break
        output.write(chunk);digest.update(chunk);count+=len(chunk)
        if count>plan['size_bytes']:raise ValueError('Wheel download exceeds approved artifact size')
assert count==plan['size_bytes'] and digest.hexdigest()==plan['sha256']
print(json.dumps({'verified':True,'bytes':count,'sha256':digest.hexdigest(),'path':str(destination),'imported_or_installed':False}))
