"""Describe retained paired test outcomes; never rerun graders or model turns."""
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import sqlite3

from aeep.assessment.models import content_digest

HERE = Path(__file__).resolve().parent
BASE = Path('/Users/edwintse/Documents/aeep-agent-router/.aeep/live-review-v3')


def load(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


analysis = load(HERE / 'comparison-analysis.json')
cohort = {c['task_id']: c for c in load(HERE / 'cohort.json')['cases']}
records = []
for mode in ('plain', 'gzip'):
    directory = HERE.parent / f'repository-usefulness-{mode}-20261029'
    model = load(directory / 'model-result.json')
    with sqlite3.connect((BASE / 'aeep.sqlite3').as_uri() + '?mode=ro', uri=True) as connection:
        plan = json.loads(connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='plan' AND id=?",
            (model['plan_id'],)).fetchone()[0])
    truths = {c['case_id'].removeprefix('development-'): c['validators'][-1]['config']['expected']
        for c in plan['suite']['cases']}
    rows = [r for r in analysis['rows'] if r['codec_condition'] == mode]
    assert len(rows) == 2 * len(truths)
    # The reviewed driver completes all reference/counterexample checks before
    # enqueueing task turns. Every valid task invokes exactly one callback.
    observations = sorted(directory.glob('observer-*.json'))[-len(rows):]
    matched = defaultdict(list)
    for path in observations:
        value = load(path)
        assert len(value['statuses']) == value['status_count']
        reply = {key: value[key] for key in ('exit_code', 'statuses', 'archive_sha256', 'python', 'pytest')}
        assert content_digest(reply) == value['reply_digest']
        identities = set(value['statuses'])
        candidates = [key for key, truth in truths.items()
            if set(truth['fail_to_pass'] + truth['pass_to_pass']) <= identities]
        assert len(candidates) == 1, (path.name, candidates)
        identity = candidates[0]
        truth = truths[identity]
        required = set(truth['fail_to_pass'] + truth['pass_to_pass'])
        broken = {key: status for key, status in value['statuses'].items() if status != 'PASSED'}
        verdict = value['exit_code'] == 0 and all(value['statuses'][key] == 'PASSED' for key in required)
        matched[identity].append({'observer': str(path.relative_to(HERE.parents[3])),
            'observer_file_sha256': sha(path), 'reply_digest_verified': True,
            'grade_recomputed': verdict, 'exit_code': value['exit_code'],
            'required_identities': len(required), 'observed_identities': len(identities),
            'remaining_bug_tests': {key: broken[key] for key in truth['fail_to_pass'] if key in broken},
            'preservation_failures': {key: broken[key] for key in truth['pass_to_pass'] if key in broken},
            'additional_nonpassed_tests': {key: status for key, status in broken.items() if key not in required}})
    assert set(matched) == set(truths)
    for identity, observations in matched.items():
        pair = [r for r in rows if r['case'] == identity]
        assert len(observations) == len(pair) == 2
        assert sorted(r['independent_grade'] for r in pair) == sorted(o['grade_recomputed'] for o in observations)
        records.append({'case': identity, 'family': cohort[identity]['family'], 'codec': mode,
            'canonical_arm_success': {r['arm']: r['independent_grade'] for r in pair},
            # Existing logs do not bind an observer entry directly to an arm.
            # Preserve the pair as an unordered observation set; do not invent it.
            'observation_arm_assignment': 'unavailable; unordered per-case pair',
            'observations': observations})

failures = [r for r in records if not all(r['canonical_arm_success'].values())]
assert len(records) == 19 and len(failures) == 5
report = {'scope': 'Supplemental retained-evidence diagnosis; frozen grades and thresholds unchanged.',
    'source_model_evidence': 'b09911a0b7b79f6f78a5371bbad53580ff0692fc3d371592a983437898a19fcf',
    'comparison_analysis_sha256': sha(HERE / 'comparison-analysis.json'),
    'complete_pairs': len(records), 'both_failed_pairs': len(failures),
    'matching_method': 'Final task-callback observations, unique protected test-identity set, complete reply digest, and recomputed per-case grade multiset.',
    'arm_assignment_limit': 'The retained observer log lacks a direct trial/arm reference. Supplemental test details remain unordered; canonical arm verdicts remain bound to their trial records.',
    'new_models_or_graders': 0, 'frozen_results_changed': False,
    'records': sorted(records, key=lambda r: r['case'])}
(HERE / 'retained-failure-analysis.json').write_text(json.dumps(report, indent=2) + '\n')
lines = ['# What the paired repository failures show', '',
    'Both arms failed the same five tasks. These are protected-test failures on completed task artifacts. The two earlier controller-censored cases remain outside this analysis.', '',
    '| Task | Ordinary / optional skill | Remaining bug tests in the two artifacts | Preservation failures in the two artifacts |',
    '| --- | --- | --- | --- |']
for row in sorted(failures, key=lambda r: r['case']):
    bugs = sorted(len(o['remaining_bug_tests']) for o in row['observations'])
    preservation = sorted(len(o['preservation_failures']) for o in row['observations'])
    lines.append(f"| {row['case']} | FAIL / FAIL | {bugs[0]}, {bugs[1]} | {preservation[0]}, {preservation[1]} |")
lines.extend(['',
    'The two counts in each cell are unordered. Existing observer logs lack a direct trial/arm reference, so this diagnosis does not assign partial progress to a specific arm. Canonical pass/fail verdicts remain independently bound to their trials. Detailed test identities and observation hashes are in [the data](retained-failure-analysis.json).', '',
    'Partial fixes can differ even when both artifacts fail. They do not satisfy the frozen task-success endpoint and cannot be promoted to a demonstrated benefit after seeing the results. Failure identities alone do not reveal why the model chose a repair or whether skill text influenced it.', '',
    'The supported selection decision is to keep the ordinary baseline for this tested scope: optional Ponytail has no observed success gain, and neither format group establishes resource savings. This is an evidence-bound non-admission, not a claim that the skill has no value on other work. AEEP has not yet demonstrated a positive live selection benefit.', '',
    'No new models, graders, installations or resource-qualification tests were run for this analysis.'])
(HERE / 'FAILURE_ANALYSIS.md').write_text('\n'.join(lines) + '\n')
print(json.dumps({'pairs_checked': len(records), 'both_failed_pairs': len(failures),
    'retained_reply_digests_verified': 38, 'new_models_or_graders': 0}))
