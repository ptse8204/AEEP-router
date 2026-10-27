"""Check only the selected optional dependency edges; do not infer image inventory."""
import hashlib
import json
from pathlib import Path
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent
j=json.loads((HERE/'runtime-wheel-read.json').read_text());assert len(j['pins'])==6 and all('error_type' not in p for p in j['pins'])
versions={canonicalize_name(p['project']):p['version'] for p in j['pins']}
# These are individually bound parent observations, not an inherited manifest
# treated as proof of installation. New probes must verify the effective image.
versions.update({'attrs':'25.4.0','rich':'14.2.0','pytest':'8.3.5'})
marker={'implementation_name':'cpython','implementation_version':'3.13.15','os_name':'posix','platform_machine':'aarch64','platform_python_implementation':'CPython','platform_release':'','platform_system':'Linux','platform_version':'','python_full_version':'3.13.15','python_version':'3.13','sys_platform':'linux'}
checks=[]
for p in j['pins']:
    raw=ROOT/p['private_cache'];assert hashlib.sha256(raw.read_bytes()).hexdigest()==p['sha256']
    for license in p['licenses']:assert hashlib.sha256((ROOT/license['retained']).read_bytes()).hexdigest()==license['sha256']
    extras={'','pytest'} if p['project']=='hypothesis' else {''}
    for line in p['requires_dist']:
        r=Requirement(line)
        if r.marker and not any(r.marker.evaluate({**marker,'extra':e}) for e in extras):continue
        selected=versions.get(canonicalize_name(r.name));assert selected is not None and Version(selected) in r.specifier,(p['project'],line,selected)
        checks.append({'project':p['project'],'requires':line,'selected':selected,'satisfied':True,'location_requires_fresh_probe':True})
value={**j,'selected_added_requirements_closed':True,'active_added_requirement_checks':checks,'target_marker_environment':marker,'parent_required_versions':{k:versions[k] for k in ('attrs','rich','pytest')},'entire_inherited_inventory_or_closure_claimed':False,'runtime_compatibility':'UNVERIFIED; exact build and effective image/portable path probes still required'}
(HERE/'runtime-support-review.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'added_pins':6,'active_edges':len(checks),'bytes':value['downloaded_wheel_bytes'],'installed':False,'whole_image_inventory_claimed':False}))
