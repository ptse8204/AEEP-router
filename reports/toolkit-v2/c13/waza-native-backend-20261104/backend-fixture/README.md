# One Waza engineering task

This first-party synthetic receipt task exercises Waza's pinned `copilot-sdk`
backend and built-in text grader in one run. The custom agent disables tools.
The grader checks the entire reply against a known answer. It uses no model.
The public disclosure scope consists of the task prompt and agent instructions.
The grader stays local. The planned run uses one trial, one attempt, no result
cache, no update check, and no external grader, MCP server or publication.

The ordinary installer retained the pinned Waza executable and its release
metadata. The [installation journal](waza-runtime-installation-result.json)
binds the installed tree to the exact review. Waza's real offline text grader
scored a synthetic correct reply 1/1 and a synthetic wrong reply 0/1. The
[offline grade receipt](offline-grader-result.json) records the settled check.
The ordinary import path treats supplied reports as upstream claims. The live
check must separately
link its exact inputs, backend launch, usage fields, grade, settled cost and
cleanup to an AEEP receipt. Missing usage or ambiguous outcomes keep the
functional check open.

The supported Copilot account setup remains an operator step. Check actual
account access and zero-cash allowance before preparing one exact live review.
The review must pin the native binaries, the credential boundary that permits
only supported Copilot operation, and the network destination. The earlier
bootstrap and mock reviews do not authorize this run. Keep the protected home
outside AEEP inspection and keep comparisons paused.
