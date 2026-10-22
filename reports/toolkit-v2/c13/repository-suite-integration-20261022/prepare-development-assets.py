"""Prepare pinned development data only: no imports or execution of external code."""
import asyncio
import base64
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import (RepositorySuiteCase, SuiteAsset, SuiteInput, SuiteTruth,
    archive_files, grade_suite_output, pack_files, patch_artifact, repository_suite_recipe)
from aeep.assessment.repository_tasks import RepositoryPatch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
CACHE = ROOT / '.aeep/repository-cohort-20261022'
OUTPUT = ROOT / '.aeep/repository-suite-integration-20261022-v2'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def asset(path):
    return SuiteAsset(path=str(path.resolve()), sha256=sha(path.read_bytes()), size_bytes=path.stat().st_size)


def normalize(data):
    files, prefix, total = {}, None, 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for member in archive:
            path = PurePosixPath(member.name)
            assert not path.is_absolute() and '..' not in path.parts
            prefix = prefix or path.parts[0]
            assert path.parts[0] == prefix
            if member.isdir():
                continue
            assert member.isfile() and len(path.parts) >= 2
            name = PurePosixPath(*path.parts[1:]).as_posix()
            assert name not in files and len(files) < 1000
            total += member.size
            assert total <= 4_000_000
            files[name] = archive.extractfile(member).read()
    normalized = pack_files(files)
    assert archive_files(normalized) == files
    return files, normalized


def apply(directory, patch, ceiling):
    # git apply is a data operation. Do not let Git discover user configuration
    # or accept a patch that creates links or aliases paths outside this tree.
    for line in patch.splitlines():
        if line.startswith(('new file mode', 'old mode', 'new mode', 'index ')):
            assert '120000' not in line and '160000' not in line
        if line.startswith('diff --git '):
            parts = line.split()
            assert len(parts) == 4
            for name in parts[2:]:
                assert name.startswith(('a/', 'b/'))
                path = PurePosixPath(name[2:])
                assert str(path) == name[2:] and not path.is_absolute() and '..' not in path.parts
    env = {'PATH': '/usr/bin:/bin', 'GIT_CEILING_DIRECTORIES': str(ceiling),
           'GIT_CONFIG_NOSYSTEM': '1', 'GIT_CONFIG_GLOBAL': '/dev/null'}
    assert subprocess.run(['/usr/bin/git', 'rev-parse', '--show-toplevel'], cwd=directory,
                          env=env, capture_output=True).returncode != 0
    for options in (['--check'], []):
        subprocess.run(['/usr/bin/git', 'apply', '--no-index', *options, '-'], cwd=directory,
                       env=env, input=patch.encode(), check=True)


