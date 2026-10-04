"""Pure source renewal; writes inert metadata only, never a store or runtime."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

from aeep.hosts.codex_dynamic_tools import CodexDynamicTools

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
OLD = ROOT / "reports/v08/luna-docx-stage/c-current-profile-v1.json"
OLD_SHA = "8d3f49299452a7b4ea1e8cbc46abcd6ef8b81989ca24e131b35fbc8ed6bcd449"
SOURCE = "e6b71acba487280dfe50057d17379e5994c9113bc651a262935474f656a5dba6"


def main():
    if hashlib.sha256(OLD.read_bytes()).hexdigest() != OLD_SHA:
        raise ValueError("historical profile changed")
    old = json.loads(OLD.read_text())
    callbacks = copy.deepcopy(old["callback_documents_by_role"])
    for document in callbacks.values():
        document["identity"]["implementation_digest"] = CodexDynamicTools.implementation_digest()
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
        "renewal": "Implementation-only callback repin; historical native setup retained, fresh conformance required."})
    target = OUT / "c-current-profile-v1.json"
    with target.open("x") as stream:
        json.dump(profile, stream, indent=2)
        stream.write("\n")
    print(json.dumps({"profile": str(target), "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "callback_implementation_digest": profile["callback_implementation_digest"],
        "callback_bindings": profile["component"]["composed"]["callback_bindings"],
        "execution_authorized": False}))


if __name__ == "__main__":
    main()
