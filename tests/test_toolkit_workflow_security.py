"""Canonical workflow scanning with explicit first-party executor substitutes."""

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from test_toolkit_contracts import extension_data
from test_toolkit_workflow_accounting import OwnedScope, accounting
from test_toolkit_workflow_v2 import definition

from aeep.assessment.models import (
    AssessmentAuthorization,
    AssessmentEnvironment,
    AssessmentLimits,
    RecipeMaterializationRequest,
    content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.errors import ConfigurationError
from aeep.executors.base import BaseExecutor
from aeep.models import RawExecution, utc_now
from aeep_toolkit import workflow_security as security
from aeep_toolkit.candidate import inspect
from aeep_toolkit.cli import main
from aeep_toolkit.installation import manifest_digest
from aeep_toolkit.models import ExtensionManifest
from aeep_toolkit.workflow_accounting import WorkflowAccountingDefinition
from aeep_toolkit.workflow_security import (
    ScanContainerExecutor,
    ScannerRuntimeDefinition,
    require_scan,
    scan,
    scan_preview,
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def configured(tmp_path):
    path, data, skill = definition(tmp_path)
    runtime = tmp_path / "docker-fixture"
    runtime.write_text("owned first-party executable identity; never executed")
    env = AssessmentEnvironment(
        environment_id="static-scanner-fixture",
        kind="container",
        identity={},
        container_image="sha256:" + "a" * 64,
        container_runtime=str(runtime),
        container_socket=str(tmp_path / "docker.sock"),
        network=False,
    )
    router, repo, wrapper, accounting_file, _ = accounting(tmp_path, path)
    subject = AssessmentService(router, tmp_path / "assessments").inspect_local(skill, kind="skill")
    subject_ref = content_digest(subject)
    recipe = OwnedScope(role="scan-recipe")
    mapping = OwnedScope(role="scan-mapping")
    refs = [
        subject_ref,
        repo.put("toolkit_engineering_scope", "scan-recipe", recipe),
        repo.put("environment", env.environment_id, env),
        repo.put("toolkit_engineering_scope", "scan-mapping", mapping),
    ]
    for ref in refs:
        repo.review(ref)
    repo.grant(
        AssessmentAuthorization(
            authorization_id="owned-static-scan",
            subject_digests=[refs[0]],
            recipe_digests=[refs[1]],
            environment_digests=[refs[2]],
            limits=AssessmentLimits(max_operations=10, max_model_turns=0, max_elapsed_seconds=1000),
            allowed_destinations=["local"],
            expires_at=utc_now() + timedelta(hours=1),
        )
    )
    request = RecipeMaterializationRequest(
        subject_digest=refs[0],
        recipe_digest=refs[1],
        environment_digest=refs[2],
        mapping_digest=refs[3],
        authorization_id="owned-static-scan",
        definition_digests=refs,
        seed=0,
    )
    repo.put("recipe_materialization_request", request.plan_id, request)
    worker = Path(security.__file__).with_name("scanner_worker.py")
    binding = ScannerRuntimeDefinition(
        environment=env,
        request=request,
        candidate_sha256=inspect(skill).sha256,
        worker_sha256=sha(worker),
        executable_dependencies={str(runtime): sha(runtime), str(worker): sha(worker)},
    )
    binding_file = tmp_path / "scanner.json"
    binding_file.write_text(binding.model_dump_json())
    ref = repo.put("toolkit_scanner_runtime", content_digest(binding), binding)
    repo.review(ref)
    metadata = ExtensionManifest.model_validate(
        extension_data()
        | {
            "extension_id": "skill-scanner",
            "role": "scanner",
            "source": dict(extension_data()["source"], revision=binding.source_revision),
            "disk_bytes": 0,
            "memory_bytes": 0,
        }
    )
    registry_file = tmp_path / "registry.json"
    registry = json.loads(registry_file.read_bytes())
    registry["extensions"].append(metadata.model_dump(mode="json"))
    registry_file.write_text(json.dumps(registry))
    policy_file = tmp_path / "policy.json"
    policy = json.loads(policy_file.read_bytes())
    policy["reviewed_dependency_manifests"].append(manifest_digest(metadata))
    policy_file.write_text(json.dumps(policy))
    for key, file in [("registry", registry_file), ("policy", policy_file)]:
        data[key]["sha256"] = sha(file)
    config = data["configurations"]["document-data"]
    config["components"].append("skill-scanner")
    config["scanner"] = {"path": binding_file.name, "sha256": sha(binding_file)}
    path.write_text(json.dumps(data))
    wrapper = WorkflowAccountingDefinition.model_validate(
        wrapper.model_dump(mode="json")
        | {
            "schema_version": "aeep.toolkit.workflow-accounting.v3",
            "workflow_sha256": sha(path),
            "operations": ["scan", "run", "report"],
        }
    )
    accounting_file.write_text(wrapper.model_dump_json())
    repo.review(repo.put("toolkit_workflow_accounting", content_digest(wrapper), wrapper))
    return path, router, repo, binding, accounting_file, wrapper


def install_fixture(monkeypatch, *, transform=None, failure=False, cleanup=True, after=None):
    calls = []

    class Fixture(BaseExecutor):
        cleanup_verified = cleanup

        async def execute(self, context):
            calls.append(context)
            payload = context.request.input
            assert context.spec.config["argv"][-2:] == ["--workspace", "/tmp"]
            assert inspect_payload(payload) == payload["candidate_sha256"]
            value = {
                "component": "skill-scanner",
                "source_revision": security.SOURCE_REVISION,
                "implementation_source": payload["implementation_source"],
                "mode": "upstream_functional",
                "check": "static_scan",
                "candidate_sha256": payload["candidate_sha256"],
                "candidate_bytes_bound": True,
                "findings": [],
                "findings_count": 0,
                "analyzer_failures": [],
                "failed_analyzers": 0,
                "analyzers_used": ["StaticAnalyzer"],
                "analyzers_executed": 1,
                "upstream_report_sha256": "b" * 64,
                "safety_verdict": "NOT_ESTABLISHED",
                "scanner_version": security.SCANNER_VERSION,
                "scanner_artifact_sha256": security.SCANNER_ARTIFACT,
                "scanner_source_files_verified": 1,
            }
            if transform:
                transform(value)
            if after:
                after()
            return RawExecution(
                status="failed" if failure else "success",
                output=value,
                error_type="FixtureFailure" if failure else None,
                metadata={
                    "evidence_kind": "first_party_fixture",
                    "runtime_ref": "untrusted-provider-claim",
                },
            )

    monkeypatch.setattr(security, "ScanContainerExecutor", Fixture)
    # Preserve actual inert command preview; no Docker/SDK runs in these tests.
    monkeypatch.setattr(Fixture, "command", ScanContainerExecutor.command, raising=False)
    original_command = ScanContainerExecutor.command
    monkeypatch.setattr(
        Fixture,
        "command",
        lambda self, context: original_command(
            ScanContainerExecutor(self.environment, runtime_digest=self.runtime_digest), context
        ),
        raising=False,
    )

    def initialize(self, environment, *, runtime_digest):
        self.environment = environment
        self.runtime_digest = runtime_digest

    monkeypatch.setattr(Fixture, "__init__", initialize)
    return calls


def inspect_payload(payload):
    import base64

    from aeep_toolkit.candidate import identity

    return identity({name: base64.b64decode(raw) for name, raw in payload["files"].items()})


def invoke(value, key="scan-one", review=None):
    path, _router, _repo, _binding, accounting_file, _scope = value
    facts, _, _ = scan_preview(path, "document-data")
    return scan(
        path,
        "document-data",
        accounting=accounting_file,
        operation_key=key,
        reviewed_digest=review or facts["review_sha256"],
    )


def test_inert_preview_lists_real_containment_without_starting_backend(
    tmp_path, monkeypatch, capsys
):
    value = configured(tmp_path)
    path, router, repo, binding, _, scope = value
    try:
        monkeypatch.setattr(security, "_docker", lambda *_: pytest.fail("preview queried Docker"))
        main(["workflow", "scan", "--workflow", str(path), "--configuration", "document-data"])
        result = json.loads(capsys.readouterr().out)
        argv = result["container_command_template"]
        assert "-i" in argv and "--pull=never" in argv and "--read-only" in argv
        assert argv[argv.index("--entrypoint") + 1] == "/opt/aeep-scanner/bin/python"
        mounts = [argv[i + 1] for i, item in enumerate(argv) if item == "--mount"]
        assert len(mounts) == 2 and all("readonly" in item for item in mounts)
        assert any("src/aeep," in item for item in mounts) and any(
            "src/aeep_toolkit," in item for item in mounts
        )
        assert (
            result["execution_authorized"] is False
            and result["safety_verdict"] == "NOT_ESTABLISHED"
        )
        assert not repo.operation_ledger(scope.request.plan_id).operations
        assert not repo.operation_ledger(binding.request.plan_id).operations
    finally:
        router.store.close()


def test_cli_scan_retains_canonical_minimized_observation_and_separate_costs(
    tmp_path, monkeypatch, capsys
):
    value = configured(tmp_path)
    path, router, repo, binding, accounting_file, scope = value
    calls = install_fixture(monkeypatch)
    try:
        facts, _, _ = scan_preview(path, "document-data")
        main(
            [
                "workflow",
                "scan",
                "--workflow",
                str(path),
                "--configuration",
                "document-data",
                "--accounting",
                str(accounting_file),
                "--operation-id",
                "one",
                "--reviewed-digest",
                facts["review_sha256"],
            ]
        )
        result = json.loads(capsys.readouterr().out)
        assert len(calls) == 1 and result["observations"]["findings_count"] == 0
        record = require_scan(repo, result["scan_ref"], path, "document-data")
        receipt = repo.get("toolkit_component_receipt", record.receipt_ref)
        assert receipt["metadata"]["runtime_ref"] == content_digest(binding)
        assert receipt["metadata"]["observed_resource_dimensions"] == ["latency_ms"]
        assert "files" not in receipt and "stdout" not in receipt and "input" not in receipt
        assert len(repo.operation_ledger(scope.request.plan_id).operations) == 1
        assert len(repo.operation_ledger(binding.request.plan_id).operations) == 1
        wrapped = repo.get("toolkit_workflow_receipt", record.wrapper_operation_id)
        assert len(wrapped["metadata"]["excluded_nested_intervals"]) == 1
        assert result["candidate_usefulness"] == "NOT_ASSESSED"
        with pytest.raises(ConfigurationError, match="already reserved"):
            invoke(value, key="one")
        assert len(calls) == 1
    finally:
        router.store.close()


@pytest.mark.parametrize("fault", ["review", "revoked", "candidate", "dependency", "no_accounting"])
def test_invalid_or_changed_bindings_start_no_component(tmp_path, monkeypatch, fault):
    value = configured(tmp_path)
    path, router, repo, binding, accounting_file, _ = value
    calls = install_fixture(monkeypatch)
    try:
        facts, _, _ = scan_preview(path, "document-data")
        if fault == "revoked":
            repo.review(content_digest(binding), revoke=True)
        if fault == "candidate":
            (tmp_path / "selected-skill/SKILL.md").write_text("changed candidate")
        if fault == "dependency":
            (tmp_path / "docker-fixture").write_text("changed runtime")
        with pytest.raises((ConfigurationError, ValueError)):
            scan(
                path,
                "document-data",
                accounting=None if fault == "no_accounting" else accounting_file,
                operation_key=None if fault == "no_accounting" else "denied",
                reviewed_digest="f" * 64 if fault == "review" else facts["review_sha256"],
            )
        assert not calls and not repo.operation_ledger(binding.request.plan_id).operations
    finally:
        router.store.close()


@pytest.mark.parametrize("fault", ["source", "counts", "missing", "private_text", "failure"])
def test_bad_child_observation_retains_failed_receipt_without_success_record(
    tmp_path, monkeypatch, fault
):
    value = configured(tmp_path)
    _path, router, repo, binding, _, _ = value

    def change(data):
        if fault == "source":
            data["implementation_source"] = "e" * 64
        elif fault == "counts":
            data["findings_count"] = 3
        elif fault == "missing":
            data.pop("analyzers_used")
        elif fault == "private_text":
            data["findings"] = [{"severity": "HIGH", "snippet": "do not retain"}]
            data["findings_count"] = 1

    calls = install_fixture(monkeypatch, transform=change, failure=fault == "failure")
    try:
        with pytest.raises(ConfigurationError):
            invoke(value)
        assert len(calls) == 1
        rows = repo.store._connection.execute(
            "SELECT payload_json FROM assessment_records WHERE kind='toolkit_component_receipt'"
        ).fetchall()
        assert len(rows) == 1 and json.loads(rows[0][0])["execution_success"] is False
        assert "do not retain" not in rows[0][0]
        assert (
            repo.store._connection.execute(
                "SELECT count(*) FROM assessment_records WHERE kind='toolkit_workflow_scan'"
            ).fetchone()[0]
            == 0
        )
        assert len(repo.operation_ledger(binding.request.plan_id).operations) == 1
    finally:
        router.store.close()


def test_uncertain_cleanup_blocks_fresh_ids_without_resetting_costs(tmp_path, monkeypatch):
    value = configured(tmp_path)
    _path, router, repo, binding, _, _ = value
    calls = install_fixture(monkeypatch, cleanup=False)
    try:
        with pytest.raises(ConfigurationError, match="cleanup is uncertain"):
            invoke(value)
        with pytest.raises(ConfigurationError, match="prior scanner cleanup"):
            invoke(value, key="new-id")
        assert (
            len(calls) == 1 and len(repo.operation_ledger(binding.request.plan_id).operations) == 1
        )
    finally:
        router.store.close()


def test_revocation_after_execution_prevents_observation_use(tmp_path, monkeypatch):
    value = configured(tmp_path)
    _path, router, repo, binding, _, _ = value
    calls = install_fixture(
        monkeypatch, after=lambda: repo.review(content_digest(binding), revoke=True)
    )
    try:
        with pytest.raises(ConfigurationError):
            invoke(value)
        assert len(calls) == 1
        assert (
            repo.store._connection.execute(
                "SELECT count(*) FROM assessment_records WHERE kind='toolkit_workflow_scan'"
            ).fetchone()[0]
            == 0
        )
    finally:
        router.store.close()


@pytest.mark.parametrize("fault", ["network", "host_roots", "image"])
def test_runtime_definition_cannot_weaken_existing_container_boundary(tmp_path, fault):
    value = configured(tmp_path)
    _, router, _, binding, _, _ = value
    try:
        raw = binding.model_dump(mode="json")
        if fault == "network":
            raw["environment"]["network"] = True
        elif fault == "host_roots":
            raw["environment"]["read_only_roots"] = [str(tmp_path)]
        else:
            raw["environment"]["container_image"] = "mutable:latest"
        with pytest.raises(ValueError):
            ScannerRuntimeDefinition.model_validate(raw)
    finally:
        router.store.close()


async def test_cleanup_preserves_an_unknown_container(tmp_path, monkeypatch):
    value = configured(tmp_path)
    _, router, _, binding, _, _ = value
    calls = []

    async def docker(environment, *argv):
        calls.append(argv)
        return 0, json.dumps(
            [
                {
                    "Image": binding.environment.container_image,
                    "Config": {"Labels": {"aeep.workflow-scan": "someone-else"}},
                    "Id": "unknown",
                    "State": {"Running": True},
                }
            ]
        ).encode()

    monkeypatch.setattr(security, "_docker", docker)
    try:
        executor = ScanContainerExecutor(
            binding.environment,
            runtime_digest=binding.executable_dependencies[
                str(binding.environment.container_runtime)
            ],
        )
        assert await executor.cleanup("owned-attempt") is False
        assert len(calls) == 1
    finally:
        router.store.close()


async def test_cleanup_stops_only_the_matching_container_id(tmp_path, monkeypatch):
    value = configured(tmp_path)
    _, router, _, binding, _, _ = value
    calls = []

    async def docker(environment, *argv):
        calls.append(argv)
        if len(calls) == 1:
            return 0, json.dumps(
                [
                    {
                        "Image": binding.environment.container_image,
                        "Config": {"Labels": {"aeep.workflow-scan": "owned-attempt"}},
                        "Id": "owned-id",
                        "State": {"Running": True},
                    }
                ]
            ).encode()
        if argv[0] == "stop":
            return 0, b"owned-id"
        return 1, b"No such container"

    monkeypatch.setattr(security, "_docker", docker)
    try:
        assert await ScanContainerExecutor(
            binding.environment,
            runtime_digest=binding.executable_dependencies[
                str(binding.environment.container_runtime)
            ],
        ).cleanup("owned-attempt")
        assert calls[1] == ("stop", "--time", "1", "owned-id")
        assert not any("--force" in call for call in calls)
    finally:
        router.store.close()


@pytest.mark.parametrize("version", ["v1", "v2"])
def test_old_accounting_versions_cannot_authorize_scan(tmp_path, version):
    value = configured(tmp_path)
    _, router, _, _, _, scope = value
    try:
        with pytest.raises(ValueError):
            WorkflowAccountingDefinition.model_validate(
                scope.model_dump(mode="json")
                | {"schema_version": "aeep.toolkit.workflow-accounting." + version}
            )
    finally:
        router.store.close()


def test_define_scanner_stores_inert_record_without_review_or_grant(tmp_path, capsys):
    value = configured(tmp_path)
    _, router, _, binding, _, _ = value
    try:
        from aeep.assessment.repository import AssessmentRepository
        from aeep.models import Manifest
        from aeep.store import ReceiptStore

        manifest = tmp_path / "inert-manifest.json"
        database = tmp_path / "inert.sqlite3"
        manifest.write_text(Manifest(database=str(database), executors=[]).model_dump_json())
        main(
            [
                "workflow",
                "define-scanner",
                "--file",
                str(tmp_path / "scanner.json"),
                "--manifest",
                str(manifest),
            ]
        )
        result = json.loads(capsys.readouterr().out)
        assert result == {
            "scanner_ref": content_digest(binding),
            "reviewed": False,
            "execution_authorized": False,
        }
        with ReceiptStore(database) as store:
            repo = AssessmentRepository(store)
            assert repo.get("toolkit_scanner_runtime", result["scanner_ref"])
            for table in ("assessment_reviews", "assessment_grants"):
                assert store._connection.execute("SELECT count(*) FROM " + table).fetchone()[0] == 0
    finally:
        router.store.close()


@pytest.mark.parametrize("fault", ["observation", "evidence", "receipt", "review"])
def test_changed_scan_proof_cannot_be_attached(tmp_path, monkeypatch, fault):
    value = configured(tmp_path)
    path, router, repo, binding, _, _ = value
    install_fixture(monkeypatch)
    try:
        result = invoke(value)
        original = repo.get

        def get(kind, ref):
            data = original(kind, ref)
            if fault == "observation" and kind == "toolkit_workflow_scan":
                data["observations"]["findings_count"] = 99
            elif fault == "evidence" and kind == "execution_evidence":
                data["attempt_id"] = "unrelated"
            elif fault == "receipt" and kind == "toolkit_component_receipt":
                data["execution_success"] = False
            return data

        monkeypatch.setattr(repo, "get", get)
        if fault == "review":
            repo.review(content_digest(binding), revoke=True)
        with pytest.raises((ConfigurationError, ValueError)):
            require_scan(repo, result["scan_ref"], path, "document-data")
    finally:
        router.store.close()


def test_cleanup_does_not_execute_a_changed_runtime(tmp_path, monkeypatch):
    import asyncio

    value = configured(tmp_path)
    _, router, _, binding, _, _ = value
    try:
        monkeypatch.setattr(security, "_docker", lambda *_: pytest.fail("changed runtime executed"))
        Path(str(binding.environment.container_runtime)).write_text("changed binary")
        assert not asyncio.run(
            ScanContainerExecutor(
                binding.environment,
                runtime_digest=binding.executable_dependencies[
                    str(binding.environment.container_runtime)
                ],
            ).cleanup("owned-attempt")
        )
    finally:
        router.store.close()
