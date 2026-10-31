"""Large public integration inputs keep their narrow reader and canonical guards."""

import asyncio
import json

import pytest
from test_toolkit_workflow_preparation import _no_close, configured

from aeep.assessment.models import AssessmentPlan, content_digest
from aeep.router import Router
from aeep_toolkit.cli import (
    INTEGRATION_PLAN_BYTES,
    METADATA_BYTES,
    main,
    read_bytes,
    read_plan_bytes,
)
from aeep_toolkit.managed import main as managed_main
from aeep_toolkit.workflow import prepare_stack
from aeep_toolkit.workflow_preparation import prepare_canonical


def test_large_task_reaches_both_cli_previews_without_loading_workers(
    tmp_path, monkeypatch, capsys
):
    path, service, cases, _ = configured(tmp_path, large=True)
    preview = prepare_stack(path, "document-data")
    monkeypatch.setattr(Router, "from_manifest", lambda *_: service.router)
    monkeypatch.setattr(service.router, "close", _no_close)
    try:
        result = prepare_canonical(
            path,
            "document-data",
            reviewed_digest=preview["review_sha256"],
            destination=tmp_path / "prepared",
        )
        plan_path = tmp_path / "prepared/plan.json"
        assert METADATA_BYTES < plan_path.stat().st_size < INTEGRATION_PLAN_BYTES
        with pytest.raises(ValueError):
            read_bytes(plan_path)
        plan = AssessmentPlan.model_validate_json(read_plan_bytes(plan_path))
        assert plan.suite.cases == cases.cases
        assert content_digest(plan) == result["plan_digest"]
        monkeypatch.setattr(
            Router, "from_manifest", lambda *_: pytest.fail("preview opened a backend")
        )
        assert (
            main(
                [
                    "workflow",
                    "plan",
                    "--workflow",
                    str(tmp_path / "prepared/workflow.json"),
                    "--configuration",
                    "document-data",
                ]
            )
            == 0
        )
        value = json.loads(capsys.readouterr().out)
        assert value["assessment"]["backend_review"]["plan_id"] == result["plan_id"]
        managed_main(
            ["plan", "--plan", str(plan_path), "--source", str(path.parent / "source.json")]
        )
        value = json.loads(capsys.readouterr().out)
        assert value["plan_sha256"] == result["plan_digest"]
        assert (
            service.router.store._connection.execute(
                "SELECT count(*) FROM assessment_jobs"
            ).fetchone()[0]
            == 0
        )
    finally:
        asyncio.run(Router.close(service.router))


@pytest.mark.parametrize(
    "version", ["assessment.plan.v1", "assessment.plan.v4", "assessment.plan.v6", "unrecognized"]
)
def test_large_metadata_or_historical_plans_cannot_use_v7_limit(tmp_path, version):
    path = tmp_path / "large.json"
    path.write_text(json.dumps({"schema_version": version, "padding": "x" * METADATA_BYTES}))
    with pytest.raises(ValueError, match="v7 integration"):
        read_plan_bytes(path)
    with pytest.raises(ValueError):
        read_bytes(path)


def test_integration_plan_bound_and_secret_denial_precede_json_parsing(tmp_path, monkeypatch):
    large = tmp_path / "oversized.json"
    with large.open("wb") as stream:
        stream.seek(INTEGRATION_PLAN_BYTES)
        stream.write(b"x")
    monkeypatch.setattr(
        json, "loads", lambda *_: pytest.fail("oversized input reached JSON parser")
    )
    with pytest.raises(ValueError, match="bounded reader"):
        read_plan_bytes(large)
    # No credential is opened, even with the new plan reader and a plausible name.
    secret = tmp_path / "auth.json"
    with pytest.raises(ValueError, match="credential files"):
        read_plan_bytes(secret)
