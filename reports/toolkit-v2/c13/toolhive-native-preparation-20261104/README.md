# Prepare ToolHive with the existing native Go SDK

This read-only inventory preserves ToolHive pin
`33ba170aad633e20520f380500a45cd158f24aed`. The selected `go.mod` declares
343 module versions; every one has both archive and module-file `h1` entries in
the pinned `go.sum`. The larger checksum inventory has 464 zip versions, including
versions not explicitly declared in this root file. This does not establish the
complete native build dependency graph.

The installed Go 1.27.1 SDK is fingerprinted, including its native ARM64 tools
and 15,570 source/toolchain entries. Source requires Go 1.27.0. No compiler was
executed and no module archive was downloaded. Build compatibility and dependency
licenses remain unverified. The SDK and all existing user resources are unchanged.

[The dependency inventory](dependency-inventory.json) binds source hashes,
declared versions, official proxy URLs and upstream checksums. The
[SDK inventory](sdk-source-inventory.json) binds the actual installed files and
records links without reading outside that SDK. These are metadata observations,
not installation, build or MCP isolation evidence.

Next, prepare a finite source/module acquisition and license review, then an
offline native build with a private module cache and networking disabled. Missing
dependencies must stop the build. Do not silently fetch them, replace the source
pin, read provider credentials or install another compiler. A separate applicable
execution review must cover the build and owned ToolHive/server lifecycle.

The pending Langfuse acquisition/wheel/docs review remains independent and
unchanged. Its completed source proof and reviewed input files were not edited.
No integration or usefulness gate is closed here. Comparisons remain paused.
