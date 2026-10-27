"""Read exact official wheel metadata/licenses; no install or downloaded import."""
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
assert shutil.disk_usage(ROOT).free>50*1024**3+100*1024**2
spec=importlib.util.spec_from_file_location('existing_official_wheel_reader',HERE.parent/'repository-replacement-runtime-20261022/prepare-runtime-wheels.py');reader=importlib.util.module_from_spec(spec);spec.loader.exec_module(reader)
reader.HERE=HERE;reader.CACHE=ROOT/'.aeep/repository-large-runtime-wheels-20261027';reader.CACHE.mkdir(exist_ok=False)
# These are finite optional grader pins, not a request for latest packages or
# a change to toolkit core requirements. Existing image requirements stay distinct.
pins={'docstring-parser':'0.17.0','rich-rst':'1.3.2','docutils':'0.22.2','wrapt':'1.17.3','hypothesis':'6.142.4','sortedcontainers':'2.4.0'}
rows=[]
for project,version in pins.items():
    try:rows.append(reader.prepare((project,version)))
    except Exception as exc:rows.append({'project':project,'version':version,'error_type':type(exc).__name__,'error':str(exc)[:200]})
value={'pins':rows,'downloaded_wheel_bytes':sum(r.get('size_bytes',0) for r in rows),'installed':False,'downloaded_code_imported':False,'runtime_compatibility':'UNVERIFIED; source/plugins,effective image and exact execution require review','entire_inherited_inventory_or_closure_claimed':False}
(HERE/'runtime-wheel-read.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'pins':[(r['project'],r.get('error_type','metadata_read')) for r in rows],'bytes':value['downloaded_wheel_bytes'],'installed':False}))
