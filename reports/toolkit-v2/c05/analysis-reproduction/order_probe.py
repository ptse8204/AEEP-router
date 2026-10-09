"""Synthetic ordering probe; these values are not benchmark observations."""
import hashlib
import json
import random
from pathlib import Path

from aeep.assessment import reporting

rng = random.Random(517)
values = {f'case-{i:03}': [rng.random(), rng.random()] for i in range(40)}
families = {case: f'family-{i % 7}' for i, case in enumerate(values)}
left = reporting.paired_interval(values, 20, 0, families)
right = reporting.paired_interval(dict(reversed(list(values.items()))), 20, 0, families)
print(json.dumps({'kind': 'synthetic', 'generator_seed': 517, 'analysis_seed': 0,
                  'source_sha256': hashlib.sha256(Path(reporting.__file__).read_bytes()).hexdigest(),
                  'forward': left, 'reverse': right, 'equal': left == right}, indent=2))
