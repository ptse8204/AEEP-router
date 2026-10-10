"""Descriptive views of normalized records; reviewed analysis owns value verdicts."""

from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter, defaultdict
from decimal import Decimal
from statistics import mean, median
from typing import Any

from .models import DeveloperIdentity, EvaluationRun, EvidenceBundle, TokenObservation

COHORT_FIELDS = (
    "plan_ref", "candidate_sha256", "adapter_sha256", "host", "host_version",
    "model", "effort", "shared_environment_sha256", "verifier_sha256", "mode", "evidence_kind",
)
METRICS = ("tokens", "agent_wall_seconds", "verification_wall_seconds", "setup_wall_seconds")


def token_total(tokens: TokenObservation | None) -> int | None:
    if tokens is None or tokens.input_tokens is None or tokens.output_tokens is None:
        return None
    total = tokens.input_tokens + tokens.output_tokens
    for count, semantics in ((tokens.cached_input_tokens, tokens.cached_semantics),
                             (tokens.reasoning_output_tokens, tokens.reasoning_semantics)):
        if semantics == "unknown" or (semantics == "separate" and count is None):
            return None
        if semantics == "separate" and count is not None:
            total += count
    return total


def measurement(run: EvaluationRun, metric: str) -> int | float | None:
    return token_total(run.tokens) if metric == "tokens" else getattr(run, metric)


def arm_summary(runs: list[EvaluationRun]) -> dict[str, Any]:
    metrics = {}
    for metric in METRICS:
        known = [value for run in runs if (value := measurement(run, metric)) is not None]
        metrics[metric] = {
            "known_runs": len(known), "total_runs": len(runs),
            "known_subtotal": sum(known) if known else None,
            "complete_total": sum(known) if runs and len(known) == len(runs) else None,
            "median_observed": median(known) if known else None,
            "maximum_observed": max(known) if known else None,
        }
    return {
        "runs": len(runs), "execution": dict(sorted(Counter(run.status for run in runs).items())),
        "verification": {state: sum(run.verification == state for run in runs)
                         for state in ("pass", "fail", "skipped", "unknown")},
        "candidate_invoked": {state: sum(run.candidate_invoked is value for run in runs)
                              for state, value in (("yes", True), ("no", False), ("unknown", None))},
        "metrics": metrics,
        "cash_accounting_references": len({run.cash_accounting_ref for run in runs if run.cash_accounting_ref}),
        "actual_cash": None, "cost_per_verified_success": None,
    }


