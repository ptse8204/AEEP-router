"""Check the four exact worker images using offline Codex App Server and real tools."""

import asyncio
import hashlib
import json
import re
import secrets
import time

from prepare_runtime import DESIGN, LOCAL, WORK, docker, read, require_reserve, write

from aeep.assessment.models import content_digest
from aeep.hosts.codex_app_server import CodexAppServerAdapter
from aeep.hosts.codex_invocation import (
    inventory,
    isolated_config,
    resolve_skill_name,
    verify_thread_inventory,
)
from aeep.models import ExecutorSpec

SOL = LOCAL / "skillsbench-react-managed-preparation-20261107"
REACT = SOL / "sol-permitted-path-live-definitions/react-pair.json"
SALES = LOCAL / "skillsbench-managed-worker-preparation-20261105/engineering/sales-pair.json"
EXCEL = LOCAL / "skillsbench-document-managed-20261106/worker-definitions/excel-pair.json"
PROBE = r"""
import hashlib, importlib.util, json, pathlib, socket, subprocess, sys
from importlib.metadata import version
root = pathlib.Path('/workspace')
canary = root/'aeep-sol-canary'
canary.write_text('owned synthetic canary')
assert canary.read_text() == 'owned synthetic canary'
canary.unlink()
facts = {'workspace': True, 'shared_tools': {}}
for name, command in {
    'python': ['python3','--version'], 'node': ['node','--version'],
    'ripgrep': ['rg','--version'],
}.items():
    value = subprocess.check_output(command, text=True, timeout=10)
    facts['shared_tools'][name] = value.splitlines()[0]
for package in ('pandas', 'openpyxl'):
    facts['shared_tools'][package] = version(package)
try:
    with socket.create_connection(('192.0.2.10',443),timeout=1):
        raise AssertionError('unexpected external connection')
except PermissionError:
    facts['external_network_denied'] = True
from pathlib import Path
try:
    with Path('/etc/codex/requirements.toml').open('ab'):
        raise AssertionError('mutable managed requirements')
except OSError:
    facts['configuration_write_denied'] = True
skill = Path(SKILL)
facts['skill'] = hashlib.sha256(skill.read_bytes()).hexdigest() if skill.is_file() else None
if DOMAIN == 'document_data':
    pdf = Path('/opt/aeep-task-tools/pypdf-6.21.4-py3-none-any.whl')
    sys.path.insert(0,str(pdf))
    import pypdf
    facts['shared_tools']['pypdf'] = {'version':pypdf.__version__, 'wheel_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
    tool = Path('/opt/dependencies/runtime/node_modules/@oai/artifact-tool')
    facts['candidate_runtime'] = tool.is_dir()
    if TREATMENT and facts['candidate_runtime']:
        fallback = Path('/worker/home/.cache/codex-runtimes/codex-primary-runtime/dependencies')
        assert (fallback/'node/bin/node').is_file()
        (root/'node_modules').symlink_to(fallback/'node_modules')
        code = root/'sample.mjs'
        code.write_text("import {Workbook} from '@oai/artifact-tool'; import assert from 'node:assert/strict';"
                        "const w=await Workbook.fromCSV('id,value\n1,7\n',{sheetName:'Fixture'});"
                        "assert.deepEqual(w.worksheets.getItem('Fixture').getRange('A1:B2').values,[['id','value'],['1','7']]);")
        subprocess.run(['node',str(code)],cwd=root,check=True,timeout=25,capture_output=True)
        helper = skill.parent/'container_tools/mark_artifact_operation_started.mjs'
        subprocess.run(['node',str(helper),'--operation-kind','create','--expected-output-count','1','--output-format','xlsx'],
                       cwd=root,check=True,timeout=10,capture_output=True)
        facts['runtime_check'] = 'artifact-tool CSV and authoring helper'
else:
    path = Path('/opt/aeep-specialists')
    facts['candidate_runtime'] = path.is_dir()
    if TREATMENT and facts['candidate_runtime']:
        sys.path.insert(0,str(path))
        import libcst
        from libcst.codemod import CodemodContext
        from libcst.codemod.commands.rename import RenameCommand
        original = libcst.parse_module('from api import Old\n# keep\nx = Old("Old")\n')
        updated = RenameCommand(CodemodContext(), 'api.Old', 'api.New').transform_module(original)
        assert updated.code == 'from api import New\n# keep\nx = New("Old")\n'
        assert Path(libcst.__file__).is_relative_to(path)
        facts['runtime_check'] = 'LibCST rename preserves comment and string'
print(json.dumps(facts))
"""
COLLECTOR_PROBE = r"""
import json,socket
try:
    connection=socket.create_connection(('127.0.0.1',PORT),timeout=2)
    connection.close()
except PermissionError:
    print(json.dumps({'collector_connection_denied': True}))
"""


