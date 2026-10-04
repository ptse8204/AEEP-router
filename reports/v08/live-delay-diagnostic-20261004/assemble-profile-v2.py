"""Pure source renewal; writes inert metadata only, never a store or runtime."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.hosts.codex_dynamic_tools import CodexDynamicTools
from aeep.hosts.codex_invocation import contract_digest
from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
from aeep.economic.prepared import executor_fingerprint
from aeep.models import Manifest

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
OLD = ROOT / "reports/v08/luna-docx-stage/c-current-profile-v1.json"
OLD_SHA = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"


def main():
    if hashlib.sha256(OLD.read_bytes()).hexdigest() != OLD_SHA:
        raise ValueError("historical profile changed")
    old = json.loads(OLD.read_text())
    manifest_path = Path(old["native_project"]) / "aeep.json"
    if hashlib.sha256(manifest_path.read_bytes()).hexdigest() != "11707d498ce6a285c85c0e7c90314e9f24ff355e1be987021898896e9e920d60":
        raise ValueError("historical native manifest changed")
    manifest = Manifest.model_validate_json(manifest_path.read_text())
    specs = {item.id: item for item in manifest.executors}
    callbacks = copy.deepcopy(old["callback_documents_by_role"])
    for document in callbacks.values():
        identity = document["identity"]
        identity["implementation_digest"] = CodexDynamicTools.implementation_digest()
        names = list(identity["executor_fingerprints"])
        identity["executor_fingerprints"] = {name: executor_fingerprint(specs[name]) for name in names}
        identity["native_backend_digest"] = contract_digest({name: native_backend_digest(
            NativeSandboxConfig.model_validate(specs[name].config["native_sandbox"])) for name in names})
    spec = importlib.util.spec_from_file_location("delay_profile_assembler", OUT / "current-profile-assembler.py")
    assembler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(assembler)
    profile = assembler.assemble_current_profile(
        profile_document={"source_digest": SOURCE,
            "pair": {role: old["component"]["composed"][role] for role in ("control", "treatment")},
            "callback_documents_by_role": callbacks},
        spreadsheets_definition=old["component"]["spreadsheets"],
        shared_physical_skill_inventory=old["shared_physical_skill_inventory"],
        selected_worker=old["selected_worker_digest"], qualification_exposure=old["qualification_exposure"],
        source_root=ROOT)
    profile.update({"callback_documents_by_role": callbacks,
        "native_setup_result_sha256": old["native_setup_result_sha256"],
        "native_project": old["native_project"], "task_instructions": old["task_instructions"],
        "historical_profile_sha256": OLD_SHA,
        "renewal": "Current-source callback, executor and native-policy repin from unchanged manifest; historical native setup retained, fresh scopes and conformance required."})
    target = OUT / "c-current-profile-v2.json"
    with target.open("x") as stream:
        json.dump(profile, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"profile": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "callback_implementation_digest": profile["callback_implementation_digest"],
        "callback_bindings": profile["component"]["composed"]["callback_bindings"],
        "execution_authorized": False}))


if __name__ == "__main__":
    main()
