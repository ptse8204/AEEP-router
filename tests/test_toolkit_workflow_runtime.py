"""Operator lifecycle fixtures; no upstream SDK, benchmark or model is executed."""

import hashlib
import json
from pathlib import Path

import pytest
from test_toolkit_runtime_install import fake_install, installation
from test_toolkit_workflow_accounting import accounting
from test_toolkit_workflow_v2 import definition

from aeep.assessment.models import content_digest
from aeep.errors import ConfigurationError
from aeep_toolkit import install_runtime
from aeep_toolkit.cli import main
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.models import ExtensionManifest
from aeep_toolkit.workflow import StackWorkflow
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_runtime import lifecycle, lifecycle_preview

pytestmark = pytest.mark.usefixtures("installer_fixture_capacity")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configured(tmp_path, count=1):
    tmp_path = tmp_path.resolve()
    workflow, data, _ = definition(tmp_path)
    selected = data["configurations"]["document-data"]
    registry = json.loads((tmp_path / "registry.json").read_text())
    policy = json.loads((tmp_path / "policy.json").read_text())
    plans = {}
    for index in range(count):
        folder = tmp_path / f"plan-{index}"
        folder.mkdir()
        plan = installation(folder)
        plans[f"python-{index}"] = plan
        path = folder / "installation.json"
        path.write_text(plan.model_dump_json())
        component = "aeep-evaluator" if index == 0 else "waza"
        if component not in selected["components"]:
            selected["components"].append(component)
        metadata = next(
            item for item in registry["extensions"] if item["extension_id"] == component
        )
        metadata["source"]["artifact_sha256"] = plan.wheels[0].sha256
        policy["reviewed_dependency_manifests"].append(
            manifest_digest(ExtensionManifest.model_validate(metadata))
        )
        policy["reviewed_dependency_manifests"].extend(
            item.manifest_sha256 for item in plan.preview.items
        )
        policy["allowed_data_rights"].append("fixture-only")
        for field in (
            "allowed_filesystem_scopes",
            "allowed_authentication",
            "allowed_financial_exposure",
        ):
            policy[field] = list(dict.fromkeys([*policy[field], *getattr(plan.policy, field)]))
        selected.setdefault("runtimes", {})[f"python-{index}"] = {
            "installation": {"path": str(path), "sha256": sha(path)},
            "components": {component: "engine"},
        }
    policy["reviewed_dependency_manifests"] = list(
        dict.fromkeys(policy["reviewed_dependency_manifests"])
    )
    for name, value in [("registry", registry), ("policy", policy)]:
        path = tmp_path / (name + ".json")
        path.write_text(json.dumps(value))
        data[name]["sha256"] = sha(path)
    workflow.write_text(json.dumps(data))
    value = accounting(tmp_path, workflow)
    router, repo, scope, scope_path, _ = value
    scope = WorkflowAccountingDefinition.model_validate(
        scope.model_dump(mode="json")
        | {
            "schema_version": "aeep.toolkit.workflow-accounting.v2",
            "operations": ["setup", "readiness", "remove"],
        }
    )
    scope_path.write_text(scope.model_dump_json())
    repo.review(repo.put("toolkit_workflow_accounting", content_digest(scope), scope))
    return workflow, plans, router, repo, scope, scope_path


def run(value, operation, key, selection=("python-0",)):
    path, _plans, _router, _repo, _scope, accounting_file = value
    preview, _ = lifecycle_preview(path, "document-data", selection, operation=operation)
    assert not preview["blockers"], preview["blockers"]
    return lifecycle(
        path,
        "document-data",
        selection,
        operation=operation,
        reviewed_digest=preview["review_sha256"],
        accounting=accounting_file,
        operation_key=key,
    )


