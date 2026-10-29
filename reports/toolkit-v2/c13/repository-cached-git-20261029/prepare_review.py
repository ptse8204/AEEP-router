"""Bind the verified existing context to one fresh, download-free runtime attempt."""
import ast
import json
from pathlib import Path
import shutil
import sqlite3
import stat
import subprocess

from aeep.assessment.models import AssessmentSubject, RecipeMaterializationRequest, AssessmentScopeAmendment, content_digest
from aeep.assessment.verification import verification_source_digest
from cached_context import NEEDED
from review_bindings import audit, sha

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OLD = HERE.parent / 'repository-review-bindings-20261029'


def save(name, value):
    with (HERE / name).open('x') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')


def main():
    previous = json.loads((OLD / 'runtime-review.json').read_text())
    assert sha(OLD / 'runtime-review.json') == 'a11807f2aaf8880661a7cf248d2d0738c26e672ed61a9b3e2d5cb184a1f4b40b'
    source = verification_source_digest(ROOT)
    assert source == previous['source_digest']
    for name in ('parent-ELF-audit.json', 'cached-context-audit.json', 'cached-context-check.json', 'predecessor-reconciliation.json'):
        assert json.loads((HERE / name).read_text())['passed']
    context_check = json.loads((HERE / 'cached-context-audit.json').read_text())
    assert set(context_check['needed_libraries']) == NEEDED
    decision = str(ROOT / 'docs/aeep-toolkit/DECISIONS.md')
    prior_notes = subprocess.check_output(['git', 'show', '87397fb:docs/aeep-toolkit/DECISIONS.md'], cwd=ROOT, text=True)
    assert Path(decision).read_text().startswith(prior_notes.rstrip())
    template = json.loads((OLD / 'template-operation-review.json').read_text())
    template['assets'][decision] = sha(decision)
    old_subject = next(v['document'] for v in template['new_documents'].values() if v['kind'] == 'subject')
    subject_data = {k: v for k, v in old_subject.items() if k != 'subject_id'}
    subject_data['dependency_digests'] = {**subject_data['dependency_digests'], decision: sha(decision)}
    subject = AssessmentSubject.model_validate(subject_data)
    request_data = {k: v for k, v in template['request'].items() if k != 'plan_id'}
    request = RecipeMaterializationRequest.model_validate({**request_data, 'subject_digest': content_digest(subject)})
    documents = {k: v for k, v in previous['build_documents'].items() if v['kind'] in ('recipe', 'environment', 'recipe_runtime')}
    new_documents = {content_digest(value): {'kind': kind, 'id': identity, 'document': value.model_dump(mode='json')}
        for kind, identity, value in [('subject', subject.subject_id, subject),
                                     ('recipe_materialization_request', request.plan_id, request)]}
    documents.update(new_documents)
    amendment = AssessmentScopeAmendment(authorization_id='onboarding', authorization_digest=previous['authorization_digest'],
        subject_digests=[content_digest(subject)], recipe_digests=[request.recipe_digest],
        environment_digests=[request.environment_digest], reviewed_digests=list(documents))
    template.update(request=request.model_dump(mode='json'), new_documents=new_documents,
        reviewed_document_digests=list(documents), amendment=amendment.model_dump(mode='json'))
    save('template-operation-review.json', template)
    assets = dict(previous['assets'])
    for name, expected in list(assets.items()):
        if name == decision:
            assets[name] = sha(decision)
        else:
            assert sha(name) == expected, name
    for file in [*HERE.glob('*.py'), *sorted((HERE / 'runtime-execution').glob('*.py')),
        *(HERE / name for name in ('parent-ELF-audit.json', 'cached-context-audit.json',
            'cached-context-check.json', 'predecessor-reconciliation.json', 'template-operation-review.json',
            'observer-envelope.json', 'observer-operator.py', 'observer-default.py',
            'upstream-metadata.json', 'upstream-copyright.txt', 'shared-default-control.json')),
        OLD / 'runtime-review.json', OLD / 'build-result.json', OLD / 'build-operation-ledger.json', OLD / 'terminal-reconciliation.json']:
        if file.suffix == '.py':
            ast.parse(file.read_text())
        assets[str(file.resolve())] = sha(file)
    context = ROOT / previous['build_context']
    for name, expected in context_check['context_files'].items():
        assert sha(context / name) == expected
        assets[str((context / name).resolve())] = expected
    assets[context_check['archive']] = context_check['archive_sha256']
    with sqlite3.connect('file:/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3/aeep.sqlite3?mode=ro', uri=True) as db:
        counters = list(db.execute("SELECT operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id='onboarding'").fetchone())
    assert counters == [13305, 3755, 120083.82735821838, '0.0']
    docker = ['/usr/local/bin/docker', '--host', 'unix:///Users/edwintse/.docker/run/docker.sock']
    assert subprocess.run([*docker, 'image', 'inspect', previous['target_tag']], capture_output=True, timeout=20).returncode != 0
    assert not (ROOT / previous['host_canary']).exists() and shutil.disk_usage(ROOT).free > 51 * 1024**3
    permissions = list(previous['permissions'])
    permissions[0] = 'Reuse only the already retained exact8665568-byte Git archive and19prepared context files,with every hash and mode checked. Zero downloads,extraction,package scripts,resolvers or context mutation.'
    permissions[1] = 'Pinned Apple LLVM reads ELF data only. Require exactly libc,PCRE2,zlib and the inherited ld-linux-aarch64.so.1 already verified in the same parent. No Linux code runs on the Mac;no library or package is added.'
    permissions[5] = 'At most21offline calls/26existing-grant operations/1335reservedseconds cumulative,including one300-second cached validation/build operation. Preserve the prior failed operation and all counters. No network request or package/docs/source-suite replay.'
    review = {**previous, 'assets': assets, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(),
        'purpose': 'One fresh cached-context Git runtime attempt after the terminal missing-loader expectation;no downloads or new software bytes.',
        'template_review_sha256': sha(HERE / 'template-operation-review.json'),
        'build_request': request.model_dump(mode='json'), 'build_documents': documents,
        'build_amendment': amendment.model_dump(mode='json'), 'required_ELF_NEEDED_set': sorted(NEEDED),
        'context_mode_pins': {name: stat.S_IMODE((context / name).stat().st_mode) for name in context_check['context_files']},
        'maximum_download_attempts': 0, 'maximum_download_bytes_per_attempt': 0,
        'permissions': permissions, 'no_authority_for': [*previous['no_authority_for'], 'No downloads,archive extraction,new software bytes or context mutation.'],
        'terminal_previous_runtime_sha256': sha(OLD / 'runtime-review.json'),
        'grant_before_preparation': counters,
        'change_boundary': 'Cached immutable verification replaces download/extraction;expected ELF names include the verified inherited loader. Append-only D123 rebound in fresh subject/request definitions. Same task/collector programs,software bytes,image recipe,assertions,payloads,permissions and26operation/1335second ceiling.',
        'evidence_reuse': 'Sourceb09911a0 retains13passed gates and wheelb3d9c5d0 retains20installed checks;docs69passed. No repeats. Fresh new-image containment/Git/native checks and frozen171-test controls remain required;no conformance or scientific result transfers automatically.',
        'approval_reason': 'The actual a11807f2approval was exercised once and ended at the dependency expectation guard. That exact review forbids automatic retry and program/expected-library changes. This fresh cached-only build/execution needs exact approval;no architecture,budget,download,package,docs or model decision.'}
    # These fields describe the prior review; do not mislabel them as this change.
    review.pop('first_party_binding_replacements', None)
    review.pop('terminal_previous_bundle_sha256', None)
    save('runtime-review.json', review)
    result = audit([HERE / 'runtime-review.json'], ROOT)
    assert result['passed'], result['errors']
    save('preparation-audit.json', {**result, 'runtime_review_sha256': sha(HERE / 'runtime-review.json'),
        'source_unchanged': True, 'cached_context_unchanged': True, 'new_software_bytes': False,
        'new_downloads_builds_installs_containers_models_or_grant_charges': 0,
        'grant_after_preparation': counters, 'actual_new_approval_received': False})
    print(json.dumps({'passed': True, 'runtime_review_sha256': sha(HERE / 'runtime-review.json'),
        'assets': len(assets), 'nested_reviews': len(result['reviews']), 'unique_file_bindings': result['unique_file_bindings']}))


if __name__ == '__main__':
    main()
