"""Probe the reviewed spreadsheet package from an ordinary workspace module."""

import argparse
import asyncio
import hashlib
import secrets
import time
from pathlib import Path

from check_sales_handoff import IMAGE_BINDINGS, ORIGINAL, SALES_PAIR
from prepare_runtime import WORK, docker, read, require_reserve, sha, write
from verify_workers import command, make_spec

from aeep.hosts.codex_app_server import CodexAppServerAdapter

REVIEW = WORK / "sales-runtime-offline-review.json"
RESULT = WORK / "sales-runtime-offline-result.json"

PROBE = r"""
import json, os, subprocess
from pathlib import Path
from zipfile import ZipFile
from openpyxl import load_workbook

root = Path('/workspace')
script = root / 'transport-check.mjs'
script.write_text(
    "import {Workbook,SpreadsheetFile} from '@oai/artifact-tool';"
    "const workbook=await Workbook.fromCSV('id,value\\n1,7\\n',{sheetName:'Fixture'});"
    "const file=await SpreadsheetFile.exportXlsx(workbook);"
    "await file.save('/workspace/transport-check.xlsx');"
)
target = root / 'node_modules'
dependencies = Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies'
package = dependencies / 'node_modules/@oai/artifact-tool'
assert not target.exists() and not target.is_symlink()
available = package.is_dir()
initial = subprocess.run(['node', str(script)], cwd=root, capture_output=True, timeout=12)
result = {'candidate_package_available': available, 'bare_import_succeeded': initial.returncode == 0,
          'bare_import_module_not_found': b'ERR_MODULE_NOT_FOUND' in initial.stderr,
          'scoped_alias_export_verified': False}
if available and initial.returncode:
    target.symlink_to(dependencies / 'node_modules', target_is_directory=True)
    restored = subprocess.run(['node', str(script)], cwd=root, capture_output=True, timeout=15)
    result['scoped_alias_exit_code'] = restored.returncode
    if restored.returncode == 0:
        workbook = load_workbook(root / 'transport-check.xlsx', read_only=True)
        assert workbook['Fixture']['B2'].value == '7'
        workbook.close()
        result['scoped_alias_export_verified'] = True
print(json.dumps(result))
"""


def frozen():
    return {
        "prior_review_sha256": sha(ORIGINAL),
        "purpose": "Check workspace module resolution and a synthetic workbook export.",
        "network": "none",
        "credential_mounts": 0,
        "model_turns": 0,
        "container_count_limit": 2,
        "cash_usd": "0",
        "worker_bindings_sha256": sha(IMAGE_BINDINGS),
        "probe_script_sha256": sha(Path(__file__)),
        "worker_spec_sha256": sha(SALES_PAIR),
    }


async def inspect(role, image):
    spec = make_spec(SALES_PAIR, "document_data", role, image, offline=True)
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    argv = adapter.transport.argv
    assert argv[argv.index("--network") + 1] == "none" and "--mount" not in argv
    assert not any("PROXY=" in value for value in argv)
    assert docker("image", "inspect", "--format", "{{.Id}}", image["id"]) == image["id"]
    process = adapter._worker_process_id
    assert process is not None
    name = "aeep-" + hashlib.sha256(process.encode()).hexdigest()[:32]
    assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    started = time.monotonic()
    try:
        await adapter.transport.start()
        observation = await command(adapter.transport, PROBE)
    finally:
        await adapter.close()
        assert not docker("ps", "-aq", "--filter", "name=^/" + name + "$")
    return {
        **observation,
        "worker_image": image["id"],
        "worker_cleanup_confirmed": True,
        "elapsed_seconds": time.monotonic() - started,
    }


async def execute(identity):
    require_reserve()
    assert sha(REVIEW) == identity and read(REVIEW) == frozen() and not RESULT.exists()
    records = {}
    for role, image in read(IMAGE_BINDINGS)["document_data"].items():
        records[role] = await inspect(role, image)
    write(RESULT, {"review_sha256": identity, "workers": records, "model_turns": 0})
    print(sha(RESULT))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--freeze", action="store_true")
    mode.add_argument("--execute")
    args = parser.parse_args()
    if args.freeze:
        write(REVIEW, frozen())
        print(sha(REVIEW))
    else:
        asyncio.run(execute(args.execute))