def test_preview_and_readiness_are_inert_and_do_not_assert_functionality(
    tmp_path, monkeypatch, capsys
):
    value = configured(tmp_path)
    path, plans, router, repo, scope, _ = value
    try:
        monkeypatch.setattr(
            "aeep_toolkit.workflow_runtime.apply", lambda *_: pytest.fail("inspection installed")
        )
        main(
            [
                "workflow",
                "readiness",
                "--workflow",
                str(path),
                "--configuration",
                "document-data",
                "--runtime",
                "python-0",
            ]
        )
        result = json.loads(capsys.readouterr().out)
        observed = result["observations"]["python-0"]
        assert observed["installed"] is False and observed["enabled"] is None
        assert (
            observed["functional_readiness"] == "NOT_VERIFIED"
            and observed["execution_permission"] == "NOT_VERIFIED"
        )
        assert result["workflow_accounting"]["coverage"] == "NOT_RECORDED"
        assert not repo.operation_ledger(scope.request.plan_id).operations
        assert not Path(plans["python-0"].destination).exists()
    finally:
        router.store.close()


def test_real_owned_fixture_lifecycle_through_the_ordinary_workflow(tmp_path, capsys):
    value = configured(tmp_path)
    path, plans, router, repo, scope, accounting_file = value
    try:
        common = [
            "--workflow",
            str(path),
            "--configuration",
            "document-data",
            "--runtime",
            "python-0",
            "--accounting",
            str(accounting_file),
        ]
        review, _ = lifecycle_preview(path, "document-data", ("python-0",), operation="setup")
        main(
            [
                "workflow",
                "setup",
                *common,
                "--operation-id",
                "setup-one",
                "--reviewed-digest",
                review["review_sha256"],
            ]
        )
        installed = json.loads(capsys.readouterr().out)
        assert (
            installed["complete"] is True
            and installed["results"][0]["observation"]["installed"] is True
        )
        # Idempotence uses exactly the same plan/review. It starts no second install.
        again, _ = lifecycle_preview(path, "document-data", ("python-0",), operation="setup")
        assert again["review_sha256"] == review["review_sha256"]
        main(
            [
                "workflow",
                "setup",
                *common,
                "--operation-id",
                "setup-two",
                "--reviewed-digest",
                review["review_sha256"],
            ]
        )
        assert json.loads(capsys.readouterr().out)["complete"] is True
        untouched = tmp_path / "user-notes.txt"
        untouched.write_text("preserve")
        removal, _ = lifecycle_preview(path, "document-data", ("python-0",), operation="remove")
        main(
            [
                "workflow",
                "remove",
                *common,
                "--operation-id",
                "remove-one",
                "--reviewed-digest",
                removal["review_sha256"],
            ]
        )
        assert json.loads(capsys.readouterr().out)["complete"] is True
        assert (
            not Path(plans["python-0"].destination).exists() and untouched.read_text() == "preserve"
        )
        assert install_runtime.paths(plans["python-0"])[1].exists()
        operations = repo.operation_ledger(scope.request.plan_id).operations
        assert [item.stage for item in operations] == [
            "workflow_remove_overhead",
            "workflow_setup_overhead",
            "workflow_setup_overhead",
        ]
        assert all(item.elapsed_seconds is not None for item in operations)
    finally:
        router.store.close()


@pytest.mark.parametrize("change", ["artifact", "policy", "file", "review", "accounting"])
def test_mismatch_or_missing_authority_prevents_effects(tmp_path, monkeypatch, change):
    value = configured(tmp_path)
    path, plans, router, _repo, _scope, accounting_file = value
    try:
        facts, _ = lifecycle_preview(path, "document-data", ("python-0",), operation="setup")
        if change == "artifact":
            registry_path = tmp_path / "registry.json"
            data = json.loads(registry_path.read_text())
            data["extensions"][0]["source"]["artifact_sha256"] = "a" * 64
            registry_path.write_text(json.dumps(data))
        elif change == "policy":
            rules = tmp_path / "policy.json"
            data = json.loads(rules.read_text())
            data["allowed_licenses"] = []
            rules.write_text(json.dumps(data))
        elif change == "file":
            p = tmp_path / "plan-0/installation.json"
            p.write_text(p.read_text() + " ")
        monkeypatch.setattr(
            "aeep_toolkit.workflow_runtime.apply",
            lambda *_: pytest.fail("invalid request installed"),
        )
        with pytest.raises((ValueError, ConfigurationError)):
            lifecycle(
                path,
                "document-data",
                ("python-0",),
                operation="setup",
                reviewed_digest="a" * 64 if change == "review" else facts["review_sha256"],
                accounting=None if change == "accounting" else accounting_file,
                operation_key=None if change == "accounting" else "denied",
            )
        assert not Path(plans["python-0"].destination).exists()
    finally:
        router.store.close()


