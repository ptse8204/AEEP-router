"""Synthetic bootstrap inputs, never measured benchmark evidence."""
import random

import pytest

from aeep.assessment.reporting import paired_interval


@pytest.mark.parametrize('success_rate', [False, True])
def test_bootstrap_uses_cases_and_families_independently_of_dictionary_order(success_rate):
    rng = random.Random(517)
    values = {f'case-{i:03}': [rng.random(), rng.random()] for i in range(40)}
    families = {case: f'family-{i % 7}' for i, case in enumerate(values)}
    expected = paired_interval(values, 20, 0, families, success_rate=success_rate)
    reordered = dict(reversed(list(values.items())))
    assert paired_interval(reordered, 20, 0, families, success_rate=success_rate) == expected
    assert expected[1]
