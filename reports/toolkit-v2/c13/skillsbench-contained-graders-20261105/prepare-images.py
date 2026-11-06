"""Prepare two reproducible protected COPY-only build contexts."""

import hashlib
import json
import shutil
import tarfile
from pathlib import Path

from aeep_toolkit.benchmarks import BenchmarkPack, asset_path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = HERE.parent
WORK = ROOT / '.aeep' / HERE.name
ASSETS = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
PARENT = 'aeep-assessment-runtime:0.8'


def read(path):
    return json.loads(path.read_bytes())


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def inventory(root):
    files = {}
    for path in sorted(root.rglob('*')):
        relative = path.relative_to(root).as_posix()
        if path.is_symlink():
            assert path.resolve(strict=True).is_relative_to(root.resolve()), relative
            files[relative] = {'link': path.readlink().as_posix()}
        elif path.is_file():
            files[relative] = {'sha256': digest(path), 'bytes': path.stat().st_size,
                               'executable': bool(path.stat().st_mode & 0o111)}
        elif not path.is_dir():
            raise ValueError('unexpected build input type')
    return files


def archive_into(archive, destination, top, maximum):
    with tarfile.open(archive, 'r:gz') as src:
        members = src.getmembers()
        assert len(members) < 10_000 and sum(member.size for member in members) <= maximum
        assert all(Path(member.name).parts[0] == top and '..' not in Path(member.name).parts
                   for member in members)
        src.extractall(path=destination.parent, members=members, filter='data')
    (destination.parent / top).rename(destination)


def copy_pinned(source, target, expected):
    assert not source.is_symlink() and digest(source) == expected, source
    shutil.copyfile(source, target)
    assert digest(target) == expected


def prepare():
    verifier = REPORTS / 'skillsbench-protected-carrier-inputs-20261105/carrier-bindings.json'
    contracts = read(REPORTS / 'skillsbench-integration-deadline-20261105/protected-verifier-contracts.json')
    bindings = {item['task_id']: item for item in read(verifier)['drafts']}
    pack_file = REPORTS / 'skillsbench-transport-20261103/task-only-pack.json'
    assert digest(pack_file) == contracts['pack_sha256']
    pack = BenchmarkPack.model_validate_json(pack_file.read_bytes())
    tools = read(HERE / 'toolchain-acquisition.json')
    assert tools['passed']
    archives = {item['filename']: item['sha256'] for item in tools['artifacts']}
    assert all(digest(WORK/name) == value for name, value in archives.items())
    assert shutil.disk_usage(WORK).free >= 52 * 1024**3
    matrix = [
        ('sales', contracts['cases'][0], 'workbook_b64', 300_000,
         REPORTS/'skillsbench-sales-protected-grading-20261105/operation-review.json'),
        ('spring', contracts['cases'][1], 'workspace_b64', 256_000,
         REPORTS/'skillsbench-spring-offline-reference-20261105/operation-review.json'),
    ]
    contexts = []
    for name, contract, output_field, limit, review_path in matrix:
        task_id = contract['task_id']
        review = read(review_path)
        bind = bindings[task_id]
        context = WORK / name
        runtime = context / 'runtime'
        runtime.mkdir(mode=0o700, parents=True)
        config = {
            'task_id': task_id, 'output_field': output_field, 'max_output_bytes': limit,
            'archive_sha256': bind['case_archive_sha256'], 'scratch': '/tmp/aeep-skillsbench-'+name,
            'collected_test_identities': contract['collected_test_identities'],
            'intentional_skips': contract['intentional_skips'],
        }
        original = Path(review['protected']) if name == 'sales' else Path(review['work'])/'protected'
        native = original/'repository_suite_native_capture.py'
        copy_pinned(native, runtime/native.name, review['pins'][str(native)])
        draft = ROOT / '.aeep/skillsbench-protected-carrier-inputs-20261105' / task_id / 'test_outputs.py'
        copy_pinned(draft, runtime/draft.name, bind['adapted_verifier_sha256'])
        shutil.copyfile(HERE/'grade.py', runtime/'grade.py')
        source_tools = Path(review['tools']) if name == 'sales' else Path(review['work'])/'tools'
        tool_records = inventory(source_tools)
        assert all('sha256' in item for item in tool_records.values())
        if name == 'sales':
            assert set(tool_records) == set(review['tool_inventory'])
            assert all(item['sha256'] == review['pins'][str(source_tools/path)] for path,item in tool_records.items())
        else:
            hashes = {path: item['sha256'] for path,item in tool_records.items()}
            tool_hash = hashlib.sha256(json.dumps(hashes,sort_keys=True,separators=(',',':')).encode()).hexdigest()
            assert tool_hash == review['tool_inventory_sha256']
        shutil.copytree(source_tools, runtime/'tools')

        public = [asset for asset in pack.task(task_id).assets if asset.role == 'input']
        if name == 'sales':
            (runtime/'inputs').mkdir()
            assert {Path(asset.path).name for asset in public} == {'income.xlsx','population.pdf'}
            for asset in public:
                copy_pinned(asset_path(ASSETS,asset),runtime/'inputs'/Path(asset.path).name,asset.sha256)
        else:
            prefix = 'tasks/'+task_id+'/environment/workspace/'
            assert all(asset.path.startswith(prefix) for asset in public)
            config['workspace_members'] = sorted(asset.path.removeprefix(prefix) for asset in public)
            settings = Path(review['settings'])
            copy_pinned(settings,runtime/'settings.xml',review['pins'][str(settings)])
            ref = Path(review['work'])
            cache = ref/'cache/reference'
            locked = read(ref/'maven-cache-lock.json')
            assert {path: item['sha256'] for path,item in inventory(cache).items()} == locked
            shutil.copytree(cache,runtime/'cache')
            archive_into(WORK/'OpenJDK21U-jdk_aarch64_linux_hotspot_21.0.2_13.tar.gz',
                         runtime/'java','jdk-21.0.2+13',480*1024**2)
            archive_into(WORK/'apache-maven-3.9.6-bin.tar.gz',
                         runtime/'maven','apache-maven-3.9.6',25*1024**2)
        (runtime/'binding.json').write_text(json.dumps(config,indent=2)+'\n')
        for path in runtime.rglob('*'):
            if not path.is_symlink():
                executable = path.is_dir() or bool(path.stat().st_mode & 0o111)
                path.chmod(0o555 if executable else 0o444)
        runtime.chmod(0o555)
        destination = '/opt/aeep-skillsbench-'+name
        dockerfile = context/'Dockerfile'
        dockerfile.write_text(f'FROM {PARENT}\nCOPY runtime/ {destination}/\n')
        files = inventory(context)
        assert set(context.iterdir()) == {dockerfile,runtime}
        contexts.append({
            'role': name, 'task_id': task_id, 'context': str(context),
            'image_tag': 'aeep-skillsbench-'+name+':protected-20261105',
            'dockerfile_sha256': digest(dockerfile), 'binding_sha256': digest(runtime/'binding.json'),
            'runtime_destination': destination, 'files': files,
            'file_bytes': sum(entry.get('bytes',0) for entry in files.values()),
        })
    with (WORK/'build-inputs.json').open('x') as stream:
        json.dump({'parent':PARENT,'contexts':contexts,'models':0,
                   'verifiers_executed':0,'images_built':0,'comparison':'PAUSED'},stream,indent=2)
        stream.write('\n')


if __name__ == '__main__':
    prepare()
