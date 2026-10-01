"""Labelled local release fixture; never evidence of real plugin savings."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from pathlib import Path
from typing import Any, Literal

from ..errors import ConfigurationError, NoRouteError
from ..execution import EventJournal, ExecutionEvidence, start_execution
from ..models import (
    ActionRequest,
    ExecutionStatus,
    Manifest,
    RawExecution,
    StrictModel,
    new_id,
    utc_now,
)
from ..router import Router
from ..store import ReceiptStore
from .models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    AssessmentPlan,
    AssessmentReport,
    AssessmentRunBinding,
    ScopedAdmission,
    content_digest,
)
from .onboarding import reference_spec
from .recipes import reference_csv
from .repository import AssessmentRepository
from .service import AssessmentService


class ControlledFixtureRecord(StrictModel):
    schema_version: Literal['assessment.controlled-fixture.v1'] = 'assessment.controlled-fixture.v1'
    purpose: Literal['controlled local lifecycle fixture; not plugin savings'] = 'controlled local lifecycle fixture; not plugin savings'
    source_digest: str
    plan_id: str
    report_id: str
    admission_id: str
    receipt_id: str
    stale_decision_id: str
    rejection_evidence_digest: str
    baseline_decision_id: str


async def slow_reference(text: str, delimiter: str = ',') -> dict[str, Any]:
    await asyncio.sleep(.02)
    return reference_csv(text, delimiter)


async def run(directory: Path) -> ControlledFixtureRecord:
    from .verification import verification_source_digest

    await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
    manifest_path = directory / 'manifest.json'
    if manifest_path.exists():
        raise ConfigurationError('controlled fixture directory already contains a run')
    candidate = reference_spec('csv').model_copy(update={'id':'fixture.candidate'})
    baseline = candidate.model_copy(deep=True)
    baseline.id = 'fixture.baseline'
    baseline.config['callable'] = 'aeep.assessment.controlled_fixture:slow_reference'
    baseline.estimate.resources.latency_ms = 1000
    manifest_path.write_text(Manifest(database=str(directory / 'authority.sqlite3'), executors=[candidate,baseline]).model_dump_json())
    router = Router.from_manifest(manifest_path)
    service = AssessmentService(router, directory / 'assessments')
    try:
        selected = directory / 'fixture.txt'
        selected.write_text('Controlled local reference versus deliberately delayed reference. No plugin benefit claim.')
        subject = service.inspect_local(selected)
        plan = service.propose(subject_id=subject.subject_id, family='csv', candidate_id=candidate.id,
            baseline_id=baseline.id, authorization_id='controlled-fixture-only',
            environment=AssessmentEnvironment(environment_id='controlled-local',kind='trusted_local',identity={'purpose':'controlled fixture'}))
        for digest in plan.definition_digests:
            service.repository.review(digest)
        service.repository.grant(AssessmentAuthorization(authorization_id=plan.authorization_id,
            subject_digests=[plan.subject_digest],recipe_digests=[plan.recipe_digest],environment_digests=[plan.environment_digest],
            limits=AssessmentLimits(max_operations=5000,max_elapsed_seconds=600),automatic_admission=True,
            expires_at=utc_now()+timedelta(hours=1)))
        report = await service.run(service.enqueue(plan.plan_id))
        admission = service.admit(report.report_id)
        request = ActionRequest(capability=plan.suite.domain,input=plan.suite.cases[0].action.input)
        outcome = await router.execute(request)
        if not outcome.ok or outcome.receipts[-1].executor_id != candidate.id:
            raise ConfigurationError('controlled automatic-use fixture did not select the admitted candidate')
        stale = router.route(request.model_copy(update={'action_id':new_id('stale')}))
        service.repository.revoke_admission(candidate.id)

        async def rejected(journal: EventJournal) -> RawExecution:
            try:
                await router.execute(stale)
            except NoRouteError:
                journal.append('permission.denied','revoked-admission',action_digest=content_digest({'decision_id':stale.decision_id,'executor_id':stale.selected_executor_id}),evidence_ref=admission.admission_id)
                return RawExecution(status=ExecutionStatus.REJECTED)
            raise ConfigurationError('revoked stale decision was not rejected')

        rejection = await start_execution(new_id('stale-fixture'),'controlled-fixture',rejected).task
        evidence = ExecutionEvidence.model_validate(rejection.metadata['execution_evidence'])
        rejection_digest = service.repository.put('execution_evidence',evidence.digest(),evidence)
        baseline_decision = router.route(request.model_copy(update={'action_id':new_id('baseline-after-revocation')}))
        record = ControlledFixtureRecord(source_digest=verification_source_digest(Path(__file__).parents[3]),
            plan_id=plan.plan_id,report_id=report.report_id,admission_id=admission.admission_id,
            receipt_id=outcome.receipts[-1].receipt_id,stale_decision_id=stale.decision_id,
            rejection_evidence_digest=rejection_digest,baseline_decision_id=baseline_decision.decision_id)
        service.repository.put('controlled_fixture',content_digest(record),record)
        validate(router.store,record)
        (directory / 'evidence.json').write_text(record.model_dump_json(indent=2)+'\n')
        return record
    finally:
        await router.close()


def validate(store: ReceiptStore, record: ControlledFixtureRecord) -> None:
    from .verification import verification_source_digest

    repository = AssessmentRepository(store)
    if record.source_digest != verification_source_digest(Path(__file__).parents[3]):
        raise ConfigurationError('controlled fixture belongs to another source revision')
    plan = AssessmentPlan.model_validate(repository.get('plan',record.plan_id))
    report = AssessmentReport.model_validate(repository.get('report',record.report_id))
    binding = AssessmentRunBinding.model_validate(repository.get('run_binding',plan.plan_id))
    admission = ScopedAdmission.model_validate(repository.get('admission',record.admission_id))
    qualification = store.get_qualification_report(admission.qualification_report_id)
    receipt = store.get_receipt(record.receipt_id)
    stale = store.get_decision(record.stale_decision_id)
    baseline = store.get_decision(record.baseline_decision_id)
    revoked = store._connection.execute('SELECT revoked,revoked_at FROM assessment_admissions WHERE admission_id=?',(record.admission_id,)).fetchone()
    rejection = ExecutionEvidence.model_validate(repository.get('execution_evidence',record.rejection_evidence_digest))
    if (binding.source_digest != record.source_digest or report.plan_digest != content_digest(plan)
            or not report.qualification_passed or report.outcome != 'useful_within_scope'
            or admission.report_id != report.report_id or qualification is None or not qualification.passed
            or qualification.passed_cases < 100 or qualification.behavior_fingerprint != admission.candidate_fingerprint
            or receipt is None or receipt.status != ExecutionStatus.SUCCESS
            or receipt.executor_id != admission.executor_id
            or receipt.metadata.get('assessment_admission_id') != admission.admission_id
            or stale is None or stale.selected_executor_id != admission.executor_id
            or baseline is None or baseline.selected_executor_id != admission.baseline_id
            or revoked is None or revoked[0] != 1 or not revoked[1]
            or not rejection.complete or rejection.events[-1].kind != 'execution.failed'
            or not any(event.kind == 'permission.denied' and event.action_digest == content_digest({'decision_id':stale.decision_id,'executor_id':stale.selected_executor_id})
                       and event.evidence_ref == admission.admission_id for event in rejection.events)):
        raise ConfigurationError('controlled fixture lineage, admission, use or revocation evidence is incomplete')
    reference = receipt.metadata.get('execution_evidence_digest')
    if not isinstance(reference,str):
        raise ConfigurationError('controlled fixture invocation reference is missing')
    execution = ExecutionEvidence.model_validate(repository.get('execution_evidence',reference))
    if not execution.complete or execution.attempt_id != receipt.metadata.get('attempt_id'):
        raise ConfigurationError('controlled fixture invocation evidence is incomplete')
    from ..benchmarking import BenchmarkCampaignReport
    from .models import RecipeDefinition
    from .reporting import fit_report
    campaign = BenchmarkCampaignReport.model_validate(repository.get('campaign',report.campaign_digest))
    recipe = RecipeDefinition.model_validate(repository.get('recipe',plan.recipe_digest))
    replay = fit_report(plan,recipe,campaign)
    if (content_digest(campaign) != report.campaign_digest or not replay.qualification_passed
            or replay.outcome != report.outcome or not report.grader_validation_digest):
        raise ConfigurationError('controlled fixture campaign does not reproduce')


def verify(directory: Path) -> dict[str, object]:
    record = ControlledFixtureRecord.model_validate_json((directory / 'evidence.json').read_bytes())
    # The verifier reads authority records without constructing live adapters.
    manifest = Manifest.model_validate_json((directory / 'manifest.json').read_bytes())
    expected = (directory / 'authority.sqlite3').resolve()
    if Path(manifest.database).resolve() != expected:
        raise ConfigurationError('controlled fixture authority store is outside its directory')
    store = ReceiptStore(expected)
    try:
        validate(store,record)
        return record.model_dump(mode='json')
    finally:
        store.close()
