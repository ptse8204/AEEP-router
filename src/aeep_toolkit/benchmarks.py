"""Pinned task-pack inspection and agent/verifier separation, without execution."""

from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Literal

from pydantic import Field, model_validator

from .models import ContractModel, Count, Digest, Identifier, SourcePin

SKILLSBENCH_REVISION = "9a1f4dd5f7659f75707435da3ce854b6e48321d1"
INITIAL_TASKS: tuple[
    tuple[str, Literal["document-data", "software-engineering"], Literal["medium", "hard"]], ...
] = (
    ("financial-modeling-qa", "document-data", "hard"),
    ("pdf-excel-diff", "document-data", "medium"),
    ("sales-pivot-analysis", "document-data", "medium"),
    ("spring-boot-jakarta-migration", "software-engineering", "hard"),
    ("react-performance-debugging", "software-engineering", "hard"),
    ("software-dependency-audit", "software-engineering", "medium"),
)
AssetRole = Literal[
    "instruction", "input", "candidate_skill", "oracle", "verifier", "environment", "license"
]


def relative_path(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value) > 1024
        or "\\" in value
        or "\x00" in value
        or path.is_absolute()
        or ".." in path.parts
        or str(path) != value
        or value == "."
        or any(part.casefold() in {".git", ".codex", ".ssh", ".aws"} for part in path.parts)
        or path.name.casefold() in {"auth.json", "credentials.json"}
        or path.name.casefold().startswith(".env")
    ):
        raise ValueError("task assets require canonical relative non-secret paths")
    return value


class TaskAsset(ContractModel):
    path: str
    sha256: Digest
    bytes: Count = Field(le=1024**3)
    role: AssetRole

    @model_validator(mode="after")
    def bounded_path(self) -> TaskAsset:
        relative_path(self.path)
        return self


class BenchmarkTask(ContractModel):
    task_id: Identifier
    domain: Literal["document-data", "software-engineering", "mcp"]
    difficulty: Literal["easy", "medium", "hard", "unknown"]
    assets: tuple[TaskAsset, ...] = Field(min_length=4, max_length=4096)
    output_paths: tuple[str, ...] = Field(min_length=1, max_length=128)
    upstream_score: Literal["binary", "native_reward"]
    rights_review_ref: Digest | None = None
    adaptations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def separated_assets(self) -> BenchmarkTask:
        paths = [asset.path.casefold() for asset in self.assets]
        roles = {asset.role for asset in self.assets}
        if (
            len(paths) != len(set(paths))
            or not {"instruction", "input", "oracle", "verifier"} <= roles
        ):
            raise ValueError(
                "task assets must be unique and include protected oracle/verifier and public inputs"
            )
        if sum(asset.role == "instruction" for asset in self.assets) != 1:
            raise ValueError("task requires exactly one reviewed instruction")
        if sum(asset.bytes for asset in self.assets) > 2 * 1024**3:
            raise ValueError("task exceeds the bounded inspection envelope; review a separate pack")
        for path in self.output_paths:
            relative_path(path)
        if len(self.output_paths) != len(set(self.output_paths)):
            raise ValueError("task output paths must be unique")
        return self


class BenchmarkPack(ContractModel):
    schema_version: Literal["aeep.toolkit.benchmark-pack.v1"] = "aeep.toolkit.benchmark-pack.v1"
    pack_id: Literal["skillsbench", "mcpmark", "mcp-universe"]
    source: SourcePin
    tasks: tuple[BenchmarkTask, ...] = Field(min_length=1, max_length=256)

    @model_validator(mode="after")
    def pinned_pack(self) -> BenchmarkPack:
        from .stack_readiness import source_revisions

        if self.source.revision != source_revisions("0" * 64)[self.pack_id]:
            raise ValueError("benchmark source differs from the selected reviewed pin")
        if len({task.task_id for task in self.tasks}) != len(self.tasks):
            raise ValueError("duplicate task identities")
        return self

    def task(self, task_id: str) -> BenchmarkTask:
        for task in self.tasks:
            if task.task_id == task_id:
                return task
        raise ValueError("unknown benchmark task")


def asset_path(root: Path, asset: TaskAsset) -> Path:
    from .install_runtime import canonical

    canonical(str(root))
    if root.absolute() != root.resolve(strict=True) or not root.is_dir():
        raise ValueError("pack root must be an existing canonical directory")
    path = root / asset.path
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError("task assets and parent directories cannot be links")
    fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or info.st_size != asset.bytes
            or hashlib.file_digest(stream, "sha256").hexdigest() != asset.sha256
        ):
            raise ValueError("task asset type, size or hash differs from its manifest")
    return path


