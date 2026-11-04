"""First-party substitutes verify wiring; these tests do not execute SkillRank."""

import base64
import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_toolkit_file_runtime import installation
from test_toolkit_runtime_install import installer_fixture_capacity as installer_fixture_capacity
from test_toolkit_workflow_runtime import configured as runtime_configured

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    content_digest,
)
from aeep.errors import ConfigurationError
from aeep.executors.base import BaseExecutor, ExecutionContext
from aeep.models import ActionRequest, ExecutorKind, ExecutorSpec, RawExecution, SideEffect, utc_now
from aeep_toolkit import catalog_worker, workflow_catalog
from aeep_toolkit.cli import main
from aeep_toolkit.install_runtime import apply, digest
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.models import ExtensionManifest
from aeep_toolkit.workflow import StackWorkflow
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_catalog import (
    CatalogContainerExecutor,
    CatalogRuntimeDefinition,
    catalog,
    catalog_preview,
)

pytestmark = pytest.mark.usefixtures("installer_fixture_capacity")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configured(tmp_path):
    tmp_path = tmp_path.resolve()
    path, _, router, repo, old_scope, scope_file = runtime_configured(tmp_path)
    folder = tmp_path / "catalog-artifacts"
    folder.mkdir()
    plan = installation(folder)
    plan_file = tmp_path / "file-installation.json"
    plan_file.write_text(plan.model_dump_json())
    apply(plan, digest(plan))  # Copies inert first-party data. No upstream code.
    data = json.loads(path.read_bytes())
    registry_file = tmp_path / "registry.json"
    registry = json.loads(registry_file.read_bytes())
    metadata = dict(registry["extensions"][0])
    metadata.update(extension_id="skillrank", role="catalog", disk_bytes=0, memory_bytes=0)
    metadata["source"] = dict(
        metadata["source"],
        revision=catalog_worker.SOURCE_REVISION,
        artifact_sha256=plan.files[0].sha256,
    )
    manifest = ExtensionManifest.model_validate(metadata)
    registry["extensions"].append(manifest.model_dump(mode="json"))
    registry_file.write_text(json.dumps(registry))
    policy_file = tmp_path / "policy.json"
    policy = json.loads(policy_file.read_bytes())
    policy["reviewed_dependency_manifests"] += [
        manifest_digest(manifest),
        *[i.manifest_sha256 for i in plan.preview.items],
    ]
    policy["allowed_data_rights"].append(plan.preview.items[0].manifest.source.data_rights)
    policy_file.write_text(json.dumps(policy))
    for key, file in [("registry", registry_file), ("policy", policy_file)]:
        data[key]["sha256"] = sha(file)
    catalog_file = tmp_path / "catalog.json"
    catalog_file.write_text(
        json.dumps([{"slug": "fixture/selected", "content": "private reviewed fixture text"}])
    )
    runtime = tmp_path / "docker-fixture"
    runtime.write_text("first-party identity only; never executed")
    control = tmp_path / "catalog-control"
    control.mkdir(mode=0o700)
    env = AssessmentEnvironment(
        environment_id="catalog-fixture",
        kind="container",
        identity={},
        network=False,
        container_image="sha256:" + "a" * 64,
        container_runtime=str(runtime),
        container_socket=str(tmp_path / "docker.sock"),
    )
    env_ref = repo.put("environment", env.environment_id, env)
    repo.review(env_ref)
    request = old_scope.request.model_copy(
        update={
            "environment_digest": env_ref,
            "authorization_id": "catalog-owned",
            "definition_digests": [*old_scope.request.definition_digests, env_ref],
        }
    )
    repo.grant(
        AssessmentAuthorization(
            authorization_id=request.authorization_id,
            subject_digests=[request.subject_digest],
            recipe_digests=[request.recipe_digest],
            environment_digests=[env_ref],
            limits=AssessmentLimits(max_operations=20, max_model_turns=0, max_elapsed_seconds=2000),
            allowed_destinations=["local"],
            expires_at=utc_now() + timedelta(minutes=20),
        )
    )
    worker = Path(catalog_worker.__file__).resolve()
    binding = CatalogRuntimeDefinition(
        runtime_id="skillrank-files",
        environment=env,
        request=request,
        catalog={"path": catalog_file.name, "sha256": sha(catalog_file)},
        catalog_source=plan.preview.items[0].manifest.source.model_copy(
            update={"artifact_sha256": sha(catalog_file)}
        ),
        control_root=str(control),
        worker_sha256=sha(worker),
        executable_dependencies={str(runtime): sha(runtime), str(worker): sha(worker)},
    )
    binding_file = tmp_path / "catalog-runtime.json"
    binding_file.write_text(binding.model_dump_json())
    repo.review(repo.put("toolkit_catalog_runtime", content_digest(binding), binding))
    selected = data["configurations"]["document-data"]
    selected["components"].append("skillrank")
    selected.setdefault("runtimes", {})["skillrank-files"] = {
        "installation": {"path": plan_file.name, "sha256": sha(plan_file)},
        "components": {"skillrank": "engine"},
    }
    selected["catalog"] = {"path": binding_file.name, "sha256": sha(binding_file)}
    path.write_text(json.dumps(data))
    scope = WorkflowAccountingDefinition.model_validate(
        old_scope.model_dump(mode="json")
        | {
            "schema_version": "aeep.toolkit.workflow-accounting.v4",
            "workflow_sha256": sha(path),
            "request": request.model_dump(mode="json"),
            "operations": ["catalog", "readiness", "remove"],
        }
    )
    scope_file.write_text(scope.model_dump_json())
    repo.review(repo.put("toolkit_workflow_accounting", content_digest(scope), scope))
    return path, router, repo, binding, scope_file, scope, plan