def descriptor(domain):
    design = read(DESIGN)
    candidate = design["candidate_arms"][domain.replace("_", "-")]
    if domain == "document_data":
        primary = "/opt/dependencies/plugin/skills/spreadsheets/SKILL.md"
        return (
            primary,
            "/etc/codex/skills/spreadsheets/SKILL.md",
            "Spreadsheets",
            candidate["skill_sha256"],
        )
    return (
        "/opt/dependencies/libcst-migrate/SKILL.md",
        "/etc/codex/skills/libcst-migrate/SKILL.md",
        "libcst-migrate",
        candidate["candidate_skill"]["sha256"],
    )


def make_spec(pair_file, domain, role, image, *, offline):
    approved = read(DESIGN)
    pair = read(pair_file)
    # Start from the ordinary configuration for both roles. All scientific
    # differences come from the explicit candidate invocation and image.
    spec = pair["control"]
    config = spec["config"]
    worker = config["managed_worker"]
    worker.update(
        image=image["id"],
        binary=approved["worker_inputs"]["sol_path"],
        binary_sha256=approved["worker_inputs"]["sol_binary"]["sha256"],
    )
    for key in ("configuration_digest", "permissions_profile", "seccomp_profile"):
        assert worker[key] == pair["treatment"]["config"]["managed_worker"][key]
    if offline:
        worker.update(credential_volume=None, network_id=None, model_proxy_url=None)
    else:
        worker["credential_volume"] = pair[role]["config"]["managed_worker"]["credential_volume"]
    label = f"sol-development-{domain.replace('_', '-')}-{role}"
    worker["worker_id"] = label
    worker["dependencies_digest"] = content_digest(
        {"image": image["id"], "policy": image["policy_sha256"]}
    )
    config.update(
        adapter_id="codex-app-server:" + label,
        argv=[worker["binary"], "app-server"],
        model_constraints={"allowed_model_ids": ["gpt-6.1-sol"]},
        reasoning_efforts=["medium"],
        timeout_seconds=300.0,
        store_prompt=False,
        store_output=False,
    )
    primary, _, name, skill_hash = descriptor(domain)
    config["invocation"] = {"mode": "turn", "local_profile": "capable_local"}
    if role == "treatment":
        worker["reviewed_files"][primary] = skill_hash
        config["invocation"].update(
            mode="skill",
            skill_name=name,
            skill_path=primary,
            skill_sha256=skill_hash,
            exposure="optional",
        )
    spec["id"] = label
    return ExecutorSpec.model_validate(spec)


async def command(transport, program):
    reply = await transport.request(
        "command/exec",
        {
            "command": ["python3", "-I", "-B", "-c", program],
            "cwd": "/workspace",
            "timeoutMs": 55000,
            "outputBytesCap": 4096,
        },
        timeout=60,
    )
    if reply.get("exitCode") != 0:
        categories = {
            key: key in str(reply.get("stderr", ""))
            for key in (
                "AssertionError",
                "PermissionError",
                "FileNotFoundError",
                "ModuleNotFoundError",
                "CalledProcessError",
                "ImportError",
                "bwrap",
                "Error [ERR_MODULE_NOT_FOUND]",
            )
        }
        line = re.search(r'File "<string>", line (\d+)', str(reply.get("stderr", "")))
        location = int(line[1]) if line else None
        raise RuntimeError(
            f"offline command exit={reply.get('exitCode')} at {location} {categories}"
        )
    return json.loads(reply["stdout"])


