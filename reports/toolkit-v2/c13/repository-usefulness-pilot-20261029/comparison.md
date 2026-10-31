# Repository usefulness development comparison

Both arms scored 14/19 (73.68%). The task-success difference is 0 percentage points; there were no candidate-only or baseline-only successes.

21 intended tasks; 19 complete pairs. A controller artifact-format error censored two tasks and three model turns. All charges and canonical records remain; there were no replacement tasks or historical replay.

## Scoring

Each task scores 1 for an independent protected-grader pass or 0 for failure. A pass requires the frozen bug-fix and preservation checks. This study did not predeclare a partial-credit quality rubric. The two engineering-censored tasks have unknown scores and are excluded from the 19-task denominator.

| Family | Tasks | Ordinary score | Ponytail score |
| --- | --- | --- | --- |
| single-file-repair | 6 | 5/6 | 5/6 |
| multi-file-repair | 6 | 3/6 | 3/6 |
| contract-audit | 7 | 6/7 | 6/7 |

## Token usage differences

Token difference means Ponytail minus ordinary Codex. Positive values mean more reported tokens; negative values mean fewer. Change divides that difference by ordinary tokens. Each token count is the provider-reported input + output total from its canonical task turn. Cached input, cache writes and reasoning output are retained separately below and are not added to this metric.

| Condition / scope | Pairs | Ordinary tokens | Ponytail tokens | Token difference | Change |
| --- | --- | --- | --- | --- | --- |
| plain / all completed tasks | 13 | 1,334,530 | 1,691,894 | +357,364 | +26.78% |
| plain / both passed only | 11 | 1,165,825 | 1,438,750 | +272,925 | +23.41% |
| gzip / all completed tasks | 6 | 683,419 | 753,147 | +69,728 | +10.20% |
| gzip / both passed only | 3 | 286,117 | 302,284 | +16,167 | +5.65% |

The all-completed rows include failed tasks. The both-passed rows show the successful paired subset separately. Neither condition reaches 20 successful measured pairs, so these descriptive differences do not establish confidence-supported savings or regression. Plain and gzip conditions are not pooled.

All 38 token capture chains were reopened and verified against canonical trials, receipts and final journals for this presentation. This verifies capture and association; the provider's meter accuracy and monetary savings remain unverified. These counts exclude setup, graders, other assessment overhead and the three charged censored engineering turns. Their costs remain in the original ledger.

## Task scores and token usage

| Task | Format | Ordinary score | Ponytail score | Ordinary tokens | Ponytail tokens | Token difference | Change |
| --- | --- | --- | --- | --- | --- | --- | --- |
| matthewwithanm__python-markdownify-200 | plain | 1/1 PASS | 1/1 PASS | 140,796 | 162,623 | +21,827 | +15.50% |
| AbsaOSS__generate-release-notes-207 | plain | 0/1 FAIL | 0/1 FAIL | 63,755 | 126,177 | +62,422 | +97.91% |
| MahjongRepository__mahjong-62-aeep-contract-audit | plain | 1/1 PASS | 1/1 PASS | 88,112 | 79,640 | -8,472 | -9.62% |
| python-markdown__markdown-1587 | plain | 1/1 PASS | 1/1 PASS | 157,993 | 212,323 | +54,330 | +34.39% |
| gerlero__foamlib-315 | plain | 1/1 PASS | 1/1 PASS | 180,820 | 170,276 | -10,544 | -5.83% |
| iluvcapra__pycmx-12-aeep-contract-audit | plain | 1/1 PASS | 1/1 PASS | 60,412 | 70,482 | +10,070 | +16.67% |
| spulec__freezegun-582 | plain | 1/1 PASS | 1/1 PASS | 63,358 | 87,492 | +24,134 | +38.09% |
| oOo0oOo__leanclient-24-declared-tests | plain | 1/1 PASS | 1/1 PASS | 95,743 | 166,481 | +70,738 | +73.88% |
| scitokens__scitokens-202-aeep-contract-audit | plain | 1/1 PASS | 1/1 PASS | 63,679 | 98,620 | +34,941 | +54.87% |
| jpadilla__pyjwt-1040-declared-tests | plain | 0/1 FAIL | 0/1 FAIL | 104,950 | 126,967 | +22,017 | +20.98% |
| python-scim__scim2-models-126-declared-tests | gzip | 1/1 PASS | 1/1 PASS | 124,158 | 141,240 | +17,082 | +13.76% |
| gidgethub__gidgethub-225-aeep-contract-audit | plain | 1/1 PASS | 1/1 PASS | 77,220 | 111,645 | +34,425 | +44.58% |
| sciunto-org__python-bibtexparser-515-declared-tests | censored | unknown | unknown | unknown | unknown | unknown | unknown |
| researchobject__ro-crate-py-248-declared-tests | censored | unknown | unknown | unknown | unknown | unknown | unknown |
| hynek__svcs-140-aeep-contract-audit | gzip | 1/1 PASS | 1/1 PASS | 74,197 | 71,445 | -2,752 | -3.71% |
| joke2k__django-environ-592-declared-tests | plain | 1/1 PASS | 1/1 PASS | 106,782 | 127,943 | +21,161 | +19.82% |
| canopen-python__canopen-613-declared-tests | gzip | 0/1 FAIL | 0/1 FAIL | 113,787 | 132,805 | +19,018 | +16.71% |
| lincolnloop__goodconf-51-aeep-contract-audit | gzip | 0/1 FAIL | 0/1 FAIL | 94,976 | 136,566 | +41,590 | +43.79% |
| serge-sans-paille__beniget-121-declared-tests-py313-truth | plain | 1/1 PASS | 1/1 PASS | 130,910 | 151,225 | +20,315 | +15.52% |
| tefra__xsdata-1126-issue-behavior-audit | gzip | 0/1 FAIL | 0/1 FAIL | 188,539 | 181,492 | -7,047 | -3.74% |
| prometheus__client_python-1134-aeep-contract-audit | gzip | 1/1 PASS | 1/1 PASS | 87,762 | 89,599 | +1,837 | +2.09% |

