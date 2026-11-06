# Financial Modeling QA and Dependency Audit runtime inspection

The [first acquisition](../skillsbench-financial-audit-acquisition-20261105/acquisition/summary.json)
verified two published Linux amd64 image identities and layer lists. Their
combined compressed layer size is 501,413,529 bytes. Actual transferred bytes
were unmeasured. Five acquisition operations settled at 54.82 seconds with
zero models. The images remain available.

The [static audit](summary.json) matched the pinned Financial Modeling workbook
and PDF, and the Dependency Audit lockfile. Two named, network-denied inspection
containers were created and never started. The audit retained hashes and
container identities. No solver, verifier, model or candidate ran.

## Financial Modeling QA asset rights

The source PDF's title identifies the ModelOff Roll the Dice case. The DSBench
item independently attributes it to the same publisher listing. The public
download listing supplies a workbook and PDF. Eloquens' terms describe
use-specific download agreements and restrict redistribution. The exact
benchmark copies have no recorded permission for provider disclosure or
packaging in AEEP. Keep the task blocked pending a rights record.
[Publisher listing](https://www.eloquens.com/tool/J1GcKr/finance/modeloff-sample-past-questions/2016-round-1-section-3-roll-the-dice),
[DSBench source attribution](https://huggingface.co/datasets/liqiang888/DSBench/blob/62722a6857cadaedaac0eaa60b364ea0142ad46f/data_analysis/data.json),
[Eloquens terms](https://www.eloquens.com/about/terms).

`invoice-fraud-detection` is a concrete substitute at the same SkillsBench
revision. The task is labeled hard and asks the agent to reconcile PDFs,
a workbook and purchase-order CSV with protected grading. Its files are
committed in the upstream task tree. It needs its own asset-rights and runtime
review before use. Replacing the named original requires the operator's
decision. The original contribution records the addition of deliberately
clean and fraudulent samples and the switch to a static ground truth.
This supports a separate provenance review of the proposed replacement.
[Pinned candidate task](https://github.com/benchflow-ai/skillsbench/tree/9a1f4dd5f7659f75707435da3ce854b6e48321d1/tasks/invoice-fraud-detection),
[original contribution](https://github.com/benchflow-ai/skillsbench/pull/105).

## Dependency Audit runtime data

The Dockerfile acquired the Trivy database from the task author's separate
Hugging Face repository. The publisher tree exposes an archive and attributes
file and supplies no license document or dataset card. The retained image
pins those runtime bytes through its layers. Before using the database,
establish its embedded metadata and original source attribution. Keep the
database outside any provider disclosure. [Pinned Dockerfile](https://github.com/benchflow-ai/skillsbench/blob/9a1f4dd5f7659f75707435da3ce854b6e48321d1/tasks/software-dependency-audit/environment/Dockerfile),
[database archive listing](https://huggingface.co/datasets/zodi1121/skillbench-software-db/tree/main),
[dataset card](https://huggingface.co/datasets/zodi1121/skillbench-software-db).

The [retained image metadata](trivy-metadata.json) identifies Trivy database
schema 2 and a January 21, 2026 snapshot. Its Java database metadata was absent
at the inspected path. The selector never started the container or copied
the database itself. Snapshot metadata does not establish the source license.

The [protected verifier preparation](dependency-audit-protected-preparation.json)
binds the original Dependency Audit verifier and all seven collected
identities, including its four parameterized checks. It reuses the retained
grader carrier. The only verifier change is the explicit output path in the
isolated scratch directory. Reversing that replacement restores the original
bytes. No original assertion, skip or score meaning changed. Runtime
compatibility, reference success and failure controls remain open.
Candidate and selection comparisons remain paused.
