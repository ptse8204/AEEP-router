"""Opt-in checks of real local release evidence; never substitute mocked results."""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from aeep.assessment.verification import verify_live_records

pytestmark = pytest.mark.skipif(not os.environ.get("AEEP_LIVE_MANIFEST"), reason="requires explicitly selected authorized live evidence")


def evidence():
    return verify_live_records(
        Path(__file__).resolve().parents[1],
        Path(os.environ["AEEP_LIVE_MANIFEST"]).resolve(),
        os.environ.get("AEEP_LIVE_ASSESSMENT_IDS", "").split(),
        os.environ.get("AEEP_LIVE_RECEIPT_IDS", "").split(),
    )


@pytest.mark.codex_conformance
def test_installed_host_conformance_has_execution_boundary_evidence():
    result = evidence()
    assert result["host_verified"], result


@pytest.mark.live_acceptance
def test_live_families_new_recipe_and_subsequent_capability_calls():
    result = evidence()
    assert result["campaigns_verified"] and result["capability_calls_verified"], result
    assert result["admitted_execution_observed"] or not result["demonstrated_savings"], result
