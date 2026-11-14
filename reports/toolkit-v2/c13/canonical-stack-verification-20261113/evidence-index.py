"""Index historical result files without converting them into current probe records."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
C13 = HERE.parent

OBSERVATIONS = {
    "agent-skill-eval": (["integration-snapshot-correction-20261103/completion-audit.json"],
        "Actual controlled dispatch and grading were reconciled. The current stack has no linked readiness probe."),
    "aeep-evaluator": (["integration-snapshot-correction-20261103/completion-audit.json"],
        "Actual managed engine and canonical recovery evidence exist. Register provenance through the current verification path."),
    "waza": (["waza-native-backend-20261104/summary.json"],
        "Native client passed version and containment. Operator sign-in and real backend grades are outstanding."),
    "skillrank": (["skillrank-cli-continuation-20261104/runtime-execution/summary.json",
                   "skillrank-certificate-deadline-20261107/native-check/native-check-result.json"],
        "Real search/show and synthetic-grade native scheduling ran. The paired managed diagnostic is still unstarted."),
    "skillsbench": (["canonical-stack-verification-20261113/skillsbench-engineering-outcomes.json"],
        "Six per-task CLI engineering results exist. The current gate still needs a protected-verifier and domain receipt binding."),
    "mcpmark": (["mcpmark-postgres-tool-schema-20261105/execution/summary.json",
                 "mcp-postgres-reference-results-20261105/results.json"],
        "Pinned PostgreSQL reference execution, rejection and cleanup passed. Current CLI component composition is pending."),
    "mcp-universe": (["mcp-universe-postgres-tool-schema-20261105/execution/summary.json",
                      "mcp-postgres-reference-results-20261105/results.json"],
        "Pinned PostgreSQL reference execution, rejection and cleanup passed. Current CLI component composition is pending."),
    "skill-scanner": (["scanner-fixture-continuation-20261103/cli-execution/summary.json"],
        "Ordinary CLI Cisco scan and proof linkage exist on the earlier source. Current checks need a receipt-bound observation."),
    "toolhive": (["toolhive-loopback-bind-20261104/summary.json"],
        "Real local server launch, inspection, invocation and stop passed. Current checks need a bounded service observation."),
    "semantic-conventions": (["langfuse-ingestion-readback-20261105/service-execution/summary.json",
                              "workflow-telemetry-20261104/runtime-execution/summary.json"],
        "Minimized OTLP and disabled-export checks exist. Current proof must link to each selected workload receipt."),
    "langfuse": (["langfuse-ingestion-readback-20261105/service-execution/summary.json"],
        "Private readback verified ingestion of the original trace without replay. Current workload trace links remain open."),
    "langgraph": (["full-stack-20261030/langgraph-bootstrap-repair/execution/summary.json"],
        "LangGraph's component check passed within a bundle whose overall result failed on another component. Verify the individual receipt chain."),
    "evoagentx": (["evoagentx-distribution-20261106/managed-turn/reconciled-result.json",
                   "evoagentx-distribution-20261106/planner-handoff/result.json"],
        "Actual managed proposal and upstream planner handoff exist. Register validation with the current coordinator."),
    "aflow": (["proposal-optimizer-preparation-20261105/calibration/finite-cycle/result.json"],
        "Finite upstream cycle, managed proposal and protected calibration grade exist. Current canonical link remains open."),
    "agent-framework": (["workflow-lifecycle-20261102/corrected-sdk-runtime/execution/framework-component-result.json"],
        "Actual SDK component calls exist. Link current workflow and interruption receipts."),
    "aeep-router": (["optional-router-20261104/summary.json"],
        "Installed CLI optional execution and independence passed on an earlier source. Current runtime linkage remains open."),
    "github-sponsors": (["canonical-stack-verification-20261113/sponsors-result.json"],
        "Both current checks have canonical settled receipts at the source in readiness.json."),
    "workflow-document-data": (["canonical-stack-verification-20261113/skillsbench-engineering-outcomes.json"],
        "All three CLI task journeys reached grading. A composed configuration still needs per-receipt telemetry, setup and removal evidence."),
    "workflow-software-engineering": (["canonical-stack-verification-20261113/skillsbench-engineering-outcomes.json"],
        "All three CLI task journeys reached grading. A composed configuration still needs per-receipt telemetry, setup and removal evidence."),
}


def index():
    snapshot = json.loads((HERE / "readiness.json").read_bytes())
    assert set(OBSERVATIONS) == {row["component"] for row in snapshot["components"]}
    return {
        "current_source": snapshot["implementation_source"],
        "comparison_dispatch": snapshot["comparison_dispatch"],
        "components": [{
            "component": row["component"],
            "expected_source_revision": row["source_revision"],
            "current_checks": row["checks"],
            "preserved_reports": [
                {"path": str(Path("..") / path), "sha256": hashlib.sha256((C13 / path).read_bytes()).hexdigest()}
                for path in OBSERVATIONS[row["component"]][0]
            ],
            "remaining": OBSERVATIONS[row["component"]][1],
        } for row in snapshot["components"]],
    }


if __name__ == "__main__":
    print(json.dumps(index(), indent=2))