## Raw token fields

| Task / arm | Input | Output | Cached input | Cache write input | Reasoning output |
| --- | --- | --- | --- | --- | --- |
| matthewwithanm__python-markdownify-200 / ordinary | 139,624 | 1,172 | 120,832 | 0 | 25 |
| matthewwithanm__python-markdownify-200 / Ponytail | 161,197 | 1,426 | 139,264 | 0 | 62 |
| AbsaOSS__generate-release-notes-207 / ordinary | 62,941 | 814 | 48,128 | 0 | 24 |
| AbsaOSS__generate-release-notes-207 / Ponytail | 124,625 | 1,552 | 102,400 | 0 | 28 |
| MahjongRepository__mahjong-62-aeep-contract-audit / ordinary | 87,253 | 859 | 69,632 | 0 | 0 |
| MahjongRepository__mahjong-62-aeep-contract-audit / Ponytail | 78,830 | 810 | 58,752 | 0 | 0 |
| python-markdown__markdown-1587 / ordinary | 156,290 | 1,703 | 139,392 | 0 | 190 |
| python-markdown__markdown-1587 / Ponytail | 210,532 | 1,791 | 190,592 | 0 | 201 |
| gerlero__foamlib-315 / ordinary | 178,157 | 2,663 | 156,032 | 0 | 392 |
| gerlero__foamlib-315 / Ponytail | 168,139 | 2,137 | 144,768 | 0 | 406 |
| iluvcapra__pycmx-12-aeep-contract-audit / ordinary | 59,788 | 624 | 50,816 | 0 | 0 |
| iluvcapra__pycmx-12-aeep-contract-audit / Ponytail | 69,644 | 838 | 51,840 | 0 | 0 |
| spulec__freezegun-582 / ordinary | 62,363 | 995 | 39,552 | 0 | 12 |
| spulec__freezegun-582 / Ponytail | 86,454 | 1,038 | 72,448 | 0 | 21 |
| oOo0oOo__leanclient-24-declared-tests / ordinary | 94,116 | 1,627 | 78,080 | 0 | 29 |
| oOo0oOo__leanclient-24-declared-tests / Ponytail | 164,710 | 1,771 | 138,880 | 0 | 101 |
| scitokens__scitokens-202-aeep-contract-audit / ordinary | 62,949 | 730 | 38,912 | 0 | 11 |
| scitokens__scitokens-202-aeep-contract-audit / Ponytail | 97,532 | 1,088 | 78,208 | 0 | 12 |
| jpadilla__pyjwt-1040-declared-tests / ordinary | 103,571 | 1,379 | 94,720 | 0 | 82 |
| jpadilla__pyjwt-1040-declared-tests / Ponytail | 125,499 | 1,468 | 112,128 | 0 | 110 |
| python-scim__scim2-models-126-declared-tests / ordinary | 122,788 | 1,370 | 107,008 | 0 | 45 |
| python-scim__scim2-models-126-declared-tests / Ponytail | 139,826 | 1,414 | 115,328 | 0 | 88 |
| gidgethub__gidgethub-225-aeep-contract-audit / ordinary | 76,507 | 713 | 48,128 | 0 | 35 |
| gidgethub__gidgethub-225-aeep-contract-audit / Ponytail | 110,104 | 1,541 | 91,136 | 0 | 39 |
| hynek__svcs-140-aeep-contract-audit / ordinary | 73,365 | 832 | 58,880 | 0 | 8 |
| hynek__svcs-140-aeep-contract-audit / Ponytail | 70,671 | 774 | 52,608 | 0 | 9 |
| joke2k__django-environ-592-declared-tests / ordinary | 104,861 | 1,921 | 97,536 | 0 | 46 |
| joke2k__django-environ-592-declared-tests / Ponytail | 125,999 | 1,944 | 111,616 | 0 | 30 |
| canopen-python__canopen-613-declared-tests / ordinary | 111,951 | 1,836 | 101,504 | 0 | 52 |
| canopen-python__canopen-613-declared-tests / Ponytail | 130,744 | 2,061 | 110,848 | 0 | 63 |
| lincolnloop__goodconf-51-aeep-contract-audit / ordinary | 92,725 | 2,251 | 83,456 | 0 | 100 |
| lincolnloop__goodconf-51-aeep-contract-audit / Ponytail | 134,428 | 2,138 | 120,960 | 0 | 70 |
| serge-sans-paille__beniget-121-declared-tests-py313-truth / ordinary | 128,909 | 2,001 | 119,168 | 0 | 126 |
| serge-sans-paille__beniget-121-declared-tests-py313-truth / Ponytail | 149,606 | 1,619 | 135,808 | 0 | 89 |
| tefra__xsdata-1126-issue-behavior-audit / ordinary | 186,749 | 1,790 | 169,856 | 0 | 81 |
| tefra__xsdata-1126-issue-behavior-audit / Ponytail | 179,779 | 1,713 | 161,024 | 0 | 81 |
| prometheus__client_python-1134-aeep-contract-audit / ordinary | 86,593 | 1,169 | 77,696 | 0 | 38 |
| prometheus__client_python-1134-aeep-contract-audit / Ponytail | 88,334 | 1,265 | 70,528 | 0 | 23 |

