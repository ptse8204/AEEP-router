"""Verify the repaired Sales Pivot handoff in the two isolated worker images."""

import argparse
import asyncio
import base64
import hashlib
import io
import json
import secrets
import time
from pathlib import Path
from zipfile import ZipFile

from prepare_runtime import WORK, docker, read, require_reserve, sha, write
from sales_handoff import corrected_sales_instructions
from verify_graders import SALES as SALES_PLAN
from verify_workers import SALES as SALES_PAIR
from verify_workers import command, make_spec

from aeep.errors import ConfigurationError
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.workers import ARTIFACT_PROGRAM

HERE = Path(__file__).resolve().parent
REVIEW = WORK / "sales-handoff-offline-review.json"
RESULT = WORK / "sales-handoff-offline-result.json"
ORIGINAL = HERE / "sol-dispatch-review.json"
IMAGE_BINDINGS = WORK / "verified-image-bindings.json"

MAKE_WORKBOOK = """
import hashlib, json, os, stat
from pathlib import Path
from zipfile import ZipFile
from openpyxl import Workbook

root = Path('/workspace')
with ZipFile(root / 'skillsbench-task.zip') as archive:
    names = {Path(member).name for member in archive.namelist()}
    assert {'income.xlsx', 'population.pdf', 'task.md'} <= names
book = Workbook()
sheet = book.active
for row in range(3200):
    sheet.append((row, hashlib.sha256(str(row).encode()).hexdigest()))
target = root / 'demographic_analysis.xlsx'
book.save(target)
properties = target.lstat()
assert stat.S_ISREG(properties.st_mode) and properties.st_nlink == 1
assert 100000 <= properties.st_size <= 300000
(root / 'symlink.xlsx').symlink_to(target.name)
with (root / 'oversized.xlsx').open('xb') as output:
    output.truncate(300001)
(root / 'directory.xlsx').mkdir()
print(json.dumps({'input_archive_readable': True, 'workbook_bytes': properties.st_size,
                  'workbook_sha256': hashlib.sha256(target.read_bytes()).hexdigest()}))
"""


def frozen():
    original = read(ORIGINAL)
    sales = next(
        row for row in original["public_input_scope"] if row["id"] == "sales-pivot-analysis"
    )
    return {
        "purpose": "Verify the Sales Pivot file handoff with no model, network or credential mount.",
        "prior_review": sha(ORIGINAL),
        "sales_archive": sales["public_archive"],
        "maximum_workers": 2,
        "model_turns": 0,
        "cash_usd": "0",
        "worker_images": {
            role: image["id"] for role, image in read(IMAGE_BINDINGS)["document_data"].items()
        },
        "worker_program_sha256": hashlib.sha256(ARTIFACT_PROGRAM.encode()).hexdigest(),
        "handoff_prefix_sha256": hashlib.sha256(
            corrected_sales_instructions("").encode()
        ).hexdigest(),
        "pins": {str(path): sha(path) for path in (Path(__file__), SALES_PAIR, IMAGE_BINDINGS)},
    }


async def inspect_worker(role, image, archive):
    spec = make_spec(SALES_PAIR, "document_data", role, image, offline=True)
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    worker = adapter._worker
    process_id = adapter._worker_process_id
    assert worker is not None and process_id is not None
    argv = adapter.transport.argv
    assert argv[argv.index("--network") + 1] == "none" and "--mount" not in argv
    assert not any("PROXY=" in arg for arg in argv)
    assert docker("image", "inspect", "--format", "{{.Id}}", image["id"]) == image["id"]
    name = "aeep-" + hashlib.sha256(process_id.encode()).hexdigest()[:32]
    assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    artifact = spec.managed_host_config().artifact
    assert artifact is not None and artifact.max_bytes == 300000
    assert artifact.input_name == "skillsbench-task.zip"
    assert artifact.output_name == "demographic_analysis.xlsx"
    started = time.monotonic()
    try:
        await adapter.transport.start()

        async def transfer(name, data=None):
            return await worker.artifact(process_id, name=name, limit=artifact.max_bytes, data=data)

        put = await transfer(artifact.input_name, base64.b64encode(archive).decode("ascii"))
        assert put == {"size": len(archive), "sha256": hashlib.sha256(archive).hexdigest()}
        observed = await command(adapter.transport, MAKE_WORKBOOK)
        workbook = await transfer(artifact.output_name)
        data = base64.b64decode(workbook["data"], validate=True)
        assert len(data) == workbook["size"] == observed["workbook_bytes"]
        assert hashlib.sha256(data).hexdigest() == workbook["sha256"] == observed["workbook_sha256"]
        with ZipFile(io.BytesIO(data)) as exported:
            assert {"xl/workbook.xml", "xl/worksheets/sheet1.xml"} <= set(exported.namelist())

        rejected = []
        for label, filename, value in (
            ("missing", "missing.xlsx", None),
            ("overwrite", artifact.input_name, "eA=="),
            ("oversize", "oversized.xlsx", None),
            ("symlink", "symlink.xlsx", None),
            ("directory", "directory.xlsx", None),
        ):
            try:
                await transfer(filename, value)
            except ConfigurationError:
                rejected.append(label)
            else:
                raise RuntimeError(f"artifact guard allowed {label}")
    finally:
        await adapter.close()
        assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    return {
        "worker_image": image["id"],
        "input_archive_readable": observed["input_archive_readable"],
        "output_sha256": workbook["sha256"],
        "output_bytes": workbook["size"],
        "rejected_transfer_controls": rejected,
        "model_turns": 0,
        "owned_worker_removed": True,
        "elapsed_seconds": time.monotonic() - started,
    }


async def run(identity):
    require_reserve(52)
    approved = frozen()
    assert sha(REVIEW) == identity and read(REVIEW) == approved and not RESULT.exists()
    fixture = read(SALES_PLAN)["suite"]["cases"][0]["action"]["input"]
    archive = base64.b64decode(fixture["task_archive_b64"], validate=True)
    assert hashlib.sha256(archive).hexdigest() == approved["sales_archive"]["sha256"]
    assert len(archive) == approved["sales_archive"]["bytes"]
    observations = {}
    for role, image in read(IMAGE_BINDINGS)["document_data"].items():
        observations[role] = await inspect_worker(role, image, archive)
    write(RESULT, {"review_sha256": identity, "synthetic_output": True, "workers": observations})
    print(json.dumps(read(RESULT), indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    options = parser.add_mutually_exclusive_group(required=True)
    options.add_argument("--freeze", action="store_true")
    options.add_argument("--execute")
    args = parser.parse_args()
    if args.freeze:
        write(REVIEW, frozen())
        print(sha(REVIEW))
    else:
        asyncio.run(run(args.execute))
