"""Task-pack fixtures check separation and identity, not upstream reproduction."""

import hashlib
import json

import pytest

from aeep_toolkit.benchmarks import (
    SKILLSBENCH_REVISION,
    BenchmarkPack,
    asset_path,
    inspect_pack,
    stage_agent_assets,
)
from aeep_toolkit.cli import main


def pack(tmp_path):
    root = tmp_path.resolve() / "task-pack"
    root.mkdir()
    assets = []
    for name, role in (
        ("task.md", "instruction"),
        ("data.csv", "input"),
        ("skill/SKILL.md", "candidate_skill"),
        ("oracle/answer.txt", "oracle"),
        ("verifier/check.py", "verifier"),
        ("environment/Dockerfile", "environment"),
    ):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = ("synthetic " + role).encode()
        path.write_bytes(raw)
        assets.append(
            dict(path=name, sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw), role=role)
        )
    value = BenchmarkPack.model_validate(
        dict(
            pack_id="skillsbench",
            source=dict(
                repository="https://github.com/benchflow-ai/skillsbench",
                revision=SKILLSBENCH_REVISION,
                artifact_sha256="a" * 64,
                license_expression="Apache-2.0",
                data_rights="synthetic fixture only",
            ),
            tasks=[
                dict(
                    task_id="fixture",
                    domain="document-data",
                    difficulty="hard",
                    assets=assets,
                    output_paths=["report.json"],
                    upstream_score="binary",
                )
            ],
        )
    )
    return root, value


def test_staging_protects_oracles_verifiers_and_baseline_candidate_absence(tmp_path):
    root, value = pack(tmp_path)
    summary = inspect_pack(value, root, ("fixture",))
    assert summary["executed"] is summary["official_benchmark_reproduction"] is False
    assert len(summary["tasks"][0]["protected_assets"]) == 2
    for available in (False, True):
        destination = tmp_path.resolve() / str(available)
        stage_agent_assets(value, root, "fixture", destination, candidate_available=available)
        names = {str(p.relative_to(destination)) for p in destination.rglob("*") if p.is_file()}
        assert names == {"task.md", "data.csv"} | ({"skill/SKILL.md"} if available else set())
        assert (destination / "data.csv").read_bytes() == (root / "data.csv").read_bytes()
        with pytest.raises(ValueError, match="new directory"):
            stage_agent_assets(value, root, "fixture", destination)


@pytest.mark.parametrize(
    "change", ["content", "size", "link", "parent-link", "hard-link", "directory"]
)
def test_asset_substitution_is_rejected_before_staging(tmp_path, change):
    root, value = pack(tmp_path)
    path = root / "data.csv"
    if change == "content":
        path.write_bytes(b"X" * path.stat().st_size)
    elif change == "size":
        path.write_bytes(b"changed length")
    elif change == "directory":
        path.unlink()
        path.mkdir()
    elif change == "parent-link":
        linked = tmp_path / "linked"
        linked.symlink_to(root, target_is_directory=True)
        root = linked
    elif change == "hard-link":
        (root / "alias.csv").hardlink_to(path)
    else:
        original = root / "original.csv"
        path.rename(original)
        path.symlink_to(original)
    with pytest.raises((ValueError, OSError)):
        stage_agent_assets(value, root, "fixture", tmp_path.resolve() / "staged")
    assert not (tmp_path / "staged").exists()


@pytest.mark.parametrize(
    "path", ["../answer", "/root/data", ".codex/auth.json", "auth.json", ".env", "a\\b", "./data"]
)
def test_pack_rejects_unsafe_asset_paths(tmp_path, path):
    _, value = pack(tmp_path)
    data = value.model_dump(mode="json")
    data["tasks"][0]["assets"][1]["path"] = path
    with pytest.raises(ValueError):
        BenchmarkPack.model_validate(data)


def test_pins_roles_and_explicit_task_selection_are_required(tmp_path):
    root, value = pack(tmp_path)
    for field, replacement in [("revision", "0" * 40)]:
        data = value.model_dump(mode="json")
        data["source"][field] = replacement
        with pytest.raises(ValueError, match="reviewed pin"):
            BenchmarkPack.model_validate(data)
    data = value.model_dump(mode="json")
    data["tasks"][0]["assets"] = [a for a in data["tasks"][0]["assets"] if a["role"] != "verifier"]
    with pytest.raises(ValueError, match="protected oracle"):
        BenchmarkPack.model_validate(data)
    for ids in ((), ("fixture", "fixture"), ("absent",)):
        with pytest.raises(ValueError):
            inspect_pack(value, root, ids)
    assert asset_path(root, value.tasks[0].assets[1]) == root / "data.csv"


