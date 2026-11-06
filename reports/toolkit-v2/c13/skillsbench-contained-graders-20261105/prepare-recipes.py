"""Bind private reference outputs and immutable grader commands to the two exact tasks."""

import base64
import hashlib
import io
import json
import stat
import zipfile
from pathlib import Path

from aeep.assessment.models import RecipeDefinition, content_digest
from aeep.models import ExecutorSpec
from aeep.registry import validate_json
from aeep_toolkit.benchmarks import BenchmarkPack, task_input

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
REPORTS = HERE.parent
WORK = ROOT / '.aeep' / HERE.name
ASSETS = ROOT / '.aeep/skillsbench-stack-9a1f4dd5'

REFERENCE_PROGRAM = '''
import hashlib
import json
import sys

data = json.load(sys.stdin)
inputs = data.get("inputs")
assert isinstance(inputs, list) and len(inputs) == 1
archive, task_id, field, *encoded = sys.argv[1:]
assert inputs[0]["task_archive_sha256"] == archive and inputs[0]["task_id"] == task_id
output = "".join(encoded)
assert hashlib.sha256(output.encode()).hexdigest() == data_sha256
print(json.dumps({"outputs": [{field: output}]}))
'''


def read(path):
    return json.loads(path.read_bytes())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
    path.chmod(0o400)


def archive(directory, members, reviewed=None):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as compressed:
        for name in sorted(members):
            path = directory / name
            assert path.is_file() and not path.is_symlink()
            raw = path.read_bytes()
            if reviewed is not None:
                assert sha(raw) == reviewed[name]['sha256'] and len(raw) == reviewed[name]['bytes']
            entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            entry.external_attr = (stat.S_IFREG | 0o444) << 16
            entry.compress_type = zipfile.ZIP_DEFLATED
            compressed.writestr(entry, raw)
    return output.getvalue()


def outputs(role, binding):
    if role == 'sales':
        report = REPORTS / 'skillsbench-sales-protected-grading-20261105'
        review = read(report / 'operation-review.json')
        work = Path(review['work'])
        basename = 'demographic_analysis.xlsx'
        reference = (work/'reference'/basename).read_bytes()
        fault = (work/'wrong-workbook'/basename).read_bytes()
        assert sha(reference) == review['artifact_sha256']
        assert sha(fault) == review['pins'][str(work/'wrong-workbook'/basename)]
    else:
        report = REPORTS / 'skillsbench-spring-offline-reference-20261105'
        review = read(report / 'operation-review.json')
        work = Path(review['work'])
        names = binding['workspace_members']
        digests = {row['path']: row for row in read(report/'execution/workspace-digests.json')}
        assert set(digests) == set(names)
        reference = archive(work/'reference', names, digests)
        legacy_file = 'src/main/java/com/example/userservice/dto/CreateUserRequest.java'
        namespace = b'import jakarta.validation.constraints.Email;'
        for name in names:
            expected = (work/'reference'/name).read_bytes()
            if name == legacy_file:
                assert expected.count(namespace) == 1
                expected = expected.replace(namespace, b'import javax.validation.constraints.Email;')
            assert (work/'legacy-namespace'/name).read_bytes() == expected
        fault = archive(work/'legacy-namespace', names)
    assert 0 < len(reference) <= binding['max_output_bytes'] and 0 < len(fault) <= binding['max_output_bytes']
    return reference, fault


