"""One exact reviewed, zero-turn B worker-component inspection; never admission."""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

from aeep.assessment.boundary import BoundaryProbeDefinition
from aeep.assessment.identity import file_digest, verify_dependencies
from aeep.assessment.models import (
    AssessmentEnvironment, AssessmentScopeAmendment, AssessmentSubject,
    ConformanceProbeRequest, RecipeRuntimeBinding, content_digest,
)
from aeep.assessment.service import AssessmentService
from aeep.assessment.verification import verification_source_digest
from aeep.assessment.workbook import workbook_recipe
from aeep.economic.prepared import executor_fingerprint
from aeep.errors import ConfigurationError
from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_pair_inspection import ComposedPairDefinition
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.hosts.workers import binding_from_config
from aeep.models import Manifest, StrictModel
from aeep.router import Router

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
PREPARED = OUT / "b-worker-components-preparation-v2.json"
EXECUTION_REVIEW = OUT / "b-worker-components-execution-review-v3.json"
STARTED = OUT / "b-worker-components-v2-started.json"
RESULT = OUT / "b-worker-components-v2-result.json"
PROFILE = OUT / "b-current-profile-v2.json"
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
CANONICAL_MANIFEST = ROOT / ".aeep/live-review-v3/aeep.json"
CANONICAL_MANIFEST_SHA256 = "091209e86a89894f5237b00021aa833117a0493d5067d1aa3091843a3ff0becb"
CANONICAL_DB = ROOT / ".aeep/live-review-v3/aeep.sqlite3"
STORAGE_PROBE = OUT / "storage_probe.py"
DOCKER = ["/usr/local/bin/docker", "--host", "unix:///Users/edwintse/.docker/run/docker.sock"]
PROXY_NAME = "aeep-reviewed-model-proxy"
PROXY_ID = "5f9a44f86633409a250d11a78cf59357495da2078724ee0261bc73acff57f0f3"
PROXY_IMAGE = "sha256:5bf590eb0bf8a06187ff092f0f75cf83b540cc27bd6a75fd8bd91305ca7b13de"
PROXY_NETWORK = "8f657f861de8897d53df66efdf595c6d2e202b174af81f2827db409fe53f19d6"


class DynamicDefinition(StrictModel):
    namespace: str
    tools: list[dict]
    identity: dict
    max_calls: int
    timeout_seconds: float


async def forbidden_call(_name, _arguments):
    raise ConfigurationError("zero-turn component inspection has no task-call authority")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_store_identity() -> dict:
    if (CANONICAL_MANIFEST.is_symlink() or sha(CANONICAL_MANIFEST) != CANONICAL_MANIFEST_SHA256
            or CANONICAL_DB.is_symlink()):
        raise ConfigurationError("canonical v3 manifest/store target changed")
    configured = Path(json.loads(CANONICAL_MANIFEST.read_text())["database"])
    if configured != CANONICAL_DB:
        raise ConfigurationError("canonical v3 database path changed")
    stat = CANONICAL_DB.stat()
    return {"manifest": str(CANONICAL_MANIFEST), "manifest_sha256": CANONICAL_MANIFEST_SHA256,
            "database": str(CANONICAL_DB), "device": stat.st_dev, "inode": stat.st_ino}


def require_storage_headroom(review: dict) -> dict:
    if review.get("storage_probe_sha256") != sha(STORAGE_PROBE):
        raise ConfigurationError("exact Foundation storage probe is not reviewed")
    output = subprocess.check_output([sys.executable, str(STORAGE_PROBE)], text=True, timeout=10)
    capacities = dict(line.split("=", 1) for line in output.splitlines() if "=" in line)
    important = int(capacities["NSURLVolumeAvailableCapacityForImportantUsageKey_bytes"])
    ordinary = int(capacities["NSURLVolumeAvailableCapacityKey_bytes"])
    if important < 50 * 1024**3 or ordinary < 52 * 1024**3:
        raise ConfigurationError("Foundation/raw capacity is below the 50 GiB reserve plus 2 GiB worker allowance")
    return {"important_usage_available_bytes": important, "ordinary_available_bytes": ordinary}


