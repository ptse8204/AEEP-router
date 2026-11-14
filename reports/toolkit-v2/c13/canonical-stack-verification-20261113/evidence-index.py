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
    "waza": (["waza-native-backend-20261104/summary.json", "waza-native-backend-20261104/backend-fixture/offline-grader-result.json"],
        "Native client passed version and containment. Waza's real offline grader accepted the correct synthetic reply and rejected the wrong one. Operator sign-in and a real backend grade are outstanding."),
    "skillrank": (["skillrank-cli-continuation-20261104/runtime-execution/summary.json",
                   "skillrank-managed-diagnostic-20261107/managed-result.json",
                   "canonical-stack-verification-20261113/skillrank-ledger-audit.json"],
        "Real search/show and the paired managed diagnostic passed. Their original ledgers verified read-only. The gate still needs current canonical bindings."),
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
    "langfuse": (["langfuse-ingestion-readback-20261105/service-execution/summary.json",
                  "canonical-stack-verification-20261113/domain-live-result.json"],
        "Private readback linked the Sales Pivot receipt and disabled export sent no POST. The export CLI recorded failed transport. Spring dispatch remains unstarted."),
    "langgraph": (["workflow-accounting-20261101/composed-sdk-runtime/execution/langgraph-sdk.json",
                   "workflow-accounting-20261101/composed-sdk-runtime/execution/summary.json"],
        "Four real SDK checks and six step receipts are retained. The bundle separately failed Agent Framework before its later correction. Current canonical integration binding remains open."),
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
        "Both checks have canonical settled receipts at the earlier source in readiness.json. Their source binding stays intact."),
    "workflow-document-data": (["canonical-stack-verification-20261113/skillsbench-engineering-outcomes.json"],
        "All three CLI task journeys reached grading. Sales Pivot telemetry linked with a failed CLI transport receipt. Composed canonical workflow registration remains open."),
    "workflow-software-engineering": (["canonical-stack-verification-20261113/skillsbench-engineering-outcomes.json"],
        "All three CLI task journeys reached grading. Spring telemetry and composed canonical workflow registration remain open."),
}


def index():
    snapshot = json.loads((HERE / "readiness-after-telemetry.json").read_bytes())
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
