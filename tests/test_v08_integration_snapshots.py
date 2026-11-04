"""Finite integration preparation survives only its exact scoped snapshot."""
from __future__ import annotations

import json

import pytest

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep.store import ReceiptStore

pytestmark = pytest.mark.assessment_lifecycle


def records(version="assessment.plan.v8"):
    recipe, environment = {"fixture": "recipe"}, {"fixture": "environment"}
    recipe_ref, environment_ref = content_digest(recipe), content_digest(environment)
    selected = {"schema_version": "assessment.integration-cases.v1", "request_id": "selected",
                "recipe_digest": recipe_ref, "environment_digest": environment_ref, "fixture": "selected tasks"}
    other = {**selected, "fixture": "unrelated tasks, same request name"}
    selected_ref = content_digest(selected)
    plan = {"schema_version": version, "integration_case_set_digest": selected_ref,
            "preparation_request_ids": ["selected"], "definition_digests": [selected_ref]}
    return plan, [
        ("recipe", recipe_ref, recipe), ("environment", environment_ref, environment),
        ("integration_case_set", selected_ref, selected),
        ("integration_case_set", content_digest(other), other),
        ("recipe_materialization_request", "selected", {"fixture": "unrelated legacy alias"}),
    ]


def seed(store, plan, documents):
    ref = content_digest(plan)
    with store._immediate_transaction() as connection:
        for kind, identity, document in [*documents, ("plan", ref, plan)]:
            connection.execute("INSERT INTO assessment_records VALUES (?,?,?,?)",
                               (kind, identity, content_digest(document), json.dumps(document)))
    return ref


@pytest.mark.parametrize("version", ["assessment.plan.v7", "assessment.plan.v8"])
def test_exact_integration_set_retained_without_unrelated_tasks_or_legacy_alias(tmp_path, version):
    plan, documents = records(version)
    with ReceiptStore(tmp_path / "source.sqlite3") as source:
        ref = seed(source, plan, documents)
        before = list(source._connection.iterdump())
        scoped = source.campaign_snapshot(bound_digests={ref})
        try:
            retained = {(row[0], row[1]) for row in scoped._connection.execute(
                "SELECT kind,id FROM assessment_records")}
            assert retained == {("plan", ref), *[(kind, identity) for kind, identity, _ in documents[:3]]}
            assert not scoped._connection.execute("SELECT * FROM assessment_operations").fetchall()
            assert not scoped._connection.execute("SELECT * FROM execution_attempts").fetchall()
            assert list(source._connection.iterdump()) == before
        finally:
            scoped.close()


@pytest.mark.parametrize("fault", ["missing_set", "wrong_kind", "wrong_schema", "different_request",
                                   "missing_request", "extra_preparation", "invalid_reference", "missing_dependency", "legacy_plan"])
def test_unbound_integration_preparation_never_falls_back_to_a_matching_name(tmp_path, fault):
    plan, documents = records()
    kind, identity, selected = documents[2]
    if fault == "missing_set":
        documents.pop(2)
    elif fault == "wrong_kind":
        documents[2] = ("recipe_case_set", identity, selected)
    elif fault in {"wrong_schema", "different_request"}:
        key, value = ("schema_version", "assessment.recipe-cases.v1") if fault == "wrong_schema" else ("request_id", "different")
        changed = {**selected, key: value}
        changed_ref = content_digest(changed)
        documents[2] = (kind, changed_ref, changed)
        plan["integration_case_set_digest"] = changed_ref
        plan["definition_digests"] = [changed_ref]
    elif fault == "missing_request":
        plan["preparation_request_ids"] = []
    elif fault == "extra_preparation":
        plan["preparation_request_ids"] = ["selected", "unrelated"]
    elif fault == "invalid_reference":
        plan["integration_case_set_digest"] = []
    elif fault == "missing_dependency":
        documents.pop(0)
    else:
        plan["schema_version"] = "assessment.plan.v6"
        # A legacy plan does not gain a new preparation alias through this fix.
        documents = [item for item in documents if item[0] != "recipe_materialization_request"]
    if fault != "legacy_plan":
        # The tempting legacy alias exists for every modern invalid task set.
        assert any(item[0] == "recipe_materialization_request" for item in documents)
    with ReceiptStore(tmp_path / "source.sqlite3") as source:
        ref = seed(source, plan, documents)
        before = list(source._connection.iterdump())
        with pytest.raises(ConfigurationError, match="missing"):
            source.campaign_snapshot(bound_digests={ref})
        assert list(source._connection.iterdump()) == before
