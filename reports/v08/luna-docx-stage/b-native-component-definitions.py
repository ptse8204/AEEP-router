"""Build exact B native-only component definitions from settled setup evidence."""
from __future__ import annotations

import errno
import hashlib
import json
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
SETUP_RESULT = OUT / "b-native-setup-v3-result.json"
SETUP_REVIEW = OUT / "b-native-setup-v3-review.json"
SOURCE = "449b2e2f6b3602107613503781a22330bbede25d7aee4ad2f67b753cbd2f31ad"
SETUP_RESULT_SHA256 = "45f2344b74181d79ca284c8d3d3adc3d8d73a3c9edd1ccc51ef6993ed2968752"
SETUP_REVIEW_SHA256 = "ab4f78de528080b8684d8d608786d15a5b8aa616755d7f9033957ac0c44ef7b5"
NATIVE_MANIFEST_SHA256 = "11707d498ce6a285c85c0e7c90314e9f24ff355e1be987021898896e9e920d60"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def definitions() -> dict:
    """Validate settled B setup artifacts and return inert command definitions."""
    from aeep.assessment.models import content_digest
    from aeep.assessment.onboarding import reference_spec
    from aeep.economic.prepared import executor_fingerprint
    from aeep.hosts.codex_invocation import contract_digest
    from aeep.hosts.codex_sandbox import NativeSandboxConfig, native_backend_digest
    from aeep.hosts.workers import ManagedWorkerBinding, validate_worker_pair
    from aeep.models import ExecutorKind, Manifest, SideEffect

    for path in (SETUP_RESULT, SETUP_REVIEW):
        if path.is_symlink() or not path.is_file():
            raise ValueError("settled B setup evidence is absent or unsafe")
    if file_sha256(SETUP_RESULT) != SETUP_RESULT_SHA256:
        raise ValueError("B setup result changed")
    if file_sha256(SETUP_REVIEW) != SETUP_REVIEW_SHA256:
        raise ValueError("B setup review changed")
    setup = json.loads(SETUP_RESULT.read_text())
    setup_review = json.loads(SETUP_REVIEW.read_text())
    setup_request = setup_review.get("request", {})
    if (setup.get("setup_complete") is not True
            or setup.get("operation_settled") is not True
            or setup.get("source_digest") != SOURCE
            or setup.get("review_sha256") != SETUP_REVIEW_SHA256
            or setup.get("request_id") != setup_request.get("plan_id")
            or setup.get("operation_id") != setup.get("request_id") + ":b_native_project_setup"
            or setup.get("model_turns") != 0
            or setup.get("task_calls") != 0
            or setup.get("worker_launches") != 0
            or setup.get("whole_system_cost_complete") is not False
            or not isinstance(setup.get("project_bytes"), int)
            or not 0 <= setup["project_bytes"] <= 1024**3
            or not isinstance(setup.get("elapsed_seconds"), (int, float))
            or not 0 <= setup["elapsed_seconds"] <= 120):
        raise ValueError("B setup result is not the exact settled zero-turn result")
    setup_definition = setup_review["definitions"][setup_request["mapping_digest"]]
    if setup_definition.get("worker_documents") != setup.get("worker_documents"):
        raise ValueError("B setup worker bindings differ from their reviewed profile snapshot")

    project = Path(setup["project"])
    if (not project.is_absolute() or project.is_symlink() or not project.is_dir()
            or project.resolve() != project or project == ROOT or ROOT in project.parents):
        raise ValueError("B project must be the exact fresh path outside the repository")
    manifest_path = project / "aeep.json"
    if (manifest_path.is_symlink() or not manifest_path.is_file()
            or file_sha256(manifest_path) != NATIVE_MANIFEST_SHA256):
        raise ValueError("actual B native manifest changed")
    manifest = Manifest.model_validate_json(manifest_path.read_bytes())
    if manifest.database != str(project / ".aeep" / "state.db"):
        raise ValueError("actual native manifest database path differs")
    specs = [spec for spec in manifest.executors if spec.id == "native.composed.workbook"]
    if len(specs) != 1 or len(manifest.executors) != 1:
        raise ValueError("actual B manifest must contain only its pinned workbook executor")
    task_spec = specs[0]
    if task_spec.kind is not ExecutorKind.COMMAND or task_spec.side_effect is not SideEffect.READ:
        raise ValueError("actual B workbook executor is not a read-only command")
    native = NativeSandboxConfig.model_validate(task_spec.config["native_sandbox"])
    native.validate_single_process()
    native.argv([])
    deny = {str(Path(value)) for value in native.deny_roots}
    expected_private_root = str((project / ".aeep").resolve())
    if (native.project_root != str(project)
            or native.network is not False
            or native.single_process is not True
            or expected_private_root not in deny
            or str((project / "aeep.json").resolve()) not in deny
            or float(task_spec.config.get("timeout_seconds", 0)) != 10.0):
        raise ValueError("actual B native backend limits or denial roots differ")
    database = Path(manifest.database)
    canary = project / ".aeep" / "b-native-components-private-canary"
    local_database = project / ".aeep" / "b-native-components-local.sqlite3"
    if (database.is_symlink() or not database.is_file()
            or canary.exists() or canary.is_symlink()
            or local_database.exists() or local_database.is_symlink()):
        raise ValueError("database/canary/local component paths are not fresh regular paths")

    workers = {
        role: ManagedWorkerBinding.model_validate(value)
        for role, value in setup["worker_documents"].items()
    }
    if set(workers) != {"control", "treatment"}:
        raise ValueError("exact B control/treatment worker bindings required")
    validate_worker_pair(workers["control"], workers["treatment"])
    worker_digests = {role: worker.digest() for role, worker in workers.items()}
    backend_digest = native_backend_digest(native)
    callback_backend = contract_digest({task_spec.id: backend_digest})
    callback_digests = {}
    for role in ("control", "treatment"):
        callback = setup.get("callback_documents_by_role", {}).get(role)
        identity = callback.get("identity") if isinstance(callback, dict) else None
        if (not isinstance(identity, dict)
                or identity.get("worker_digest") != worker_digests[role]
                or identity.get("native_backend_digest") != callback_backend
                or identity.get("approval_ceiling") != "read"
                or identity.get("scope_limits") != {"max_attempts": 1, "max_attempt_seconds": 10.0}):
            raise ValueError("settled callback declarations are not bound to the exact B role/backend")
        callback_digests[role] = content_digest(callback)

    # The command emits only bounded enforcement observations, never file bytes.
    output_keys = {
        "hard_nproc": "string",
        "session_leader": "boolean",
        "marker": "string",
        "fork_errno": "string",
        "spawn_errno": "string",
        "raise_denied": "boolean",
        "private_denied": "boolean",
        "database_denied": "boolean",
        "network_denied": "boolean",
    }
    program = (
        "import errno,json,os,resource,socket\n"
        "r={'hard_nproc':':'.join(map(str,resource.getrlimit(resource.RLIMIT_NPROC))),"
        "'session_leader':os.getpid()==os.getpgid(0)==os.getsid(0),'marker':'post_exec'}\n"
        "try:\n"
        " p=os.fork()\n"
        " if p==0: os._exit(73)\n"
        " os.waitpid(p,0);r['fork_errno']='unexpected'\n"
        "except OSError as e:r['fork_errno']=str(e.errno)\n"
        "try:\n"
        " p=os.posix_spawn('/usr/bin/true',['/usr/bin/true'],{})\n"
        " os.waitpid(p,0);r['spawn_errno']='unexpected'\n"
        "except OSError as e:r['spawn_errno']=str(e.errno)\n"
        "try: resource.setrlimit(resource.RLIMIT_NPROC,(1,1));r['raise_denied']=False\n"
        "except (OSError,ValueError):r['raise_denied']=True\n"
        f"try: open({str(canary)!r},'rb').read(1);r['private_denied']=False\n"
        "except PermissionError:r['private_denied']=True\n"
        f"try: open({str(database)!r},'rb').read(1);r['database_denied']=False\n"
        "except PermissionError:r['database_denied']=True\n"
        "s=socket.socket();s.settimeout(.25)\n"
        "try: s.connect(('127.0.0.1',9));r['network_denied']=False\n"
        "except PermissionError:r['network_denied']=True\n"
        "except OSError:r['network_denied']=False\n"
        "finally: s.close()\n"
        "print(json.dumps(r,sort_keys=True))\n"
    )
    base = reference_spec("csv")
    guard = base.model_copy(deep=True)
    guard.id = "b.native.component.guard"
    guard.kind = ExecutorKind.COMMAND
    guard.side_effect = SideEffect.READ
    guard.idempotent = True
    guard.config = {
        "argv": [native.python_binary, "-I", "-c", program],
        "argv_literal": True,
        "stdin_json": False,
        "output": {"type": "json"},
        "timeout_seconds": 10,
        "max_output_bytes": 8192,
        "max_stdin_bytes": 0,
        "native_sandbox": native.model_dump(mode="json"),
    }
    guard.output_schema = {
        "type": "object",
        "properties": {key: {"type": kind} for key, kind in output_keys.items()},
        "required": list(output_keys),
        "additionalProperties": False,
    }
    expected = {
        "hard_nproc": "0:0",
        "session_leader": True,
        "marker": "post_exec",
        "fork_errno": str(errno.EAGAIN),
        "spawn_errno": str(errno.EAGAIN),
        "raise_denied": True,
        "private_denied": True,
        "database_denied": True,
        "network_denied": True,
    }
    cancel_program = (
        "import json,os,time\n"
        "print(json.dumps({'native_component_ready':True,'pid':os.getpid()}),flush=True)\n"
        "time.sleep(30)\n"
    )
    cancel = guard.model_copy(deep=True)
    cancel.id = "b.native.component.cancel"
    cancel.config = {
        **guard.config,
        "argv": [native.python_binary, "-I", "-c", cancel_program],
        "timeout_seconds": 10,
        "max_output_bytes": 1024,
    }
    cancel.output_schema = {"type": "object", "additionalProperties": True}
    component_specs = {
        "guard": {"spec": guard.model_dump(mode="json"), "fingerprint": executor_fingerprint(guard),
                   "input": {"text": "b-native-component-probe", "delimiter": ","}},
        "cancel": {"spec": cancel.model_dump(mode="json"), "fingerprint": executor_fingerprint(cancel),
                   "input": {"text": "b-native-cancellation-probe", "delimiter": ","}},
    }
    return {
        "source_digest": SOURCE,
        "setup_request_id": setup["request_id"],
        "setup_result_digest": SETUP_RESULT_SHA256,
        "setup_review_digest": SETUP_REVIEW_SHA256,
        "project": str(project),
        "manifest_path": str(manifest_path),
        "manifest_digest": NATIVE_MANIFEST_SHA256,
        "database_path": str(database),
        "canary_path": str(canary),
        "local_database_path": str(local_database),
        "native_config": native.model_dump(mode="json"),
        "native_backend_digest": backend_digest,
        "task_spec_id": task_spec.id,
        "callback_document_digests": callback_digests,
        "worker_documents": {role: worker.model_dump(mode="json") for role, worker in workers.items()},
        "worker_digests": worker_digests,
        "selected_worker_role": "treatment",
        "selected_worker_digest": worker_digests["treatment"],
        "components": component_specs,
        "native_boundary_expected": expected,
        "native_boundary_output_schema": guard.output_schema,
        "callback_requirement": {
            "status": "required_unobserved",
            "detail": "This native-only operation does not invoke the host-issued callback. The callback declaration digests are linkage only; actual host invocation evidence remains a separate gate.",
        },
        "full_conformance": False,
    }
