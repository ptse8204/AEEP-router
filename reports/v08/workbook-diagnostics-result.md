# Workbook diagnostic follow-up

The fresh required-invocation workflow delivered an artifact and stopped at its
first screening failure, with `invalid_workbook` retained as the reviewed code.
One model task ran; there were no holdouts or candidate activation.

An independent check then exposed a grader defect: converting a known-correct
fixture from inline text to `str` text cells made the grader reject it. Openpyxl
3.1.5 in the offline container read identical values, formulas, caches, sheets
and bold formatting from both files. Microsoft documents both text-cell types in
its [Open XML enumeration](https://learn.microsoft.com/en-us/dotnet/api/documentformat.openxml.spreadsheet.cellvalues).

The live artifact was not retained, so this does not establish the cause of its
rejection. The immutable report still records `unsuitable`; it cannot now support
a claim that the plugin was unsuitable. Reviews for both affected workbook
recipe definitions have been revoked. Historical records and usage remain intact.

Repair the parser and add the alternate encoding to independent fixtures before
reviewing a new recipe and running fresh cases. Do not change the task's values,
formula, cache, structure, grading thresholds or acceptance policy.

[Source-bound live result and revocations](workbook-diagnostics-result.json),
[independent encoding probe](workbook-string-cell-grader-probe.json),
[implementation validation](grader-diagnostics-validation.json).

The current grant has 185 turn allowances and 1,872.08 operation seconds remaining.
No budget expansion was applied. Release readiness remains false.