def test_cli_lists_equal_domains_without_claiming_task_execution(capsys):
    assert main(["benchmark", "list"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["revision"] == SKILLSBENCH_REVISION
    assert sum(t["domain"] == "document-data" for t in result["tasks"]) == 3
    assert sum(t["domain"] == "software-engineering" for t in result["tasks"]) == 3
    assert all(t["functional_status"] == "NOT_VERIFIED" for t in result["tasks"])


def test_six_task_original_import_retains_blob_identity_and_never_clears_rights(tmp_path):
    from aeep_toolkit.benchmarks import INITIAL_TASKS, skillsbench_manifest

    root = tmp_path.resolve()
    entries = []
    for name, _domain, _difficulty in INITIAL_TASKS:
        for relative in (
            "task.md",
            "environment/workspace/input.txt",
            "oracle/solve.sh",
            "verifier/test.py",
            "environment/Dockerfile",
            "environment/api-simulator/server.ts",
            "environment/skills/test/SKILL.md",
            "environment/skills/test/LICENSE.txt",
        ):
            path = "tasks/" + name + "/" + relative
            raw = ("synthetic importer fixture " + relative).encode()
            dest = root / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(raw)
            blob = b"blob " + str(len(raw)).encode() + bytes([0]) + raw
            entries.append(
                dict(
                    path=path,
                    sha256=hashlib.sha256(raw).hexdigest(),
                    sha=hashlib.sha1(blob).hexdigest(),
                    size=len(raw),
                )
            )
    inventory = root / "source-inventory.json"

    def freeze():
        inventory.write_text(json.dumps(dict(revision=SKILLSBENCH_REVISION, assets=entries)))
        return hashlib.sha256(inventory.read_bytes()).hexdigest()

    pin = freeze()
    value = skillsbench_manifest(root, pin)
    assert len(value.tasks) == 6 and all(t.rights_review_ref is None for t in value.tasks)
    assert {t.domain for t in value.tasks} == {"document-data", "software-engineering"}
    task = value.tasks[0]
    assert next(a for a in task.assets if a.path.endswith("server.ts")).role == "environment"
    assert next(a for a in task.assets if a.path.endswith("LICENSE.txt")).role == "license"
    with pytest.raises(ValueError, match="inventory changed"):
        skillsbench_manifest(root, "a" * 64)
    entries[0]["sha"] = "a" * 40
    with pytest.raises(ValueError, match="Git blob differs"):
        skillsbench_manifest(root, freeze())
    entries[0]["sha"] = hashlib.sha1(
        b"blob "
        + str(entries[0]["size"]).encode()
        + bytes([0])
        + (root / entries[0]["path"]).read_bytes()
    ).hexdigest()
    entries.append(entries[0])
    with pytest.raises(ValueError, match="duplicate"):
        skillsbench_manifest(root, freeze())
    entries.pop()
    entries[:] = [
        e
        for e in entries
        if not e["path"].startswith("tasks/financial-modeling-qa/environment/workspace/")
    ]
    with pytest.raises(ValueError, match="inputs are external"):
        skillsbench_manifest(root, freeze())


def extractbench_fixture(tmp_path, instruction=None):
    from aeep_toolkit.benchmarks import (
        EXTRACTBENCH_ASSET_ROLES,
        EXTRACTBENCH_REPOSITORY,
        EXTRACTBENCH_REVISION,
    )

    root, original = pack(tmp_path)
    value = original.model_dump(mode="json")
    value["pack_id"] = "extractbench"
    value["source"].update(repository=EXTRACTBENCH_REPOSITORY, revision=EXTRACTBENCH_REVISION)
    task = value["tasks"][0]
    task.update(output_paths=["output.json"], upstream_score="native_reward", assets=[])
    public = {}
    for relative, role in EXTRACTBENCH_ASSET_ROLES.items():
        name = "tasks/fixture/" + relative
        payload = ("synthetic " + relative).encode()
        if relative == "instruction.md" and instruction is not None:
            payload = instruction
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        task["assets"].append(dict(path=name, sha256=hashlib.sha256(payload).hexdigest(),
                                   bytes=len(payload), role=role))
        if role in {"instruction", "input"}:
            public[relative] = payload
    return root, BenchmarkPack.model_validate(value), public


def test_extractbench_pack_archive_preserves_original_paths_and_rejects_role_drift(tmp_path):
    import base64
    import io
    from zipfile import ZipFile

    from aeep_toolkit.benchmarks import task_input

    root, selected, public = extractbench_fixture(tmp_path)
    value = selected.model_dump(mode="json")
    task = value["tasks"][0]
    archived = task_input(selected, root, "fixture")
    with ZipFile(io.BytesIO(base64.b64decode(archived["task_archive_b64"]))) as files:
        assert {name: files.read(name) for name in files.namelist()} == public
    stage_agent_assets(selected, root, "fixture", tmp_path.resolve() / "extractbench-worker")
    assert (tmp_path / "extractbench-worker/environment/document.pdf").read_bytes() == public["environment/document.pdf"]

    from aeep.assessment.adapters import project_document_archive
    from aeep.errors import ConfigurationError
    from aeep_toolkit.benchmarks import stage_document_archive

    transport = tmp_path.resolve() / "public-zips"
    transport.mkdir()
    descriptor = stage_document_archive(selected, root, "fixture", "small", transport)
    assert "task_archive_b64" not in descriptor
    assert "instruction_delivery" not in descriptor
    assert project_document_archive(descriptor, [str(transport)])["task"] == public["instruction.md"].decode()
    assert project_document_archive(descriptor, [str(transport)])["task_archive_b64"] == archived["task_archive_b64"]
    with pytest.raises(ConfigurationError, match="reviewed public document assets"):
        project_document_archive({**descriptor, "document_sha256": "0" * 64}, [str(transport)])
    poison = io.BytesIO()
    with ZipFile(poison, "w") as files:
        for name, body in {**public, "solution/expected.json": b"protected"}.items():
            files.writestr(name, body)
    raw = poison.getvalue()
    poisoned_digest = hashlib.sha256(raw).hexdigest()
    (transport / f"{poisoned_digest}.zip").write_bytes(raw)
    with pytest.raises(ConfigurationError, match="reviewed public document assets"):
        project_document_archive({**descriptor, "task_archive_sha256": poisoned_digest}, [str(transport)])

    for field, replacement in [
        ("repository", "https://example.test/unrelated"),
        ("revision", "0" * 40),
    ]:
        with pytest.raises(ValueError, match=r"pinned dataset|reviewed pin"):
            BenchmarkPack.model_validate({**value, "source": {**value["source"], field: replacement}})
    for field, replacement in [
        ("upstream_score", "binary"),
        ("output_paths", ["other.json"]),
        ("assets", [{**a, "role": "input"} if a["path"].endswith("/tests/verifier.py") else a
                    for a in task["assets"]]),
    ]:
        with pytest.raises(ValueError, match="protected task layout"):
            BenchmarkPack.model_validate({**value, "tasks": [{**task, field: replacement}]})


async def test_file_backed_document_instructions_reach_worker_without_inline_copy(tmp_path, capsys):
    import base64
    import io
    from zipfile import ZipFile

    from aeep.assessment.adapters import prepare_context, require_document_worker_archives
    from aeep.errors import ConfigurationError
    from aeep.executors.base import ExecutionContext
    from aeep.executors.managed_host import ManagedHostExecutor
    from aeep.hosts import HostProbe, ManagedHostRegistry
    from aeep.models import ActionRequest, ExecutorSpec, RawExecution
    from aeep_toolkit.benchmarks import stage_document_archive

    instruction = (b"distinct synthetic archive instruction\n" * 15_000)[:567_600]
    root, selected, public = extractbench_fixture(tmp_path, instruction)
    transport = tmp_path / "public-zips"
    transport.mkdir()
    with pytest.raises(ValueError, match="instruction exceeds"):
        stage_document_archive(selected, root, "fixture", "large", transport)
    assert not list(transport.iterdir())

    pack_path = tmp_path / "pack.json"
    pack_path.write_text(selected.model_dump_json())
    main(["benchmark", "stage-document", "--pack", str(pack_path), "--root", str(root),
          "--task", "fixture", "--family", "large", "--destination", str(transport),
          "--archive-instructions"])
    descriptor = json.loads(capsys.readouterr().out)
    assert descriptor["instruction_delivery"] == "archive"
    assert descriptor["instruction_sha256"] == hashlib.sha256(instruction).hexdigest()
    archive, = transport.iterdir()
    raw = archive.read_bytes()
    assert archive.name == hashlib.sha256(raw).hexdigest() + ".zip"

    spec = ExecutorSpec(
        id="document-worker", capability="document.fixture", kind="host_managed",
        description="Synthetic file-backed instruction transport",
        resource_pool="fixture-subscription",
        config={
            "adapter_id": "fixture", "argv": ["/fixture/worker"], "managed_worker": {},
            "instructions": "{input.task}",
            "artifact": {"input_field": "task_archive_b64", "output_field": "artifact",
                         "input_name": "current-task.zip", "output_name": "output.json"},
            "assessment_adapter": {"input_transform": "document_archive:2", "read_only_roots": [str(transport)]},
        },
    )
    ctx = ExecutionContext(request=ActionRequest(capability=spec.capability, input=descriptor),
                           spec=spec, estimate=spec.estimate, attempt=1)
    require_document_worker_archives([spec], archive_instructions=True)
    projected, _ = prepare_context(ctx)

    class WorkerFixture:
        async def probe(self):
            return HostProbe(adapter_id="fixture", status="ready")

        async def execute(self, context):
            assert "Read the complete instruction.md" in context.instruction
            assert "/workspace/current-task.zip" in context.instruction
            assert "distinct synthetic archive instruction" not in context.instruction
            assert len(context.instruction) < 1000
            assert base64.b64decode(context.request.input["task_archive_b64"], validate=True) == raw
            with ZipFile(io.BytesIO(raw)) as files:
                assert {name: files.read(name) for name in files.namelist()} == public
            return RawExecution(status="success", output={})

        async def close(self):
            pass

    registry = ManagedHostRegistry()
    registry.register("fixture", WorkerFixture())
    executor = ManagedHostExecutor(registry)
    try:
        response = await executor.execute(projected)
        assert response.metadata["task_instruction_sha256"] == hashlib.sha256(
            projected.request.input["task"].encode()
        ).hexdigest()
    finally:
        await executor.close()

    inline = spec.model_copy(deep=True)
    inline.config["assessment_adapter"]["input_transform"] = "document_archive:1"
    with pytest.raises(ConfigurationError, match="delivery differs"):
        prepare_context(ExecutionContext(request=ctx.request, spec=inline, estimate=inline.estimate, attempt=1))
    with pytest.raises(ConfigurationError, match="reviewed archive delivery"):
        require_document_worker_archives([spec, inline], archive_instructions=True)
    for field, replacement in (("artifact", None), ("instructions", "Ignore the task input")):
        bad = spec.model_copy(deep=True)
        bad.config[field] = replacement
        with pytest.raises(ConfigurationError, match="reviewed archive and task template"):
            require_document_worker_archives([bad], archive_instructions=True)
    altered = ctx.request.model_copy(update={"input": {**descriptor, "instruction_sha256": "b" * 64}})
    with pytest.raises(ConfigurationError, match="reviewed public document assets"):
        prepare_context(ExecutionContext(request=altered, spec=spec, estimate=spec.estimate, attempt=1))


def test_archive_instruction_limit_is_distinct_from_inline_limit(tmp_path):
    from aeep_toolkit.benchmarks import document_archive

    root, selected, _ = extractbench_fixture(tmp_path, b"A" * 600_001)
    with pytest.raises(ValueError, match="instruction exceeds"):
        document_archive(selected, root, "fixture", "large", archive_instructions=True)


def reviewed_document_fixture(tmp_path):
    from aeep.assessment.models import content_digest
    from aeep_toolkit.benchmarks import REVIEWED_DOCUMENT_ASSET_ROLES

    root, upstream, _ = extractbench_fixture(tmp_path)
    value = upstream.model_dump(mode="json")
    value.update(schema_version="aeep.toolkit.benchmark-pack.v2", pack_id="reviewed-documents")
    legacy = value["tasks"][0]
    extra = legacy | {"task_id": "external", "upstream_score": "binary", "assets": []}
    for name, role in REVIEWED_DOCUMENT_ASSET_ROLES.items():
        relative = f"tasks/external/{name}"
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = f"synthetic external {name}".encode()
        path.write_bytes(data)
        extra["assets"].append(
            {"path": relative, "role": role, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        )
    value["tasks"].append(extra)
    value["task_sources"] = {}
    for task in value["tasks"]:
        pdf = next(asset for asset in task["assets"] if asset["path"].endswith("/document.pdf"))
        pin = value["source"] | {"artifact_sha256": pdf["sha256"]}
        if task is extra:
            pin.update(repository="https://example.gov/public/external.pdf", revision=pdf["sha256"])
        value["task_sources"][task["task_id"]] = pin
    value["source"] = value["source"] | {"repository": "https://example.org/reviewed-inventory"}
    value["source"]["artifact_sha256"] = content_digest(
        {key: value[key] for key in ("tasks", "task_sources")}
    )
    return root, upstream, value


def test_reviewed_document_cli_stages_both_sources_without_verifiers(tmp_path, capsys):
    from zipfile import ZipFile

    root, upstream, value = reviewed_document_fixture(tmp_path)
    selected = BenchmarkPack.model_validate(value)
    assert "task_sources" not in upstream.model_dump(mode="json")
    assert inspect_pack(selected, root, ("fixture", "external"))["tasks"][1]["source"] == value["task_sources"]["external"]
    path = tmp_path / "reviewed.json"
    path.write_text(selected.model_dump_json())
    output = tmp_path.resolve() / "public-zips"
    output.mkdir()
    for identity in ("fixture", "external"):
        assert main([
            "benchmark", "stage-document", "--pack", str(path), "--root", str(root),
            "--task", identity, "--family", "multiple-collections", "--destination", str(output),
            "--archive-instructions",
        ]) == 0
        descriptor = json.loads(capsys.readouterr().out)
        assert descriptor["task_id"] == identity and descriptor["instruction_delivery"] == "archive"
        with ZipFile(output / (descriptor["task_archive_sha256"] + ".zip")) as archive:
            assert set(archive.namelist()) == {"instruction.md", "environment/document.pdf", "environment/schema.json"}


@pytest.mark.parametrize("change", ["role", "missing-pin", "pdf-drift", "upstream-revision", "v1"])
def test_reviewed_document_pack_rejects_changed_scope(tmp_path, change):
    from aeep.assessment.models import content_digest

    _, _, value = reviewed_document_fixture(tmp_path)
    if change == "role":
        next(asset for asset in value["tasks"][1]["assets"] if asset["role"] == "oracle")["role"] = "input"
    elif change == "missing-pin":
        value["task_sources"].pop("external")
    elif change == "pdf-drift":
        value["task_sources"]["external"]["artifact_sha256"] = "0" * 64
    elif change == "upstream-revision":
        value["task_sources"]["fixture"]["revision"] = "0" * 40
    else:
        value["schema_version"] = "aeep.toolkit.benchmark-pack.v1"
    value["source"]["artifact_sha256"] = content_digest(
        {key: value[key] for key in ("tasks", "task_sources")}
    )
    with pytest.raises(ValueError):
        BenchmarkPack.model_validate(value)


def test_reviewed_document_rights_bind_the_exact_task_source(tmp_path):
    from aeep.assessment.models import content_digest
    from aeep.assessment.repository import AssessmentRepository
    from aeep.errors import ConfigurationError
    from aeep.store import ReceiptStore
    from aeep_toolkit.models import SourcePin
    from aeep_toolkit.workflow_preparation import TaskRightsReview, require_rights

    _, _, value = reviewed_document_fixture(tmp_path)
    external = value["tasks"][1]
    pin = SourcePin.model_validate(value["task_sources"]["external"])
    rights = TaskRightsReview(
        source_revision=pin.revision,
        source_pin_sha256=content_digest(pin.model_dump(mode="json")),
        task_id="external",
        assets={asset["path"]: asset["sha256"] for asset in external["assets"]},
        basis=["Synthetic reviewed individual source"],
        local_execution_allowed=True,
        provider_disclosure_allowed=True,
    )
    external["rights_review_ref"] = content_digest(rights)
    value["source"]["artifact_sha256"] = content_digest(
        {key: value[key] for key in ("tasks", "task_sources")}
    )
    selected = BenchmarkPack.model_validate(value)
    with ReceiptStore(tmp_path / "rights.sqlite3") as store:
        repository = AssessmentRepository(store)
        repository.put("toolkit_task_rights", content_digest(rights), rights)
        repository.review(content_digest(rights))
        require_rights(repository, selected, ("external",))
        value["task_sources"]["external"]["repository"] = "https://different.example.gov/public/external.pdf"
        value["source"]["artifact_sha256"] = content_digest(
            {key: value[key] for key in ("tasks", "task_sources")}
        )
        with pytest.raises(ConfigurationError, match="mismatched"):
            require_rights(repository, BenchmarkPack.model_validate(value), ("external",))
