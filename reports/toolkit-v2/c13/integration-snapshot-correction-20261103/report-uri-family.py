"""Read-only URI family serialization for the completed canonical run.

All original validation in _run is preserved; only the legacy wire key is encoded.
This script cannot execute a task, review a grant, install or launch a model.
"""
from __future__ import annotations
import asyncio,hashlib,json,re,sys
from pathlib import Path
import integration as prepared
import run as original
from aeep_toolkit.managed import (AEEPAssessmentAdapter,ConfigurationError,ExecutionStatus,
 ExecutorKind,TOKEN_FIELDS,TokenObservation,EvaluationRun,content_digest,require_conformance,
 evidence_cohort_digest,BenchmarkTrial,ExecutionReceipt,comparison_summary)
from aeep_toolkit.models import SourcePin
from aeep_toolkit.reporting import render
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[3]
LABELS={}

def family_key(label):
 if re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9._:-]{0,199}',label):return label
 key='source-family:'+hashlib.sha256(label.encode()).hexdigest()
 LABELS[key]=label
 return key

class URIReportAdapter(AEEPAssessmentAdapter):
    async def evaluate(self,*_args,**_kwargs):raise RuntimeError('Read-only report adapter; execution is forbidden')
    def _run(self, trial: BenchmarkTrial, receipt: ExecutionReceipt) -> EvaluationRun:
        comparison = self.plan.comparison
        assert comparison is not None and comparison.experiment is not None
        metadata = receipt.metadata
        keys = (
            "protocol_version",
            "actual_model",
            "worker_digest",
            "host_runtime_digest",
            "boundary_digest",
            "task_instruction_sha256",
        )
        if receipt.executor_kind != ExecutorKind.MANAGED_HOST or any(
            not isinstance(metadata.get(key), str) or not metadata[key] for key in keys
        ):
            raise ConfigurationError(
                "observed host, model, worker, boundary or task-prompt binding unavailable"
            )
        if type(metadata.get("model_turn_count")) is not int or metadata["model_turn_count"] != 1:
            raise ConfigurationError("no single observed managed model turn")
        require_conformance(
            self.service.repository,
            metadata["boundary_digest"],
            source_digest=self.capabilities.implementation_sha256,
            worker_digest=metadata["worker_digest"],
            identity_digest=metadata["host_runtime_digest"],
        )
        spec = (
            self.mapping.candidate
            if trial.route_id == self.plan.candidate_id
            else self.mapping.baseline
        )
        config = spec.managed_host_config()
        expected_binding = evidence_cohort_digest(spec, receipt.action_features, metadata['host_runtime_digest'])
        if (receipt.executor_fingerprint, receipt.cohort_digest) != expected_binding:
            raise ConfigurationError('receipt executor or runtime cohort differs from the frozen route')
        if (
            config.adapter_id.split(":")[0] != "codex-app-server"
            or len(config.reasoning_efforts) != 1
        ):
            raise ConfigurationError("requires one pinned Codex effort")
        case = next((case for case in self.plan.suite.cases if case.case_id == trial.case_id), None)
        if case is None or trial.route_fingerprint != self.plan.route_fingerprints.get(
            trial.route_id
        ):
            raise ConfigurationError("trial is outside the frozen case or route binding")
        receipt_ref = content_digest(receipt)
        if any(
            getattr(receipt.actual_resources, field) != getattr(trial.actual_resources, field)
            for field in TOKEN_FIELDS.values()
        ):
            raise ConfigurationError("receipt usage differs from canonical trial measurements")
        if (
            trial.status != receipt.status
            or trial.host_models is None
            or trial.host_models.get(trial.route_id) != metadata["actual_model"]
            or trial.host_runtime_digests.get(trial.route_id) != metadata["host_runtime_digest"]
        ):
            raise ConfigurationError(
                "receipt status or observed identity differs from canonical trial"
            )
        observed = json.loads(metadata.get("codex_token_fields", "[]"))
        if not isinstance(observed, list) or any(
            not isinstance(key, str) or key not in {*TOKEN_FIELDS, "totalTokens"}
            for key in observed
        ):
            raise ConfigurationError("invalid token observation mask")
        tokens = None
        if observed and receipt.status == ExecutionStatus.SUCCESS:
            counts = {
                field: getattr(receipt.actual_resources, field) if wire in observed else None
                for wire, field in TOKEN_FIELDS.items()
                if field != "cache_write_input_tokens"
            }
            tokens = TokenObservation(
                source_ref=receipt_ref,
                cached_semantics="included_in_input",
                reasoning_semantics="included_in_output",
                **counts,
            )
        discovery = trial.capability_discovery or {}
        if discovery != (metadata.get("capability_discovery") or {}):
            raise ConfigurationError("candidate discovery differs from its canonical receipt")
        status = (
            "completed"
            if receipt.status == ExecutionStatus.SUCCESS
            else "timeout"
            if receipt.status == ExecutionStatus.TIMEOUT
            else "indeterminate"
            if receipt.status
            in {ExecutionStatus.UNKNOWN, ExecutionStatus.HOST_SELECTED, ExecutionStatus.DELEGATED}
            else "failed"
        )
        verification = "unknown"
        graded = (
            bool(case.validators)
            and len(trial.case_validation) == len(case.validators)
            and all(
                result.kind == validator.kind and type(result.valid) is bool
                for result, validator in zip(trial.case_validation, case.validators, strict=True)
            )
        )
        if graded:
            passed = all(result.valid is True for result in trial.case_validation)
            if passed != trial.valid:
                raise ConfigurationError(
                    "trial verification disagrees with its independent grader results"
                )
            verification = (
                "pass" if passed and status == "completed" else "fail" if not passed else "unknown"
            )
        return EvaluationRun.model_validate(
            dict(
                run_id=trial.trial_id,
                plan_ref=content_digest(self.plan),
                candidate_sha256=self.source.artifact_sha256,
                adapter_sha256=self.capabilities.implementation_sha256,
                host="codex",
                host_version=metadata["protocol_version"],
                model=metadata["actual_model"],
                effort=config.reasoning_efforts[0],
                shared_environment_sha256=comparison.experiment.environment.shared_definition_digest,
                worker_sha256=metadata["worker_digest"],
                task_sha256=content_digest(case),
                task_family=family_key(case.template_family or self.recipe.recipe_id),
                verifier_sha256=self.plan.recipe_digest,
                prompt_sha256=metadata["task_instruction_sha256"],
                arm="treatment" if trial.route_id == self.plan.candidate_id else "control",
                mode="optional"
                if comparison.experiment.exposure == "optional"
                else "forced_diagnostic",
                candidate_exposed=discovery.get("exposed"),
                candidate_invoked=discovery.get("invoked"),
                verification=verification,
                verification_ref=content_digest(trial) if verification != "unknown" else None,
                status=status,
                retries=trial.retry_fallback_count,
                evidence_kind="live",
                receipt_refs=(receipt_ref,),
                tokens=tokens,
                agent_wall_seconds=trial.wall_time_ms / 1000
                if trial.wall_time_ms is not None
                else None,
                verification_wall_seconds=trial.grading_wall_time_ms / 1000
                if trial.grading_wall_time_ms is not None
                else None,
                timing_source_ref=content_digest(trial),
                cash_accounting_ref=receipt_ref,
            )
        )

