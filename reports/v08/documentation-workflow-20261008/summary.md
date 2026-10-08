# Documentation workflow revision, October 8, 2026

Revised the active documentation on `main` at the operator's request. The prose
now leads with AEEP's intended effect on a workflow, explains why a step helps,
and introduces mechanisms afterward. Goals remain distinct from measured results.

The pass covers 45 documents: the README and index, active guides and examples,
reference introductions, integration READMEs and authoring instructions. The
README drops from 862 to 731 whitespace-delimited words. Its first-use shortcut
and existing demo remain in place.

## Preservation

All 133 code fences in the changed documents are unchanged. Existing headings
remain or have explicit anchor aliases. External URL targets are unchanged.
The specification and security contract bodies are unchanged. Historical reports,
adopted ADRs, campaign definitions, packaged skills, executable files and CI
are preserved.

## Validation

All required local checks passed. Ordinary pytest and branch-coverage pytest each
reported 1,293 passed, 21 skipped and one existing Starlette deprecation warning.
Combined coverage is 81.32%; the 80% floor and both critical/assessment
branch gates pass. The verification source stayed unchanged across both runs.

Markdown and local-link checks pass across 47 active documents: 493 occurrences,
zero errors. Compile, schema, version, policy, Ruff, mypy, Node integration and
retained proof checks pass. The legacy router compatibility profiles pass; live
OpenAI verification remains skipped and live marketplace networking disabled.
Wheel/sdist builds pass; 40 packaged Markdown files and six root documents match
their source bytes.

[checks.json](checks.json) records exact commands, results, coverage, package
hashes and temporary resources. [validation.log](validation.log) retains output.
Commands were unchanged, so no new sign-in, example execution or live trial was
needed. External URL targets were unchanged; this pass did not repeat the prior
external-link review.

Rendered review covered the README, its setup shortcut, the index tables,
onboarding and the loaded demo GIF using a temporary loopback preview. The
preview server and browser tab were closed. This review is not a human-usability
measurement.

## Evidence binding

The fingerprinted integration README edits change `verification_source_digest`:

- Before this pass: `4c19ad6a9ea186c660b8e37db1baf188e159700d405425eec64a4babb9e5a8a3`.
- After this pass: `67737187ddfff12e3555c00eaceff4709b82d7be78e8754968b1fd35022d247e`.

Historical live results keep their original bindings. Applicable source-bound
verification needs renewal before those results can cover this revision. No
qualification, live-comparison, human-usability or release gate is closed by
this editorial work.

No runtime behavior, production configuration, dependency or publication changed.
No Docker resource or live provider trial was created.
