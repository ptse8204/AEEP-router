# Protected SkillsBench graders and CLI preparation

The packaged Sales Pivot and Spring Boot graders both accepted the pinned
reference and rejected missing and defective output through AEEP's
ordinary contained executor. Their recipes use binary scores.

| Workflow | Reference | Missing output | Deliberate fault |
| --- | --- | --- | --- |
| [Sales Pivot](../skillsbench-sales-dependencies-20261105/grader-execution/summary.json) | 1 | 0 | 0 |
| [Spring Boot](grader-execution/summary.json) | 1 | 0 | 0 |

The packaging binds the original 26 Sales test identities, including
three intentional skips, and all ten Spring identities. The graded
Spring reference used the same Java and Maven versions in an ARM64
runtime. Maven was offline with a read-only dependency cache. The
Sales grader needed the two pinned workbook libraries in its own image.
The initial missing-module attempt and both earlier Buildx charges
remain recorded. Both passing images are retained. The ordinary
executor removed only its own ephemeral grading containers.

The original task text and input bytes stay intact. The local recipe
keeps the calibration outputs private. Integration recipes can now use
their reviewed task cases and independent reference without duplicating
the public archive across extra literal fixtures. The older recipe
versions still require their original fixture counts. No solver or
model ran in these packaged checks.

The [ordinary CLI preparation](cli-preparation.json) defined both
recipes and showed both named workflows. The subsequent [approved
asset-use binding](../skillsbench-task-disclosure-20261105/result.json)
registered the two rights decisions and exact inert case sets. It did
not authorize provider dispatch. The [packaged managed workers](../skillsbench-managed-worker-preparation-20261105/README.md)
passed their offline tool checks. Both live
ordinary CLI journeys still require task worker conformance, exact
plan reviews and a bounded engineering dispatch approval.

See [joined results](joined-results.json) for image, receipt, case and
review links. Comparisons remain paused.
