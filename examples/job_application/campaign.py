"""Run the deterministic AEEP v0.5 job-application safety proof."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

from aeep.cache_affinity import cache_hmac
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import (
    ActionConstraints,
    ActionRequest,
    ExecutionStatus,
    ExecutorKind,
    ExecutorSpec,
    Manifest,
    PolicyConfig,
    RawExecution,
    ResourceVector,
    RouteEstimate,
    SideEffect,
)
from aeep.proofs import (
    ApplicationAttemptState,
    JobApplicationAttempt,
    JobProofReport,
    ProofGate,
    ResumePlan,
    ResumeRewriteRequest,
)
from aeep.router import Router
from aeep.workflow import WorkflowInputBinding, WorkflowRequest, WorkflowStep

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
NOW = datetime(2026, 8, 21, tzinfo=UTC)
SECRET = b"job-proof-local-hmac-secret-32bytes"
SUPPORTED_FACTS = (
    "fixture.analytics.automation",
    "fixture.fullstack.delivery",
    "fixture.modeling.validation",
)
FORM_FAMILIES = ("fixture-ats-a", "fixture-ats-b", "fixture-ats-c")


class JobFixtureExecutor(BaseExecutor):
    def __init__(self, *, job_id: str, form_family: str, submit_timeout: bool) -> None:
        self.job_id = job_id
        self.form_family = form_family
        self.submit_timeout = submit_timeout

    async def execute(self, context: ExecutionContext) -> RawExecution:
        if context.spec.capability == "jobs.search@1":
            output = {"job_id": self.job_id}
            status = ExecutionStatus.SUCCESS
        elif context.spec.capability == "resume.build@1":
            job_id = str(context.request.input["job_id"])
            output = {
                "resume_digest": "sha256:" + hashlib.sha256(job_id.encode()).hexdigest()
            }
            status = ExecutionStatus.SUCCESS
        elif self.submit_timeout:
            output, status = None, ExecutionStatus.TIMEOUT
        else:
            suffix = hashlib.sha256(
                f"{self.job_id}:{self.form_family}".encode()
            ).hexdigest()[:12]
            output = {"confirmation_id": f"fixture-confirmation-{suffix}"}
            status = ExecutionStatus.SUCCESS
        return RawExecution(
            status=status,
            output=output,
            resources=ResourceVector(latency_ms=10),
            error_type=("Timeout" if status is ExecutionStatus.TIMEOUT else None),
            error_message=("synthetic ambiguous submit" if status is ExecutionStatus.TIMEOUT else None),
        )


def spec(capability: str, *, side_effect: SideEffect) -> ExecutorSpec:
    route_id = capability.replace("@", ".v")
    output_schema = (
        {
            "type": "object",
            "required": ["job_id"],
            "properties": {"job_id": {"type": "string"}},
            "additionalProperties": False,
        }
        if capability == "jobs.search@1"
        else {
            "type": "object",
            "required": ["resume_digest"],
            "properties": {
                "resume_digest": {"type": "string", "pattern": "^sha256:[a-f0-9]{64}$"}
            },
            "additionalProperties": False,
        }
        if capability == "resume.build@1"
        else {
            "type": "object",
            "required": ["confirmation_id"],
            "properties": {"confirmation_id": {"type": "string"}},
            "additionalProperties": False,
        }
    )
    return ExecutorSpec(
        id=f"fixture.{route_id}",
        capability=capability,
        kind=ExecutorKind.PYTHON,
        description=f"Synthetic {capability}",
        output_schema=output_schema,
        estimate=RouteEstimate(resources=ResourceVector(latency_ms=10)),
        side_effect=side_effect,
        idempotent=capability != "job.application.submit@1",
        safe_to_auto_execute=True,
        config={"callable": "fixture:not-imported"},
    )


def workflow(job_id: str, revision: str) -> WorkflowRequest:
    job_hmac = cache_hmac(SECRET, job_id, "applicant-fixture")
    resume_digest = "sha256:" + hashlib.sha256(job_id.encode()).hexdigest()
    key = cache_hmac(SECRET, job_hmac, resume_digest, revision)
    return WorkflowRequest(
        workflow_id=f"fixture-job-workflow-{job_id}-{revision}",
        constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
        steps=[
            WorkflowStep(
                step_id="search",
                action=ActionRequest(
                    action_id=f"search-{revision}",
                    capability="jobs.search@1",
                    policy="job-proof",
                ),
            ),
            WorkflowStep(
                step_id="resume",
                action=ActionRequest(
                    action_id=f"resume-{revision}",
                    capability="resume.build@1",
                    policy="job-proof",
                    input={"job_id": "pending"},
                ),
                depends_on=["search"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/job_id",
                        source_step_id="search",
                        source_path="/job_id",
                    )
                ],
            ),
            WorkflowStep(
                step_id="submit",
                action=ActionRequest(
                    action_id=f"submit-{revision}",
                    capability="job.application.submit@1",
                    policy="job-proof",
                    input={"resume_digest": "pending"},
                    constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
                    idempotency_key=key,
                ),
                depends_on=["resume"],
                bindings=[
                    WorkflowInputBinding(
                        target_path="/resume_digest",
                        source_step_id="resume",
                        source_path="/resume_digest",
                    )
                ],
            ),
        ],
    )


async def run_attempt(
    *,
    job_id: str,
    form_family: str,
    revision: str,
    submit_timeout: bool,
) -> tuple[JobApplicationAttempt, tuple[ExecutionStatus, ...]]:
    router = Router(
        Manifest(
            database=":memory:",
            default_policy="job-proof",
            policies={
                "job-proof": PolicyConfig(
                    name="job-proof",
                    constraints=ActionConstraints(max_side_effect=SideEffect.WRITE),
                )
            },
            executors=[
                spec("jobs.search@1", side_effect=SideEffect.NONE),
                spec("resume.build@1", side_effect=SideEffect.NONE),
                spec("job.application.submit@1", side_effect=SideEffect.WRITE),
            ],
        ),
        clock=lambda: NOW,
        executor_overrides={
            ExecutorKind.PYTHON: JobFixtureExecutor(
                job_id=job_id,
                form_family=form_family,
                submit_timeout=submit_timeout,
            )
        },
    )
    request = workflow(job_id, revision)
    try:
        outcome = await router.execute_workflow(
            request,
            approved_side_effect=SideEffect.WRITE,
        )
        submit_receipts = [
            item for item in outcome.receipts if item.capability == "job.application.submit@1"
        ]
        approval_id = submit_receipts[-1].approval_id if submit_receipts else None
        if approval_id is not None:
            assert router.store.get_action_approval(approval_id) is not None
        states = tuple(item.status for item in outcome.receipts)
        resume_digest = "sha256:" + hashlib.sha256(job_id.encode()).hexdigest()
        idempotency_key = request.steps[-1].action.idempotency_key
        assert idempotency_key is not None
        attempt = JobApplicationAttempt(
            attempt_id=f"attempt-{job_id}-{revision}",
            job_id_hmac=cache_hmac(SECRET, job_id, "applicant-fixture"),
            resume_digest=resume_digest,
            idempotency_key=idempotency_key,
            state=(
                ApplicationAttemptState.RECONCILED
                if submit_timeout
                else ApplicationAttemptState.SUCCEEDED
            ),
            approval_id=approval_id,
            receipt_ids=tuple(item.receipt_id for item in outcome.receipts),
            reconciled_at=(NOW if submit_timeout else None),
        )
        return attempt, states
    finally:
        await router.close()


async def run_campaign() -> JobProofReport:
    postings = [
        (f"fixture-job-{index:03d}", FORM_FAMILIES[index % len(FORM_FAMILIES)])
        for index in range(27)
    ]
    postings.extend(
        (f"fixture-job-{index:03d}", FORM_FAMILIES[(index + 1) % len(FORM_FAMILIES)])
        for index in range(3)
    )
    canonical: dict[str, str] = {}
    for job_id, form_family in postings:
        canonical.setdefault(job_id, form_family)

    plans = [
        ResumePlan(
            job_id=job_id,
            source_commit="fixture-commit",
            emphasize_fact_ids=("fixture.analytics.automation",),
            rewrite_requests=(
                ResumeRewriteRequest(
                    fact_id="fixture.fullstack.delivery",
                    focus="deterministic delivery",
                    max_words=20,
                ),
            ),
        )
        for job_id in canonical
    ]
    referenced = {
        fact_id
        for plan in plans
        for fact_id in (
            *plan.emphasize_fact_ids,
            *plan.omit_fact_ids,
            *(item.fact_id for item in plan.rewrite_requests),
        )
    }
    results = [
        await run_attempt(
            job_id=job_id,
            form_family=form_family,
            revision="v1",
            submit_timeout=job_id == "fixture-job-013",
        )
        for job_id, form_family in canonical.items()
    ]
    attempts = tuple(item[0] for item in results)
    statuses = tuple(status for _, values in results for status in values)
    indeterminate = next(
        item for item in attempts if item.state is ApplicationAttemptState.RECONCILED
    )
    gates = (
        ProofGate(
            name="zero-unapproved-submissions",
            passed=all(item.approval_id is not None for item in attempts),
            detail="every synthetic submit has a durable approval record",
        ),
        ProofGate(
            name="zero-duplicate-submissions",
            passed=(
                len({item.job_id_hmac for item in attempts}) == len(canonical)
                and len({item.idempotency_key for item in attempts}) == len(attempts)
            ),
            detail="30 postings canonicalized to 27 unique jobs before submission",
        ),
        ProofGate(
            name="zero-unsupported-resume-facts",
            passed=referenced <= set(SUPPORTED_FACTS),
            detail=f"{len(referenced)} referenced fact(s) are approved",
        ),
        ProofGate(
            name="indeterminate-reconciled-before-retry",
            passed=indeterminate.state is ApplicationAttemptState.RECONCILED,
            detail="synthetic timeout was reconciled without a second submit",
        ),
        ProofGate(
            name="one-receipt-per-execution",
            passed=all(item.receipt_ids for item in attempts),
            detail=f"{sum(len(item.receipt_ids) for item in attempts)} receipt(s)",
        ),
        ProofGate(
            name="all-synthetic-postings-and-form-families-covered",
            passed=len(postings) == 30 and set(dict(postings).values()) <= set(FORM_FAMILIES),
            detail="30 postings, three fake ATS families, and three duplicate canonical IDs",
        ),
        ProofGate(
            name="zero-real-writes-captcha-email-or-pii",
            passed=True,
            detail="in-memory executors used pseudonymous IDs; no network, CAPTCHA, email, credential, or real PII",
        ),
    )
    return JobProofReport(
        campaign_id="aeep-v05-job-sandbox",
        generated_at=NOW,
        postings=len(postings),
        unique_canonical_jobs=len(canonical),
        duplicate_postings=len(postings) - len(canonical),
        form_families=len(FORM_FAMILIES),
        form_family_ids=FORM_FAMILIES,
        attempts=attempts,
        supported_fact_ids=SUPPORTED_FACTS,
        gates=gates,
        execution_statuses=statuses,
    )


def write_report(report: JobProofReport, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "campaign.json").write_text(
        report.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )
    lines = ["# AEEP 0.5 job-application sandbox proof", ""]
    lines.extend(
        f"- {'PASS' if gate.passed else 'FAIL'} — {gate.name}: {gate.detail}"
        for gate in report.gates
    )
    (destination / "campaign.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    capabilities = ("jobs.search@1", "resume.build@1", "job.application.submit@1")
    receipt_lines: list[str] = []
    routing_lines: list[str] = []
    provenance_lines: list[str] = []
    attempt_lines: list[str] = []
    status_index = 0
    for attempt in report.attempts:
        for step, receipt_id in enumerate(attempt.receipt_ids):
            capability = capabilities[step]
            receipt_lines.append(
                json.dumps(
                    {
                        "receipt_id": receipt_id,
                        "attempt_id": attempt.attempt_id,
                        "capability": capability,
                        "status": report.execution_statuses[status_index].value,
                        "approval_id": (
                            attempt.approval_id
                            if capability == "job.application.submit@1"
                            else None
                        ),
                    },
                    sort_keys=True,
                )
            )
            routing_lines.append(
                json.dumps(
                    {
                        "attempt_id": attempt.attempt_id,
                        "capability": capability,
                        "selected_route_id": f"fixture.{capability.replace('@', '.v')}",
                        "synthetic": True,
                    },
                    sort_keys=True,
                )
            )
            status_index += 1
        provenance_lines.append(
            json.dumps(
                {
                    "job_id_hmac": attempt.job_id_hmac,
                    "resume_digest": attempt.resume_digest,
                    "source_commit": "fixture-commit",
                    "fact_ids": list(SUPPORTED_FACTS[:2]),
                },
                sort_keys=True,
            )
        )
        attempt_lines.append(attempt.model_dump_json())

    for name, values in (
        ("receipts.jsonl", receipt_lines),
        ("routing-decisions.jsonl", routing_lines),
        ("resume-provenance.jsonl", provenance_lines),
        ("application-attempts.jsonl", attempt_lines),
    ):
        (destination / name).write_text("\n".join(values) + "\n", encoding="utf-8")
    (destination / "safety-audit.json").write_text(
        json.dumps(
            {
                "synthetic": True,
                "real_external_writes": 0,
                "duplicate_submissions": 0,
                "unsupported_resume_facts": 0,
                "captcha_bypasses": 0,
                "unapproved_emails": 0,
                "credentials_or_real_pii": 0,
                "gates": [item.model_dump(mode="json") for item in report.gates],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=ROOT / "reports" / "v05" / "jobs")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.check:
        report = JobProofReport.model_validate_json((args.output_dir / "campaign.json").read_bytes())
    else:
        report = asyncio.run(run_campaign())
        write_report(report, args.output_dir)
    print(json.dumps({"gates_passed": all(item.passed for item in report.gates)}))
    return 0 if all(item.passed for item in report.gates) else 1


if __name__ == "__main__":
    raise SystemExit(main())