async def main():
    assert shutil.disk_usage(ROOT).free > 50 * 1024**3
    OUTPUT.mkdir(exist_ok=False)
    public, private = OUTPUT / 'public', OUTPUT / 'protected'
    public.mkdir()
    private.mkdir()
    wheel_review = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/wheel-source-review.json').read_text())
    base_wheels = [asset(CACHE / 'wheels' / record['filename']) for record in wheel_review['pins']]
    for actual, reviewed in zip(base_wheels, wheel_review['pins'], strict=True):
        assert actual.sha256 == reviewed['sha256']
    extra = {record['project']: asset(ROOT / record['private_cache']) for record in json.loads((HERE / 'runtime-wheel-review.json').read_text())}
    sources = json.loads((HERE / 'development-source-review.json').read_text())
    loguru_review = json.loads((ROOT / 'reports/toolkit-v2/c13/repository-cohort-20261022/development-source-review.json').read_text())
    entries = [dict(identity='delgan__loguru-1451', row=CACHE / 'development-task.json',
                    archive=CACHE / 'development-repo.tar.gz', review=loguru_review, prefix='loguru/', extras=[])]
    for source in sources:
        click = source['repository'] == 'pallets/click'
        folder = ROOT / source['private_cache']
        entries.append(dict(identity=source['instance_id'], row=folder / 'row.json', archive=folder / 'source.tar.gz',
            review=source, prefix='src/click/' if click else 'src/marshmallow/',
            extras=['click'] if click else ['marshmallow', 'simplejson']))
    cases, summary = [], []
    for entry in entries:
        row, review = json.loads(entry['row'].read_text()), entry['review']
        raw = entry['archive'].read_bytes()
        assert sha(raw) == review['archive_sha256'] and row['base_commit'] == review['base_commit']
        files, normalized = normalize(raw)
        source_path = public / (sha(normalized) + '.tar.gz')
        with source_path.open('xb') as stream:
            stream.write(normalized)
        editable = sorted(name for name in files if name.startswith(entry['prefix']) and name.endswith('.py'))
        text = row['problem_statement'] + ('\n\n' + row['interface'] if row.get('interface') else '')
        text += '\n\nAEEP scope: repair behavior within the listed editable Python source. Documentation, release notes and packaging changes are outside this source-only adaptation.'
        changes = {}
        with tempfile.TemporaryDirectory(prefix='aeep-suite-data-') as temporary:
            directory = Path(temporary).resolve()
            for name, data in files.items():
                path = directory / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            apply(directory, row['test_patch'], directory.parent)
            after_test = {path.relative_to(directory).as_posix(): path.read_bytes()
                          for path in directory.rglob('*') if path.is_file()}
            assert set(files) <= after_test.keys()
            overlay = {name: data for name, data in after_test.items() if files.get(name) != data}
            assert overlay and all(name.startswith('tests/') for name in overlay)
            apply(directory, row['patch'], directory.parent)
            after_fix = {path.relative_to(directory).as_posix(): path.read_bytes()
                         for path in directory.rglob('*') if path.is_file()}
            assert after_test.keys() == after_fix.keys()
            changed_names = {name for name, data in after_fix.items() if after_test[name] != data}
            omitted = sorted(changed_names - set(editable))
            assert all(name.endswith(('.md', '.rst', '.txt')) for name in omitted)
            changes = {name: after_fix[name].decode('utf-8') for name in changed_names if name in editable}
            assert changes
        test_path = private / (entry['identity'] + '-tests.tar.gz')
        test_path.write_bytes(pack_files(overlay))
        value = SuiteInput(task_id=entry['identity'], task=text,
            family='multi-file-repair' if len(changes) > 1 else 'single-file-repair',
            source_sha256=sha(normalized), editable_paths=editable)
        binding = content_digest(value)
        reference = patch_artifact(RepositoryPatch(base_sha256=binding, files=changes))
        reference_path = private / (entry['identity'] + '-reference.json')
        reference_path.write_text(json.dumps(reference, separators=(',', ':')))
        fault = dict(changes)
        first = sorted(fault)[0]
        fault[first] += '\nraise RuntimeError("AEEP development semantic fault")\n'
        names = row['FAIL_TO_PASS'] + row['PASS_TO_PASS']
        truth = SuiteTruth(input_sha256=binding, source=asset(source_path), tests=asset(test_path),
            wheels=[*base_wheels, *(extra[name] for name in entry['extras'])], python='3.13', pytest='8.3.5',
            test_paths=sorted({name.split('::')[0] for name in names}),
            fail_to_pass=row['FAIL_TO_PASS'], pass_to_pass=row['PASS_TO_PASS'])
        case = RepositorySuiteCase(input=value, truth=truth, reference=asset(reference_path),
            fault_outputs=[patch_artifact(RepositoryPatch(base_sha256=binding, files=fault))],
            source_repository='https://github.com/' + row['repo'], source_revision=row['base_commit'],
            independent_case_id=row['instance_id'], license='Source: ' + review.get('license', review.get('repo_license')) + '; task metadata: CC-BY-4.0',
            origin_kind='upstream_issue', provenance='Development only; original archive SHA256 ' + sha(raw) +
                '. Strip only Codeload root/directories; retain regular file bytes. Public editable prefix ' + entry['prefix'] +
                '. Published documentation/release-note edits are outside the declared source-only task; omitted paths: ' + repr(omitted) + '. No gold tests or reference patch sent to agent. Adapted Python3.13 / pytest8.3.5; official project wheel supplies distribution metadata; no editable install, optional plugins or official-image equivalence.')
        cases.append(case)
        (private / (entry['identity'] + '-case.json')).write_text(case.model_dump_json(indent=2) + '\n')
        summary.append({'instance_id':entry['identity'], 'base_commit':row['base_commit'],
            'normalized_source_sha256':value.source_sha256, 'source_bytes':len(normalized),
            'editable_count':len(editable), 'reference_changed_files':sorted(changes), 'published_non_source_edits_excluded':omitted,
            'upstream_fail_to_pass':len(truth.fail_to_pass), 'upstream_pass_to_pass':len(truth.pass_to_pass),
            'runtime_wheels':len(truth.wheels), 'declared_python':row['install_config']['python'],
            'adapted_python':'3.13','origin_kind':case.origin_kind,'split':'development','executed':False})
    recipe = repository_suite_recipe(cases)
    (private / 'cases.json').write_text(json.dumps([case.model_dump(mode='json') for case in cases], indent=2) + '\n')
    (private / 'recipe.json').write_text(recipe.model_dump_json(indent=2) + '\n')
    staged = []
    class Captured(Exception):
        pass
    for case in cases:
        for label, output in [('reference', json.loads(case.reference.read())),
            ('unchanged', patch_artifact(RepositoryPatch(base_sha256=content_digest(case.input), files={}))),
            ('semantic_fault', case.fault_outputs[0])]:
            async def capture(payload):
                path = private / (case.input.task_id + '-' + label + '-payload.json')
                path.write_text(json.dumps(payload, separators=(',', ':')))
                staged.append({'case':case.input.task_id,'variant':label,'payload':str(path.relative_to(ROOT)),
                    'sha256':sha(path.read_bytes()),'bytes':path.stat().st_size})
                raise Captured()
            try:
                await grade_suite_output(case.input.model_dump(mode='json'), case.truth.model_dump(mode='json'), output, capture)
            except Captured:
                pass
            else:
                raise AssertionError('Preparation unexpectedly returned a candidate grade')
    assert len(staged) == 9
    (HERE / 'development-assets-preparation.json').write_text(json.dumps({'prepared':True,'external_code_executed':False,
        'candidate_grades_returned':0,'containers_started':0,'model_turns':0,'cases':summary,'staged_payloads':staged,
        'cases_file':str((private/'cases.json').relative_to(ROOT)),'cases_file_sha256':sha((private/'cases.json').read_bytes()),
        'recipe_sha256':sha((private/'recipe.json').read_bytes()),'recipe_definition_digest':content_digest(recipe)},indent=2)+'\n')
    print(json.dumps({'cases':summary,'payloads':len(staged),'execution_started':False}))


if __name__ == '__main__':
    asyncio.run(main())
