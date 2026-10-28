"""Read bounded official wheel data and licenses;never install or import it."""
import importlib.util
import json
from pathlib import Path
import shutil
import urllib.request

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
assert shutil.disk_usage(ROOT).free>50*1024**3+100*1024**2
spec=importlib.util.spec_from_file_location('existing_official_wheel_reader',HERE.parent/'repository-replacement-runtime-20261022/prepare-runtime-wheels.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
reader.HERE=HERE;reader.CACHE=ROOT/'.aeep/repository-multifile-runtime-wheels-20261027';reader.CACHE.mkdir(exist_ok=False)
opener=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def bounded_read(url,ceiling):
    assert url.startswith(('https://pypi.org/','https://files.pythonhosted.org/'))
    # Each reviewed data artifact is kept below8MiB;no source builds or installer.
    ceiling=min(ceiling,8*1024**2)
    with opener.open(urllib.request.Request(url,headers={'User-Agent':'AEEP-bounded-wheel-data-review/1'}),timeout=45) as response:
        assert response.geturl().startswith(('https://pypi.org/','https://files.pythonhosted.org/'));data=response.read(ceiling+1)
    assert len(data)<=ceiling
    return data
reader.read=bounded_read
pins={'python-can':'4.6.1','canmatrix':'1.2','asn1crypto':'1.5.1','cbor2':'5.6.5','pyOpenSSL':'25.3.0','lxml':'6.0.2','docformatter':'1.7.5','untokenize':'0.1.1','toposort':'1.10'}
rows=[]
for project,version in pins.items():
    try:rows.append(reader.prepare((project,version)))
    except Exception as exc:rows.append({'project':project,'version':version,'error_type':type(exc).__name__,'error':str(exc)[:200]})
value={'pins':rows,'downloaded_wheel_bytes':sum(r.get('size_bytes',0) for r in rows),'installed':False,'downloaded_code_imported':False,'maximum_single_data_read_bytes':8*1024**2,'scope':'Optional controlled grader runtime only;no core dependencies or subject-project installers. No claim that source references run until exact new approval and execution.','runtime_compatibility':'UNVERIFIED','entire_inherited_inventory_claimed':False}
(HERE/'runtime-wheel-read.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'pins':[(r['project'],r.get('error_type','metadata_read')) for r in rows],'bytes':value['downloaded_wheel_bytes'],'installed':False}))