def test_shared_runtime_is_retained_for_other_configuration(tmp_path):
    value = configured(tmp_path)
    path, plans, router, *_ = value
    try:
        data = json.loads(path.read_text())
        data["configurations"]["software-engineering"] = data["configurations"]["document-data"]
        path.write_text(json.dumps(data))
        facts, _ = lifecycle_preview(path, "document-data", ("python-0",), operation="remove")
        assert facts["shared_references"]["python-0"] == ["software-engineering:python-0"]
        assert any("retained" in reason for reason in facts["blockers"])
        assert not Path(plans["python-0"].destination).exists()
    finally:
        router.store.close()


def test_independent_runtime_continues_after_terminal_install_failure(tmp_path, monkeypatch):
    value = configured(tmp_path, 2)
    _path, plans, router, repo, scope, _ = value
    fake_install(monkeypatch)

    def process(_argv, root):
        if str(root) == plans["python-0"].destination:
            raise TimeoutError("first-party fixture only")

    monkeypatch.setattr(install_runtime, "run", process)
    try:
        result = run(value, "setup", "separate-components", ("python-0", "python-1"))
        assert result["complete"] is False
        assert [item["status"] for item in result["results"]] == ["failed", "installed"]
        assert (
            install_runtime.load_state(install_runtime.paths(plans["python-0"])[1])[1]["status"]
            == "failed"
        )
        assert Path(plans["python-1"].destination).exists()
        receipts = router.store.list_receipts()
        assert (
            receipts[-1].execution_success is False
            and receipts[-1].error_type == "RuntimeLifecycleFailure"
        )
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1
    finally:
        router.store.close()


def test_user_edit_survives_selected_removal(tmp_path, monkeypatch):
    value = configured(tmp_path)
    _path, plans, router, *_ = value
    fake_install(monkeypatch)
    try:
        assert run(value, "setup", "install")["complete"]
        file = Path(plans["python-0"].destination) / "user-file"
        file.write_text("mine")
        result = run(value, "remove", "conflict")
        assert result["complete"] is False and file.read_text() == "mine"
        assert result["results"][0]["observation"]["installer_status"] == "modified_runtime"
    finally:
        router.store.close()


def test_legacy_definitions_and_accounting_version_keep_their_meaning(tmp_path):
    path, data, _ = definition(tmp_path)
    model = StackWorkflow.model_validate(data)
    assert "runtimes" not in model.model_dump(mode="json")["configurations"]["document-data"]
    data["configurations"]["document-data"]["runtimes"] = {
        "bad": {
            "installation": {"path": "unused.json", "sha256": "a" * 64},
            "components": {"unselected": "engine"},
        }
    }
    with pytest.raises(ValueError, match="selected components"):
        StackWorkflow.model_validate(data)
    fields = {
        "workflow_sha256": "a" * 64,
        "configurations": ["document-data"],
        "operations": ["setup"],
        "source_digest": "a" * 64,
        "manifest_path": str(path),
        "manifest_sha256": "a" * 64,
        "request": {
            "subject_digest": "a" * 64,
            "recipe_digest": "b" * 64,
            "mapping_digest": "c" * 64,
            "environment_digest": "d" * 64,
            "authorization_id": "fixture",
            "definition_digests": ["a" * 64],
            "seed": 0,
        },
        "maximum_overhead_seconds": 30,
    }
    with pytest.raises(ValueError, match="v2"):
        WorkflowAccountingDefinition.model_validate(fields)
    assert WorkflowAccountingDefinition.model_validate(
        fields | {"schema_version": "aeep.toolkit.workflow-accounting.v2"}
    ).operations == ("setup",)


def refresh_scope(value):
    path, _plans, _router, repo, _scope, scope_file = value
    scoped = WorkflowAccountingDefinition.model_validate_json(scope_file.read_bytes())
    scoped.workflow_sha256 = sha(path)
    scope_file.write_text(scoped.model_dump_json())
    repo.review(repo.put("toolkit_workflow_accounting", content_digest(scoped), scoped))
    return scoped