def substitute(monkeypatch, *, cleanup=True, change=None, failure=None):
    calls = []

    class Fixture(BaseExecutor):
        def __init__(self, *_):
            self.cleanup_verified = cleanup

        async def cleanup(self, _):
            return self.cleanup_verified

        async def execute(self, context):
            calls.append(context)
            if context.invocation_check:
                context.invocation_check()
            if failure:
                raise failure("private diagnostic content")
            payload = context.request.input
            result = {
                "component": "skillrank",
                "source_revision": catalog_worker.SOURCE_REVISION,
                "version": catalog_worker.VERSION,
                "binary_sha256": payload["binary_sha256"],
                "catalog_sha256": payload["catalog_sha256"],
                "implementation_source": payload["implementation_source"],
                "status": "completed",
                "result": {
                    "items": [{"slug": "fixture/selected", "summary": "ephemeral catalog contents"}]
                },
                "server_stopped": True,
                "provider_claims_are_not_scan_or_usefulness_evidence": True,
            }
            if change:
                change(result)
            return RawExecution(status="success", output=result)

    monkeypatch.setattr(workflow_catalog, "CatalogContainerExecutor", Fixture)
    return calls


def invoke(value, key="lookup"):
    path, _, _, _, scope, *_ = value
    facts = catalog_preview(path, "document-data", "search", "private query string")[0]
    assert not facts["blockers"], facts["blockers"]
    return catalog(
        path,
        "document-data",
        "search",
        "private query string",
        accounting=scope,
        operation_key=key,
        reviewed_digest=facts["review_sha256"],
    )


def test_preview_is_inert_and_legacy_selection_stays_absent(tmp_path, monkeypatch, capsys):
    value = configured(tmp_path)
    path, router, repo, _, _, scope, *_ = value
    try:
        monkeypatch.setattr(
            workflow_catalog, "CatalogContainerExecutor", lambda *_: pytest.fail("preview executed")
        )
        main(
            [
                "workflow",
                "catalog",
                "--workflow",
                str(path),
                "--configuration",
                "document-data",
                "--mode",
                "search",
                "--value",
                "private query string",
            ]
        )
        facts = json.loads(capsys.readouterr().out)
        assert (
            facts["execution_authorized"] is False
            and facts["functional_readiness"] == "NOT_VERIFIED_BY_PREVIEW"
        )
        assert "private query string" not in json.dumps(facts)
        assert not repo.operation_ledger(scope.request.plan_id).operations
        data = json.loads(path.read_bytes())
        del data["configurations"]["document-data"]["catalog"]
        assert (
            "catalog"
            not in StackWorkflow.model_validate(data).model_dump(mode="json")["configurations"][
                "document-data"
            ]
        )
    finally:
        router.store.close()


