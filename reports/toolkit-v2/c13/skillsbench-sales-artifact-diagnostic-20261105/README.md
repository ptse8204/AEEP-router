# Sales Pivot file handoff diagnostic

The [exact offline check](operation-review.json) ran the existing
artifact program as UID 65534 in the retained Sales worker image.
The [result](result.json) records a byte-identical 188,500-byte
round trip and rejection of missing, oversized, overwrite and
symbolic-link cases. No model, task asset or verifier ran. The
temporary container was removed and the one charge settled.

The prior live invocation returned a generic artifact error. This
check establishes that the same image and file-transfer program can
carry a workbook-sized payload. It cannot recover the discarded
live workspace or distinguish the live failure's underlying cause.