def test_aliases_share_one_installation_and_missing_second_config_does_not_run(
    tmp_path, monkeypatch
):
    value = configured(tmp_path)
    path, _plans, router, *_ = value
    data = json.loads(path.read_text())
    data["configurations"]["document-data"]["runtimes"]["alias"] = data["configurations"][
        "document-data"
    ]["runtimes"]["python-0"]
    path.write_text(json.dumps(data))
    refresh_scope(value)
    fake_install(monkeypatch)
    observed = []
    original = install_runtime.apply

    def once(plan, review):
        observed.append(plan.destination)
        return original(plan, review)

    monkeypatch.setattr("aeep_toolkit.workflow_runtime.apply", once)
    try:
        result = run(value, "setup", "aliases", ("python-0", "alias"))
        assert result["complete"] is True and len(observed) == 1
        assert result["results"][1]["shared_operation"] is True
        assert result["results"][0]["record_ref"] == result["results"][1]["record_ref"]
    finally:
        router.store.close()


def test_revocation_between_independent_installations_stops_further_effects(tmp_path, monkeypatch):
    value = configured(tmp_path, 2)
    _path, plans, router, repo, scope, _ = value
    fake_install(monkeypatch)
    original = install_runtime.apply

    def revoke(plan, review):
        result = original(plan, review)
        repo.review(content_digest(scope), revoke=True)
        return result

    monkeypatch.setattr("aeep_toolkit.workflow_runtime.apply", revoke)
    try:
        with pytest.raises(ConfigurationError, match="operator review"):
            run(value, "setup", "revoked-after-first", ("python-0", "python-1"))
        assert Path(plans["python-0"].destination).exists()
        assert not Path(plans["python-1"].destination).exists()
        operations = repo.operation_ledger(scope.request.plan_id).operations
        assert len(operations) == 1 and operations[0].elapsed_seconds is not None
    finally:
        router.store.close()


def test_changed_runtime_binding_stops_before_second_effect(tmp_path, monkeypatch):
    value = configured(tmp_path, 2)
    _path, plans, router, *_ = value
    fake_install(monkeypatch)
    original = install_runtime.apply

    def change(plan, review):
        result = original(plan, review)
        file = tmp_path / "plan-1/installation.json"
        file.write_text(file.read_text() + " ")
        return result

    monkeypatch.setattr("aeep_toolkit.workflow_runtime.apply", change)
    try:
        with pytest.raises(ValueError, match="changed after binding"):
            run(value, "setup", "changed-after-first", ("python-0", "python-1"))
        assert Path(plans["python-0"].destination).exists()
        assert not Path(plans["python-1"].destination).exists()
    finally:
        router.store.close()


def test_exported_workflow_keeps_parent_runtime_reference(tmp_path):
    value = configured(tmp_path)
    path, plans, router, *_ = value
    try:
        data = json.loads(path.read_text())
        copied = tmp_path / "prepared-workflow.json"
        binding = data["configurations"]["document-data"]["runtimes"]["python-0"]
        binding["references"] = [{"path": str(path), "sha256": sha(path)}]
        copied.write_text(json.dumps(data))
        result, _ = lifecycle_preview(copied, "document-data", ("python-0",), operation="remove")
        assert any(str(path) in ref for ref in result["shared_references"]["python-0"])
        assert result["blockers"]
        assert not Path(plans["python-0"].destination).exists()
    finally:
        router.store.close()


@pytest.mark.parametrize("target", [str(Path.home()), str(Path.home() / ".ssh/runtime"), "/"])
def test_readiness_never_inspects_protected_runtime_targets(tmp_path, monkeypatch, target):
    value = configured(tmp_path)
    path, _plans, router, *_ = value
    try:
        file = tmp_path / "plan-0/installation.json"
        model = json.loads(file.read_text())
        model["destination"] = target
        file.write_text(json.dumps(model))
        data = json.loads(path.read_text())
        data["configurations"]["document-data"]["runtimes"]["python-0"]["installation"][
            "sha256"
        ] = sha(file)
        path.write_text(json.dumps(data))
        monkeypatch.setattr(
            "aeep_toolkit.workflow_runtime.snapshot",
            lambda *_: pytest.fail("protected tree scanned"),
        )
        with pytest.raises(ConfigurationError, match="credential-state"):
            lifecycle_preview(path, "document-data", ("python-0",), operation="readiness")
    finally:
        router.store.close()