async def observe(domain, role, image, spec, directory):
    require_reserve(51)
    assert docker("image", "inspect", "--format", "{{.Id}}", image["id"]) == image["id"]
    adapter = CodexAppServerAdapter.from_executor(spec, principal_salt=secrets.token_bytes(32))
    transport = adapter.transport
    argv = transport.argv
    assert argv[argv.index("--network") + 1] == "none" and "--mount" not in argv
    assert not any("PROXY=" in arg for arg in argv)
    container = "aeep-" + hashlib.sha256(adapter._worker_process_id.encode()).hexdigest()[:32]
    observations = {
        "image": image["id"],
        "model_turns": 0,
        "candidate_exposure": role == "treatment",
    }
    started = time.monotonic()
    primary, _, _, digest = descriptor(domain)
    stage = "startup"
    try:
        await transport.start()
        models = await adapter.list_models()
        assert any(
            model.id == "gpt-6.1-sol" and "medium" in model.reasoning_efforts for model in models
        )
        observations.update(sol_medium_catalogue=True, protocol=transport.protocol_version)
        stage = "tool runtime"
        program = (
            PROBE.replace("SKILL", repr(primary))
            .replace("DOMAIN", repr(domain))
            .replace("TREATMENT", str(role == "treatment"))
        )
        facts = await command(transport, program)
        observations["runtime"] = facts
        assert (
            facts["workspace"]
            and facts["external_network_denied"]
            and facts["configuration_write_denied"]
        )
        assert facts["skill"] == (digest if role == "treatment" else None)
        assert facts["candidate_runtime"] is (role == "treatment")
        assert bool(facts.get("runtime_check")) is (role == "treatment")
        stage = "credential canary"
        docker(
            "exec",
            "--user",
            "65534:65534",
            container,
            "python3",
            "-I",
            "-B",
            "-c",
            "from pathlib import Path; Path('/worker/auth/aeep-synthetic-canary').write_text('synthetic')",
        )
        observations["auth_canary"] = await command(
            transport,
            """
import json
try:
    with open('/worker/auth/aeep-synthetic-canary','rb'):
        observation='readable'
except OSError:
    observation='blocked'
print(json.dumps({'result':observation}))
""",
        )
        assert observations["auth_canary"] == {"result": "blocked"}
        stage = "collector denial"
        sockets = docker("exec", "--user", "65534:65534", container, "cat", "/proc/net/tcp")
        ports = [
            int(row.split()[1].split(":")[1], 16)
            for row in sockets.splitlines()[1:]
            if row.split()[1].startswith("0100007F:") and row.split()[3] == "0A"
        ]
        assert len(ports) == 1
        observations["collector"] = await command(
            transport, COLLECTOR_PROBE.replace("PORT", str(ports[0]))
        )
        assert observations["collector"] == {"collector_connection_denied": True}
        stage = "effective inventory"
        catalog = await inventory(transport, "/workspace")
        config = spec.managed_host_config()
        target = resolve_skill_name(catalog, config.invocation)
        files = config.managed_worker["reviewed_files"]
        override = isolated_config(
            catalog,
            target,
            verified_worker_skill=role == "treatment"
            and files.get(target.skill_path) == target.skill_sha256,
            reviewed_worker_files=files,
        )
        active = await transport.request(
            "thread/start",
            {
                "ephemeral": True,
                "cwd": "/workspace",
                "model": "gpt-6.1-sol",
                "permissions": "aeep",
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "config": override,
            },
        )
        await verify_thread_inventory(transport, active["thread"]["id"], target)
        observations["effective_skill"] = target.skill_name
        observations["passed"] = True
    finally:
        await adapter.close()
        observations.update(
            stage=stage,
            elapsed_seconds=time.monotonic() - started,
            cleanup_confirmed=not docker("ps", "-aq", "--filter", "name=^/" + container + "$"),
        )
        write(directory / f"{domain}-{role}.json", observations)
    assert observations["cleanup_confirmed"]
    return observations


async def verify():
    directory = WORK / "worker-observations"
    assert directory.is_dir()
    final = read(WORK / "final-worker-images.json")
    results = {}
    for domain, file in (("document_data", SALES), ("software_engineering", REACT)):
        pair = final[domain]
        records = {}
        for role, image in pair.items():
            recorded = directory / f"{domain}-{role}.json"
            if recorded.exists():
                records[role] = read(recorded)
                continue
            spec = make_spec(file, domain, role, image, offline=True)
            records[role] = await observe(domain, role, image, spec, directory)
        results[domain] = records
    all_passed = all(row.get("passed", False) for pair in results.values() for row in pair.values())
    shared_tools_match = all(
        pair["control"].get("runtime", {}).get("shared_tools")
        == pair["treatment"].get("runtime", {}).get("shared_tools")
        for pair in results.values()
    )
    write(
        WORK / "offline-worker-verification.json",
        {
            "pairs": results,
            "shared_tools_matched": shared_tools_match,
            "passed": all_passed and shared_tools_match,
            "model_turns": 0,
            "provider_contact": False,
            "credential_mounts": 0,
            "scope": "Offline evidence; authenticated identity and operational readiness are gated separately.",
        },
    )


if __name__ == "__main__":
    asyncio.run(verify())
