# Real repository test pack

This pack lets AEEP grade a source repair against the repository's actual tests.
It feeds the existing assessment and comparison path; it adds no evaluation
service or routing engine. Capability usefulness still requires a separate model
comparison, followed by selection evaluation against independently established
value labels.

## Stack and evidence

| Layer | Reused implementation | Current evidence |
| --- | --- | --- |
| Task source | Pinned SWE-rebench issue metadata and original repository revisions | Three development cases prepared; source, license and adaptations recorded |
| Test execution | Pinned pytest wheels and the existing offline ContainerExecutor | Earlier one-case prototype passed; changed v5 execution awaits exact approval |
| Test parsing | MIT SWE-rebench pytest parser bodies | Static source pins and first-party parser contract tests |
| Evaluation | Existing AssessmentService, BenchmarkRunner, callbacks, attempts and receipts | v5 source checks and private wheel preparation recorded here |
| Model workers | Existing managed AEEP fallback | No new model run in this increment; agent-skill-eval's Codex harness remains unqualified |
| Usefulness and selection | Existing four-arm analysis and separate selection scorer | No new value label, admission or demonstrated selection improvement |

The prior approved six-call check is terminal and passed. Its receipts and
independent audit are in [the prototype record](../rebench-grader-20261022/completion-audit.json).
That result belongs to its original source and cannot qualify v5 by transfer.

## Prepared cases

| Development case | Required bug tests | Preservation tests | Adaptation |
| --- | --- | --- | --- |
| Loguru 1451 | 2 | 22 | Python 3.13, pytest 8.3.5 |
| Click 3239 | 4 | 694 | Python 3.13; published documentation edits excluded from the explicit Python-only task |
| Marshmallow 2800 | 5 | 185 | Python 3.11 task adapted to 3.13; author/changelog edits excluded from the explicit Python-only task |

These are three tasks with 912 required test identities. All three published
repairs affect one Python file. They do not supply multi-file or no-change
coverage, an official benchmark score, or a representative holdout cohort.
Development repositories, including the previously inspected pgmpy source,
are excluded from later stages.

`development-assets-preparation.json` binds nine inert observation payloads.
Preparation returned no grades and executed no external software. Source is
public within each task; repair patches and private test overlays stay with the
coordinator. Click and Marshmallow's official pure wheels provide distribution
metadata; reviewed source precedes their code on the import path.

The pending grader scope contains twelve fresh containers: three authored
containment/state probes and each real case's reference, unchanged and scoped
fault variants. Reference and unchanged runs require every expected test identity.
The intentionally broken import may prevent collection; missing tests stay invalid.
No candidate model, image build, installer or network access is included.

## Verification limits and retained failures

The first source run passed 1,657 tests before a source-layout defect was found.
Its drift guard then stopped verification before coverage. `validation/` retains
that incomplete result. The corrected process test proves reviewed `src/` code
precedes conflicting wheel code. Current verification is in `validation-v2/`;
its terminal source-stability record is authoritative.

An initial data draft rejected Click's documentation changes at the Python edit
boundary. The second draft states a narrower source-only task and excludes only
published non-source edits. Both drafts remain; no edit guard was relaxed.
The full published repair is not claimed as completed.

The metadata inventory has 684 preliminary repair candidates from 357
repositories. Their licenses, archives, exact dependencies and test reproduction
are still unverified. There are no adopted assessment cases or frozen holdouts,
and no authored no-change controls in that inventory. Counts are not acceptance
evidence.

After approved conformance, curate the independent workload and freeze worker,
candidate, generated challenger, stronger-compute arm and utility definitions.
Run qualification before optional-use comparisons. Selection evaluation follows
actual value evidence; the old INCONCLUSIVE result cannot provide useful/useless
labels. Keep infrastructure resource observations in a separate record.
