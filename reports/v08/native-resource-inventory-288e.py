"""Bounded read-only resource inventory; no credentials or payload contents read."""
import asyncio,hashlib,importlib.metadata,json,os,time,tomllib,zipfile
from collections import defaultdict
from pathlib import Path
from aeep.assessment.verification import verification_source_digest
from aeep.router import Router
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/v08/native-resource-inventory-result-288e.json'
async def main():
    assert not OUT.exists();started=time.perf_counter();groups=defaultdict(lambda:{'files':0,'logical_bytes':0,'allocated_bytes':0});skipped=0
    for parent,dirs,files in os.walk(ROOT/'.aeep',followlinks=False):
        dirs[:]=[name for name in dirs if not Path(parent,name).is_symlink() and name not in {'credentials','auth','codex-home'}]
        for name in files:
            if time.perf_counter()-started>30:raise TimeoutError('inventory bound')
            p=Path(parent,name)
            if p.is_symlink() or name in {'auth.json','credentials.json'}:skipped+=1;continue
            stat=p.stat();key=p.relative_to(ROOT/'.aeep').parts[0];g=groups[key];g['files']+=1;g['logical_bytes']+=stat.st_size;g['allocated_bytes']+=stat.st_blocks*512
    distributions={};seen=set();queue=[x.split('>=')[0] for x in tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['dependencies']]
    from packaging.requirements import Requirement
    while queue:
        name=queue.pop()
        key=name.lower().replace('_','-')
        if key in seen:continue
        seen.add(key)
        try:dist=importlib.metadata.distribution(name)
        except importlib.metadata.PackageNotFoundError:distributions[key]={'status':'unavailable'};continue
        paths=[dist.locate_file(p) for p in dist.files or ()];paths=[p for p in paths if p.is_file() and not p.is_symlink()]
        distributions[key]={'version':dist.version,'logical_bytes':sum(p.stat().st_size for p in paths),'allocated_bytes':sum(p.stat().st_blocks*512 for p in paths),'files':len(paths),'ownership':'already-installed/shared; not an observed AEEP install delta'}
        for value in dist.requires or ():
            dep=Requirement(value)
            if dep.marker is None or dep.marker.evaluate({'extra':''}):queue.append(dep.name)
    wheel=ROOT/'dist/aeep_agent_router-0.8.0-py3-none-any.whl'
    with zipfile.ZipFile(wheel) as archive:wheel_inventory={'compressed_bytes':wheel.stat().st_size,'uncompressed_member_bytes':sum(p.file_size for p in archive.infolist()),'members':len(archive.infolist()),'sha256':hashlib.sha256(wheel.read_bytes()).hexdigest(),'incremental_install_delta':'unknown; no installation performed'}
    router=Router.from_manifest(ROOT/'.aeep/live-review-v3/aeep.json')
    try:
        ledger=[dict(zip(('grant','operations','model_turns','elapsed_seconds','cash_usd'),row)) for row in router.store._connection.execute('SELECT id,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants')]
        tables={row[0] for row in router.store._connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        counts={name:router.store._connection.execute('SELECT COUNT(*) FROM "'+name+'"').fetchone()[0] for name in ('execution_receipts','execution_attempts','assessment_operations','decisions') if name in tables}
    finally:await router.close()
    value={'source_digest':verification_source_digest(ROOT),'groups':dict(sorted(groups.items())),'skipped_symlinks_or_credential_names':skipped,'installed_runtime_dependency_inventory':distributions,'wheel_inventory':wheel_inventory,'ledger':ledger,'main_ledger_table_counts':counts,'inventory_seconds':time.perf_counter()-started,'logical_vs_allocated':'Allocated bytes include filesystem effects; shared package files may overlap. Closed historical lab storage is not production install overhead.','retention_growth':'Finite local samples measure lifecycle retention and recovery WAL/close growth; indefinite or model-driven growth unknown. No extrapolation or automated deletion.','auth_state_read':False,'model_turns':0,'source_or_configuration_mutation':False,'resource_gate_complete':False,'release_ready':False}
    OUT.write_text(json.dumps(value,indent=2)+'\n');print(json.dumps({'groups':value['groups'],'wheel_inventory':wheel_inventory,'ledger':ledger,'inventory_seconds':value['inventory_seconds']}))
asyncio.run(main())