def require_running_proxy(review: dict) -> dict:
    if (review.get("proxy_name") != PROXY_NAME
            or review.get("proxy_id_prefix") != PROXY_ID
            or review.get("proxy_image") != PROXY_IMAGE
            or review.get("network_id") != PROXY_NETWORK):
        raise ConfigurationError("exact reviewed proxy identity is required")
    template = '{"Id":{{json .Id}},"Image":{{json .Image}},"Running":{{json .State.Running}},"Networks":{{json .NetworkSettings.Networks}}}'
    actual = json.loads(subprocess.check_output(
        DOCKER + ["inspect", "--format", template, PROXY_NAME], text=True, timeout=15,
        stderr=subprocess.DEVNULL))
    if (actual["Id"] != PROXY_ID or actual["Image"] != PROXY_IMAGE
            or actual["Running"] is not True
            or PROXY_NETWORK not in [value.get("NetworkID") for value in actual["Networks"].values()]):
        raise ConfigurationError("reviewed model proxy is not running with the exact identity/network")
    return {"container_id": actual["Id"], "image": actual["Image"],
            "network_id": PROXY_NETWORK, "running": True}


def typed_record(kind: str, value: dict, collector):
    if kind == "subject":
        return AssessmentSubject.model_validate(value)
    if kind == "recipe":
        return workbook_recipe()
    if kind == "environment":
        return AssessmentEnvironment.model_validate(value)
    if kind == "probe_runtime":
        return RecipeRuntimeBinding.model_validate(value)
    if kind == "composed_pair_definition":
        return ComposedPairDefinition.model_validate(value)
    if kind == "composed_worker_component":
        return collector.WorkerComponentDefinition.model_validate(value)
    if kind == "b_shared_spreadsheets_definition":
        return collector.SharedSpreadsheetsDefinition.model_validate(value)
    if kind == "codex_dynamic_tools":
        return DynamicDefinition.model_validate(value)
    if kind == "boundary_probe_definition":
        return BoundaryProbeDefinition.model_validate(value)
    if kind == "conformance_request":
        return ConformanceProbeRequest.model_validate(value)
    raise ValueError("unrecognized reviewed component record kind")


def safe_worker_summary(record: dict, request: ConformanceProbeRequest, pair_item: dict) -> dict:
    observations = record.get("observations", {})
    inspection = observations.get("inspection", {})
    models = [item for item in inspection.get("models", [])
              if isinstance(item, dict) and item.get("id") == "gpt-6-luna"]
    return {
        "request_id": request.plan_id,
        "worker_digest": record.get("worker_digest"),
        "execution_evidence_digest": record.get("execution_evidence_digest"),
        "probe_digests": pair_item.get("probe_digests", []),
        "component_probes_match": observations.get("component_probes_match") is True,
        "cleanup_confirmed": observations.get("cleanup_confirmed") is True,
        "identity_digest": inspection.get("identity_digest"),
        "luna_present_once": len(models) == 1,
        "xhigh_available": len(models) == 1 and "xhigh" in models[0].get("reasoning_efforts", []),
        "model_turns": observations.get("model_turns"),
    }


