"""Bind the fixed upstream worker fixture to existing AEEP analysis and C02 reports."""
import hashlib
import json
from pathlib import Path

from receipts import FixtureRecord

from aeep.assessment.models import (
    AssessmentComparison,
    AssessmentPlan,
    RecipeDefinition,
    content_digest,
)
from aeep.assessment.reporting import fit_report
from aeep.benchmarking import BenchmarkCampaignReport, BenchmarkCase, BenchmarkSuite, BenchmarkTrial
from aeep.models import ActionRequest
from aeep_toolkit.cli import read_bytes
from aeep_toolkit.models import (
    AdapterCapabilities,
    ComparisonReport,
    EvaluationRun,
    EvidenceBundle,
    SourcePin,
)
from aeep_toolkit.reporting import render, summarize


def freeze(repository, request, suite, spec):
    """Freeze the expected positions and unchanged legacy thresholds before dispatch."""
    recipe = RecipeDefinition(recipe_id='toolkit.synthetic', capability=spec.capability,
        description='Engineering fixture only; no real holdouts or model value', input_schema={'type':'object'},
        output_schema={'type':'string'}, generator='fixed-fixture:1', grader='upstream-independent-fixture:1',
        extractor='fixed-case:1', variations=[case['id'] for case in suite['evals']])
    recipe_ref = repository.put('recipe', request.plan_id, recipe)
    comparison = AssessmentComparison(structure='direct', primary_condition='fresh-worker',
        candidate={'executor_id':'treatment','fingerprint':content_digest(spec),'dependencies':{}},
        baseline={'executor_id':'control','fingerprint':content_digest(spec),'dependencies':{}})
    comparison_ref = repository.put('comparison', request.plan_id, comparison)
    plan = AssessmentPlan(schema_version='assessment.plan.v2', plan_id=request.plan_id,
        subject_digest=request.subject_digest, recipe_digest=recipe_ref, mapping_digest=request.mapping_digest,
        environment_digest=request.environment_digest, authorization_id=request.authorization_id,
        candidate_id='treatment', baseline_id='control', definition_digests=[recipe_ref,comparison_ref],
        route_fingerprints={arm:content_digest(spec) for arm in ('control','treatment')},
        suite=BenchmarkSuite(suite_id=request.plan_id, domain='synthetic-upstream-harness', repetitions=1,
            routes=[{'route_id':arm,'executor_id':arm} for arm in ('control','treatment')], conditions=['fresh-worker'],
            cases=[BenchmarkCase(case_id=c['id'], split='holdout', action=ActionRequest(capability=spec.capability,input={'prompt_sha256':content_digest({'prompt':c['prompt']})}),
                                 variation=c['id'],template_family=c['id']) for c in suite['evals']]),
        applicability={'evidence_kind':['synthetic']}, comparison=comparison, feature_combinations=[{'fixture':True}])
    repository.put('toolkit_analysis_plan', request.plan_id, plan)
    repository.review(recipe_ref)
    repository.review(comparison_ref)
    return plan, recipe


