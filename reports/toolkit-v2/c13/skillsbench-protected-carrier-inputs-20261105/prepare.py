"""Stage exact path-only and Maven-launch adaptations without running either verifier."""

import ast
import hashlib
import json
from pathlib import Path

from aeep.assessment.models import content_digest
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = HERE.parent
ASSETS = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'
PRIVATE = ROOT / '.aeep/skillsbench-protected-carrier-inputs-20261105'
PACK_FILE = REPORTS / 'skillsbench-transport-20261103/task-only-pack.json'
CONTRACTS = REPORTS / 'skillsbench-integration-deadline-20261105/protected-verifier-contracts.json'


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def adapt(source: bytes, substitutions: dict[str, str]) -> bytes:
    result = source
    for old, new in substitutions.items():
        before, after = old.encode(), new.encode()
        if result.count(before) != 1 or after in result:
            raise ValueError('unexpected verifier layout')
        result = result.replace(before, after, 1)
    restored = result
    for old, new in reversed(substitutions.items()):
        restored = restored.replace(new.encode(), old.encode(), 1)
    if restored != source:
        raise ValueError('verifier changed outside the reviewed adaptation')
    tree = ast.parse(result)
    original_asserts = [ast.dump(node) for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Assert)]
    staged_asserts = [ast.dump(node) for node in ast.walk(tree) if isinstance(node, ast.Assert)]
    if original_asserts != staged_asserts:
        raise ValueError('upstream verifier assertions changed')
    compile(tree, 'test_outputs.py', 'exec')
    return result


def prepare() -> None:
    contracts = json.loads(CONTRACTS.read_bytes())
    pack_bytes = PACK_FILE.read_bytes()
    if digest(pack_bytes) != contracts['pack_sha256']:
        raise ValueError('task pack changed')
    pack = BenchmarkPack.model_validate_json(pack_bytes)
    pack_digest = content_digest(pack.model_dump(mode='json'))
    sales_scratch = '/tmp/aeep-skillsbench-sales'
    spring_scratch = '/tmp/aeep-skillsbench-spring'
    spring_runtime = '/opt/aeep-skillsbench-spring'
    maven = [
        spring_runtime + '/maven/bin/mvn', '--offline',
        '--settings', spring_runtime + '/settings.xml',
        '-Dmaven.repo.local=' + spring_runtime + '/cache', '-Dstyle.color=never',
    ]
    sales_paths = {
        json.dumps('/root/' + name): json.dumps(sales_scratch + '/' + name)
        for name in ('demographic_analysis.xlsx', 'population.pdf', 'income.xlsx')
    }
    shell = 'source /root/.sdkman/bin/sdkman-init.sh && sdk use java 21.0.2-tem && mvn '
    spring_launch = {
        json.dumps(['bash', '-c', shell + ' '.join(goal)]): json.dumps([*maven, *goal])
        for goal in (['clean', 'compile', '-q'], ['test', '-q'])
    }
    substitutions = {
        'sales-pivot-analysis': sales_paths,
        'spring-boot-jakarta-migration': {
            json.dumps('/workspace'): json.dumps(spring_scratch + '/workspace'),
            **spring_launch,
        },
    }
    drafts = []
    for contract in contracts['cases']:
        task = contract['task_id']
        relative = f'tasks/{task}/verifier/test_outputs.py'
        source = (ASSETS / relative).read_bytes()
        if digest(source) != contract['verifier_assets'][relative]:
            raise ValueError('original verifier differs from the passing reference pin')
        adapted = adapt(source, substitutions[task])
        task_data = task_input(pack, ASSETS, task)
        if task_data['benchmark_pack_sha256'] != pack_digest:
            raise ValueError('canonical task and pack digests differ')
        record = {
            'task_id': task,
            'pack_content_digest': pack_digest,
            'case_input_content_digest': content_digest(task_data),
            'case_archive_sha256': task_data['task_archive_sha256'],
            'original_verifier_sha256': digest(source),
            'adapted_verifier_sha256': digest(adapted),
            'adapted_verifier_bytes': len(adapted),
            'substitutions': substitutions[task],
            'test_identities': len(contract['collected_test_identities']),
            'intentional_skips': len(contract['intentional_skips']),
            'original_assertions_preserved': True,
        }
        drafts.append((task, adapted, record))
    PRIVATE.mkdir(mode=0o700)
    for task, adapted, _ in drafts:
        directory = PRIVATE / task
        directory.mkdir(mode=0o700)
        path = directory / 'test_outputs.py'
        with path.open('xb') as stream:
            stream.write(adapted)
        path.chmod(0o400)
    result = {
        'scope': 'Private deterministic carrier preparation with compile-only verification',
        'source_revision': pack.source.revision,
        'pack_file_sha256': digest(pack_bytes),
        'reference_contracts_sha256': digest(CONTRACTS.read_bytes()),
        'drafts': [record for _, _, record in drafts],
        'spring_required_java_home': spring_runtime + '/java',
        'runtime_built': False,
        'verifiers_executed': 0,
        'provider_disclosure_authorized': False,
        'model_turns': 0,
        'comparisons': 'PAUSED',
    }
    with (HERE / 'carrier-bindings.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')


if __name__ == '__main__':
    prepare()
