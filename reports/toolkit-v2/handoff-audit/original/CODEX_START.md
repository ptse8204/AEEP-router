# Start AEEP Toolkit work in Codex with one prompt

## Installation of this handoff

This bundle contains `docs/aeep-toolkit/` with all planning, checkpoint, research and continuation documents. Copy/extract that directory into the root of a checkout of `https://github.com/ptse8204/AEEP-router`. Prefer a new feature branch. Do not overwrite a pre-existing `docs/aeep-toolkit` directory without inspecting/merging it.

No source code was changed as part of this handoff. Source hash observed while preparing this document: `8b015bf0247d4d9f49038982c49f3711a2802d97` on `main` (may now be stale).

## One prompt to paste into Codex

> You are responsible for implementing the AEEP Evaluation Toolkit V2 rearchitecture in this repository. Read `AGENTS.md`, `docs/ASSESSMENT_TESTING.md`, and **all** `docs/aeep-toolkit/` documents. `docs/aeep-toolkit/MASTER_PROMPT.md` is the complete product steering instruction; `CHECKPOINTS.md` is the acceptance-gated roadmap, `STATE.md` is durable actual progress, and `CONTINUATION.md` explains how to resume after context resets. Follow existing project security and authorization policies. Start at C00 and implement/verify consecutive safe checkpoints, updating and committing evidence and state at each milestone; proceed without requesting a new steering prompt for each checkpoint. Do not install unknown code, run paid trials, change host-global config, publish or weaken controls without proper approval. If a gate is externally blocked, document precisely and continue independent safe work. Preserve legacy AEEP functionality as optional extensions. Keep the product purpose focused on plugin-value evidence, token/time/quality/cost measurements, and developer support. No untested completion claims. Begin now.

## Reuse on a new Codex context/session

> Resume AEEP Toolkit V2 from the repository. Read `AGENTS.md` and `docs/ASSESSMENT_TESTING.md`, then `docs/aeep-toolkit/STATE.md`, `CHECKPOINTS.md`, `CONTINUATION.md`, `README.md` and `ACCEPTANCE.md`. Validate the last recorded evidence; continue the earliest eligible checkpoint and commit updated state. Do not rely on the prior conversation.

## Optional note for repository `AGENTS.md`

To make new Codex sessions automatically aware of this track, after evaluating normal repository instruction precedence and permissions, append the following *non-overriding* pointer to `AGENTS.md` on the project feature branch:

> **AEEP Evaluation Toolkit V2 track:** When working on the evidence-first modular toolkit, read `docs/aeep-toolkit/STATE.md`, `CHECKPOINTS.md`, `CONTINUATION.md`, and `README.md` before modifying it. All pre-existing safety, approval, assessment and release instructions above remain in force. Chat history is not the project record.

Do not blindly append twice; preserve existing AGENTS content and do not amend historical test rules.
