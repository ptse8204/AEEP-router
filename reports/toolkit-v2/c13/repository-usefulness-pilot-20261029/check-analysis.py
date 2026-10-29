"""Check analysis on retained real development rows and explicit missing-data fixtures."""
import copy
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PRIOR = HERE.parent / 'repository-task-delivery-20261023'
spec = importlib.util.spec_from_file_location('pilot_analysis', HERE / 'analyze-and-check-admission.py')
analysis = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analysis)
rows = json.loads((PRIOR / 'completion-audit.json').read_text())['rows']
proposal = json.loads((PRIOR / 'collector-definitions.json').read_text())
recipe = proposal['definitions'][proposal['requests'][0]['recipe_digest']]
cases = {case['input']['task_id']: {'repository': case['source_repository'], 'family': case['input']['family']}
         for case in recipe['generator_config']['cases']}
summary = analysis.summarize(rows, cases)
assert summary['complete_pairs'] == 3
assert summary['arms']['control']['verified_successes'] == 3
assert summary['arms']['treatment']['verified_successes'] == 3
assert summary['paired_success_difference'] == 0
assert summary['exploratory_repository_grouped_success_interval'] == []
assert all(value['exploratory_corrected_interval'] == [] for value in summary['resource_comparisons'].values())
assert summary['candidate_instruction_loads'] == 3 and summary['cash_savings'] is None
partial = copy.deepcopy(rows)
partial[0]['token_capture']['status'] = 'unknown'
incomplete = analysis.summarize(partial, cases)
assert incomplete['resource_comparisons']['provider_reported_input_plus_output_tokens']['both_successful_measured_pairs'] == 2
failed = copy.deepcopy(rows)
failed[0]['independent_grade'] = False
mixed = analysis.summarize(failed, cases)
assert mixed['paired_success_difference'] > 0
assert mixed['resource_comparisons']['agent_wall_seconds']['both_successful_measured_pairs'] == 2
result = {'passed': True, 'retained_real_development_pairs_reanalyzed_read_only': 3,
          'small_n_has_no_interval': True, 'unknown_or_failed_pairs_excluded_from_resource_claims': True,
          'provider_usage_not_cash': True, 'synthetic_modified_rows_are_not_new_benchmark_evidence': True,
          'new_execution_or_models': 0}
(HERE / 'analysis-check.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
