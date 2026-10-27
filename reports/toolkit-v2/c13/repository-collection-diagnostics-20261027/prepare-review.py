"""Freeze four diagnostic inputs; inspect bytes/AST only, never import subject code."""
import ast
import base64
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile

from aeep.assessment.identity import runtime_dependencies
from aeep.assessment.models import (AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject,
    ExecutableRecipeExtension, RecipeDefinition, RecipeFeatureRule, RecipeLiteralFixture,
    RecipeMaterializationRequest, RecipeRuntimeBinding, content_digest)
from aeep.assessment.verification import verification_source_digest
from aeep.models import ExecutorSpec
from sanitize import IDENTIFIER, self_check
import review_budget

ROOT = Path(__file__).resolve().parents[4]
HERE = Path(__file__).resolve().parent


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value, compact=False):
    text = json.dumps(value, indent=None if compact else 2,
                      separators=(',', ':') if compact else None, allow_nan=False)
    if not compact:
        text += '\n'
    if path.exists():
        assert path.is_file() and not path.is_symlink() and path.read_text() == text
        return
    with path.open('x') as stream:
        stream.write(text)


def identifiers(payload):
    names = set(sys.stdlib_module_names) | set(sys.builtin_module_names) | set(payload.get('pytest_plugins', []))
    names.update(payload.get('source_modules', []))
    parsed = skipped = 0
    data = base64.b64decode(payload['archive'], validate=True)
    assert hashlib.sha256(data).hexdigest() == payload['archive_sha256']
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for item in archive:
            assert item.isfile() and not item.name.startswith('/') and '..' not in Path(item.name).parts
            if not item.name.endswith('.py'):
                continue
            text = archive.extractfile(item).read()
            try:
                tree = ast.parse(text)
            except (SyntaxError, UnicodeError):
                skipped += 1
                continue
            parsed += 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        names.add(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        names.add(node.module)
                    names.update(alias.name for alias in node.names if alias.name != '*')
                elif isinstance(node, ast.Attribute):
                    names.add(node.attr)
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    names.add(node.name)
    for name in list(names):
        names.update('.'.join(name.split('.')[:i]) for i in range(1, len(name.split('.'))))
    result = sorted(n for n in names if len(n) <= 128 and IDENTIFIER.fullmatch(n))
    assert len(result) <= 20_000
    return result, {'public_python_files_parsed_as_ast': parsed, 'syntax_files_not_parsed': skipped,
                    'subject_code_imported_or_executed': False, 'identifier_count': len(result)}


def main():
    assert not (HERE / 'operation-review.json').exists()
    inputs = ROOT / '.aeep/repository-collection-diagnostic-inputs-20261027-v2'
    inputs.mkdir(exist_ok=True)
    assert inputs.resolve() == inputs and not inputs.is_symlink()
    base = HERE.parent
    source = verification_source_digest(ROOT)
    runtime = RecipeRuntimeBinding(dependencies=runtime_dependencies())
    groups, assets, records = [], {}, []
    selected = [
        ('repository-supported-suites-20261027', [
            ('modelcontextprotocol__python-sdk-222-declared-tests', 4),
            ('modelcontextprotocol__python-sdk-384-aeep-contract-audit', 5),
            ('elementsinteractive__twyn-317-declared-tests', 8)]),
        ('repository-independent-sources-20261024', [('ucfopen__canvasapi-716-declared-tests', 12)])]
    probe_spec = authorization = None
    for folder, selected_cases in selected:
        origin = base / folder
        parent_file = origin / 'runtime-execution/parent-runtime-review.json'
        parent = json.loads(parent_file.read_text())
        completed_file = origin / 'runtime-execution/completion-audit.json'
        completed = json.loads(completed_file.read_text())
        assert completed['physical_receipt_integrity_passed'] and completed['all_owned_containers_absent']
        assert parent['source_digest'] == source
        if probe_spec is None:
            probe_spec = ExecutorSpec.model_validate(parent['recipe']['extension']['grader'])
            authorization = parent['authorization_digest']
        assert probe_spec == ExecutorSpec.model_validate(parent['recipe']['extension']['grader'])
        assert authorization == parent['authorization_digest']
        environment = AssessmentEnvironment.model_validate(next(d['document'] for d in parent['documents'].values() if d['kind'] == 'environment'))
        image_tag = json.loads((origin / 'build-result.json').read_text())['target_tag']
        assert subprocess.check_output(['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock',
                                       'image', 'inspect', '--format', '{{.Id}}', image_tag], text=True, timeout=20).strip() == environment.container_image
        group = {'origin': folder, 'image_id': environment.container_image, 'image_tag': image_tag,
                 'environment': environment.model_dump(mode='json'), 'prior_containment_audit': str(completed_file.relative_to(ROOT)), 'prior_containment_audit_sha256': sha(completed_file),
                 'probes': [], 'diagnostics': []}
        operation = json.loads((origin / 'runtime-execution/operation-review.json').read_text())
        variants = json.loads((ROOT / operation['variants_file']).read_text())
        metadata = json.loads((origin / 'prepared-cases.json').read_text())
        for path in [parent_file, completed_file, origin / 'approval-bundle.json', origin / 'build-result.json',
                     origin / 'runtime-execution/operation-review.json', ROOT / operation['variants_file'], ROOT / operation['cases_file']]:
            assets[str(path)] = sha(path)
        for case_id, raw_index in selected_cases:
            row = next(v for v in variants if v['case'] == case_id and v['variant'] == 'reference')
            original_file = ROOT / row['payload']
            assert sha(original_file) == row['sha256']
            payload = json.loads(original_file.read_text())
            prior_file = origin / 'runtime-execution' / ('raw-observation-' + str(raw_index) + '.json')
            prior = json.loads(prior_file.read_text())
            assert prior['output']['exit_code'] == 2 and prior['output']['archive_sha256'] == payload['archive_sha256']
            allowed, identifier_review = identifiers(payload)
            payload['reviewed_identifiers'] = allowed
            target = inputs / (case_id + '.json')
            save(target, payload, compact=True)
            for path in (original_file, prior_file, target):
                assets[str(path)] = sha(path)
            description = next(c for c in metadata['cases'] if c['id'] == case_id)
            for license in description['license_records']:
                path = ROOT / license['path']; assert sha(path) == license['sha256']; assets[str(path)] = sha(path)
            group['diagnostics'].append({'kind': 'diagnostic', 'name': case_id, 'image_id': environment.container_image,
                'payload_file': str(target.relative_to(ROOT)), 'payload_sha256': sha(target),
                'original_payload_file': str(original_file.relative_to(ROOT)), 'original_payload_sha256': sha(original_file),
                'prior_failed_result': str(prior_file.relative_to(ROOT)), 'prior_failed_result_sha256': sha(prior_file),
                'source_revision': description['revision'], 'source_repository': description['repository'],
                'archive_sha256': payload['archive_sha256'], 'identifier_review': identifier_review})
            records.append({'case': case_id, **identifier_review})
        groups.append(group)
    program = (HERE / 'diagnostic-program.py').read_text()
    original_program = (ROOT / 'integrations/assessment-runtime/repository_suite_plugins_program.py').read_text()
    # Verify extraction, Python bootstrap, plugin order, argv and child environment
    # are byte-identical; only the private log handling/structured reply changes.
    boot_start = original_program.index('def main():')
    boot_end = original_program.index("        with log.open('wb') as stream:")
    assert program[program.index('def main():'):program.index('        timed_out = False')] == original_program[boot_start:boot_end]
    spec_data = probe_spec.model_dump(mode='json')
    spec_data.update(id='repository.collection.diagnose', capability='assessment.repository_collection_diagnostic@1',
                     description='Operator-only sanitized collection diagnostics; no statuses or correctness grade.')
    spec_data['config'] = {**spec_data['config'], 'argv': ['python3', '-B', '-c', program], 'max_output_bytes': 8192}
    diagnostic = ExecutorSpec.model_validate(spec_data)
    literal = lambda label: RecipeLiteralFixture(input={'family': 'diagnostic', 'synthetic_redaction_fixture': label},
                                                 output={'diagnostic_only': True})
    recipe = RecipeDefinition(schema_version='assessment.recipe.v2', recipe_id='operator-collection-diagnostic-20261027',
        capability=diagnostic.capability, description='Operator-only collection diagnosis. Not a materializable campaign or validated task grader.',
        input_schema={'type': 'object'}, output_schema={'type': 'object'}, generator='contained_json:1',
        generator_config={'operator_only': True, 'campaign_materialization_authorized': False},
        grader='contained_json:1', extractor='structural_json:1', variations=['diagnostic'],
        dependencies={'diagnostic_program': sha(HERE / 'diagnostic-program.py')},
        exclusions=['campaign materialization', 'model trials', 'grading', 'qualification', 'admission', 'selection evidence'],
        extension=ExecutableRecipeExtension(generator=diagnostic, grader=diagnostic, reference=diagnostic,
            independent_fixtures=[literal('one'), literal('two')], transformed_fixtures=[literal('three')],
            fault_outputs=[{'raw_log': 'synthetic forbidden field'}],
            feature_rules={'family': RecipeFeatureRule(path='/family', operation='enum', values=['diagnostic'])},
            variation_features={'diagnostic': {'family': 'diagnostic'}}, template_families=['operator-diagnostic']))
    assets.update({str(HERE / n): sha(HERE / n) for n in ['run.py', 'sanitize.py', 'diagnostic-program.py',
                   'review_budget.py', 'prepare-review.py', 'audit-execution.py', 'check-preparation.py']})
    subject = AssessmentSubject(kind='command', location=str(inputs), dependency_digests=assets,
                                description='Four public frozen failed references; sanitized diagnostic only. No new source or installation.')
    documents = {}
    def document(kind, identity, value):
        documents[content_digest(value)] = {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
    document('subject', subject.subject_id, subject); document('recipe', recipe.recipe_id, recipe)
    document('recipe_runtime', content_digest(runtime), runtime)
    for index, group in enumerate(groups):
        environment = AssessmentEnvironment.model_validate(group.pop('environment'))
        document('environment', environment.environment_id, environment)
        request = RecipeMaterializationRequest(schema_version='assessment.recipe-materialization.v2',
            subject_digest=content_digest(subject), recipe_digest=content_digest(recipe), mapping_digest=content_digest(recipe),
            environment_digest=content_digest(environment), authorization_id='onboarding', seed=84 + index,
            definition_digests=[content_digest(recipe), content_digest(environment), content_digest(runtime)],
            runtime_dependencies=runtime.dependencies)
        document('recipe_materialization_request', request.plan_id, request)
        group['request'] = request.model_dump(mode='json')
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=authorization,
        subject_digests=[content_digest(subject)], recipe_digests=[content_digest(recipe)],
        environment_digests=[g['request']['environment_digest'] for g in groups], reviewed_digests=list(documents))
    for n in ['run.py', 'sanitize.py', 'diagnostic-program.py', 'prepare-review.py', 'audit-execution.py', 'check-preparation.py']:
        ast.parse((HERE / n).read_text())
    review = {'purpose': 'Diagnose four exact failed public reference collections without guessing dependency fixes or changing grades.',
        'source_digest': source, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'authorization_digest': authorization, 'subject_digest': content_digest(subject), 'runtime_dependencies': runtime.dependencies,
        'assets': assets, 'recipe': recipe.model_dump(mode='json'), 'documents': documents,
        'amendment': amendment.model_dump(mode='json'), 'groups': groups,
        'maximum_contained_calls': 4, 'maximum_operations': 6, 'maximum_reserved_seconds': 290,
        'maximum_model_turns': 0, 'cash_usd': 0, 'automatic_retry': False,
        'permissions': ['At most4 offline contained diagnostic calls: MCP222/MCP384/Twyn references on retainedf60342e9 and CanvasAPI reference on retainedb0eb4add. Reuse the completed source/image-bound containment/state/runtime evidence; no new probes or canaries.',
            'Use existing AssessmentService, ContainerExecutor, reserve/finish operations and canonical attempts/receipts. At most6 existing-grant operations and290 reserved seconds:30 setup +120 analysis +4 times35. No new budget or counter reset.',
            'The subject archives, tests, plugins, Python/pytest settings and runtime images are identical to their failed references. Only the first-party observer reply changes. No repair, counterexample, partial repair or grading is authorized.',
            'Retain only fixed schema, archive/runtime identity, pytest exit/timeout flags, recognized exception categories and public static-reviewed identifier allowlists. No raw test log, traceback, error message, path, source snippet or arbitrary identifier is retained. These are untrusted log-reported diagnostic facts, not verified root-cause or task grades.',
            'Keep all images, volumes, historical results, receipts and charges. Remove only new attempt-owned containers. No host canary or other host resource is created or removed. No automatic retry or reuse of unstarted slots.',
            'No model turns/cash, builds/pulls, installs, downloads, OS/project/host changes, credentials, new services/destinations, package/docs reruns, activation, publication or release.'],
        'limitations': ['Prior failed references remain failed. Diagnostic exit0 does not add an eligible case. No qualification/usefulness/selection/resource-acceptance claim follows.',
            'Category and identifiers originate in untrusted public test output and can be forged; they guide a subsequent source/runtime review, not automatic installation or a proven causal attribution.',
            'If no allowlisted cause is captured, report unknown and preserve the terminal attempt. Do not expand output, change inputs or replay automatically.',
            'Synthetic fixture fields in the operator recipe are inert schema scaffolding. They are not subject observations or grader-validation evidence, and campaign materialization is outside authority.'],
        'approval_reason': 'Your continuation reserves untrusted execution and CONTINUATION.md requires applicable container-provisioning authority. Terminalc81557a2 andbe8b0e5f forbid automatic retry and bind different observer bytes. Standing delegation covers this exact routine definition, but a new execution approval is required. No architecture, budget or infrastructure choice is needed.'}
    save(HERE / 'operation-review.json', review)
    save(HERE / 'preparation-checks.json', {'passed': True, 'source_unchanged': True, 'review_sha256': sha(HERE / 'operation-review.json'),
        'assets': len(assets), 'sanitizer_guards': self_check(), 'budget_guards': review_budget.self_check(),
        'identifier_reviews': records, 'same_subject_payloads_except_allowlists': True, 'bootstrap_and_pytest_argv_unchanged': True,
        'containers_started': 0, 'models': 0, 'new_installations': 0, 'source_code_executed': False})
    print(json.dumps({'review_sha256': sha(HERE / 'operation-review.json'), 'assets': len(assets),
                      'sanitizer_guards': self_check(), 'budget_guards': review_budget.self_check(), 'prepared_only': True}))


if __name__ == '__main__':
    main()
