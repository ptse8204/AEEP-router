"""Offline first-party checks only; these cases must never become live holdouts."""
import copy
import hashlib
import json
from pathlib import Path
from collections import Counter
from generator import generate
from reference import transform
from grader import valid

# Literals are independent of the fixture generator and exercise preservation.
literals = [
 ({'files': {'a': 'helo\n', 'b': 'helo'}, 'task': {'operation': 'literal_replace', 'file': 'a', 'old': 'helo', 'new': 'hello'}}, {'files': {'a': 'hello\n', 'b': 'helo'}, 'answer': None}),
 ({'files': {'a.py': 'def old(x):\r\n    "old" # old\r\n    return x\r\n', 'note': 'old'}, 'task': {'operation': 'python_name_rename', 'files': ['a.py'], 'names': {'old': 'new_name'}}}, {'files': {'a.py': 'def new_name(x):\r\n    "old" # old\r\n    return x\r\n', 'note': 'old'}, 'answer': None}),
 ({'files': {'log': 'error one\n error two\nerror three\n'}, 'task': {'operation': 'count_prefix', 'file': 'log', 'prefix': 'error '}}, {'files': {'log': 'error one\n error two\nerror three\n'}, 'answer': 2})]
for value, expected in literals:
 assert transform(value) == expected
 assert valid({'input': value, 'output': expected, 'expected': expected})

payload = {'seed': 7, 'stages': [{'split': 'qualification', 'count': 8}, {'split': 'training', 'count': 28}, {'split': 'holdout', 'count': 105}]}
cases = generate(payload)['cases']; assert len(cases) == 141
assert len({json.dumps(x['input'], sort_keys=True) for x in cases}) == 141
counts = Counter(x['variation'] for x in cases[36:]); assert len(counts) == 21 and set(counts.values()) == {5}
assert generate(payload)['cases'] == cases
other = generate({**payload, 'seed': 8})['cases']; assert not {json.dumps(x['input'], sort_keys=True) for x in other} & {json.dumps(x['input'], sort_keys=True) for x in cases}
mutations = 0
for case in cases:
 actual = transform(case['input']); assert actual == case['output']
 example = {'input': case['input'], 'output': actual, 'expected': case['output']}; assert valid(example)
 wrong = copy.deepcopy(actual); wrong['files']['NOTES.txt'] += 'changed'; assert not valid({**example, 'output': wrong}); mutations += 1
 wrong = copy.deepcopy(actual); wrong['files']['new.txt'] = ''; assert not valid({**example, 'output': wrong}); mutations += 1
 assert not valid({**example, 'output': {**actual, 'answer': True}}); mutations += 1
 assert not valid({**example, 'output': {**actual, 'extra': ''}}); mutations += 1
for family in ('easy', 'multi_file'):
 case = next(x for x in cases if x['input']['family'] == family)
 assert not valid({'input': case['input'], 'output': {'files': case['input']['files'], 'answer': None}, 'expected': case['output']})
root = Path(__file__).parent
record = {'evidence_kind': 'first_party_offline_fixture_validation', 'model_calls': 0, 'candidate_execution': False, 'literal_checks': 3, 'generated_cases_checked': 141, 'rejected_artifact_mutations': mutations + 2, 'excluded_live_seeds': [7, 8], 'live_qualification': False, 'source_sha256': {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.glob('*.py')}}
(root/'checks.json').write_text(json.dumps(record, indent=2)+'\n');print(json.dumps(record))
