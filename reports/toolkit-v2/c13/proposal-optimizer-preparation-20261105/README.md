# EvoAgentX and AFlow integration preparation

The [source capture](source-contracts.json) verifies 19 contract files against
their pinned Git blobs. Source files remain private. No upstream optimizer,
model, generated workflow or benchmark ran in this step.

## EvoAgentX proposal path

Use the pinned `WorkFlowGenerator.generate_plan` and
`build_workflow_from_plan` methods. The first method calls the real upstream
task planner with a `BaseLLM` interface. Supply the response through the
existing approved worker and account for that turn. The second method derives
edges from the plan's declared ports. Normalize the result into an inert
AEEP `GoalSpec` with operator-allowed step and port bindings. It can then
use the existing stack planner's graph and eligibility checks.

The all-in-one workflow generation method can generate agents after planning.
This proposal integration will call only the planning and graph construction
methods. The `models` initializer eagerly imports several provider clients.
An isolated runtime needs those import dependencies, even with a managed
worker bridge. Its dependency closure and the real proposal run remain open.
[Pinned planner](https://github.com/ANative-Lab/EvoAgentX/blob/d77fd6b9a3e76c8dd83bebe3374c53a3f5d16f54/evoagentx/workflow/workflow_generator.py).

## AFlow finite optimizer path

AFlow's existing optimizer performs reference evaluation, proposes a
modification and evaluates the new round. Its standard graph loader imports
the generated Python, and the inner proposal loop can repeat independently of
the outer round ceiling. Use the optimizer in a reviewed isolated runtime.
Bind a single proposal request and stop at its allowance. Route evaluation
through the existing protected grader and charge its two calls separately
from optimizer overhead. Keep generated source in its owned sandbox, and
keep calibration inputs separate from any future usefulness study.
[Pinned optimizer](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer.py),
[pinned graph loader](https://github.com/FoundationAgents/AFlow/blob/3f457218fc716093fe53f6df8a5d5e6379d66346/scripts/optimizer_utils/graph_utils.py).

The [wheel selection](aflow-wheel-selection.json) resolves the unchanged
31-entry lock to exact Linux ARM64 wheels for CPython 3.12. The [acquisition
audit](aflow-wheel-acquisition-result.json) verified all 31 files, reused 12
local artifacts and found zero unresolved wheel requirements for that target.
The artifact total is 43,017,107 bytes. The private wheelhouse is retained.
The [runtime input acquisition](aflow-runtime-inputs-result.json)
also verifies 24 original source files and the exact portable CPython
3.12.16 Linux ARM64 archive. The retained Spring interpreter is x86-64.
The ARM64 artifact uses the same upstream release and matches the
compiled AFlow wheels. The optimizer imports the upstream benchmark
modules; close that source dependency set and bind the protected
calibration adapter before installation and execution. The source capture and wheel acquisition provide no
candidate or selection evidence.


## Retained offline build and pending check

The [offline build](aflow-runtime-build-receipt.json) installed the exact
wheel lock in the case-sensitive Linux guest and produced the retained
ARM64 image. The first [runtime check](aflow-runtime-result.json) stopped
before importing AFlow because the first-party sysfs interface-list
assertion failed. Both operations settled. The check container was
removed and the runtime image remains available.

The [exact continuation](namespace-check/operation-review.json) changes
only the probe. It checks the guest socket interface index and route
table, then runs the original AFlow graph-parser check. It uses the
same image with a single read-only probe mount, one offline operation,
and no model turn. The previous terminal check cannot be repeated
under its original authority. The continuation awaits operator approval.
