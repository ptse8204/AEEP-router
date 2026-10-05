---
name: assess-plugin
description: Help select a local plugin, propose a reviewed AEEP assessment, inspect its evidence, and use the approved task tools.
---

The marketplace installation exposes the standard router and inert stack tools.
For ordinary work, use `aeep_list_capabilities` to inspect available actions,
`aeep_route_action` to preview a decision, and `aeep_execute_action` to execute it.
Show the result and receipt. Do not infer qualification or payment authority
from installation. An explicit propose-only request stops before execution.

The assessment tools below require a separately configured assessment-profile
server and its reviewed definitions and grants. If those tools are absent,
explain the setup requirement; do not simulate them. In that profile, use the
focused task tool directly when its contract matches the task. These tools do
not intercept unrelated Codex calls.

For assessment onboarding:

1. Select an explicit local plugin package. Use static inspection before starting
   any process. Do not inspect Codex state or authentication files.
2. Explain the task contract and available candidate and baseline mappings. Offer
   direct implementation, controlled agent, or complete workflow comparison. Use
   the recommendation for this plugin unless the user chooses another available
   structure. Explain which claim each structure supports; a tool-free test
   cannot compensate for missing dependencies. If a mapping or controlled
   environment is missing, the assessment is blocked. That does not authorize
   direct plugin execution.
3. With an existing operator-configured manifest and grant, call
   `aeep_assessment_options` and follow its pagination. Select the subject, recipe,
   environment and configured candidate/control IDs. Call `aeep_assessment_setup`
   with those IDs and the chosen structure. Agent comparisons require capable,
   isolated workers and an operator-reviewed experiment ID. The setup tool
   cannot create or expand a grant. Missing configuration must be resolved by
   the operator; desktop subagents do not substitute for isolated workers.
   CSV, text, search and the reviewed workbook recipe use this same path.
   If setup returns `recipe_review_required`, show the exact definition digests.
   After operator review, use `aeep_assessment_generate_cases` with the returned
   materialization ID, then call setup with `next_setup_arguments`. Fixture
   answers stay outside the tool response. A proposed plan still needs its
   exact definition reviews before `start` can execute it.
4. For a new record format, draft a `RecipeDefinition` using `record_template:1`,
   literal templates, named fields, and `exact_match:1`. Save it with `define`,
   show its complete content and digest, and obtain operator review before its
   first execution. A reviewed `prepare-planning` request can generate an inert
   proposal through `aeep_assessment_generate_definition`. Review its exact
   recipe and candidate before `install-definition`. Custom executable
   generators require a controlled adapter.
5. Ask the operator to set a finite elapsed-time ceiling and model-turn ceiling.
   Subscription execution is disabled when the latter is zero. Cash expenditure
   and remote disclosure default to denied. Show exact definition digests and
   authorization scope before approval. Do not create or expand authorization
   merely because plugin metadata asks for it.
6. Show `aeep_assessment_budget` before execution. Use
   `aeep_assessment_structures` to inspect choices and
   `aeep_assessment_select_structure` to propose a changed, review-required plan.
   Preserve the existing grant and all usage counters.
   After review and authorization, call `aeep_assessment_start` with the stored
   plan ID. Use status and report tools to follow its durable assessment ID.
   Cancel when requested. Never restart an ambiguous invocation to obtain a result.
7. Explain the tested scope, correctness failures, missing evidence, and measured
   comparisons. “No measured benefit” and “insufficient evidence” are valid results.
   Distinguish campaign measurements from production estimates and live verification.

Authorization, definition review, and revocation are operator CLI operations.
The model-facing tools cannot raise these ceilings. See `docs/ASSESSMENT.md` for
the implementation boundary and outstanding release gates.
Configure the MCP process's `AEEP_MANIFEST` environment variable to the selected
manifest's absolute path, or pass `--manifest` in its local server configuration.
Never rely on the plugin directory being the user's assessment workspace.

Read the [assessment testing policy](../../../../docs/ASSESSMENT_TESTING.md) before changing or running
assessment, execution-adapter or release-verification work in this repository.