## Task execution time

| Format | Arm | Successes | Agent seconds |
| --- | --- | --- | --- |
| plain | control | 11/13 | 646.22 |
| plain | treatment | 11/13 | 637.81 |
| gzip | control | 3/6 | 273.44 |
| gzip | treatment | 3/6 | 272.23 |

## What remains unknown

Supplemental observer logs lack direct arm references. Their test-level results remain unordered within each pair, so they cannot supply an arm-specific test-pass fraction or partial quality score. See the retained failure analysis for those diagnostics.

Ponytail instructions were positively loaded in 19/19 candidate turns; semantic contribution remains unproven. Public-task contamination is unknown. This small development sample and its attrition establish no formal qualification, broad absence of value, or positive AEEP selection benefit.

The actual admission API refused both development reports because passed qualification and measured benefit are required. Admissions and allowances stayed unchanged. No candidate was admitted or activated; release remains unauthorized. Resource qualification remains separate from capability usefulness.

## Evidence

- [Task scores, raw counts and differences (JSON)](comparison-metrics.json)
- [Task scores and counts (CSV)](comparison-metrics.csv)
- [Original frozen comparison analysis](comparison-analysis.json)
- [Read-only canonical capture checks](presentation-20261030/canonical-check.json)
- [Original HTML snapshot](presentation-20261030/original-comparison.html)
- [Supplemental unordered test details](retained-failure-analysis.json)
- [Paired failure diagnosis](FAILURE_ANALYSIS.md)
- [Stopped-attempt reconciliation](stopped-accounting-audit.json)
- [Plain canonical audit](../repository-usefulness-plain-20261029/completion-audit.json)
- [Gzip canonical audit](../repository-usefulness-gzip-20261029/completion-audit.json)
- [Original plan and authority](PLAN.md)

Presentation updated October 30 from retained evidence only. No model, grader, installer or container was run. Frozen grades, analysis, thresholds and ledgers are unchanged.