def inspect_pack(pack: BenchmarkPack, root: Path, task_ids: tuple[str, ...]) -> dict[str, Any]:
    """Hash reviewed files only; neither Dockerfiles nor task programs execute."""
    if not task_ids or len(task_ids) != len(set(task_ids)):
        raise ValueError("select distinct benchmark tasks explicitly")
    selected = [pack.task(identity) for identity in task_ids]
    for task in selected:
        for asset in task.assets:
            asset_path(root, asset)
    from .install_runtime import digest

    return {
        "pack": pack.pack_id,
        "source_revision": pack.source.revision,
        "pack_sha256": digest(pack),
        "tasks": [
            {
                "task_id": task.task_id,
                "domain": task.domain,
                "difficulty": task.difficulty,
                "agent_assets": [
                    a.model_dump(mode="json")
                    for a in task.assets
                    if a.role in {"instruction", "input"}
                ],
                "candidate_assets": [
                    a.model_dump(mode="json") for a in task.assets if a.role == "candidate_skill"
                ],
                "protected_assets": [
                    a.model_dump(mode="json")
                    for a in task.assets
                    if a.role in {"oracle", "verifier"}
                ],
                "rights_review_ref": task.rights_review_ref,
                "adaptations": list(task.adaptations),
                "upstream_score": task.upstream_score,
                "output_paths": list(task.output_paths),
            }
            for task in selected
        ],
        "executed": False,
        "official_benchmark_reproduction": False,
        "notice": "File identity and separation only. Runtime, rights reviews, independent grader calibration and authority must be resolved before execution.",
    }


def stage_agent_assets(
    pack: BenchmarkPack,
    root: Path,
    task_id: str,
    destination: Path,
    *,
    candidate_available: bool = False,
) -> None:
    """Copy only public task bytes to a new private input tree, never a worker host."""
    from .install_runtime import canonical

    task = pack.task(task_id)
    inspect_pack(pack, root, (task_id,))
    canonical(str(destination))
    if destination.exists() or destination.is_symlink():
        raise ValueError("task staging requires a new directory")
    selected = [
        a
        for a in task.assets
        if a.role in {"instruction", "input"}
        or (candidate_available and a.role == "candidate_skill")
    ]
    destination.mkdir(mode=0o700)
    # Recheck each captured byte stream before writing; no oracle or verifier is selected.
    for asset in selected:
        raw = asset_path(root, asset).read_bytes()
        if len(raw) != asset.bytes or hashlib.sha256(raw).hexdigest() != asset.sha256:
            raise ValueError("task input changed during staging; retain the incomplete tree")
        target = destination / asset.path
        target.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with target.open("xb") as stream:
            stream.write(raw)


