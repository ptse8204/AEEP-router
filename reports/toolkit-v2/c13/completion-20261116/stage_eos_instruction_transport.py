"""Verify EOS's exact long statement through the normal worker preparation path."""

import asyncio
import base64
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from stage_repository_transport import HERE, ROOT, WORK, digest, encode, read, write

from aeep.assessment.adapters import prepare_context
from aeep.assessment.models import content_digest
from aeep.assessment.repository_suites import SuiteInputV7, archive_files
from aeep.executors.base import ExecutionContext
from aeep.executors.managed_host import ManagedHostExecutor
from aeep.hosts.base import HostProbe
from aeep.models import ActionRequest, ExecutorKind, ExecutorSpec, RawExecution

CASE = "Akkudoktor-EOS__EOS-459"
RESULT = WORK / "eos-exact-instruction-transport-20261119.json"
PREFIX = "Current task JSON: "
CAPABILITY = "assessment.repository_suite@1"


class Recorder:
    instruction = ""

    async def probe(self):
        return HostProbe(adapter_id="c13-recording", status="ready")

    async def execute(self, context):
        self.instruction = context.instruction
        return RawExecution(status="success", output={})


def load_asset(ref):
    return read(ROOT / ref["path"], ref["sha256"])


async def project(root, task, source, role):
    spec = ExecutorSpec(
        id=role, capability=CAPABILITY, kind=ExecutorKind.MANAGED_HOST,
        description="First-party recording adapter for instruction preparation only.",
        resource_pool="c13-recording",
        config={
            "adapter_id": "c13-recording", "argv": [sys.executable],
            "instructions": PREFIX + "{input}", "managed_worker": {},
            "artifact": {"input_field": "source_b64", "output_field": "patch_gzip_b64",
                         "input_name": "repository.tar.gz", "output_name": "patch.json.gz",
                         "max_bytes": 3_500_000},
            "assessment_adapter": {"input_transform": "repository_archive:2", "read_only_roots": [str(root)]},
        },
    )
    raw = task.model_dump(mode="json")
    context = ExecutionContext(request=ActionRequest(capability=CAPABILITY, input=raw),
                               spec=spec, estimate=spec.estimate, attempt=1)
    projected, _ = prepare_context(context)
    arguments = projected.request.input
    if set(arguments) != set(raw) | {"base_sha256", "source_b64"}:
        raise ValueError("public mapping exposed unexpected fields")
    if base64.b64decode(arguments["source_b64"], validate=True) != source:
        raise ValueError("mapped archive is not the reviewed public source")
    recorder = Recorder()
    result = await ManagedHostExecutor(SimpleNamespace(get=lambda _key: recorder)).execute(projected)
    prompt = recorder.instruction
    actual = json.loads(prompt.removeprefix(PREFIX))
    expected = raw | {"base_sha256": content_digest(raw),
                      "input_path": "/workspace/repository.tar.gz", "output_path": "/workspace/patch.json.gz"}
    if actual != expected or result.metadata["task_instruction_sha256"] != digest(prompt.encode()):
        raise ValueError("ordinary worker template changed the exact statement or public boundary")
    return {"prompt_sha256": digest(prompt.encode()), "prompt_bytes": len(prompt.encode()),
            "statement_sha256": digest(actual["task"].encode())}


def main():
    intake = json.loads((HERE / "full-rebench-three-leads-result-20261119.json").read_bytes())
    frozen = intake["cases"][CASE]
    stage = json.loads(load_asset(intake["protected_staging"]))
    row, = [item for item in stage["cases"] if item["case"] == CASE]
    source = load_asset(row["assets"]["untouched-source"])
    statement = load_asset(frozen["full_statement"])
    overlay = archive_files(load_asset(frozen["protected_overlay"]), large=True)
    public = archive_files(source, large=True)
    if any(public.get(path) == content for path, content in overlay.items()):
        raise ValueError("protected overlay already appeared in the public bytes")
    task = SuiteInputV7(
        task_id=CASE, task=statement.decode(), family="energy-analysis",
        source_sha256=digest(source), editable_paths=row["source_changes"],
        instruction_format="source-statement-v1",
    )
    if len(task.task) <= 4000 or task.task.encode() != statement:
        raise ValueError("the exact statement did not survive input binding")
    with tempfile.TemporaryDirectory(prefix="aeep-eos-prompt-", dir="/private/tmp") as temp:
        root = Path(temp).resolve()
        write(root / (task.source_sha256 + ".tar.gz"), source)
        results = {role: asyncio.run(project(root, task, source, role)) for role in ("control", "treatment")}
    if results["control"] != results["treatment"]:
        raise ValueError("prepared arms received different instructions")
    write(RESULT, encode({
        "scope": "Actual EOS input through ordinary mapping and prompt rendering with a first-party recording adapter.",
        "publisher_revision": frozen["source_revision"],
        "statement_sha256": digest(statement), "statement_utf8_bytes": len(statement),
        "statement_characters": len(task.task), "public_source_sha256": task.source_sha256,
        "task_input_sha256": content_digest(task), "protected_overlay_separate": True,
        "projected_arms": results, "protected_assertions": row["required_issue"] + row["required_preservation"],
        "real_worker_invocations": 0, "protected_grader_invocations": 0, "model_turns": 0,
    }))


if __name__ == "__main__":
    main()
