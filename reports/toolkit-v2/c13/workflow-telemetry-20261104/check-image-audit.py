"""First-party archive fixtures; no Docker or upstream executable runs."""
import gzip,hashlib,importlib.util,io,json,tarfile
from pathlib import Path

HERE=Path(__file__).resolve().parent
loader=importlib.util.spec_from_file_location('bounded_static_image_reader',HERE/'audit-images.py')
module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)


def tar(items):
    out=io.BytesIO()
    with tarfile.open(fileobj=out,mode='w') as archive:
        for name,data,mode in items:
            info=tarfile.TarInfo(name);info.mode=mode;info.uid=info.gid=1001;info.size=len(data)
            archive.addfile(info,io.BytesIO(data))
    return out.getvalue()


base=tar([('app/LICENSE',b'First-party fixture license',0o444),
          ('app/NOTICE',b'Old first-party notice',0o444),('app/web/entrypoint.sh',b'First-party inert executable fixture',0o555)])
upper=tar([('app/.wh.NOTICE',b'',0o000),('app/LICENSE',b'Replacement first-party fixture notice',0o444)])
config={'rootfs':{'diff_ids':['sha256:'+hashlib.sha256(raw).hexdigest() for raw in (base,upper)]},'config':{'User':'1001'}}
config_raw=json.dumps(config).encode();config_sha=hashlib.sha256(config_raw).hexdigest()
manifest=[{'Config':'blobs/sha256/'+config_sha,'Layers':['layer-base','layer-upper']}]
outer=tar([('layer-upper',gzip.compress(upper),0o444),('layer-base',base,0o444),
           ('blobs/sha256/'+config_sha,config_raw,0o444),('manifest.json',json.dumps(manifest).encode(),0o444)])
with tarfile.open(fileobj=io.BytesIO(outer),mode='r|*') as archive:first=module.first_pass(archive,'sha256:'+config_sha)
with tarfile.open(fileobj=io.BytesIO(outer),mode='r|*') as archive:result=module.second_pass(archive,first)
assert 'app/NOTICE' not in result['final_entries']
assert result['notice_data']['app/LICENSE']['text']=='Replacement first-party fixture notice'
assert result['final_entries']['app/web/entrypoint.sh']['mode']=='0o555'
assert 'app/web/entrypoint.sh' not in result['notice_data']
bad=json.loads(json.dumps(first));bad['config']['rootfs']['diff_ids'][0]='sha256:'+'0'*64
try:
    with tarfile.open(fileobj=io.BytesIO(outer),mode='r|*') as archive:module.second_pass(archive,bad)
except AssertionError:pass
else:raise AssertionError('Corrupt layer identity accepted')
value={'passed':True,'evidence_kind':'FIRST_PARTY_ARCHIVE_FIXTURES_NOT_UPSTREAM',
       'checks':['exact config digest','mixed gzip/plain layer digests','manifest order differs from archive order',
                 'whiteout semantics','replacement notice','executable mode retained without extraction','bad diffID rejected'],
       'docker_executed':False,'guest_executed':False}
(HERE/'image-audit-controls.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
