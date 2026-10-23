"""Synthetic canonical-trial grading regression; no worker or model execution."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

from aeep.benchmarking import BenchmarkTrial
from aeep.models import ValidationResult

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('reviewed_grade_binding',HERE/'run-model-journey.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
receipt=SimpleNamespace(receipt_id='receipt',executor_id='candidate',task_valid=None,validation_results=[])
trial=BenchmarkTrial(trial_id='trial',run_id='run',suite_id='suite',case_id='case',route_id='candidate',condition='fresh-worker',repetition=0,phase='measurement',state='complete',valid=True,receipt_ids=['receipt'],case_validation=[ValidationResult(kind='callback',valid=True,trust='verified')])
assert m.independent_grade(trial,receipt)
trial.valid=False;trial.case_validation[0].valid=False;assert m.independent_grade(trial,receipt)
trial.case_validation=[];assert not m.independent_grade(trial,receipt)
trial.case_validation=[ValidationResult(kind='callback',valid=True,trust='self_asserted')];assert not m.independent_grade(trial,receipt)
trial.route_id='wrong'
try:m.independent_grade(trial,receipt)
except AssertionError:pass
else:raise AssertionError('Wrong route was accepted')
result={'passed':True,'synthetic_fixture_only':True,'checks':5,'task_grade_source':'Bound canonical BenchmarkTrial.case_validation,not execution receipt.task_valid','actual_model_or_grader_runs':0,'actual_grant_operations':0}
(HERE/'grade-binding-check.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
