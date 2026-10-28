"""Freeze one existing public task and an optional stable container workspace."""
import ast
import base64
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment,
    AssessmentSubject, RecipeDefinition, RecipeMaterializationRequest,
    RecipeRuntimeBinding, content_digest)
from aeep.assessment.repository_suites import RepositorySuiteCase, pack_files, repository_suite_recipe
from aeep.assessment.verification import verification_source_digest
REPOSITORY = '/tmp/aeep-repository-native-v6'

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'repository-native-batch-ready-20261028'
SOURCE = HERE


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    source = verification_source_digest(ROOT)
    stable = json.loads((SOURCE / 'validation/source-stability.json').read_text())
    assert stable['all_passed'] and stable['source_digest'] == source
    completed = json.loads((OLD / 'completion-audit.json').read_text())
    assert completed['physical_receipt_integrity_passed'] and completed['all_owned_containers_absent']
    assert completed['canonical_receipts_reopened'] == 12 and completed['cases_adopted'] == 0
    previous = json.loads((OLD / 'operation-review.json').read_text())
    parent = json.loads((ROOT / previous['parent_review']).read_text())
    recipe = RecipeDefinition.model_validate(parent['recipe'])
    fixtures = [RepositorySuiteCase.model_validate(c).model_copy(update={'split':'development','used_for_development':True}) for c in recipe.generator_config['cases']]
    shared = repository_suite_recipe(fixtures).extension.grader
    default = shared.config['argv'][-1]
    operator = default.replace('OPERATOR_REVIEW = False', 'OPERATOR_REVIEW = True')
    actual = HERE.parent / 'repository-stable-workspace-20261028'
    assert default == (actual/'observer-default.py').read_text()
    assert operator == (actual/'observer-operator.py').read_text()
    assert (HERE/'observer-default.py').read_text() == default
    assert (HERE/'observer-operator.py').read_text() == operator
    recipe.extension.reference = shared.model_copy(deep=True)
    recipe.extension.grader = shared.model_copy(deep=True)
    recipe.extension.grader.id = 'repository.suite.observe.diagnostic'
    recipe.extension.grader.config['argv'] = ['python3','-B','-c',operator]
    recipe.recipe_id = 'repository-shared-native-' + source[:16]
    recipe.dependencies.update(program=hashlib.sha256(operator.encode()).hexdigest(),
        operator_program=hashlib.sha256(operator.encode()).hexdigest(),
        default_program=hashlib.sha256(default.encode()).hexdigest())
    recipe.generator_config['operator_stable_workspace'] = {
        'repository_literal': REPOSITORY, 'private_mode': '0700',
        'fresh_container_required': True, 'existing_path_fails_closed': True,
        'no_runtime_host_path_argument': True, 'no_identity_normalization': True}
    recipe = RecipeDefinition.model_validate(recipe.model_dump(mode='json'))
    old_env = next(v['document'] for v in parent['documents'].values() if v['kind']=='environment')
    assert old_env['container_image'] == previous['parent_image']
    env = AssessmentEnvironment.model_validate({**old_env,
        'environment_id':'repository-shared-native-base-'+source[:12],
        'identity':{'source_digest':source,'observer_program_sha256':hashlib.sha256(operator.encode()).hexdigest(),
            'shared_default_program_sha256':hashlib.sha256(default.encode()).hexdigest(),
            'purpose':'Fresh shared-source/runtime qualification;no transfer of old source conformance.'}})
    assert runtime_dependencies() == previous['request']['runtime_dependencies']
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    documents = {content_digest(v): {'kind': k, 'id': i, 'document': v.model_dump(mode='json')}
        for k, i, v in [('recipe', recipe.recipe_id, recipe), ('environment', env.environment_id, env),
                        ('recipe_runtime', content_digest(runtime), runtime)]}
    cache = ROOT / '.aeep/repository-shared-native-runtime-20261028'
    cases = [RepositorySuiteCase.model_validate(v) for v in json.loads((cache / 'seeds.json').read_text())]
    assert len(cases) == 1 and 'asottile__dead-204' in cases[0].input.task_id
    seed = cases[0]
    code = """import importlib.metadata,hashlib,pkgutil,subprocess,tempfile
from pathlib import Path
def test_git_component():
    import identify.identify as api
    assert importlib.metadata.version('identify')=='2.6.15'
    assert 'identify-2.6.15-py2.py3-none-any.whl/identify/' in api.__file__
    assert 'python' in api.tags_from_filename('fixture.py')
    assert subprocess.check_output(['/usr/bin/git','--version']).decode().strip()=='git version 2.47.3'
    linked=subprocess.check_output(['/usr/bin/ldd','/usr/bin/git']).decode()
    assert 'not found' not in linked and 'libpcre2-8.so.0' in linked and 'libz.so.1' in linked
    with tempfile.TemporaryDirectory() as directory:
        root=Path(directory)
        subprocess.run(['/usr/bin/git','init','-q',str(root)],check=True)
        (root/'fixture.py').write_text('public first-party fixture\\n')
        subprocess.run(['/usr/bin/git','-C',str(root),'add','fixture.py'],check=True)
        assert subprocess.check_output(['/usr/bin/git','-C',str(root),'ls-files','-z'])==b'fixture.py\\x00'
"""
    ast.parse(code)
    archive = pack_files({'tests/test_native_support.py': code.encode()})
    payload = {'archive': base64.b64encode(archive).decode(),
        'archive_sha256': hashlib.sha256(archive).hexdigest(), 'python': '3.13', 'pytest': '8.3.5',
        'test_paths': ['tests/test_native_support.py'], 'pytest_plugins': [], 'source_modules': [],
        'wheels': [{'filename': Path(a.path).name, 'sha256': a.sha256,
                   'data': base64.b64encode(a.read()).decode()} for a in seed.truth.wheels]}
    support = {'payload': payload,
        'payload_sha256': hashlib.sha256(json.dumps(payload, separators=(',', ':')).encode()).hexdigest(),
        'archive_sha256': payload['archive_sha256'],
        'nodes': ['tests/test_native_support.py::test_git_component']}
    names = ('observer-operator.py', 'observer-default.py',
        'git_component.py', 'component-check.json', 'upstream-metadata.json',
        'upstream-copyright.txt', 'image-package-inventory.json', 'prepare-template.py', 'shared-default-control.json')
    paths = [HERE / n for n in names] + [HERE / 'runtime-execution' / n
        for n in ('run.py','audit-execution.py','classify.py','operator_output.py','native_scope.py','review-budget.py')]
    paths += [cache / 'seeds.json', cache / 'records.json',
        OLD / 'completion-audit.json', OLD / 'derived-review.json', OLD / 'operation-review.json',
        SOURCE / 'validation/source-stability.json', HERE.parent / 'repository-stable-workspace-20261028/provisional-pool.json',
        ROOT / 'docs/ASSESSMENT_TESTING.md', ROOT / 'docs/aeep-toolkit/CONTINUATION.md',
        ROOT / 'docs/aeep-toolkit/DECISIONS.md']
    # Include all original source/test/reference/wheel/provenance pins unchanged.
    # Old status prose and old execution drivers are not new execution assets.
    for path, digest in previous['assets'].items():
        if '/.aeep/' in path or '/licenses/' in path or path.endswith('/build-result.json'):
            assert sha(Path(path)) == digest
            paths.append(Path(path))
    control = json.loads((HERE/'shared-default-control.json').read_text())
    control_case = RepositorySuiteCase.model_validate(control['case'])
    assert len(control_case.truth.fail_to_pass+control_case.truth.pass_to_pass)==171
    paths += [Path(a.path) for a in (control_case.truth.source,control_case.truth.tests,control_case.reference,*control_case.truth.wheels)]
    paths.append(ROOT/control['source_M1_evidence'])
    for item in control['variants']:
        path=ROOT/item['payload'];assert sha(path)==item['sha256'];paths.append(path)
    assets = {str(p.resolve()): sha(p) for p in paths}
    assert all(Path(p).is_file() and not Path(p).is_symlink() for p in assets)
    subject = AssessmentSubject(kind='command', location=str(cache), dependency_digests=assets,
        description='One exact cached Dead204 snapshot, fixed private repository path in fresh containers, exhaustive native identities; no models or installations.')
    request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
        subject_digest=content_digest(subject), recipe_digest=content_digest(recipe),
        mapping_digest=content_digest(recipe), environment_digest=content_digest(env),
        authorization_id='onboarding', seed=119, definition_digests=list(documents),
        runtime_dependencies=runtime.dependencies)
    new = {content_digest(v): {'kind': k, 'id': i, 'document': v.model_dump(mode='json')}
        for k, i, v in [('subject', subject.subject_id, subject),
                        ('recipe_materialization_request', request.plan_id, request)]}
    amendment = AssessmentScopeAmendment(authorization_id='onboarding',
        authorization_digest=parent['authorization_digest'], subject_digests=[content_digest(subject)],
        recipe_digests=[content_digest(recipe)], environment_digests=[content_digest(env)],
        reviewed_digests=[*documents, *new])
    envelope = {**{k: parent[k] for k in ('authorization_digest', 'image', 'docker', 'socket', 'host_canary')},
        'source_digest': source, 'recipe': recipe.model_dump(mode='json'),
        'request': request.model_dump(mode='json'), 'documents': documents, 'external_execution': False}
    envelope['host_canary'] = '.aeep/repository-shared-native-runtime-20261028/host-canary'
    assert not (ROOT / envelope['host_canary']).exists()
    save(HERE / 'observer-envelope.json', envelope)
    assets[str((HERE / 'observer-envelope.json').resolve())] = sha(HERE / 'observer-envelope.json')
    review = {'source_digest': source,
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'authorization_digest': parent['authorization_digest'], 'assets': assets,
        'cases_file': str((cache / 'seeds.json').relative_to(ROOT)),
        'records_file': str((cache / 'records.json').relative_to(ROOT)),
        'active_case_ids': [seed.input.task_id], 'expected_required_counts': {seed.input.task_id: 38},
        'collections': [v for v in previous['collections'] if v['case_id'] == seed.input.task_id],
        'derived_directory': str((cache / 'derived').relative_to(ROOT)),
        'method_sha256': sha(HERE / 'runtime-execution/native_scope.py'),
        'parent_review': str((HERE / 'observer-envelope.json').relative_to(ROOT)),
        'parent_review_sha256': sha(HERE / 'observer-envelope.json'),
        'driver_files': {n: sha(HERE / 'runtime-execution' / n) for n in ('run.py', 'audit-execution.py', 'classify.py', 'operator_output.py')},
        'request': request.model_dump(mode='json'), 'new_documents': new,
        'reviewed_document_digests': [*documents, *new], 'amendment': amendment.model_dump(mode='json'),
        'parent_image': env.container_image, 'host_canary': envelope['host_canary'],
        'probes': previous['probes'], 'native_fixtures': previous['native_fixtures'],
        'support_probe': support, 'case_support_nodes': {seed.input.task_id: support['nodes'][0]},
        'initial_contained_calls': 19, 'maximum_contained_calls': 21,
        'maximum_operations': 26, 'maximum_reserved_seconds': 1335,
        'maximum_model_turns': 0, 'cash_usd': 0, 'maximum_builds': 0, 'maximum_downloads': 0,
        'shared_default_control_file': str((HERE/'shared-default-control.json').relative_to(ROOT)),
        'bounded_control_repairs': {'maximum_extra_calls': 2,
            'maximum_additional_setup_analysis_operations': 2,
            'allowed': 'Exact recorded first-party receipt/report correction after known completion and cleanup, with unchanged programs, software, source, tests, rules, permissions and sealed payloads.',
            'forbidden': 'No program, software, source, assertion, reference, rule, model, permission, input or threshold changes. No automatic retry, uncertain replay, refunds or budget resets.'},
        'permissions': ['Contained calls use only the exact derived output image authorized by the separate parent Git review. No models,cash,credentials,services,new destinations,pulls,deletion,activation or release.',
            'Both profiles each run four fresh boundary/state/transport probes and two native fixtures. Git/Identify support,Dead collection,reference/original and raw reference follow. Two frozen171-test JSON-logger raw controls additionally check the shared default;controls are not new independent cases.',
            'Fixed repository literal /tmp/aeep-repository-native-v6 exists only in a fresh container private tmpfs; exclusive mode-0700 mkdir rejects every existing path or symlink. No caller path argument, identity rewriting or assertion change.',
            'Require all 38 native obligations. Freeze exhaustive mapping, truth, selector and payload hashes before body execution. A reference failure excludes the case; no outcome-based dropping or remapping.',
            'Maximum21calls/26existing-grant operations/1335reservedseconds includes the single300-second build/download operation,two optional unchanged-payload report controls and one extra setup/analysis phase. Preserve charges and history.',
            'Keep 50 GiB free and all images. Remove only new owned containers and unchanged canary; retain receipts and at most 8192 bytes per failed public log.'],
        'evidence_reuse': 'New source passes its own13gates. Prior actual program1f099dfb is byte-equal,but old source/package conformance does not transfer. Corrected wheel requires a fresh private check;shared-default171-test controls require actual execution.',
        'known_exclusion': 'Dead204 stays excluded until this new actual runtime reproduces. Original33Git fixture errors remain. Isort and Sopel separately require genuine distribution metadata/runtime closure and are outside this review.',
        'approval_reason': 'This is an inert template. New Git software, download and image binding require the separate exact parent runtime review and deterministic post-build derivation;no authority is inferred from this template.',
        'scientific_qualification_usefulness_selection_resource_human_release': False}
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    assert subprocess.check_output([parent['docker'], '--host', parent['socket'], 'image', 'inspect',
        env.container_image, '--format', '{{.Id}}'], timeout=20).decode().strip() == env.container_image
    save(HERE / 'template-operation-review.json', review)
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as con:
        counters = list(con.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    save(HERE / 'template-preparation-checks.json', {'passed': True, 'assets_bound': len(assets),
        'review_sha256': sha(HERE / 'template-operation-review.json'), 'source_digest': source,
        'source13_and_wheel20_checks_reused': True, 'required_native_tests': 38, 'shared_default_control_tests':171,
        'grant_unchanged': counters, 'actual_external_execution': False})
    print(json.dumps({'prepared': True, 'review_sha256': sha(HERE / 'template-operation-review.json'),
        'assets': len(assets), 'external_execution': False}))


if __name__ == '__main__':
    main()
