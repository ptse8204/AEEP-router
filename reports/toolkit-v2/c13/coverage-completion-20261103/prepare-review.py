"""Prepare immutable review inputs; no installs, Docker calls, grants or models."""
from __future__ import annotations
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
OLD=HERE.parent/'scanner-fixture-continuation-20261103'
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
r=json.loads((OLD/'operation-review.json').read_bytes())
r.update(
 purpose='Finish only interrupted branch coverage and downstream source gates; reuse full regression/build successes and only the original unstarted scanner/package components. Comparisons paused.',
 predecessor_review_sha256=sha(OLD/'operation-review.json'),
 scanner_context=str(OLD),
 completed_source_checks=str(OLD/'verification/checks.json'),
 hard_minimum_free_bytes=50*1024**3,
 source_minimum_free_bytes=50*1024**3,
 source_capacity_stop_bytes=None,
 source_capacity_baseline='Record actual free space and net changes as diagnostics. A shared-host net change is not task allocation. No net-change stop criterion for this source completion.',
 space_scope='Restore the normal50GiB actual usable reserve during source verification and before scanner/package dispatch, plus16MiB dispatch headroom. Do not extend original expiry. The original native installation plan remains unchanged with its own42GiB/1GiB scoped controls. Sampled guards are not continuous peak guarantees.',
 changes='First-party controller only: reuse six completed exact-source source checks including full pytest and the completed build; run only coverage/downstream gates. Replace the broad net-host-change stop rule with the normal actual50GiB reserve. No application/test/dependency/image/wheel change.',
 source_checks_reused=['compileall','schemas','assessment-policy','ruff','mypy','pytest','build'],
 source_checks_to_execute=['coverage-tests','coverage-json','coverage-report','critical-coverage','assessment-coverage','toolkit-integration-fixtures'],
 attempt_policy='One fresh coverage-only source attempt. Do not repeat full pytest or docs. Keep every terminal attempt and interrupted coverage backup. Unstarted scanner retains one bootstrap and one actual scan, original grants/amendments/counters. Original package retains one installation/check attempt through its unchanged helper. All13 exact-source gates required first. Common accounting/ownership uncertainty stops dispatch; independent settled component failure does not authorize retry or block other unstarted safe components.',
 original_expiry='2026-11-04T19:05:52.620563Z',
 full_pytest_result={'passed':2021,'skipped':21,'source':r['source'],'repeated':False},
 interrupted_coverage={'passed_before_stop':1539,'completed':False,'minimum_sampled_free_bytes':66446917632,'monitor_limit_bytes':1342177280,'measurements_preserved':True},
)
r.pop('superseded_unapproved_draft_sha256',None)
names=set(r['bound_files'])
names.update(str(p.relative_to(ROOT)) for p in HERE.rglob('*') if p.is_file() and p.name not in {'operation-review.json','preflight.json','preparation-checks.json'} and '__pycache__' not in p.parts)
names.update(str(p.relative_to(ROOT)) for p in (OLD/'verification').rglob('*') if p.is_file())
names.update(str((OLD/name).relative_to(ROOT)) for name in ['operation-review.json','operator-approval.json','host-capacity-start.json','verification-started.json','run-1793741901694059000.json'])
names.update(['docs/aeep-toolkit/DECISIONS.md','docs/aeep-toolkit/UPSTREAM_MATRIX.md','reports/toolkit-v2/c13/next-stack-integration-audit-20261103/readiness-preparation.json'])
# A later preparation-checks file is inert evidence, bound only after it exists.
if (HERE/'preparation-checks.json').exists():names.add(str((HERE/'preparation-checks.json').relative_to(ROOT)))
r['bound_files']={name:sha(ROOT/name) for name in sorted(names)}
(HERE/'operation-review.json').write_text(json.dumps(r,indent=2)+'\n')
print(json.dumps({'review_sha256':sha(HERE/'operation-review.json'),'bound_files':len(names),'execution':False}))
