# C13 local Waza execution review

This review keeps Waza's evaluator and protected text grader and uses a local
Ollama model in place of the hosted Copilot model. The approved native Waza
runtime and pinned Copilot CLI 1.0.85 stay in the execution path. The SDK
uses its documented custom provider route. Waza's protected Copilot sign-in
remains unstarted and is unnecessary for this route.

The [exact review](operation-review.json) is **`25d22dca`**. It expires
November 18 at 2:06 p.m. Vancouver time. Execution awaits approval. Current
readiness stays at 37 of 39 and comparisons remain paused.

## Scope

- Acquire the publisher's Ollama 0.40.16 Darwin archive and five exact
  registry blobs for Qwen3-4B-Instruct-2507 Q4_K_M. The
  [checked model manifest](model-manifest.json) binds all blob sizes and
  hashes. The model license blob matched its Apache-2.0 notice. The artifact
  response body ceiling is 2,683,409,985 bytes. The review also pins the
  observed GitHub asset and Ollama registry storage redirect hosts.
- Install privately under `.aeep`. Check the archive digest, limit expansion
  to 1 GiB and verify the executable signature. Confirm that the host starts
  with at least 55 GiB free and preserve the 50 GiB host reserve. Retain the
  archive, verified runtime and model blobs for reuse.
- Start one owned Ollama service and a loopback gateway. Waza's sandbox can
  reach only the gateway. The sandboxed Ollama implementation uses loopback
  TCP for the model child. macOS's sandbox bind matcher also permits wildcard
  socket creation, so the pinned API and runner bind literal loopback and
  the driver checks the actual process-group listeners before accepting use.
- Run one uncached Waza task with grading disabled. The gateway permits one
  authenticated local completion using a temporary generated nonce. It
  sets a 128-token output ceiling, rejects tool activity and retains
  measured token counts and a reply digest. The grader definition and
  other local files are denied to the inference sandbox.
- Shut down the local processes. Pass only the verified reply into one
  network-denied Waza grading process using the original text assertion.
  Preserve the binary score, native receipts and settlement. Remove only
  the new owned scratch after cleanup is verified. An uncertain result
  preserves its reservation and prevents further dispatch.

The existing Waza grant receives a bounded amendment. The limit is four
additional operations, 1,815 reserved seconds, one local model turn, zero
remote model turns and $0 cash. The earlier six operations and their costs
remain. Reserved time sets a ceiling and does not estimate runtime.

## Evidence and continuation

[First-party preflight](preflight.json) verified 19 file pins. It checked the
sandbox boundaries, loopback ownership, request budget, artifact redirect
guard, archive rejection and copied-ledger accounting. The two grade
outcomes and reply mismatch control used synthetic replies. The retained
upstream offline grade is recorded separately. This preparation acquired
public release metadata and a license notice. Ollama software, model
weights and live replies are still absent. Runtime compatibility and the
protected score remain open.

The exact executable copy lives at
`.aeep/waza-ollama-20261115-exact/operation-review.json`. After explicit
approval, revalidate its digest, pins, host reserve, ports, expiry and grant
baseline. Record the matching approval next to that copy and invoke the
[reviewed driver](run.py) once. The [preflight](check.py) uses first-party
substitutes and leaves the live attempt unstarted. Terminal results require
receipt reconciliation before deciding whether any further approval is needed.

[Ollama release](https://github.com/ollama/ollama/releases/tag/v0.40.16)
· [Ollama model](https://ollama.com/library/qwen3:4b-instruct-2507-q4_K_M)
· [Pinned runner binding](https://github.com/ollama/ollama/blob/d63b702609c4300a2ca07be2bdb0adb9834725e5/llm/llama_server.go#L375)
· [Pinned Waza custom provider](https://github.com/microsoft/waza/blob/e534d149d89ae77ea158469fb4d2003804b2ee76/README.md#custom-copilot-sdk-providers)
· [GitHub SDK local provider](https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/byok#ollama)
