# Bounded integration grader deadline

Executable recipe extension v6 can bind a protected grader command up to
60 seconds. It requires an exact benchmark pack and a canonical integration
case set. Calibration sends one bounded example per grader call and reserves
the command deadline through the existing ledger. Generator and reference
commands still use 30 seconds. Extension versions v1 through v5 retain their
original command limits and serialized definitions.

The [two ordinary CLI previews](../skillsbench-ordinary-cli-preparation-20261105/README.md)
recorded a 42.97-second Spring Boot reference grader command. That is the
reason to make a longer protected deadline selectable. Sixty seconds is an
engineering ceiling for this extension. An actual recipe still needs to
choose and review its deadline against its packaged runtime.

The next SkillsBench step is the actual grader carrier. The ordinary
contained executor runs as UID 65534 with a read-only image, 32 MiB scratch
and no network. Keep the original test bytes and record the path adaptation
from `/root` or `/workspace` to private scratch. Bind the verifier and Maven
closure in the protected runtime. Verify the required Maven build and tests
with that actual containment. A deadline definition alone supplies no
rights, worker evidence, or authorization to run a task.

The [artifact bindings](managed-artifact-bindings.json) use the existing
managed single-file transport for the workbook and workspace ZIP. The
observed reference artifacts fit the draft bounds. The [retained image
check](retained-runtime-preflight.json) found the pinned runtimes after the
host cleanup. The bindings still require the actual protected carrier and
an applicable execution review.

The [verifier contracts](protected-verifier-contracts.json) bind the observed
test identities and intentional skips to the original verifier and negative
control records. They give the protected carrier an exact expected collection.

The [carrier audit](carrier-readiness.json) pins an existing nonroot
Sales parent. A compile-only check verified that the draft Sales verifier
changes only three file paths. Spring's 2,728 cached Maven files match
their lock and occupy 122 MiB. Keep that cache in the read-only runtime.
The build output and protected verdict boundary still need a contained
engineering check.

The [source verification](source-verification.json) is offline engineering
evidence. Both ordinary CLI workload execution gates remain open.