def test_lookup_has_linked_minimized_evidence_exclusive_accounting_and_no_replay(
    tmp_path, monkeypatch
):
    value = configured(tmp_path)
    _, router, repo, _, _, scope, *_ = value
    calls = substitute(monkeypatch)
    try:
        result = invoke(value)
        assert len(calls) == 1 and result["result"]["items"][0]["slug"] == "fixture/selected"
        record = repo.get("toolkit_workflow_catalog", result["catalog_ref"])
        receipt = repo.get("toolkit_component_receipt", result["operation_id"])
        evidence = repo.get("execution_evidence", result["execution_evidence_ref"])
        assert evidence["attempt_id"] == record["operation_id"] and evidence["complete"]
        assert receipt["execution_success"] and record["cleanup_verified"]
        persisted = json.dumps([record, receipt, evidence])
        assert (
            "private query string" not in persisted
            and "ephemeral catalog contents" not in persisted
        )
        operations = repo.operation_ledger(scope.request.plan_id).operations
        assert {o.stage for o in operations} == {"workflow_catalog_overhead", "workflow_catalog"}
        wrapper = repo.get("toolkit_workflow_receipt", record["wrapper_operation_id"])
        assert (
            wrapper["metadata"]["excluded_nested_intervals"][0]["stage"]
            == "canonical_catalog_lookup"
        )
        with pytest.raises(ConfigurationError, match="already reserved"):
            invoke(value)
        assert len(calls) == 1
    finally:
        router.store.close()


@pytest.mark.parametrize(
    "change",
    [
        lambda r: r.update(version="wrong"),
        lambda r: r.update(server_stopped=False),
        lambda r: r.update(status="not_found"),
        lambda r: r.update(result=[]),
        lambda r: r.update(result={"items": None}),
    ],
)
def test_invalid_upstream_output_retains_charges_without_success(tmp_path, monkeypatch, change):
    value = configured(tmp_path)
    _, router, repo, _, _, scope, *_ = value
    substitute(monkeypatch, change=change)
    try:
        with pytest.raises(ConfigurationError, match="incomplete"):
            invoke(value)
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 2
        assert all(
            o.elapsed_seconds is not None
            for o in repo.operation_ledger(scope.request.plan_id).operations
        )
        assert not router.store.list_receipts()[-1].execution_success
    finally:
        router.store.close()


@pytest.mark.parametrize("failure", [RuntimeError, KeyboardInterrupt])
def test_interrupt_or_failure_is_charged_and_uncertain_cleanup_blocks_new_dispatch(
    tmp_path, monkeypatch, failure
):
    value = configured(tmp_path)
    _, router, repo, _, _, scope, *_ = value
    calls = substitute(monkeypatch, cleanup=False, failure=failure)
    try:
        with pytest.raises(failure):
            invoke(value)
        with pytest.raises(ConfigurationError, match="cleanup is uncertain"):
            invoke(value, "second")
        assert len(calls) == 1
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 3
        assert all(
            o.elapsed_seconds is not None
            for o in repo.operation_ledger(scope.request.plan_id).operations
        )
    finally:
        router.store.close()


@pytest.mark.parametrize("change", ["binary", "catalog", "worker", "review", "control", "rights"])
def test_drift_or_missing_review_stops_before_backend(tmp_path, monkeypatch, change):
    value = configured(tmp_path)
    path, router, repo, binding, scope_file, _, plan = value
    substitute(monkeypatch, failure=AssertionError)
    try:
        facts = catalog_preview(path, "document-data", "search", "metadata")[0]
        if change == "binary":
            (Path(plan.destination) / plan.files[0].destination).chmod(0o600)
            (Path(plan.destination) / plan.files[0].destination).write_bytes(b"changed")
        elif change == "catalog":
            (tmp_path / "catalog.json").write_text("[]")
        elif change == "worker":
            binding.worker_sha256 = "0" * 64
            file = tmp_path / "catalog-runtime.json"
            file.write_text(binding.model_dump_json())
            data = json.loads(path.read_bytes())
            data["configurations"]["document-data"]["catalog"]["sha256"] = sha(file)
            path.write_text(json.dumps(data))
        elif change == "control":
            Path(binding.control_root).rmdir()
        elif change == "rights":
            file = tmp_path / "policy.json"
            policy = json.loads(file.read_bytes())
            policy["allowed_data_rights"] = []
            file.write_text(json.dumps(policy))
        else:
            repo.store._connection.execute(
                "UPDATE assessment_reviews SET revoked=1 WHERE digest=?", (content_digest(binding),)
            )
            repo.store._connection.commit()
        with pytest.raises((ValueError, ConfigurationError)):
            catalog(
                path,
                "document-data",
                "search",
                "metadata",
                accounting=scope_file,
                operation_key="denied",
                reviewed_digest=facts["review_sha256"],
            )
    finally:
        router.store.close()


