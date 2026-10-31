"""Synthetic evidence validity checks; no efficacy or billing evidence."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from aeep_toolkit.cli import main
from aeep_toolkit.models import EvidenceBundle, TokenObservation
from aeep_toolkit.reporting import render, summarize, token_total

D = "a" * 64


def bundle(**changes):
    run = dict(run_id="control", plan_ref=D, candidate_sha256=D, adapter_sha256=D,
               host="fake", host_version="fixture-1", model="fixture", effort="none",
               shared_environment_sha256=D, worker_sha256=D, task_sha256=D,
               task_family="format", verifier_sha256=D, prompt_sha256=D,
               arm="control", mode="optional", candidate_exposed=False,
               candidate_invoked=None, verification="pass", verification_ref=D,
               status="completed", retries=0, evidence_kind="synthetic", receipt_refs=[D])
    return EvidenceBundle.model_validate({
        "candidate": dict(repository="https://example.org/fixture", revision="b" * 40,
                          artifact_sha256=D, license_expression="MIT", data_rights="no dataset"),
        "adapter": dict(adapter_id="fixture", implementation_sha256=D, hosts=["fake", "other"],
                        candidate_types=["skill"], optional_invocation=True,
                        telemetry=["tokens", "agent_wall_seconds", "setup_wall_seconds", "verification_wall_seconds"],
                        containment="unverified"),
        "runs": [run, run | dict(run_id="treatment", arm="treatment", candidate_exposed=True) | changes],
    })


def family(value):
    return summarize(value)["cohorts"][0]["families"][0]


def modify(value, runs):
    return EvidenceBundle.model_validate(value.model_dump() | {"runs": runs})


def test_unknown_metrics_and_billing_references_never_become_zero_or_cash():
    value = bundle(cash_accounting_ref=D)
    report = summarize(value)
    assert report["outcome"] == "NOT_ASSESSED"
    facts = family(value)
    assert facts["observed_pairs"] == facts["graded_pairs"] == 1
    for arm in facts["arms"].values():
        assert arm["metrics"]["tokens"]["complete_total"] is None
        assert arm["cost_per_verified_success"] is None
        assert arm["actual_cash"] is None
    assert facts["arms"]["treatment"]["cash_accounting_references"] == 1
    assert "recurring fees" in render(report, "markdown")


@pytest.mark.parametrize("changes", [
    {"host": "other"}, {"host_version": "different"}, {"model": "other"},
    {"effort": "high"}, {"shared_environment_sha256": "b" * 64},
    {"plan_ref": "b" * 64}, {"verifier_sha256": "b" * 64}, {"evidence_kind": "live"},
])
def test_incompatible_cohorts_cannot_be_pooled(changes):
    result = summarize(bundle(**changes))
    assert len(result["cohorts"]) == 2
    for cohort in result["cohorts"]:
        facts = cohort["families"][0]
        assert facts["observed_pairs"] == 0
        assert facts["success_rate_treatment_minus_control"] is None
        assert facts["rejected_tasks"]


@pytest.mark.parametrize("changes", [
    {"prompt_sha256": "b" * 64}, {"candidate_exposed": None},
    {"candidate_exposed": False}, {"mode": "forced_diagnostic"},
    {"retries": 1}, {"status": "indeterminate", "verification": "unknown"},
])
def test_invalid_pairs_remain_visible_and_cannot_supply_effects(changes):
    report = summarize(bundle(**changes))
    for cohort in report["cohorts"]:
        facts = cohort["families"][0]
        assert facts["observed_pairs"] == 0
        assert facts["rejected_tasks"]
        assert facts["metric_differences"]["tokens"]["median_control_minus_treatment"] is None
        assert facts['task_observations']
        assert all('run_id' in row and 'receipt_refs' in row and 'binary_task_score' in row
                   for row in facts['task_observations'])


def test_missing_and_duplicate_arms_do_not_inflate_distinct_cases():
    value = bundle()
    for runs in ([value.runs[0]], [*value.runs, value.runs[1].model_copy(update={"run_id": "repeat"})]):
        facts = family(modify(value, runs))
        assert facts["observed_tasks"] == 1
        assert facts["observed_pairs"] == 0
        assert facts["success_rate_treatment_minus_control"] is None


@pytest.mark.parametrize("verification", ["skipped", "unknown"])
def test_missing_grades_are_not_failures_or_successes(verification):
    facts = family(bundle(verification=verification, verification_ref=None))
    assert facts["observed_pairs"] == 1
    assert facts["graded_pairs"] == 0
    assert facts["success_rate_treatment_minus_control"] is None
    assert facts["arms"]["treatment"]["verification"][verification] == 1


def test_fewer_tokens_with_worse_success_is_never_reported_as_benefit():
    tokens = dict(source_ref=D, input_tokens=100, output_tokens=10, cached_input_tokens=80,
                  reasoning_output_tokens=5, cached_semantics="included_in_input", reasoning_semantics="included_in_output")
    value = bundle(verification="fail", tokens=tokens | {"input_tokens": 90})
    value = modify(value, [value.runs[0].model_copy(update={"tokens": TokenObservation(**tokens)}), value.runs[1]])
    facts = family(value)
    assert facts["success_rate_treatment_minus_control"] == -1
    assert facts["metric_differences"]["tokens"]["median_control_minus_treatment"] == 10
    assert facts["arms"]["control"]["metrics"]["tokens"]["complete_total"] == 110
    assert summarize(value)["outcome"] == "NOT_ASSESSED"
    task = facts['task_comparisons'][0]
    assert task['arms']['control']['binary_task_score'] == 1
    assert task['arms']['treatment']['binary_task_score'] == 0
    assert task['tokens_control_minus_treatment'] == 10
    assert task['arms']['treatment']['raw_tokens']['cached_semantics'] == 'included_in_input'
    assert task['arms']['control']['verification_ref'] == D
    assert 'Per-task comparison' in render(summarize(value), 'html')


def test_token_overlap_separate_unknown_and_zero_semantics():
    tokens = dict(source_ref=D, input_tokens=10, output_tokens=4, cached_input_tokens=6,
                  reasoning_output_tokens=2, cached_semantics="included_in_input", reasoning_semantics="included_in_output")
    assert token_total(TokenObservation(**tokens)) == 14
    assert token_total(TokenObservation(**(tokens | {"cached_semantics": "separate", "reasoning_semantics": "separate"}))) == 22
    for change in ({"input_tokens": None}, {"output_tokens": None},
                   {"cached_input_tokens": None, "cached_semantics": "separate"},
                   {"reasoning_output_tokens": None, "reasoning_semantics": "unknown"}):
        assert token_total(TokenObservation(**(tokens | change))) is None
    assert token_total(TokenObservation(**(tokens | {key: 0 for key in ("input_tokens", "output_tokens", "cached_input_tokens", "reasoning_output_tokens")}))) == 0


def test_failed_execution_counts_and_zero_successes_have_no_invented_cost():
    value = bundle(status="timeout", verification="fail")
    value = modify(value, [value.runs[0].model_copy(update={"status": "failed", "verification": "fail"}), value.runs[1]])
    facts = family(value)
    assert facts["success_rate_treatment_minus_control"] == 0
    assert facts["arms"]["treatment"]["execution"] == {"timeout": 1}
    assert facts["arms"]["treatment"]["cost_per_verified_success"] is None


def test_partial_and_long_tailed_timings_preserve_coverage_and_maximum():
    value = bundle()
    runs = []
    for index, seconds in enumerate([1.0, 2.0, 1000.0, None]):
        for original in value.runs:
            runs.append(original.model_copy(update={
                "run_id": f"{original.arm}-{index}", "task_sha256": str(index) * 64,
                "agent_wall_seconds": seconds, "timing_source_ref": D,
            }))
    facts = family(modify(value, runs))
    metric = facts["arms"]["control"]["metrics"]["agent_wall_seconds"]
    assert metric == dict(known_runs=3, total_runs=4, known_subtotal=1003.0, complete_total=None,
                          median_observed=2.0, maximum_observed=1000.0)
    assert facts["metric_differences"]["agent_wall_seconds"]["measured_pairs"] == 3
    assert facts["metric_differences"]["agent_wall_seconds"]["confidence_interval"] is None


def test_rendered_host_metadata_cannot_inject_html_or_markdown():
    report = summarize(bundle(host_version="fixture\n`````\n<script>alert(1)</script>\n`````"))
    assert "<script>" not in render(report, "html")
    assert "&lt;script&gt;" in render(report, "html")
    markdown = render(report, "markdown")
    assert markdown.startswith("`````````text\n")
    assert json.loads(render(report, "json"))["evidence_sha256"] == report["evidence_sha256"]
    with pytest.raises(ValueError):
        render(report, "unsupported")


def test_report_cli_reads_only_selected_evidence_and_writes_stdout(tmp_path, capsys):
    path = tmp_path / "evidence.json"
    path.write_text(bundle().model_dump_json())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    with patch("subprocess.Popen", side_effect=AssertionError("execution forbidden")), patch("socket.socket", side_effect=AssertionError("network forbidden")), patch.object(Path, "write_text", side_effect=AssertionError("writes forbidden")):
        assert main(["report", "--evidence", str(path), "--format", "json"]) == 0
    assert json.loads(capsys.readouterr().out)["outcome"] == "NOT_ASSESSED"
    assert before == {p.name: p.read_bytes() for p in tmp_path.iterdir()}


def test_empty_bundle_is_explicitly_unassessed():
    result = summarize(modify(bundle(), []))
    assert result["cohorts"] == []
    assert result["outcome"] == "NOT_ASSESSED"


def test_finite_measurements_cannot_overflow_into_a_report():
    value = bundle(agent_wall_seconds=1.7e308, timing_source_ref=D)
    runs = [*value.runs, value.runs[1].model_copy(update={"run_id": "other", "task_sha256": "b" * 64})]
    with pytest.raises(ValueError, match="Out of range"):
        summarize(modify(value, runs))


def test_terminal_control_codes_in_declared_version_are_escaped():
    output = render(summarize(bundle(host_version="\x1b[2J")), "markdown")
    assert "\x1b" not in output
    assert "\\u001b" in output


def test_report_exposes_inspection_references_without_inventing_authority():
    report = summarize(bundle())
    assert report["inspection_references"][0] == {
        "task_sha256": D, "arm": "control", "receipt_refs": [D], "verification_ref": D,
    }
    for format in ("json", "markdown", "html"):
        text = render(report, format)
        assert "pending approvals" in text
        assert "grades alone do not describe edits" in text
        assert D in text