async def main():
 original.require_assets(prepared.load(HERE/'operation-review.json'))
 router=original.Router.from_manifest(prepared.WORK/'selected-manifest.json')
 try:
  service=original.AssessmentService(router,original.BASE/'.aeep/assessments')
  plan_id='plan_f966c3a56138439aa2aedd84cfe511cd'
  adapter=URIReportAdapter(service,plan_id,SourcePin.model_validate(prepared.load(HERE/'source.json')))
  before=original.counters(service.repository);job=adapter.preview()['job']
  assert job and job['state']=='complete' and job['error_code'] is None
  bundle=adapter.normalize(job['report_id']);details=adapter.details
  assert len(bundle.runs)==1 and not details['normalization_gaps'] and details['unresolved_operations']==0
  assert bundle.runs[0].verification=='pass' and bundle.runs[0].status=='completed' and bundle.runs[0].retries==0
  capture=details['telemetry_capture'][bundle.runs[0].run_id]
  assert capture['tokens']['status']=='verified' and capture['candidate']['instructions_loaded'] is True
  assert details['external_scheduler'].get('process_receipt_ref')
  summary=comparison_summary(adapter,bundle)
  summary['serialization_adaptation']={'source_family_map':LABELS,'reporter_sha256':prepared.sha(Path(__file__)),
   'canonical_plan_trial_receipts_and_statistics_unchanged':True,'new_model_or_trial_executions':0}
  summary['limitations'].append('Read-only URI-family serialization adaptation; original label is retained in source-family-map.json. The earlier failed export remains unchanged. This is the same single canonical trial, never an additional observation.')
  output=HERE/'unstarted-engines/ase-uri-report';output.mkdir(mode=0o700)
  for name,doc in [('toolkit-evidence',bundle.model_dump(mode='json')),('managed-evidence',details),('accounting-records',adapter.accounting_records),('summary',summary),('source-family-map',LABELS)]:prepared.write(output/(name+'.json'),doc)
  for kind,suffix in [('markdown','md'),('html','html')]:
   with (output/('report.'+suffix)).open('x') as f:f.write(render(summary,kind))
  assert original.counters(service.repository)==before
  result={'passed':True,'read_only':True,'same_canonical_trial':bundle.runs[0].run_id,'source_family_map':LABELS,
   'score':1,'token_capture':'verified provider_report, not independently verified usage','instructions_loaded':True,
   'candidate_semantic_invocation':'UNKNOWN','new_trials':0,'grant_unchanged':True,'original_empty_export_preserved':True,
   'candidate_usefulness':'NOT_ASSESSED','selection_usefulness':'NOT_ASSESSED'}
  prepared.write(HERE/'unstarted-engines/serialization-repair-result.json',result);print(json.dumps(result))
 finally:await router.close()

if __name__=='__main__':asyncio.run(main())
