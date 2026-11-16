# Sales Pivot handoff repair

The dispatch used an earlier Sales pair whose instructions said to treat
upstream absolute paths as private workspace paths. It omitted the explicit
mapping and output checks from the earlier successful [handoff
recovery](../skillsbench-sales-handoff-20261105/run.py). The upstream task
requests `/root/demographic_analysis.xlsx`, while the approved artifact reader
opens only `/workspace/demographic_analysis.xlsx`. The continuation applies the
[same handoff correction](sales_handoff.py) to both arms. It maps the public
inputs and output explicitly and calls for checking the exact output file type,
link count, readability and existing byte limit after saving. The workbook
requirements, grader and capacity limits are unchanged. The original trial
failure remains indeterminate because its receipt lacks the exact retrieval
error.

The [offline evidence](sales-handoff-offline-evidence.json) comes from the
[check script](check_sales_handoff.py) using both pinned Sales worker images.
Each disposable worker used network-none and had no mounts or model proxy
settings. The ordinary artifact writer delivered the exact 217,907-byte
approved public archive. A sandboxed command read the input archive and made
a synthetic OOXML workbook with the shared openpyxl installation. The ordinary
reader returned 176,292 bytes from control and 176,293 bytes from treatment
under the unchanged 300,000-byte ceiling. Host-side checks validated the
decoded bytes, digest, and required XLSX entries. Both workers rejected a
missing file, an overwrite, an oversized file, a symlink and a directory.
Both were removed. Offline preparation took 3.53 and 3.21 seconds of local
worker time, with zero model turns and zero cash.

The repaired live control delivered a 296,189-byte workbook through the
same reader and received a protected score of 0/1 after 173.32 seconds of
agent time. The treatment reached the fixed 300-second deadline before it
delivered an artifact. Its verified grade and token difference remain
unavailable. The [timeout reconciliation](sales-treatment-timeout.json)
settled the existing charge at 300.63 seconds after checking the canonical
timeout, partial accounting and worker cleanup. It preserves both earlier
reservations and records no new turn.