def summarize(bundle: EvidenceBundle, *, accounting_records: dict[str, Any] | None = None,
              currency: str = "USD", recurring_fee: dict[str, str] | None = None) -> dict[str, Any]:
    if recurring_fee is not None and accounting_records is None:
        raise ValueError("fee scenarios require receipt accounting")
    if accounting_records is not None:
        cash_summary(list(bundle.runs), accounting_records, currency, recurring_fee)
    groups: dict[tuple[Any, ...], list[EvaluationRun]] = defaultdict(list)
    for run in bundle.runs:
        groups[tuple(getattr(run, field) for field in COHORT_FIELDS)].append(run)
    cohorts = []
    for key, runs in sorted(groups.items()):
        families = []
        for family in sorted({run.task_family for run in runs}):
            selected = [run for run in runs if run.task_family == family]
            tasks: dict[str, list[EvaluationRun]] = defaultdict(list)
            for run in selected:
                tasks[run.task_sha256].append(run)
            pairs: list[dict[str, EvaluationRun]] = []
            rejected = []
            for task, trials in sorted(tasks.items()):
                reasons = []
                arms = Counter(run.arm for run in trials)
                if arms != {"control": 1, "treatment": 1}:
                    reasons.append("Exactly one observed run per arm is required; missing or repeated arms cannot be paired.")
                if len({run.prompt_sha256 for run in trials}) != 1:
                    reasons.append("Prompts differ.")
                if any(run.mode != "optional" for run in trials):
                    reasons.append("Forced invocation is diagnostic only.")
                if any(run.candidate_exposed is not (run.arm == "treatment") for run in trials):
                    reasons.append("Candidate exposure is missing or inconsistent.")
                if any(run.status == "indeterminate" or run.retries for run in trials):
                    reasons.append("Unresolved execution or retries require reviewed reconciliation.")
                if reasons:
                    rejected.append({"task_sha256": task, "reasons": reasons})
                else:
                    pairs.append({run.arm: run for run in trials})
            differences = {}
            for metric in METRICS:
                values, controls, treatments = [], [], []
                for pair in pairs:
                    control = measurement(pair["control"], metric)
                    treatment = measurement(pair["treatment"], metric)
                    if control is not None and treatment is not None:
                        values.append(control - treatment)
                        controls.append(control)
                        treatments.append(treatment)
                control_mean = mean(controls) if controls else None
                treatment_mean = mean(treatments) if treatments else None
                difference_mean = mean(values) if values else None
                differences[metric] = {
                    "measured_pairs": len(values), "observed_pairs": len(pairs),
                    "mean_observed_control": control_mean, "mean_observed_treatment": treatment_mean,
                    "mean_control_minus_treatment": difference_mean,
                    "relative_mean_control_minus_treatment": difference_mean / control_mean if difference_mean is not None and control_mean else None,
                    "median_control_minus_treatment": median(values) if values else None,
                    "confidence_interval": None,
                }
            graded = [pair for pair in pairs if all(run.verification in {"pass", "fail"} for run in pair.values())]
            success_difference = (
                sum(int(pair["treatment"].verification == "pass") - int(pair["control"].verification == "pass")
                    for pair in graded) / len(graded) if graded and len(graded) == len(pairs) and not rejected else None
            )
            cash = None
            if accounting_records is not None:
                cash = cash_summary(selected, accounting_records, currency, recurring_fee)
                cash['break_even_scenario'] = fee_break_even(pairs, cash) if not rejected else None
            families.append({
                "task_family": family, "observed_tasks": len(tasks), "observed_pairs": len(pairs),
                "graded_pairs": len(graded), "rejected_tasks": rejected,
                "arms": {arm: arm_summary([run for run in selected if run.arm == arm]) | ({"actual_cash": cash["arms"][arm]["complete_total"], "cost_per_verified_success": cash["arms"][arm]["cost_per_verified_success"]} if cash else {}) for arm in ("control", "treatment")},
                "success_rate_treatment_minus_control": success_difference,
                "metric_differences": differences,
                **({"cash": cash} if cash is not None else {}),
            })
        cohorts.append({"binding": dict(zip(COHORT_FIELDS, key, strict=True)), "families": families})
    raw = json.dumps(bundle.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False)
    result = {
        "schema": "aeep.toolkit.descriptive-summary.v1",
        "evidence_sha256": hashlib.sha256(raw.encode()).hexdigest(),
        "outcome": "NOT_ASSESSED", "cohorts": cohorts,
        "candidate": bundle.candidate.model_dump(mode="json"),
        "adapter": bundle.adapter.model_dump(mode="json"),
        "inspection_references": [
            {"task_sha256": run.task_sha256, "arm": run.arm,
             "receipt_refs": list(run.receipt_refs), "verification_ref": run.verification_ref}
            for run in bundle.runs
        ],
        "limitations": [
            "Artifact contents and file changes are not included in these normalized records. Resolve receipt and verification references in the originating run; grades alone do not describe edits.",
            "Access ceilings, spending permission, pending approvals and activation state are not established by this summary. Consult the exact reviewed plan and installation record before further execution.",
            "Describes supplied records; this command does not authenticate referenced receipts, worker conformance or grading evidence.",
            "Only observed tasks are checked. Entire missing pairs cannot be detected without the reviewed plan's expected cases.",
            "Different cohort bindings are never pooled. Repetitions lack a pairing index and are rejected rather than counted as independent cases.",
            "Partial measurements are labeled as known subsets. Resource differences do not override task failures or establish benefit.",
            "Synthetic and replay records cannot establish real model value. Invocation is not evidence of causation.",
            "Confidence and value verdicts require the existing reviewed analysis. Supplied receipt accounting is descriptive; recurring fees are explicit scenarios, not incurred charges or a demonstrated benefit.",
        ],
    }
    # Finite individual measurements can overflow during aggregation.
    json.dumps(result, allow_nan=False)
    return result


