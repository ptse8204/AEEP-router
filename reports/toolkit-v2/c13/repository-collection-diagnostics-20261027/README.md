# Identify four collection failures before changing dependencies

This operator diagnostic is intended to explain why four public repository
references could not collect their tests. It reuses AEEP's existing assessment
service, controlled executor and durable accounting. No task grade, workload
eligibility, model comparison or admission can result from these observations.

| Failed reference | Exact retained image | Earlier result |
| --- | --- | --- |
| MCP Python SDK222 | `f60342e9` | Collection error, required55 identities absent |
| MCP Python SDK384 audit | `f60342e9` | Collection error, required5 identities absent |
| Twyn317 | `f60342e9` | Collection error, required43 identities absent |
| CanvasAPI716 | `b0eb4add` | Collection error, required62 identities absent |

The original observer retained statuses and exit codes but discarded exception
causes. Static imports do not establish the runtime cause, so dependency fixes
would currently be guesses. All four failures and their charges remain unchanged.

## Exact review

[Operation review](operation-review.json), SHA-256:
`faa107724324d63bebe2e6445bd2552e90496481b7e20f344a0db02914eb7ff9`.
Prepared only: no actual approval or new contained invocation is recorded.

The new collector keeps the original extraction, plugin order, Python bootstrap,
pytest arguments and child environment unchanged. It replaces the log reply with
exception categories and identifiers from a frozen public-source allowlist.
Raw logs, tracebacks, messages, source snippets, paths and arbitrary identifiers
stay inside the disposable container. A timeout or oversized log is explicit.
The coordinator validates the reply before retaining it. Facts reported by
untrusted test output guide review; they do not prove a cause or authorize a fix.

At most four offline calls use the same frozen reference payloads and images.
The only added input is the identifier allowlist, derived by parsing443 public
Python files as syntax trees without importing them. Completed source/image-bound
containment evidence is retained and checked; no redundant probes run. There is
no image build, installation, download, model turn, cash, credential access,
new external service/destination, package/docs rerun, activation or release.
All images and volumes remain. Only new attempt-owned containers are removed;
no host canaries or retained resources are created or deleted.

The bound is six existing-grant operations and290 reserved seconds:30 setup,
120 analysis and four calls at35 each. The hard review guard runs before every
reservation. Usage counters are never reset or refunded. Any uncertain authority,
transport, accounting, binding or cleanup stops dispatch. No automatic retry or
reuse of an unstarted slot is allowed.

## Preparation evidence

[Preparation checks](preparation-checks.json) bind37 assets, unchanged product source
`4cb0bf74`, four exact prior payloads and two retained image digests. Thirteen
sanitizer checks and seven budget guards passed. [The driver check](static-driver-check.json)
exercised actual definition storage, scope authorization and rejection of a seventh
operation in an isolated synthetic database, then removed that database. Three
whole-collector synthetic checks covered error, timeout and oversized output with
the child subprocess replaced; no subject or pytest code ran.

Earlier unexecuted review drafts are retained. One synthetic check failed because
its subprocess substitute omitted the standard-library `STDOUT` constant; the
substitute was corrected before the passing checks. The last scope reduction
removed six redundant probes and canaries. None of the drafts was approved or
executed. These checks do not count as repository observations.

## Resume after actual approval

Inspect the actual response and terminal markers. Record the exact approval once
in `operator-approval.json`, including this digest, then check the current grant
and reserve before running once from the repository root:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 reports/toolkit-v2/c13/repository-collection-diagnostics-20261027/run.py faa107724324d63bebe2e6445bd2552e90496481b7e20f344a0db02914eb7ff9
```

After terminal completion, run the first-party evidence audit once:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 reports/toolkit-v2/c13/repository-collection-diagnostics-20261027/audit-execution.py
```

If the collector identifies an applicable mismatch, review a bounded correction
against the public source and exact runtime before proposing further execution.
If it remains unknown, record that limit. Do not promote any case from this
operator diagnostic or retry a terminal review.
