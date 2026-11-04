"""Read pinned Go source/toolchain metadata only; no compiler or module download."""
import hashlib
import json
import re
from pathlib import Path

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
CACHE=ROOT/'.aeep/toolhive-source-preparation-20261104'
SDK=Path('/usr/local/Cellar/go/1.27.1/libexec')


def sha(path):
    with path.open('rb') as source:
        return hashlib.file_digest(source,'sha256').hexdigest()


def escape(value):
    return ''.join('!'+char.lower() if char.isupper() else char for char in value)


def main():
    metadata=json.loads((ROOT/'reports/toolkit-v2/c13/mcp-state-packs-20261104/toolhive-build-preparation.json').read_bytes())
    for item in metadata['source_files']:
        path=Path(item['cache']);assert sha(path)==item['sha256']
    sums={}
    for line in (CACHE/'go.sum').read_text().splitlines():
        module,version,digest=line.split();assert digest.startswith('h1:')
        assert (module,version) not in sums
        sums[(module,version)]=digest
    required=[];inside=False
    for line in (CACHE/'go.mod').read_text().splitlines():
        code=line.split('//',1)[0].strip()
        assert not code.startswith(('replace ','exclude ','toolchain '))
        if code=='require (':inside=True;continue
        if inside and code==')':inside=False;continue
        if inside:
            match=re.fullmatch(r'([A-Za-z0-9._/!~+\-]+) (v\S+)',code)
            assert match,code
            module,version=match.groups();base='https://proxy.golang.org/'+escape(module)+'/@v/'+escape(version)
            required.append({'module':module,'version':version,'archive_go_h1':sums.get((module,version)),
                'module_file_go_h1':sums.get((module,version+'/go.mod')),
                'archive_url':base+'.zip','module_url':base+'.mod','license_reviewed':False,'downloaded':False})
    assert len(required)==343 and len({row['module'] for row in required})==343
    nodes=[];tree=hashlib.sha256(b'aeep.go-sdk-static-tree.v1\0')
    for path in sorted(SDK.rglob('*')):
        relative=path.relative_to(SDK).as_posix()
        if path.is_symlink():
            # Record links without reading anything outside the selected SDK.
            link=path.readlink().as_posix();tree.update(relative.encode()+b'\0link\0'+link.encode()+b'\0')
            nodes.append({'path':relative,'symlink':link});continue
        if not path.is_file():continue
        digest=sha(path);tree.update(relative.encode()+b'\0'+bytes.fromhex(digest))
        nodes.append({'path':relative,'sha256':digest,'bytes':path.stat().st_size})
    assert sha(SDK/'bin/go')==metadata['available_go']['sha256']
    tool_dependencies={str(path):sha(path) for path in sorted((SDK/'pkg/tool/darwin_arm64').iterdir()) if path.is_file() and not path.is_symlink()}
    result={'evidence_kind':'STATIC_SOURCE_AND_TOOLCHAIN_INVENTORY_NOT_BUILD_EVIDENCE',
        'source_revision':metadata['source_revision'],'go_mod_sha256':sha(CACHE/'go.mod'),'go_sum_sha256':sha(CACHE/'go.sum'),
        'required_go':'1.27.0','available_sdk_metadata':(SDK/'VERSION').read_text().splitlines(),
        'declared_modules':required,'declared_count':len(required),
        'declared_archive_hashes_present':sum(row['archive_go_h1'] is not None for row in required),
        'declared_module_file_hashes_present':sum(row['module_file_go_h1'] is not None for row in required),
        'checksum_inventory_zip_versions':sum(not version.endswith('/go.mod') for _,version in sums),
        'complete_native_dependency_graph_verified':False,'licenses_cleared':False,
        'sdk_root':str(SDK),'sdk_tree_sha256':tree.hexdigest(),'sdk_entries':len(nodes),
        'sdk_regular_file_bytes':sum(row.get('bytes',0) for row in nodes),'native_tool_fingerprints':tool_dependencies,
        'compiler_executed':False,'archives_downloaded':0,'credentials_read':False,'models':0,
        'build_environment_proposal':{'GOTOOLCHAIN':'local','GOWORK':'off','GOPROXY':'off','GOSUMDB':'off','CGO_ENABLED':'0','GOTELEMETRY':'off'},
        'next':'Review a finite module/source acquisition and license closure, exact native sandbox and owned ToolHive/MCP lifecycle before requesting build/execution authority. Missing modules must stop offline build, not trigger implicit downloads. Preserve all existing artifacts and user work.'}
    (HERE/'dependency-inventory.json').write_text(json.dumps(result,indent=2)+'\n')
    (HERE/'sdk-source-inventory.json').write_text(json.dumps({'sdk_root':str(SDK),'tree_sha256':tree.hexdigest(),'entries':nodes},indent=2)+'\n')
    print(json.dumps({key:result[key] for key in ['source_revision','declared_count','declared_archive_hashes_present','declared_module_file_hashes_present','sdk_tree_sha256','sdk_entries','compiler_executed','archives_downloaded','complete_native_dependency_graph_verified']}))


if __name__=='__main__':main()