def recipe_for(role, binding, value, reference, fault):
    task_id = binding['task_id']
    capability = 'assessment.skillsbench.' + role + '@1'
    field = binding['output_field']
    destination = '/opt/aeep-skillsbench-' + role

    def program(name, argv, seconds):
        return ExecutorSpec(id='skillsbench.'+role+'.'+name, capability=capability, kind='command',
            description='Protected SkillsBench '+name, config={
                'argv':argv, 'argv_literal':True, 'stdin_json':True, 'timeout_seconds':seconds,
                'max_output_bytes':1_000_000, 'output':{'type':'json'},
            })

    answer = base64.b64encode(reference).decode('ascii')
    chunks = [answer[start:start+48000] for start in range(0,len(answer),48000)]
    reference_program = 'data_sha256 = ' + repr(sha(answer.encode())) + '\n' + REFERENCE_PROGRAM
    properties = {name: {'const': item} for name, item in value.items() if name != 'task_archive_b64'}
    properties['task_archive_b64'] = {'type':'string','maxLength':400000}
    truth = {'task_archive_sha256':binding['archive_sha256']}
    truth_schema = {'type':'object','additionalProperties':False,'required':list(truth),
                    'properties':{name:{'const':item} for name,item in truth.items()}}
    return RecipeDefinition.model_validate({
        'schema_version':'assessment.recipe.v2','recipe_id':'skillsbench-'+role+'-protected-v1',
        'capability':capability,'description':'One pinned original SkillsBench task with protected binary upstream grading.',
        'input_schema':{'type':'object','additionalProperties':False,'required':sorted(properties),'properties':properties},
        'output_schema':{'type':'object','additionalProperties':False,'required':[field],
                         'properties':{field:{'type':'string','minLength':1,
                                              'maxLength':4*((binding['max_output_bytes']+2)//3)}}},
        'generator':'contained_json:1','grader':'contained_json:1','extractor':'structural_json:1',
        'generator_config':{'official_reproduction':False,'integration_only':True},
        'dependencies':{'benchmark_pack':value['benchmark_pack_sha256'],
                        'protected_binding':content_digest(binding),'reference_output':sha(reference)},
        'variations':[task_id],
        'exclusions':['formal holdout','automatic admission','candidate or selection usefulness'],
        'extension':{
            'schema_version':'assessment.recipe-extension.v6',
            'generator':program('generator',['python3','-I','-B','-c','raise SystemExit(2)'],30),
            'reference':program('reference',['python3','-I','-B','-c',reference_program,
                 binding['archive_sha256'],task_id,field,*chunks],30),
            'grader':program('grader',['python3','-I','-B',destination+'/grade.py'],20 if role=='sales' else 60),
            'independent_fixtures':[],'transformed_fixtures':[],
            'fault_outputs':[{field:base64.b64encode(fault).decode('ascii')}],
            'feature_rules':{'task':{'path':'/task_id','operation':'enum','values':[task_id]}},
            'variation_features':{task_id:{'task':task_id}},'template_families':['skillsbench:'+task_id],
            'truth_schema':truth_schema,'failure_codes':['output_contract','upstream_rejected'],
        },
    })


def prepare():
    private = WORK/'recipes'
    private.mkdir(mode=0o700, exist_ok=True)
    assert not private.is_symlink() and stat.S_IMODE(private.stat().st_mode) == 0o700
    pack_path = REPORTS / 'skillsbench-transport-20261103/task-only-pack.json'
    pack = BenchmarkPack.model_validate_json(pack_path.read_bytes())
    rows = []
    for role in ('sales','spring'):
        binding = read(WORK/role/'runtime/binding.json')
        value = task_input(pack, ASSETS, binding['task_id'])
        assert value['task_archive_sha256'] == binding['archive_sha256']
        good, bad = outputs(role, binding)
        recipe = recipe_for(role, binding, value, good, bad)
        validate_json(value, recipe.input_schema, label='original selected task')
        path = private/(role+'-recipe.json')
        serialized = recipe.model_dump(mode='json')
        if path.exists():
            assert not path.is_symlink() and read(path) == serialized
        else:
            save(path, serialized)
        assert path.stat().st_size < 1_000_000
        rows.append(dict(role=role, recipe_id=recipe.recipe_id, recipe_digest=content_digest(recipe),
                         file_sha256=sha(path.read_bytes()), file_bytes=path.stat().st_size,
                         task_input_digest=content_digest(value), reference_sha256=sha(good),
                         fault_sha256=sha(bad), protected_reference_transient_in_execution=True))
    save(HERE/'recipe-bindings.json',dict(ordinary_cli_preparation='OPEN', private_recipe_paths=str(private),
                                         records=rows, provider_disclosure_authorized=False,model_turns=0))


if __name__ == '__main__':
    prepare()
