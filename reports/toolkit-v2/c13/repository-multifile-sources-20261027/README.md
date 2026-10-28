# Four multi-file repository repairs — execution complete

These tasks test whether a repair preserves behavior across two functional source
files. Static review selected Canopen613,WebAuthn241 andXsdata1126/1132,with125
required test identities and16 reference/counterexample/partial-repair variants.
Each partial restores one changed source file. [Actual results](RESULTS.md) admit
only Canopen to the provisional pool. No model or candidate ran here.

## Curation and exclusions

Fourteen bounded public source reads retained9,379,970bytes. Eleven snapshots
passed the initial file-safety screen,two contained prohibited members/paths,and
Csvkit exceeded the3.5MB cap and remains a partial read. Seven initial inert cases
were prepared. Pymdown2576/2807 each change one functional file and a version
constant;they cannot count as multi-file behavior repairs. Pyinfra needs its
project entrypoints/dynamic metadata and a broader gevent/SSH runtime,and remains
deferred. Raygun/Fromager change packaging outside this existing-source task
profile. Dataclasses-avroschema has only one functional body change. Pyserde adds
`examples/type_statement.py`;the current profile permits existing-file edits only.
[The original errors](prepared-cases.json) and [precise dispositions](curation-dispositions.json)
remain;no required change or assertion was dropped to make a case fit.

## Optional grader runtime

[Eight official cached wheels](runtime-support-review.json) total5,852,012bytes:
python-can4.6.1,canmatrix1.2,asn1crypto1.5.1,cbor2 5.6.5,pyOpenSSL25.3.0,lxml6.0.2,
docformatter1.7.5 andtoposort1.10. Only lxml is native;its CPython3.13 Linux aarch64
wheel is pinned. Added requirements close against versions actually asserted by
the completed parent-image probes,not an assumed whole-image inventory.

Untokenize0.1.1 has no compatible published wheel. The plan copies its unchanged
2,634-byte upstream module,in-file permission notice and exact publisher
PKG-INFO as dist-info METADATA. Its setup.py is never run. This identifies an
upstream source copy,not a wheel installation;no version or license is invented.
A fresh probe must verify source/metadata hashes,image locations and behavior.
Ruff and unrelated project extras are not installed:the selected Xsdata tests do
not invoke the generator's Ruff subprocess. No core dependency or service changes.

## Exact pending execution

[The combined review](approval-bundle.json) binds one private offline image build
from retained2386,eight cached wheels and the unchanged upstream source/metadata
copy. It permits four fresh probes and16 fixed variants. Output image identity
must be bound before calls;parent layers/configuration must remain,with exactly
three new filesystem layers and at most96MiB growth. Keep50GiB free and all images.
These are finite check limits,not production resource acceptance criteria.

The cumulative maximum is24 calls,29 existing-grant operations and1,320 reserved
seconds. Initial maximum:20 calls/23 operations/1,030seconds. Four extra calls and
one additional setup/analysis phase cover only recorded same-software report
controls after known completion/cleanup. No uncertain replay,refund,source/test/
reference change,extra build or permission widening is allowed. No models,cash,
downloads,pulls,credentials,services,host/project installers,activation or release.
Cached offline documentation checking is the second exact component. No unchanged
source suite,package build or installation journey is repeated.

Static checks verify16 payload derivations,20 grader guards,22 classifier guards,
the image-bound derivation and actual budget enforcement. They do not establish
runtime compatibility or benchmark value. Source374579f1 remains unchanged,with
its previous all13 gates,installed wheel9b00 checks and actual corrected-worker
execution intact. [The56-case pool](../repository-worker-input-20261027/provisional-pool.json)
retains every historical binding;85cases remain. Qualification,usefulness,
selection,resource,human and release gates stay open.

## Resume

The approved bundle completed once. Read [actual results](RESULTS.md) and
[canonical accounting](final-accounting-audit.json). Do not rerun this driver.
The new task-contract/plugin review is prepared separately; no unused slot or
changed-payload authority transfers. Source verification and package checks remain
current. The earlier preparation sections describe the frozen scope, not four
successful reproductions.
