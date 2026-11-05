# Native ToolHive build stopped after successful compilation

Under exact delegated first-attempt reviewa6a013aa, the real native sandbox
boundary and Go1.27.1 version check passed. The exact source/dependency/SDK
fingerprints passed before compilation. The offline compile command then exited0
and produced a128,306,930-byte binary with SHA256
`d74830a864e7f9d6227b03384ba76013c9b96dcceb70744f8353c6b61af97707`.
Networking was denied; the build used only the existing SDK and verified cache.

The pipeline stopped in the post-build input audit. Go serialized21 writable
`.info` cache files with a different Origin-field order. All source files, module
ZIPs and module files retain their original hashes. The metadata values also
remain the same: the original SHA256 for every changed file is reproduced by
putting Ref before Hash. The read-only diagnoses retain both hashes and the
matching encodings. No new data or measurements were invented.

The original summary leaves compiler_executed null because that field was assigned
only after the audit. Keep it unchanged. The separate successful process record
and new output binary establish that compilation produced an artifact. No
ToolHive version/help command or MCP server has run yet; do not mark the whole
pipeline or integration passed.

Four operations remain charged and settled at85.84042441658676seconds and zero
models. Cash/CPU/memory remain unknown. Old grants, images, volumes, user work,
source and caches remain. The immutable artifact-preservation recipe and corrected
post-build audit are prepared, unexecuted and pending specific repeat approval.
The continuation reuses this binary and runs only the three unstarted info
commands. No rebuild, download, source-suite, wheel or docs replay is proposed.

Source, SDK licenses and all343 selected dependency notice records remain private.
The memory/process proposals are finite engineering guards, not product budgets
or resource qualification. Both domain journeys and all-stack integration stay
open. Comparisons remain paused.