def create(output, repository, plan, recipe, definition, environment, results, rows, *, artifact_root=None, incomplete=False):
    cases = {case.case_id:case for case in plan.suite.cases}
    expected = {(case,arm) for case in cases for arm in ('control','treatment')}
    positions = {(r['case'],r['arm']) for r in results}
    graded = {(r['case'],'treatment' if r['arm']=='with_skill' else 'control'):r for r in rows}
    if (len(positions) != len(results) or not positions <= expected
            or len(graded) != len(rows) or not set(graded) <= positions
            or any(r['arm'] not in {'with_skill','without_skill'} for r in rows)
            or (not incomplete and (positions != expected or set(graded) != expected))):
        raise ValueError('missing, duplicate or unreviewed trial positions')
    trials, runs = [], []
    source = SourcePin(**definition.facts['stack']['fixture_source'])
    adapter_hash = definition.facts.get('review_sha256') or content_digest(definition)
    verifier_hash = hashlib.sha256(read_bytes(Path(__file__).resolve())).hexdigest()
    adapter = AdapterCapabilities(adapter_id='agent-skill-eval.controlled-fixture', implementation_sha256=adapter_hash,
        hosts=('fake',),candidate_types=('skill',),optional_invocation=True,telemetry=(),containment='unverified')
    for result in results:
        row = graded.get((result['case'],result['arm']))
        operation = result['operation_id']
        receipt = repository.store.get_receipt(result['receipt_id'])
        frozen_receipt = repository.get('toolkit_controlled_receipt', operation)
        if (receipt is None or content_digest(receipt) != result['receipt_ref']
                or content_digest(frozen_receipt) != result['receipt_ref']
                or (not incomplete and not receipt.execution_success)
                or receipt.metadata.get('case') != result['case'] or receipt.metadata.get('arm') != result['arm']):
            raise ValueError('worker receipt differs from canonical trial')
        if row is not None:
            artifact = (artifact_root if artifact_root is not None else output/'upstream')/row['artifact']/'outputs/output.txt'
            if not receipt.execution_success or hashlib.sha256(read_bytes(artifact)).hexdigest() != result['output_sha256']:
                raise ValueError('graded output differs from worker result')
        verification = FixtureRecord(facts={'row':row,'output_sha256':result['output_sha256'], 'verifier_sha256':verifier_hash})
        verification_ref = repository.put('toolkit_controlled_verification', operation, verification)
        passed = row['verified'] if row is not None else None
        trials.append(BenchmarkTrial(trial_id=operation,run_id=plan.plan_id,suite_id=plan.suite.suite_id,
            case_id=result['case'],route_id=result['arm'],route_fingerprint=plan.route_fingerprints[result['arm']],
            condition='fresh-worker',repetition=0,phase='holdout',state='complete' if receipt.execution_success else 'failed',
            ok=receipt.execution_success,valid=passed,status=receipt.status,
            correctness_failed=not passed if passed is not None else None,receipt_ids=[receipt.receipt_id],
            accounting=receipt.accounting))
        case = cases[result['case']]
        status = {'success':'completed','failed':'failed','rejected':'failed','timeout':'timeout'}.get(receipt.status.value,'indeterminate')
        runs.append(EvaluationRun(run_id=receipt.receipt_id,plan_ref=content_digest(plan),candidate_sha256=source.artifact_sha256,
            adapter_sha256=adapter_hash,host='fake',host_version='agent-skill-eval-0.7.0',model='synthetic-no-model',effort='none',
            shared_environment_sha256=content_digest(environment),worker_sha256=content_digest({'environment':content_digest(environment),'worker':result['worker_name']}),
            task_sha256=content_digest(case),task_family=result['case'],verifier_sha256=verifier_hash,
            prompt_sha256=case.action.input['prompt_sha256'],arm=result['arm'],mode='optional',
            candidate_exposed=result['candidate_exposed'],candidate_invoked=None,
            verification='unknown' if passed is None else 'pass' if passed else 'fail',
            verification_ref=verification_ref,status=status,retries=0,evidence_kind='synthetic',receipt_refs=(result['receipt_ref'],)))
    campaign = BenchmarkCampaignReport(run_id=plan.plan_id,suite_id=plan.suite.suite_id,domain=plan.suite.domain,
        deterministic_tools_available=True,pricing_snapshot_ids=[],frozen_holdout_decisions={},trials=trials,
        summaries=[],baseline_deltas=[],oracles=[],subscription_conservation=[])
    ledger = repository.operation_ledger(plan.plan_id)
    analysis = fit_report(plan,recipe,campaign,ledger=ledger)
    if analysis.qualification_passed or analysis.outcome == 'useful_within_scope':
        raise ValueError('fixed engineering fixture cannot qualify or demonstrate benefit')
    campaign_ref = repository.put('toolkit_controlled_campaign',plan.plan_id,campaign)
    analysis_ref = repository.put('toolkit_controlled_analysis',plan.plan_id,analysis)
    bundle = EvidenceBundle(candidate=source,adapter=adapter,runs=tuple(runs))
    bundle_ref = repository.put('toolkit_controlled_bundle',plan.plan_id,FixtureRecord(facts=bundle.model_dump(mode='json')))
    comparison = ComparisonReport(evidence_bundle_ref=bundle_ref, plan_ref=content_digest(plan),
        outcome='INCONCLUSIVE' if results else 'NOT_ASSESSED', evidence_kind='synthetic', analysis_ref=analysis_ref,
        limitations=('Scripted engineering trials cannot establish real candidate value.',
                     'Existing qualification and paired-case thresholds remain unchanged.'))
    comparison_ref = repository.put('toolkit_controlled_comparison', plan.plan_id, FixtureRecord(facts=comparison.model_dump(mode='json')))
    summary = summarize(bundle)
    summary['comparison'] = comparison.model_dump(mode='json')
    summary['comparison_ref'] = comparison_ref
    summary['reviewed_analysis'] = {'plan_ref':content_digest(plan),'analysis_ref':analysis_ref,'campaign_ref':campaign_ref,'bundle_ref':bundle_ref,
        'outcome':analysis.outcome,'qualification_passed':False,'minimum_holdout_cases':recipe.minimum_holdout_cases,
        'minimum_paired_cases':recipe.minimum_paired_cases,'expected_trial_positions':len(expected),
        'matched_receipts':len(results),'missing_trial_positions':len(expected-positions),
        'unresolved_operations':sum(operation.elapsed_seconds is None for operation in ledger.operations),
        'worker_operation_seconds_known':sum(operation.elapsed_seconds for operation in ledger.operations if operation.elapsed_seconds is not None),
        'worker_operations_measured':sum(operation.elapsed_seconds is not None for operation in ledger.operations),
        'worker_operations_reserved':len(ledger.operations),
        'model_tokens':None,'model_wall_seconds':None,'actual_cash':None,
        'cost_per_verified_success':None,'recurring_fee_break_even':None}
    summary['limitations'][:0] = [
        'Scripted scope: separate network-disabled workers receive only their current case; treatment also receives the captured candidate. No model, credential or billing calls are permitted.',
        'This evaluation creates its result directory and temporary workers. It does not activate a host connection or persistent service, so there is no ongoing service to pause after completion. A different run needs its own exact plan review.',
        'Stop this foreground run with Ctrl-C; interruption does not prove cleanup. Preserve the result directory and receipts.sqlite3. Do not replay execution into it or refund unresolved operations.',
        'Inspect without dispatch: aeep-toolkit eval scripted report --output /absolute/result-directory. Receipt references resolve in receipts.sqlite3; result.json identifies recorded workers and output retention. Retained outputs are under upstream; otherwise only hashes and grading records remain.',
        'If verification fails, records are missing, or an operation is unresolved, stop and give the operator the plan reference, operation IDs and verifier error. There is no automatic reconciliation or resume for this scripted backend. Any cleanup must identify the exact owned worker; preserve unrelated containers and evidence.',
        'Private package removal is separate: use the installation record and aeep-toolkit remove --help for its exact-review controls. Stop runtime users first; preserve edited runtime files for inspection.',
    ]
    if incomplete:
        summary['limitations'].insert(0,'Execution stopped. Missing results and unknown grades are not successes; incurred and unresolved operations remain in the ledger. No retry was performed.')
    summary['limitations'].insert(0,'Each synthetic trial resolves to its own canonical worker receipt; existing AEEP fit_report returned '+analysis.outcome+'. No model measurements are supplied.')
    repository.put('toolkit_controlled_summary',plan.plan_id,FixtureRecord(facts=summary))
    for name,value in [('toolkit-evidence',bundle.model_dump(mode='json')),('assessment-analysis',analysis.model_dump(mode='json')),('comparison',comparison.model_dump(mode='json')),('summary',summary)]:
        (output/(name+'.json')).write_text(json.dumps(value,indent=2)+'\n')
    for fmt,suffix in [('html','html'),('markdown','md')]:
        (output/('report.'+suffix)).write_text(render(summary,fmt))
    return summary
