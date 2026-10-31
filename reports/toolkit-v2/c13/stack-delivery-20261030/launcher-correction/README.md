# Correct the Docker launcher and use canonical receipts

This amendment permits one fresh availability attempt with the same specialist
software and boundary. The previous attempt failed at the Docker CLI before any
image or package installation. Its two operations, failed receipt and terminal
attempt remain intact. No old slot is refunded or reused.

The private Docker config now sets `cliPluginsExtraDirs` to the existing Docker
Desktop plugin directory. Its Buildx binary is pinned; no credential config is
read or copied. Help-only checks verify that the corrected launcher recognizes
the unchanged build flags. The receipt guard retains sanitized canonical records
while rejecting differences in identity, resources, accounting and journal bindings.

[The exact review](specialist-runtime-review.json) allows one private offline
build, three synthetic availability/boundary calls, at most six additional grant
operations and 600 reserved seconds. There are zero models, cash, execution-time
downloads, new dependencies, host installations, activation, release or deletions
of retained images. The resulting image is kept for the remaining work.

The original review explicitly forbids automatic retries after a started attempt.
Fresh specific approval is required. [Preparation checks](preparation-check.json)
passed without dispatch. No actual approval is recorded here yet.

After approval, record the actual user response and invoke `run.py` with this
review's complete SHA-256 from the repository root and `PYTHONPATH=src`. Inspect
durable started/results markers first. The driver uses existing assessment
reservations, scoped definition reviews, CommandExecutor, attempts, receipts and
journals. It creates no new runner or service. Do not invoke Docker commands
outside those controls or rerun a terminal driver.

This check cannot close working-stack integration, candidate usefulness or AEEP
selection usefulness. The reusable workflow and real-task comparisons remain
separate subsequent work, with applicable conformance and exact authority.
