# Cached Git runtime: inherited-loader correction

The approved `a11807f2` attempt downloaded and verified the exact Git archive,
then stopped before Docker. Its expected dependency names omitted
`ld-linux-aarch64.so.1`. That system loader already exists in the retained parent.
The failed operation remains charged: **one operation, 2.9479576251469553 seconds**.
No image was built and no worker started. The exact number of network attempts
is unknown; the code allowed at most two. The verified archive and prepared
context remain unchanged.

[The parent audit](parent-ELF-audit.json) verified the image's configuration,
layers, loader path and aliases, and actual libc, PCRE2 and zlib files. It read
image data without starting a container or executing Linux code. The unchanged
230,109,184-byte owned export and ELF scratch were removed. All images and
existing containers remain untouched.

[The context audit](cached-context-audit.json) verifies all 19 prepared files,
modes, copyright, archive and actual ELF dependencies. The new verifier reads
this existing context; it cannot download, extract, install packages or mutate
the files. Seven authored guards and the actual verifier passed. The actual
driver's stale-pin stop, definition/budget and image-binding fixtures also passed.
Fixtures do not supply runtime authority or benchmark evidence.

The new exact review is [runtime-review.json](runtime-review.json), SHA-256
`d1caf28bf7a888cd02acbc7fc56986bfc147028e68818a505410557bc521a677`.
Its nested audit verifies 149 assets and 305 unique file bindings across three
execution reviews. It permits, only after actual approval:

- Zero downloads or extraction. Reuse the same Git bytes, templates, copyright
  and COPY-only Dockerfile. No library or package is added.
- One local image build from the same retained `9f473c49` parent, with unchanged
  inherited configuration/layers, three COPY layers and at most 16 MiB growth.
- The same fresh boundary, native-event, Git/linker/local-command and Identify
  checks; all 38 Dead obligations and frozen 171-test JSON-logger controls remain.
- At most 21 offline calls, 26 additional existing-grant operations and
  1,335 reserved seconds. Preserve the prior failed operation and all counters.
- Keep all images, context, cache and receipts. Remove only new owned containers
  and the unchanged canary; preserve at least 50 GiB host free.

No models, cash, credentials, external services, host activation, publication,
release or retained-resource deletion is included. Completed source, package and
docs checks are not repeated. A new actual approval is needed because the
terminal exact review forbids retries and changes to its dependency expectation.

After approval and a current grant/expiry check, run once:

```bash
PYTHONPATH=src /Library/Frameworks/Python.framework/Versions/3.13/bin/python3 reports/toolkit-v2/c13/repository-cached-git-20261029/run-bundle.py d1caf28bf7a888cd02acbc7fc56986bfc147028e68818a505410557bc521a677
```

The pool remains **64 provisional cases, with 77 missing**. No task stage,
qualification, comparative usefulness, live selection, resource acceptance or
release gate closes from this static preparation. The actual contained checks
are still pending.