def test_container_command_preserves_boundaries_and_adds_only_one_binary_mount(tmp_path):
    value = configured(tmp_path)
    path, router, _, binding, *_ = value
    try:
        _, _, _, binary, *_ = catalog_preview(path, "document-data", "search", "metadata")
        executor = CatalogContainerExecutor(binding, binary, tmp_path / "empty-docker-config")
        spec = ExecutorSpec(
            id="catalog",
            capability="catalog@1",
            kind=ExecutorKind.COMMAND,
            side_effect=SideEffect.READ,
            description="first-party inert command inspection",
            config={"argv": ["python3", "-I", "-B", str(Path(catalog_worker.__file__).resolve())]},
        )
        context = ExecutionContext(
            request=ActionRequest(capability=spec.capability),
            spec=spec,
            estimate=spec.estimate,
            attempt=1,
            attempt_id="catalog-owned",
            approved_side_effect=SideEffect.READ,
        )
        argv, _ = executor.command(context)
        assert argv[1:3] == ["--config", str(tmp_path / "empty-docker-config")]
        assert "--pull=never" in argv and "--read-only" in argv
        assert argv[argv.index("--network") + 1] == "none"
        mounts = [argv[i + 1] for i, item in enumerate(argv) if item == "--mount"]
        assert len(mounts) == 3 and all("readonly" in m for m in mounts)
        assert any("dst=/opt/aeep-skillrank" in m for m in mounts)
        assert "aeep.workflow-catalog=catalog-owned" in argv
        assert all("docker.sock" not in m for m in mounts)
    finally:
        router.store.close()


def test_worker_uses_real_cli_contract_and_stops_owned_process_with_substitutes(
    tmp_path, monkeypatch
):
    """No subprocess or upstream server executes: this is protocol wiring only."""
    binary = tmp_path / "first-party-inert-binary"
    binary.write_text("never executed")
    monkeypatch.setattr(catalog_worker, "BINARY", binary)
    calls = []
    from subprocess import CompletedProcess

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if "--version" in argv:
            return CompletedProcess(argv, 0, b"skillrank 0.1.5\n", b"")
        return CompletedProcess(argv, 0, b'{"items":[]}', b"")

    class Process:
        stopped = False

        def poll(self):
            return 0 if self.stopped else None

        def terminate(self):
            self.stopped = True

        def wait(self, **_):
            return 0

    process = Process()
    monkeypatch.setattr(catalog_worker.subprocess, "run", run)
    monkeypatch.setattr(catalog_worker.subprocess, "Popen", lambda *_, **__: process)
    data = b'[{"slug":"fixture/selected"}]'
    request = {
        "binary_sha256": sha(binary),
        "catalog_sha256": hashlib.sha256(data).hexdigest(),
        "catalog_base64": base64.b64encode(data).decode(),
        "query": {"mode": "search", "value": "selected"},
        "implementation_source": "a" * 64,
    }
    result = catalog_worker.lookup(request, tmp_path / "work")
    assert result["server_stopped"] and process.stopped
    assert calls[-1][0][1:] == ["search", "selected", "--json"]
    assert all("CODEX_HOME" not in kw["env"] for _, kw in calls)
    assert calls[-1][1]["env"]["SKILLRANK_API_URL"] == "http://127.0.0.1:18899"


@pytest.mark.parametrize(
    "mode,value",
    [
        ("search", "--flag"),
        ("show", "https://bad"),
        ("search", "x\ny"),
        ("show", "../x"),
        ("other", "x"),
    ],
)
def test_query_rejects_flags_and_unbounded_identifiers(mode, value):
    with pytest.raises(ValueError):
        catalog_worker.query(mode, value)


@pytest.mark.parametrize("version", ["v1", "v2", "v3"])
def test_old_accounting_cannot_silently_gain_catalog_authority(tmp_path, version):
    value = configured(tmp_path)
    try:
        fields = value[5].model_dump(mode="json")
        fields["schema_version"] = "aeep.toolkit.workflow-accounting." + version
        with pytest.raises(ValueError):
            WorkflowAccountingDefinition.model_validate(fields)
    finally:
        value[1].store.close()
