# Bounded upstream issue review

These GitHub API snapshots supplement the original pinned-source review. Each
records its URL, observation time, returned page size, issue titles and bounded
body excerpts. Only the first 30 open issues/PRs sorted by update were requested;
PRs were excluded from the saved issue list. This is not an exhaustive issue or
security audit. No issue-body command was executed.

Selected integration concerns appear in the adjacent
[worksheet](../review-worksheet.json): Waza backend/sandbox support; SkillsBench
oracle and verifier consistency; MCPMark reset/timeout behavior; MCP-Universe
server-version reproducibility; scanner false positives; ToolHive error reporting;
LangGraph recovery; EvoAgentX shared state; AFlow dataset/generated-code execution;
Microsoft Agent Framework retries; and OpenTelemetry timeout semantics.

These are reported concerns, not reproduced defects at the recorded pins. They
supply future conformance cases, not evidence for installing or rejecting a whole
project. Missing entries do not imply absence of issues. The existing AEEP/ARD
boundaries remain recorded in the repository rather than inferred from this page.