def render(summary: dict[str, Any], format: str) -> str:
    if format == "json":
        return json.dumps(summary, indent=2, allow_nan=False) + "\n"
    lines = ["AEEP evidence summary", "", "Value verdict: NOT_ASSESSED", "",
             "Descriptive records only. Unknown is not zero; fewer resources do not establish benefit.", ""]
    if 'candidate' in summary:
        source = summary['candidate']
        lines += [f"Candidate source: {json.dumps(source['repository'])}",
                  f"Revision: {source['revision']}; payload SHA-256: {source['artifact_sha256']}",
                  "Source metadata is supplied provenance, not verified developer ownership.", ""]
    if 'comparison' in summary:
        comparison = summary['comparison']
        lines += [f"Engineering comparison status: {comparison['outcome']}; evidence: {comparison['evidence_kind']}.",
                  *comparison['limitations'], ""]
    analysis = summary.get('reviewed_analysis')
    if analysis is not None:
        lines += [f"Existing AEEP analysis: {analysis['outcome']}; source: {analysis['analysis_ref']}",
                  f"Expected trial positions: {analysis['expected_trial_positions']}; receipts: {analysis['matched_receipts']}.",
                  f"Missing trial positions: {analysis.get('missing_trial_positions', 'unknown')}; unresolved operations: {analysis.get('unresolved_operations', 'unknown')}."]
        if 'worker_operation_seconds_known' in analysis:
            lines += [f"Worker-operation elapsed seconds, known subtotal: {analysis['worker_operation_seconds_known']}; measured operations: {analysis['worker_operations_measured']}/{analysis['worker_operations_reserved']}.",
                      "Worker-operation time is assessment overhead, not model latency or a complete evaluation-cost total."]
        lines.append("")
    managed = summary.get("managed_analysis")
    if managed is not None:
        lines += ["Canonical managed assessment",
                  f"Recorded outcome: {managed['outcome']}; qualification passed: {managed['qualification_passed']}.",
                  f"Analysis: {managed['analysis_ref']}; campaign: {managed['campaign_ref']}; operation ledger: {managed['operation_ledger_ref']}.",
                  f"Distinct holdouts: {managed['distinct_holdout_cases']}; distinct paired cases: {managed['distinct_paired_cases']}.",
                  f"Correctness failures: {managed['correctness_failures']}; execution failures: {managed['execution_failures']}.",
                  f"Expected trial positions: {managed['expected_trial_positions']}; missing: {managed['missing_trial_positions']}; unexpected: {managed['unexpected_trial_positions']}; duplicate: {managed['duplicate_trial_positions']}.",
                  f"Unresolved operations: {managed['unresolved_operations']}.",
                  managed['timing_scope'],
                  "Positive paired resource differences mean control used more. Success gains use treatment minus control. Intervals and guardrails retain the frozen analysis policy."]
        for label, key in (
            ("Paired measurement coverage", "paired_measurement_cases"),
            ("Paired resource differences", "paired_savings"),
            ("Uncertainty intervals", "savings_interval"),
            ("Separate worker conditions", "condition_comparisons"),
            ("Utility, guardrails and challengers", "utility_evidence"),
            ("Assessment usage, including known subtotals", "measured_usage"),
            ("Measurement coverage", "measurement_coverage"),
            ("Assessment resource break-even uses", "break_even_uses"),
        ):
            lines.append(label + ": " + json.dumps(managed[key], sort_keys=True, allow_nan=False))
        lines += ["Null means unavailable. Resource break-even is not billed-cash savings or a plugin-price forecast.", ""]
    for index, cohort in enumerate(summary["cohorts"], 1):
        binding = cohort["binding"]
        lines += [f"Cohort {index}: {binding['host']} {json.dumps(binding['host_version'])} / {binding['model']} / {binding['effort']}",
                  f"Evidence: {binding['evidence_kind']}; plan: {binding['plan_ref']}", ""]
        for family in cohort["families"]:
            lines += [f"Task family: {family['task_family']}",
                      f"Observed pairs: {family['observed_pairs']}; rejected tasks: {len(family['rejected_tasks'])}"]
            delta = family['success_rate_treatment_minus_control']
            shown_delta = f'{delta * 100:+.4g} percentage points' if delta is not None else 'unknown'
            lines += [f"Verified-success difference, treatment minus control: {shown_delta}; graded pairs: {family['graded_pairs']}/{family['observed_pairs']}.",
                      "Observed differences are descriptive; no confidence-supported conclusion follows from them."]
            for arm, facts in family["arms"].items():
                counts = facts["verification"]
                lines.append(f"{arm.title()}: {counts['pass']} passed, {counts['fail']} failed, {counts['skipped']} skipped, {counts['unknown']} unknown.")
                invoked = facts['candidate_invoked']
                lines.append(f"  Candidate use: {invoked['yes']} observed, {invoked['no']} observed absent, {invoked['unknown']} unknown.")
                for metric, values in facts["metrics"].items():
                    total = values['complete_total'] if values['complete_total'] is not None else 'unknown'
                    observed = values['median_observed'] if values['median_observed'] is not None else 'unknown'
                    lines.append(f"  {metric}: {values['known_runs']}/{values['total_runs']} measured; total {total}; observed median {observed}.")
            for metric, difference in family['metric_differences'].items():
                if difference['measured_pairs']:
                    relative = difference.get('relative_mean_control_minus_treatment')
                    percent = f'{Decimal(str(relative)) * 100:.4g}%' if relative is not None else 'unknown'
                    lines.append(f"  Paired {metric}: mean control minus treatment {difference.get('mean_control_minus_treatment', 'unknown')}; relative mean difference {percent}; median difference {difference['median_control_minus_treatment']}; measured pairs {difference['measured_pairs']}/{difference['observed_pairs']}.")
            for rejected in family["rejected_tasks"]:
                lines.append(f"Unpaired task {rejected['task_sha256']}: {' '.join(rejected['reasons'])}")
            if 'cash' in family:
                cash = family['cash']
                lines.append(f"Cash currency: {cash['currency']}; evidence kind: {binding['evidence_kind']}.")
                for arm, amounts in cash['arms'].items():
                    lines.append(f"{arm.title()} cash: {amounts['complete_total'] or 'unknown'}; cost per verified success: {amounts['cost_per_verified_success'] or 'unknown'}.")
                lines.append("Recurring-fee scenario: " + json.dumps(cash['break_even_scenario']))
                lines += [cash['notice'], ""]
            else:
                lines += ["Actual cash, cost per verified success, recurring fees and break-even: unknown.", ""]
    if summary.get("inspection_references"):
        lines += ["Inspection references", json.dumps(summary["inspection_references"], sort_keys=True), ""]
    lines += ["Limits", *summary["limitations"]]
    text = "\n".join(lines) + "\n"
    if format == "markdown":
        # The fence must exceed every supplied backtick run, including embedded ones.
        fence = "`" * (max(map(len, re.findall(r"`+", text)), default=0) + 4)
        return fence + "text\n" + text + fence + "\n"
    if format == "html":
        return ('<!doctype html><html lang="en"><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                '<title>AEEP evidence summary</title><style>body{max-width:72rem;margin:2rem auto;padding:0 1rem;'
                'font:16px/1.6 system-ui}pre{white-space:pre-wrap;overflow-wrap:anywhere}</style>'
                '<main><h1>AEEP evidence summary</h1><pre>' + html.escape(text) + '</pre></main></html>\n')
    raise ValueError("unsupported report format")


def cash_summary(runs: list[EvaluationRun], records: dict[str, Any], currency: str,
                 fee: dict[str, str] | None = None) -> dict[str, Any]:
    from decimal import Decimal

    from aeep.accounting import aggregate_accounting
    from aeep.assessment.models import content_digest
    from aeep.models import ExecutionReceipt
    if not re.fullmatch(r'[A-Z]{3}', currency):
        raise ValueError('invalid currency')
    if fee is not None:
        if set(fee) != {'amount', 'period', 'source_ref'} or fee['period'] not in {'month', 'year'} or not re.fullmatch(r'[a-f0-9]{64}', fee['source_ref']):
            raise ValueError('fee needs exact period and source reference')
        if not isinstance(fee['amount'], str) or not re.fullmatch(r'[0-9]{1,18}(?:\.[0-9]{1,18})?', fee['amount']):
            raise ValueError('fee must be a bounded decimal string')
        amount = Decimal(fee['amount'])
        if not amount.is_finite() or amount < 0:
            raise ValueError('fee must be finite and non-negative')
    receipts: dict[str, Decimal | None] = {}
    seen_ids: set[str] = set()
    seen_charges: set[str] = set()
    arms = {}
    for run in runs:
        if len(run.receipt_refs) < run.retries + 1:
            raise ValueError('retry receipts are incomplete')
        items = []
        for ref in run.receipt_refs:
            if ref not in records:
                raise ValueError('missing referenced cash receipt')
            receipt = ExecutionReceipt.model_validate(records[ref])
            if content_digest(receipt) != ref or receipt.receipt_id in seen_ids:
                raise ValueError('changed or shared receipt; accounting attribution is ambiguous')
            seen_ids.add(receipt.receipt_id)
            # Workflow summaries already include component charges. Do not count a component twice.
            component_ids = receipt.metadata.get('component_receipt_ids')
            if component_ids:
                raise ValueError('provide independent terminal receipts, not workflow summaries')
            items.append(receipt)
        accounting = aggregate_accounting(items)
        charges = {c.charge_id for c in accounting.cash.components}
        if charges & seen_charges:
            raise ValueError('shared charge across runs; cost attribution is ambiguous')
        seen_charges.update(charges)
        value = accounting.cash.actual_cash_cost(currency) if run.status != 'indeterminate' else None
        receipts[run.run_id] = value
    for arm in ('control', 'treatment'):
        selected = [run for run in runs if run.arm == arm]
        values = [receipts[run.run_id] for run in selected]
        known = [v for v in values if v is not None]
        total = sum(known, Decimal(0)) if selected and len(known) == len(values) else None
        successes = sum(run.verification == 'pass' for run in selected)
        graded = bool(selected) and all(run.verification in {'pass', 'fail'} for run in selected)
        arms[arm] = {'known_runs':len(known), 'total_runs':len(selected),
                     'known_subtotal':str(sum(known, Decimal(0))) if known else None,
                     'complete_total':str(total) if total is not None else None,
                     'cost_per_verified_success':str(total/successes) if total is not None and graded and successes else None}
    return {'currency':currency, 'arms':arms, 'fee_scenario':fee,
            'evaluation_overhead_cash':None,
            'notice':'Receipt contents must be resolved by the caller. Hash consistency is not billing attestation. Fees are supplied scenarios, not observed charges; evaluation overhead is separate.'}


def fee_break_even(pairs: list[dict[str, EvaluationRun]], cash: dict[str, Any]) -> dict[str, Any] | None:
    from decimal import ROUND_CEILING, Decimal


    # Only a complete matched cohort with complete grades can supply a descriptive scenario.
    if not pairs or cash['fee_scenario'] is None or any(run.verification not in {'pass','fail'} for pair in pairs for run in pair.values()):
        return None
    control_successes = sum(pair['control'].verification == 'pass' for pair in pairs)
    treatment_successes = sum(pair['treatment'].verification == 'pass' for pair in pairs)
    if not control_successes or treatment_successes < control_successes:
        return None
    control = cash['arms']['control']['cost_per_verified_success']
    treatment = cash['arms']['treatment']['cost_per_verified_success']
    if control is None or treatment is None:
        return None
    difference = Decimal(control) - Decimal(treatment)
    if difference <= 0:
        return None
    amount = Decimal(cash['fee_scenario']['amount'])
    return {'observed_cost_per_success_control_minus_treatment':str(difference),
            'verified_successes_per_fee_period':int((amount/difference).to_integral_value(rounding=ROUND_CEILING)),
            'period':cash['fee_scenario']['period'],
            'interpretation':'Scenario using observed cost per verified success, including failed-run costs. Assumes the same future task mix and success rates; not a confidence-supported forecast. Excludes assessment overhead.'}

def portable_summary(bundle: EvidenceBundle, *, disclose_source: bool = False,
                     developer: DeveloperIdentity | None = None) -> dict[str, Any]:
    """Prepare minimized local sharing bytes; this neither publishes nor authenticates."""
    summary = summarize(bundle)
    if developer is not None and (not disclose_source or developer.source != bundle.candidate):
        raise ValueError('developer assertion requires the exact disclosed candidate source')
    cohorts = []
    for index, cohort in enumerate(summary['cohorts'], 1):
        binding = json.dumps(cohort['binding'], sort_keys=True, separators=(',', ':'), allow_nan=False)
        families = []
        for number, family in enumerate(cohort['families'], 1):
            families.append({
                'family': number,
                **{key: family[key] for key in ('observed_tasks', 'observed_pairs', 'graded_pairs',
                    'success_rate_treatment_minus_control', 'metric_differences')},
                'rejected_tasks': len(family['rejected_tasks']),
                'arms': {arm: {key: values[key] for key in ('runs', 'execution', 'verification',
                         'candidate_invoked', 'metrics')} for arm, values in family['arms'].items()},
            })
        cohorts.append({'cohort': index, 'scope_sha256': hashlib.sha256(binding.encode()).hexdigest(),
                        'evidence_kind': cohort['binding']['evidence_kind'], 'families': families})
    document = {
        'schema': 'aeep.toolkit.portable-summary.v1',
        'outcome': 'NOT_ASSESSED', 'trust': 'unverified_supplied_records',
        'source_bundle_sha256': summary['evidence_sha256'],
        'candidate_sha256': bundle.candidate.artifact_sha256,
        'adapter_sha256': bundle.adapter.implementation_sha256,
        'cohorts': cohorts,
        'source': bundle.candidate.model_dump(mode='json') if disclose_source else None,
        'developer': ({'assertion': developer.model_dump(mode='json'),
                       'status': 'operator_supplied_unverified',
                       'notice': 'Ownership and destination are unverified. A donation is optional support; a purchase link is not price or payment authority.'}
                      if developer else None),
        'publication_performed': False,
        'limitations': [
            'Prepared locally for review; no publication or independent reproduction is established.',
            'Task labels, prompts, paths, run IDs, receipt references and host/model names are omitted. Digests and aggregate measurements may still identify a study; this is not guaranteed anonymity.',
            'Scope hashes retain cohort separation but require the private source records to interpret applicability or reproduce results.',
            'Synthetic and replay results cannot establish real-host benefit. Unknown measurements remain unknown.',
            'Any disclosed source or developer metadata is an explicit supplied assertion, not verified ownership or authorization to pay.',
        ],
    }
    payload = json.dumps(document, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    return {'content_sha256': hashlib.sha256(payload).hexdigest(), 'document': document}