async def execute(review_sha256: str) -> None:
    if not EXECUTION_REVIEW.is_file() or sha(EXECUTION_REVIEW) != review_sha256:
        raise SystemExit("exact reviewed execution bundle hash required")
    review = json.loads(EXECUTION_REVIEW.read_text())
    if (review.get("execution_authorized") is not True
            or review.get("source_digest") != SOURCE
            or review.get("runner_sha256") != sha(Path(__file__))
            or review.get("preparation_sha256") != sha(PREPARED)
            or verification_source_digest(ROOT) != SOURCE):
        raise SystemExit("current source, runner, preparation or authorization differs")
    preparation = json.loads(PREPARED.read_text())
    if (preparation.get("source_digest") != SOURCE
            or preparation.get("request_ids") != review.get("request_ids")
            or preparation.get("component_digest") != review.get("component_digest")
            or preparation.get("component_evidence_only") is not True
            or preparation.get("maximum_operations") != 2
            or preparation.get("maximum_model_turns") != 0
            or preparation.get("maximum_reserved_seconds") != 480
            or review.get("maximum_operations") != 2
            or review.get("maximum_model_turns") != 0
            or review.get("maximum_reserved_seconds") != 480):
        raise SystemExit("fresh bounded two-operation component review differs")
    profile = json.loads(PROFILE.read_text())
    setup = json.loads(SETUP_RESULT.read_text())
    native_manifest = Path(profile["native_project"]).resolve() / "aeep.json"
    if review.get("native_manifest_path") != str(native_manifest):
        raise SystemExit("execution review does not name the actual native project manifest")
    for path, expected in preparation.get("inputs", {}).items():
        if sha(Path(path)) != expected:
            raise SystemExit("a reviewed profile/setup/collector input changed")
    if review.get("native_manifest_sha256") != preparation["inputs"].get(str(native_manifest)):
        raise SystemExit("execution review native-manifest digest differs")
    if (profile.get("source_digest") != SOURCE or setup.get("setup_complete") is not True
            or setup.get("operation_settled") is not True
            or setup.get("model_turns") != 0 or setup.get("task_calls") != 0
            or setup.get("worker_launches") != 0):
        raise SystemExit("fresh zero-turn protected B setup is not settled")
    dependencies = review.get("supervisor_dependencies")
    if not isinstance(dependencies, dict) or dependencies.get(str(Path(__file__).resolve())) != sha(Path(__file__)):
        raise SystemExit("exact supervisor dependency review is missing")
    verify_dependencies(dependencies)
    canonical = canonical_store_identity()
    if review.get("canonical_store") != canonical:
        raise SystemExit("canonical manifest/database identity differs from exact execution review")
    storage = require_storage_headroom(review)
    proxy = require_running_proxy(review)
    if STARTED.exists() or RESULT.exists():
        raise SystemExit("preserve any prior start/result; replay is forbidden")

    loader = importlib.util.spec_from_file_location(
        "aeep_b_component_collector", OUT / "b-composed-worker-collector-v2.py")
    collector = importlib.util.module_from_spec(loader)
    loader.loader.exec_module(collector)
    records = preparation.get("records", [])
    definitions = preparation.get("definitions", {})
    if not isinstance(records, list) or not isinstance(definitions, dict):
        raise SystemExit("prepared immutable record bundle is malformed")

    router = Router.from_manifest(CANONICAL_MANIFEST)
    service = AssessmentService(router, ROOT / ".aeep/live-review-v3")
    repo = service.repository
    try:
        amendment = AssessmentScopeAmendment.model_validate(preparation["amendment"])
        if (amendment.authorization_id != "onboarding"
                or set(amendment.reviewed_digests) - set(definitions)
                or set(amendment.environment_digests) - set(definitions)):
            raise ConfigurationError("current onboarding scope amendment differs")
        typed = []
        record_digests = set()
        for item in records:
            model = typed_record(item["kind"], item["value"], collector)
            digest = content_digest(model)
            if digest not in definitions or definitions[digest] != model.model_dump(mode="json"):
                raise ConfigurationError("prepared definition digest or serialization differs")
            expected_identity = {
                "subject": model.subject_id if item["kind"] == "subject" else None,
                "recipe": model.recipe_id if item["kind"] == "recipe" else None,
                "environment": model.environment_id if item["kind"] == "environment" else None,
                "conformance_request": model.plan_id if item["kind"] == "conformance_request" else None,
            }.get(item["kind"], digest)
            if expected_identity != item["identity"]:
                raise ConfigurationError("prepared definition record identity differs")
            record_digests.add(digest)
            typed.append((item["kind"], item["identity"], model, digest))
        if record_digests != set(definitions):
            raise ConfigurationError("prepared records do not cover the exact approved definition bundle")
        with repo.store._lock:
            for digest in record_digests:
                row = repo.store._connection.execute(
                    "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)).fetchone()
                if row is not None and row[0]:
                    raise ConfigurationError("a prepared definition is already revoked")
        for kind, identity, model, digest in typed:
            if repo.put(kind, identity, model) != digest:
                raise ConfigurationError("canonical record digest differs")
        repo.approve_bundle(amendment, definitions)

        requests = [ConformanceProbeRequest.model_validate(value)
                    for value in preparation["requests"]]
        if [item.plan_id for item in requests] != preparation["request_ids"]:
            raise ConfigurationError("prepared request IDs differ")
        for request in requests:
            if content_digest(repo.get("conformance_request", request.plan_id)) != content_digest(request):
                raise ConfigurationError("canonical request differs from reviewed request")
            repo.authorize(request)
            from aeep.assessment.identity import verify_dependencies as verify_request_dependencies
            verify_request_dependencies(request.executable_dependencies)

        profile_component = collector.WorkerComponentDefinition.model_validate(profile["component"])
        callbacks = []
        native_manifest = Path(profile["native_project"]).resolve() / "aeep.json"
        manifest = Manifest.model_validate_json(native_manifest.read_text())
        specs = {item.id: item for item in manifest.executors}
        for role in ("control", "treatment"):
            selected = getattr(profile_component, role)
            worker = binding_from_config(selected.managed_host_config().managed_worker)
            digest = profile_component.composed.callback_bindings[worker.digest()]
            document = DynamicDefinition.model_validate(profile["callback_documents_by_role"][role])
            if content_digest(document) != digest:
                raise ConfigurationError("current profile callback binding changed")

            def check(document=document, digest=digest, worker=worker, selected=selected):
                verify_dependencies(dependencies)
                if verification_source_digest(ROOT) != SOURCE or sha(native_manifest) != review["native_manifest_sha256"]:
                    raise ConfigurationError("source or protected native manifest changed")
                with repo.store._lock:
                    row = repo.store._connection.execute(
                        "SELECT revoked FROM assessment_reviews WHERE digest=?", (digest,)).fetchone()
                if (row is None or row[0]
                        or repo.get("codex_dynamic_tools", digest) != document.model_dump(mode="json")
                        or document.identity["worker_digest"] != worker.digest()
                        or document.identity["implementation_digest"] != CodexDynamicTools.implementation_digest()
                        or document.identity.get("artifact") != selected.managed_host_config().artifact.model_dump(mode="json")):
                    raise ConfigurationError("reviewed callback binding or worker changed")
                actual = {name: specs[name] for name in document.identity["executor_fingerprints"] if name in specs}
                if ({name: executor_fingerprint(spec) for name, spec in actual.items()}
                        != document.identity["executor_fingerprints"]):
                    raise ConfigurationError("actual native executor fingerprints changed")
                backends = {}
                for name, child in actual.items():
                    backend = NativeSandboxConfig.model_validate(child.config.get("native_sandbox", {}))
                    backend.validate_single_process()
                    backend.argv([])
                    backends[name] = native_backend_digest(backend)
                if contract_digest(backends) != document.identity["native_backend_digest"]:
                    raise ConfigurationError("actual native backend changed")
                return digest

            callbacks.append(CodexDynamicTools(**document.model_dump(mode="json"),
                call=forbidden_call, check=check))
            callbacks[-1].verify(digest, worker.digest())

        component, checked_requests, _workers, _probe_definitions = collector.authorize_component(
            service, requests[0].plan_id, requests[1].plan_id, tuple(callbacks))
        if (content_digest(component) != preparation["component_digest"]
                or [item.plan_id for item in checked_requests] != preparation["request_ids"]):
            raise ConfigurationError("current exact composed component differs")
        with STARTED.open("x") as stream:
            json.dump({"review_sha256": review_sha256, "request_ids": preparation["request_ids"],
                       "component_digest": preparation["component_digest"]}, stream, indent=2)
            stream.write("\n")

        result = {"source_digest": SOURCE, "review_sha256": review_sha256,
                  "request_ids": preparation["request_ids"], "component_digest": preparation["component_digest"],
                  "model_turns": 0, "component_evidence_only": True,
                  "storage": storage, "proxy_identity": proxy,
                  "full_conformance": False, "qualification": False, "replay_allowed": False}
        try:
            async with asyncio.timeout(420):
                pair = await collector.execute_composed_workers(
                    service, requests[0].plan_id, requests[1].plan_id, bindings=tuple(callbacks))
            summaries = {}
            for role, request in zip(("control", "treatment"), requests, strict=True):
                item = pair["workers"][role]
                record = repo.get("worker_pair_inspection", "pair-inspection:" + request.plan_id)
                summaries[role] = safe_worker_summary(record, request, item)
                if (content_digest(record) != item["record_digest"]
                        or summaries[role]["model_turns"] != 0
                        or summaries[role]["component_probes_match"] != item["component_probes_match"]):
                    raise ConfigurationError("stored component observation digest or zero-turn count differs")
            if pair.get("model_turns") != 0:
                raise ConfigurationError("component collector reported a nonzero model-turn count")
            result.update(failed_stage=pair.get("failed_stage"), collector_error_type=pair.get("error_type"),
                          component_probes_match=pair.get("component_probes_match") is True,
                          workers=summaries, source_unchanged=verification_source_digest(ROOT) == SOURCE)
        except BaseException as exc:
            result.update(error_type=type(exc).__name__, component_probes_match=False,
                          source_unchanged=verification_source_digest(ROOT) == SOURCE)
        with RESULT.open("x") as stream:
            json.dump(result, stream, indent=2)
            stream.write("\n")
        print(json.dumps({key: result.get(key) for key in
                          ("component_probes_match", "model_turns", "request_ids", "source_unchanged")}))
        if result.get("component_probes_match") is not True:
            raise SystemExit("component observations failed; preserve canonical partial accounting and do not replay")
    finally:
        await router.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-reviewed", required=True)
    args = parser.parse_args()
    asyncio.run(execute(args.execute_reviewed))


if __name__ == "__main__":
    main()