def task_input(pack: BenchmarkPack, root: Path, task_id: str) -> dict[str, Any]:
    """Preserve original public bytes in the existing single-file worker transport.

    This is packaging only. The operator still resolves rights, runtime/path
    adaptations and protected verifier execution before any worker receives it.
    Candidate skills, environment installers, oracles and verifiers are excluded.
    """
    from aeep.assessment.models import content_digest

    task = pack.task(task_id)
    inspect_pack(pack, root, (task_id,))
    public = [asset for asset in task.assets if asset.role in {'instruction', 'input'}]
    if sum(asset.bytes for asset in public) > 16_000_000:
        raise ValueError('task exceeds this adapter expanded-input limit; review a larger transport')
    stream = io.BytesIO()
    instruction = None
    with zipfile.ZipFile(stream, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for asset in sorted(public, key=lambda item:item.path):
            raw = asset_path(root, asset).read_bytes()
            if len(raw) != asset.bytes or hashlib.sha256(raw).hexdigest() != asset.sha256:
                raise ValueError('task input changed while packaging')
            if asset.role == 'instruction':
                instruction = raw.decode('utf-8')
            entry = zipfile.ZipInfo(asset.path, date_time=(1980, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = (stat.S_IFREG | 0o444) << 16
            archive.writestr(entry, raw)
    raw = stream.getvalue()
    if len(raw) > 4_000_000:
        raise ValueError('task exceeds the existing managed artifact transport limit')
    return {'task_id':task_id, 'task':instruction, 'benchmark_pack_sha256':content_digest(pack.model_dump(mode='json')),
            'task_archive_b64':base64.b64encode(raw).decode('ascii'),
            'task_archive_sha256':hashlib.sha256(raw).hexdigest(),
            'output_paths':list(task.output_paths)}


def initial_catalog() -> dict[str, Any]:
    return {
        "pack": "skillsbench",
        "revision": SKILLSBENCH_REVISION,
        "tasks": [
            {
                "task_id": name,
                "domain": domain,
                "difficulty": difficulty,
                "source_url": f"https://github.com/benchflow-ai/skillsbench/blob/{SKILLSBENCH_REVISION}/tasks/{name}/task.md",
                "functional_status": "NOT_VERIFIED",
            }
            for name, domain, difficulty in INITIAL_TASKS
        ],
        "notice": "Initial equal-domain integration workload; not an installed pack, completed study or formal qualification.",
    }


def skillsbench_manifest(root: Path, inventory_sha256: str) -> BenchmarkPack:
    """Import exact original local files. This grants no asset rights or execution."""
    from .cli import read_bytes

    raw = read_bytes(root / "source-inventory.json")
    if hashlib.sha256(raw).hexdigest() != inventory_sha256:
        raise ValueError("original SkillsBench inventory changed")
    inventory = json.loads(raw)
    if inventory.get("revision") != SKILLSBENCH_REVISION:
        raise ValueError("SkillsBench inventory has a different source pin")
    outputs = {
        "financial-modeling-qa": "answer.txt",
        "pdf-excel-diff": "diff_report.json",
        "sales-pivot-analysis": "demographic_analysis.xlsx",
        "spring-boot-jakarta-migration": "workspace",
        "react-performance-debugging": "app",
        "software-dependency-audit": "security_audit.csv",
    }
    tasks = []
    entries = inventory["assets"]
    if len({entry["path"] for entry in entries}) != len(entries):
        raise ValueError("duplicate SkillsBench source path")
    for name, domain, difficulty in INITIAL_TASKS:
        prefix = "tasks/" + name + "/"
        assets = []
        for entry in entries:
            path = entry["path"]
            if not path.startswith(prefix) and path != "LICENSE":
                continue
            local = path.removeprefix(prefix)
            role: AssetRole
            if "LICENSE" in PurePosixPath(path).name.upper():
                role = "license"
            elif local == "task.md":
                role = "instruction"
            elif local.startswith("oracle/"):
                role = "oracle"
            elif local.startswith("verifier/"):
                role = "verifier"
            elif local.startswith("environment/skills/"):
                role = "candidate_skill"
            elif local.startswith(("environment/workspace/", "environment/website/")) or local in {
                "environment/data.xlsx",
                "environment/background.pdf",
                "environment/income.xlsx",
                "environment/population.pdf",
                "environment/employees_backup.pdf",
                "environment/employees_current.xlsx",
                "environment/package-lock.json",
            }:
                role = "input"
            else:
                role = "environment"
            asset = TaskAsset(path=path, sha256=entry["sha256"], bytes=entry["size"], role=role)
            original = asset_path(root, asset).read_bytes()
            git_blob = b"blob " + str(len(original)).encode() + bytes([0]) + original
            if hashlib.sha1(git_blob).hexdigest() != entry["sha"]:
                raise ValueError("SkillsBench original Git blob differs")
            assets.append(asset)
        # PDF/Excel diff downloads its inputs outside the upstream repository.
        # Missing original input artifacts prevent creating an executable task.
        if not any(asset.role == "input" for asset in assets):
            raise ValueError(
                "task inputs are external and still require exact reviewed artifacts: " + name
            )
        tasks.append(
            BenchmarkTask(
                task_id=name,
                domain=domain,
                difficulty=difficulty,
                assets=tuple(assets),
                output_paths=(outputs[name],),
                upstream_score="binary",
                adaptations=(
                    "Original files only; worker path mapping and offline runtime are unreviewed.",
                ),
            )
        )
    return BenchmarkPack(
        pack_id="skillsbench",
        source=SourcePin(
            repository="https://github.com/benchflow-ai/skillsbench",
            revision=SKILLSBENCH_REVISION,
            artifact_sha256=inventory_sha256,
            license_expression="Apache-2.0",
            data_rights="Repository notice only. Task-specific assets and bundled skills remain unreviewed; no rights grant inferred.",
        ),
        tasks=tuple(tasks),
    )


def main(argv: list[str] | None = None) -> None:
    import argparse

    from .cli import read_json

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="operation", required=True)
    sub.add_parser("list")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("--pack", type=Path, required=True)
    inspect.add_argument("--root", type=Path, required=True)
    inspect.add_argument("--task", action="append", required=True)
    imported = sub.add_parser("skillsbench-import")
    imported.add_argument("--root", type=Path, required=True)
    imported.add_argument("--inventory-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        if args.operation == "list":
            value = initial_catalog()
        elif args.operation == "skillsbench-import":
            value = skillsbench_manifest(args.root, args.inventory_sha256).model_dump(mode="json")
        else:
            value = inspect_pack(
                BenchmarkPack.model_validate(read_json(args.pack)), args.root, tuple(args.task)
            )
        print(json.dumps(value, indent=2))
    except (ValueError, OSError):
        parser.exit(2, "Pinned task-pack inspection failed; no execution or automatic retry.\n")
