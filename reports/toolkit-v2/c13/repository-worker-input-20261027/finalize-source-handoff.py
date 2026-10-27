"""Record completed source gates and the exact next scope;never execute that scope."""
import hashlib
import json
from pathlib import Path
import re

from aeep.assessment.verification import verification_source_digest

ROOT=Path(__file__).resolve().parents[4];HERE=Path(__file__).resolve().parent

def main():
    stable=json.loads((HERE/'validation/source-stability.json').read_text());assert stable['all_passed'] and stable['source_unchanged'] and stable['completed_checks']==13
    assert verification_source_digest(ROOT)==stable['source_digest']=='374579f1121ee62964613f5b5a392fa2063939feba9393c65086da8052f2ac13'
    for name in ('03.log','04.log'):assert re.search(r'1735 passed, 21 skipped', (HERE/'validation'/name).read_text())
    assert re.search(r'^TOTAL.*\b82%',(HERE/'validation/05.log').read_text(),re.MULTILINE)
    files=list((HERE/'validation/artifacts').iterdir());assert len(files)==2
    artifacts=[{'path':str(p.relative_to(ROOT)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size,'retained_locally':True,'tracked_in_git':False} for p in sorted(files)]
    (HERE/'build-artifacts.json').write_text(json.dumps({'artifacts':artifacts,'installed_check_pending':True},indent=2)+'\n')
    wheel=next(p for p in artifacts if p['path'].endswith('.whl'))
    p=ROOT/'docs/aeep-toolkit/STATE.md';s=p.read_text();s=s.replace('Focused framing regressions pass, including a 2.7 MB round trip through both real\nprotocol readers. [Full source verification](../../reports/toolkit-v2/c13/repository-worker-input-20261027/source-in-progress.json)\nis running in session38330; inspect its actual status before resuming.', 'Focused framing regressions pass, including a 2.7 MB round trip through both real\nprotocol readers. [All 13 source checks](../../reports/toolkit-v2/c13/repository-worker-input-20261027/validation/checks.json)\npassed: 1,735 tests in each full run, 21 skips, 82% coverage and both branch gates.\nThe corrected wheel is built; its installation and fresh container profile remain\npending the exact new execution approval.')
    s=s.replace("last_verified_commit: 'a43a7b6'", "last_verified_commit: '1f7d27d'")
    a=s.index('last_check_command:');b=s.index('blocked_actions:',a)
    s=s[:a]+'''last_check_command: 'repository-worker-input-20261027/run-source-checks.py; check-legacy-recipe.py; check-terminal-controls.py; exact runtime/package/docs preparation'
last_check_result: 'All13 source gates passed on374579f1:both full runs1735passed/21skipped,82%coverage,both branch gates. Frozen d02 recipe remains identical. Five actual collector fixtures preserve terminal-failure/uncertainty distinctions. Prior e6b runtime failure and8charged operations remain;old-source package19checks/docs passed. No corrected-source external execution or model turn.'
next_action: 'Read repository-worker-input-20261027/README.md and approval-bundle.json. Obtain one exact executable approval for corrected-source4fresh probes/12unchanged variants on retained2386 plus changed-wheel19installed checks and cached offline docs. Runtime maximum20calls/24operations/1000reserved seconds includes bounded report controls. No new download,dependency or image build. Record actual approval and run the combined driver once;preserve prior failed probe,8charges and51-case pool. Source session38330 is terminal;do not rerun it.'
''' +s[b:]
    s+='''
## Inner-worker correction source verification completed — October27

[All13 source gates](../../reports/toolkit-v2/c13/repository-worker-input-20261027/validation/checks.json)
passed on374579f1/commit1f7d27d. Both full runs passed1,735 tests with21 skips and
one existing warning;coverage82%,both branch gates passed. Compilation,schemas,
integration tests,Ruff,mypy and wheel/sdist builds passed. Frozen d02 recipe
reconstruction is unchanged. Session38330 is terminal and was not repeated.
The first-party collector checks now also bind complete execution evidence by
its canonical repository digest,keeping its separate journal identifier distinct.
Five fixtures accept known terminal failure only as failure and stop on nonterminal,
incomplete-journal or cleanup uncertainty. No live/container call supplied them.

The new wheel and exact remaining runtime/package/docs scope are prepared. Source
and wheel changes require approval because the preceding explicit control-repair
room excluded product changes. Reuse image2386 and all unchanged case/probe/test
bytes;no dependency,download,image build,service,model,cash,architecture or budget
decision is needed. Maximum20calls/24operations/1000reserved seconds includes four
bounded same-software report diagnostics. Current13189/3755/119834.18554038461/0.0
counters,all images,the51-case pool and90-case gap remain. No qualification,
usefulness,selection,resource,human-control or release gate closes.

The next metadata-only multi-file queue contains14 potential tasks across11repos.
It preserves prior queue/exclusion flags and still needs semantic/runtime review.
Its initial reader confused an integer row count with row records;that local
schema handling was corrected before the final queue. No new source archive,
untrusted code,installation or model was involved in this preparation.
''';p.write_text(s)
    p=HERE/'README.md';s=p.read_text();a=s.index('Full13-gate source verification');b=s.index('\n## Next execution scope',a)
    s=s[:a]+'''[All13 source checks](validation/checks.json) passed on source374579f1 and commit
1f7d27d:1,735 tests in each full run,21 skips,82%coverage and both branch gates.
Compilation,schemas,integration checks,Ruff,mypy and wheel/sdist builds passed.
Session38330 is terminal and was not repeated. [The built artifacts](build-artifacts.json)
retain exact hashes. The corrected wheel's SHA-256 is `'''+wheel['sha256']+'''`.
No corrected-wheel installation or new container invocation has run.
''' +s[b:]
    s=s.replace('Prepare one exact combined review after the source gates pass.', '[The prepared combined review](approval-bundle.json) binds the exact source,wheel,\nruntime and documentation. It is not yet approved or executed.')
    p.write_text(s)
    for filename,text in [
        ('docs/aeep-toolkit/DECISIONS.md','''

### D111 source verification completed

All13 gates passed on374579f1,with1,735 tests in both full runs and82%coverage.
Frozen legacy recipe serialization remains identical. Five collector fixtures
exercise actual code against private copies of terminal evidence,including
incomplete-journal denial. Journal identifiers and canonical repository content
digests stay distinct. The retained image and task bytes are unchanged;fresh
worker/wheel execution requires the exact new review,with no new software build
or architecture. No scientific/resource threshold or prior cost is changed.
'''),
        ('docs/aeep-toolkit/UPSTREAM_MATRIX.md','''

## Corrected reader source verified, October27

Source374579f1 passed all13 gates. Reuse the already verified seven-wheel optional
grader image2386;there is no new core dependency,artifact download or image build.
The same six subjects and protected oracle bytes still require fresh corrected-
source execution. The actual frozen legacy recipe remains unchanged. Installed
worker framing and exact offline docs checks are prepared separately. None of
these source/fixture results establishes capability value or selector quality.
'''),
        ('reports/v08/plan-coverage.md','''

### Inner worker source gates complete; exact execution remains — October27

Source374579f1/commit1f7d27d passed all13 gates:1,735tests in both full runs,
21skips,82%coverage,both branch gates. Compilation,schemas,integration,Ruff,mypy,
wheel/sdist builds and frozen legacy recipe reconstruction passed. Session38330
is terminal. Five report-control fixtures exercise actual collector code with
complete canonical evidence;they preserve failed/uncertain distinctions. The
corrected wheel and same6case/4probe runtime use retained2386 without downloads,
new dependencies or builds. Exact execution approval is required because the
prior envelope excluded changed product source/wheel. Runtime maximum20calls/
24operations/1000reserved seconds includes bounded report controls,zero models/cash.
The old8charges,pool51/gap90,all images and open scientific/resource/human gates
remain. New exact docs-check execution is pending;raw logs/licenses stay verbatim.
''')]:
        p=ROOT/filename;p.write_text(p.read_text()+text)
    print(json.dumps({'source_checks_completed':13,'wheel_sha256':wheel['sha256'],'source_digest':stable['source_digest'],'execution_started':False}))

if __name__=='__main__':main()
