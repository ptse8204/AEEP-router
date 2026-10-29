"""Prepare a fresh runtime attempt; preserve terminal review and completed components."""
import ast
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import subprocess

from aeep.assessment.verification import verification_source_digest
from aeep.assessment.models import AssessmentSubject, RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from review_bindings import audit, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / 'repository-shared-native-20261028'


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    parent = json.loads((OLD / 'approval-bundle.json').read_text())
    assert sha(OLD / 'approval-bundle.json') == '17defe15993ee2b54a84193c5bd047243060d372ecc04ecb00d740bba77ed40e'
    reconciliation = json.loads((OLD / 'preflight-failure-reconciliation.json').read_text())
    assert reconciliation['passed'] and reconciliation['runtime_attempt_terminal_no_retry']
    independent = json.loads((OLD / 'independent-component-results.json').read_text())
    assert len(independent['results']) == 2 and all(v['passed'] for v in independent['results'])
    assert json.loads((HERE / 'binding-check.json').read_text())['passed']
    previous = json.loads((OLD / 'runtime-review.json').read_text())
    assert previous['source_digest'] == verification_source_digest(ROOT)
    decision_path = str(ROOT / 'docs/aeep-toolkit/DECISIONS.md')
    old_notes = subprocess.check_output(['git', 'show', '2bc86b1:docs/aeep-toolkit/DECISIONS.md'], cwd=ROOT, text=True)
    assert Path(decision_path).read_text().startswith(old_notes.rstrip())
    template = json.loads((OLD / 'template-operation-review.json').read_text())
    template['assets'][decision_path] = sha(decision_path)
    prior_subject = next(v['document'] for v in template['new_documents'].values() if v['kind'] == 'subject')
    subject_data = {k: v for k, v in prior_subject.items() if k != 'subject_id'}
    subject_data['dependency_digests'] = {**subject_data['dependency_digests'], decision_path: sha(decision_path)}
    subject = AssessmentSubject.model_validate(subject_data)
    request_data = {k: v for k, v in template['request'].items() if k != 'plan_id'}
    request = RecipeMaterializationRequest.model_validate({**request_data, 'subject_digest': content_digest(subject)})
    documents = {k: v for k, v in previous['build_documents'].items()
                 if v['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new_documents = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
        for kind, identity, value in [('subject', subject.subject_id, subject),
                                     ('recipe_materialization_request', request.plan_id, request)]}
    documents.update(new_documents)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=previous['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(documents))
    template.update(request=request.model_dump(mode='json'), new_documents=new_documents,
        reviewed_document_digests=list(documents), amendment=amendment.model_dump(mode='json'))
    (HERE / 'template-operation-review.json').write_text(json.dumps(template, indent=2) + '\n')
    # Never flatten conflicting mappings first: each child retains its own audit.
    assets = dict(previous['assets'])
    replacements = []
    for name, expected in list(assets.items()):
        actual = sha(name)
        if actual != expected:
            assert name == decision_path or parent['assets'][name] == actual
            replacements.append({'file': name, 'previous': expected, 'current': actual})
            assets[name] = actual
    assert len(replacements) == 4
    copied = ['derive-execution.py', 'git_component.py', 'review-budget.py',
        'observer-operator.py', 'observer-default.py', 'observer-envelope.json',
        'upstream-metadata.json', 'upstream-copyright.txt',
        'shared-default-control.json']
    for name in copied:
        assert (HERE / name).read_bytes() == (OLD / name).read_bytes()
    for file in (HERE / 'runtime-execution').glob('*.py'):
        assert file.read_bytes() == (OLD / 'runtime-execution' / file.name).read_bytes()
    for file in [*HERE.glob('*.py'), *(HERE / n for n in copied), HERE / 'template-operation-review.json',
                 *sorted((HERE / 'runtime-execution').glob('*.py')),
                 HERE / 'binding-check.json', OLD / 'runtime-review.json',
                 OLD / 'preflight-failure-reconciliation.json',
                 OLD / 'independent-component-results.json']:
        if file.suffix == '.py':
            ast.parse(file.read_text())
        assets[str(file.resolve())] = sha(file)
    for component in independent['results']:
        assets[component['result_file']] = component['result_sha256']
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        counters = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert counters == parent['grant_before_preparation']
    for name in (previous['build_context'], previous['component_cache'], previous['host_canary']):
        assert not (ROOT / name).exists()
    docker = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
    assert subprocess.run([*docker, 'image', 'inspect', previous['target_tag']], capture_output=True, timeout=20).returncode != 0
    assert shutil.disk_usage(ROOT).free > 51 * 1024**3
    corrected = {**previous, 'assets': assets,
        'template_review_sha256': sha(HERE / 'template-operation-review.json'),
        'build_request': request.model_dump(mode='json'), 'build_documents': documents,
        'build_amendment': amendment.model_dump(mode='json'),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'purpose': 'Fresh exact runtime attempt after the terminal outer/child pin mismatch; package and docs already passed and are not rerun.',
        'terminal_previous_bundle_sha256': sha(OLD / 'approval-bundle.json'),
        'terminal_previous_runtime_sha256': sha(OLD / 'runtime-review.json'),
        'first_party_binding_replacements': replacements,
        'completed_package_and_docs_are_not_repeated': independent['results'],
        'change_boundary': 'Three nested pins are aligned to the actual previously approved outer pins;the appended D122 work record is rebound in content-addressed subject/request definitions. A first-party recursive audit is added before any runtime marker. New owned report/receipt location;identical runtime drivers except that audit,source,Git bytes,image recipe,task data,assertions,frozen payloads,permissions and absolute allowances. No new source,wheel or docs execution.',
        'approval_reason': 'The actual17defe159approval was exercised once and stopped at a known preflight pin error. That review forbids automatic retries. A new exact approval is required for this fresh one-attempt runtime; finite first-party review preparation is delegated. No architecture, model or budget decision.',
        'grant_before_preparation': counters}
    save('runtime-review.json', corrected)
    result = audit([HERE / 'runtime-review.json'], ROOT)
    assert result['passed'], result['errors']
    save('preparation-audit.json', {**result, 'runtime_review_sha256': sha(HERE / 'runtime-review.json'),
        'source_unchanged': True, 'all_previous_source_checks_retained': True,
        'task_programs_and_upstream_software_unchanged': True,
        'canonical_counters_unchanged': counters,
        'download_build_container_model_cash_or_installation': False,
        'actual_approval_received': False})
    print(json.dumps({'passed': True, 'review_sha256': sha(HERE / 'runtime-review.json'),
        'assets': len(assets), 'nested_reviews': len(result['reviews']),
        'unique_file_bindings': result['unique_file_bindings']}))


if __name__ == '__main__':
    main()
