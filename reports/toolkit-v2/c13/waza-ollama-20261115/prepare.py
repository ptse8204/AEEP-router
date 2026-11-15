"""Freeze one local Waza execution, without downloading software or starting it."""

import argparse
import json
import shutil
from datetime import timedelta
from pathlib import Path

from aeep.assessment.identity import file_digest
from aeep.assessment.models import AssessmentAuthorization, content_digest
from aeep.assessment.repository import AssessmentRepository
from aeep.assessment.verification import verification_source_digest
from aeep.models import utc_now
from aeep.store import ReceiptStore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
WAZA = HERE.parent / "waza-native-backend-20261104"
FIXTURE = WAZA / "backend-fixture"
MODEL = "qwen3:4b-instruct-2507-q4_K_M"
SANDBOX = Path("/usr/bin/sandbox-exec")
PORT = 39181
ENGINE_PORT = 39182
GIB = 1024**3
ARCHIVE = {
    "url": "https://github.com/ollama/ollama/releases/download/v0.40.16/ollama-darwin.tgz",
    "sha256": "a743717494315da7cd352982b805f6b992d4b4452ca117fd5fbf86c4ee46fca0",
    "size": 186116182,
}
STAGES = {
    "download_and_install": {"operations": 1, "model_turns": 0, "reserved_seconds": 1500},
    "service_and_boundaries": {"operations": 1, "model_turns": 0, "reserved_seconds": 90},
    "waza_local_inference": {"operations": 1, "model_turns": 1, "reserved_seconds": 180},
    "protected_grade": {"operations": 1, "model_turns": 0, "reserved_seconds": 45},
}


def load(path):
    return json.loads(Path(path).read_bytes())


def write(path, data):
    if isinstance(data, bytes):
        with path.open("xb") as stream:
            stream.write(data)
    else:
        write(path, (json.dumps(data, indent=2, allow_nan=False) + "\n").encode())
    return path


def profile(read_roots, write_roots, *, connect=None, listen=None, local_runner=False):
    entries = [
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny file-write*)",
        '(deny file-read* (subpath "/Users") (subpath "/Volumes") (subpath "/private/tmp") '
        '(subpath "/tmp") (subpath "/private/var/folders") (subpath "/var/folders") '
        '(subpath "/Library/Keychains") (subpath "/private/var/db"))',
        '(deny mach-lookup (global-name "com.apple.securityd") '
        '(global-name "com.apple.security.agent") (global-name "com.apple.securityd.xpc"))',
    ]
    if connect is not None:
        entries.append(f'(allow network-outbound (remote ip "localhost:{connect}"))')
    if local_runner:
        # The pinned Ollama implementation allocates loopback TCP ports for its
        # child runners. Waza itself still gets one fixed gateway port.
        entries.append('(allow network-outbound (remote ip "localhost:*"))')
        listen = "*"
    if listen is not None:
        entries.append(f'(allow network-bind (local ip "localhost:{listen}"))')
        entries.append(f'(allow network-inbound (local ip "localhost:{listen}"))')
    for root in read_roots:
        entries.append(f"(allow file-read* (subpath {json.dumps(str(root))}))")
    for root in write_roots:
        entries.append(f"(allow file-write* (subpath {json.dumps(str(root))}))")
    entries.append('(allow file-write* (literal "/dev/null"))')
    ancestors = sorted({str(parent) for root in read_roots for parent in root.parents})
    entries.append(
        "(allow file-read-metadata "
        + " ".join(f"(literal {json.dumps(p)})" for p in ancestors)
        + ")"
    )
    return ("\n".join(entries) + "\n").encode()


def grant_snapshot(database, authorization):
    with ReceiptStore(database, read_only=True) as store:
        repo = AssessmentRepository(store)
        grant = AssessmentAuthorization.model_validate(repo.get("authorization", authorization))
        effective = repo.effective_grant(authorization)
        state = store._connection.execute(
            "SELECT revoked,operations,model_turns,elapsed_seconds,cash_usd FROM assessment_grants WHERE id=?",
            (authorization,),
        ).fetchone()
        predecessor = store._connection.execute(
            "SELECT digest FROM assessment_records WHERE kind='budget_amendment' "
            "AND json_extract(payload_json, '$.authorization_id')=? ORDER BY rowid DESC LIMIT 1",
            (authorization,),
        ).fetchone()
        reserved = store._connection.execute(
            "SELECT id FROM assessment_operations WHERE grant_id=? AND state='reserved'",
            (authorization,),
        ).fetchall()
        if state is None or state[0] or state[4] not in {"0", "0.0"} or reserved:
            raise RuntimeError("Waza accounting baseline is unavailable, revoked or unsettled")
        return {
            "id": authorization,
            "root": content_digest(grant),
            "state": list(state),
            "predecessor": predecessor[0] if predecessor else None,
            "effective_limits": effective.limits.model_dump(mode="json"),
            "effective_expiry": effective.expires_at.isoformat(),
        }


def prepare(work):
    if shutil.disk_usage(ROOT).free < 55 * GIB:
        raise RuntimeError("setup requires at least 55 GiB free")
    work.mkdir(mode=0o700)
    staging = work / "retained"
    exec_root = work / "scratch"
    live, grader, serve = (exec_root / name for name in ("model-task", "grader", "ollama"))
    public = work / "public"
    for entry in (public / "agent", public / "tasks", public / "fixtures"):
        entry.mkdir(parents=True, mode=0o700)
    pinned = load(FIXTURE / "offline-grader-review.json")
    installed = load(FIXTURE / "waza-runtime-installation-result.json")
    waza = Path(installed["destination"]) / "bin/waza"
    op = load(WAZA / "operator-setup-20261113/protected-login-review.json")
    copilot = Path(op["argv"][0])
    for relative in ("tasks/receipt-total.yaml", "agent/aeep-receipt-check.agent.md"):
        old = FIXTURE / relative
        assert file_digest(old) == pinned["pins"][str(old)]
        write(public / relative, old.read_bytes())
    grader_spec = FIXTURE / "eval.yaml"
    assert file_digest(grader_spec) == pinned["pins"][str(grader_spec)]
    assert file_digest(waza) == pinned["pins"][str(waza)]
    assert file_digest(copilot) == op["assets"][str(copilot)]
    live_spec = load(grader_spec)
    live_spec["config"]["model"] = MODEL
    # Waza validates the grader structure before --skip-graders turns execution off.
    # This inert public text condition contains no expected answer.
    live_spec["graders"][0]["config"] = {"regex_match": [".+"]}
    live_spec["graders"][0]["name"] = "public-placeholder-not-executed"
    public_spec = write(public / "eval.yaml", live_spec)
    profiles = {
        "serve": write(work / "serve.sb", profile([staging, serve], [serve], local_runner=True)),
        "live": write(
            work / "live.sb",
            profile([Path(installed["destination"]), copilot, public, live], [live], connect=PORT),
        ),
        "grade": write(
            work / "grade.sb", profile([Path(installed["destination"]), FIXTURE, grader], [grader])
        ),
    }
    previous = load(WAZA / "operation-review.json")
    database = previous["ledger"]
    authorization = load(WAZA / "prepared.json")["request"]["authorization_id"]
    baseline = grant_snapshot(database, authorization)
    source = verification_source_digest(ROOT)
    expires = utc_now() + timedelta(days=3)
    manifest = HERE / "model-manifest.json"
    model = load(manifest)
    assert (
        file_digest(manifest) == "0edcdef34593eac1aa2be9c7d06c432dcf81945adca5eca2f27662c18f168ba0"
    )
    model_assets = []
    for item in [model["config"], *model["layers"]]:
        assert item["digest"].startswith("sha256:")
        model_assets.append(
            {
                "url": "https://registry.ollama.ai/v2/library/qwen3/blobs/" + item["digest"],
                "sha256": item["digest"].removeprefix("sha256:"),
                "size": item["size"],
                "media_type": item["mediaType"],
            }
        )
    pins = {
        str(p): file_digest(p)
        for p in [
            Path(__file__).resolve(),
            HERE / "run.py",
            HERE / "local_gate.py",
            HERE / "check.py",
            manifest,
            waza,
            copilot,
            SANDBOX,
            Path("/usr/sbin/lsof"),
            Path("/usr/bin/codesign"),
            Path("/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"),
            *profiles.values(),
            public_spec,
            public / "tasks/receipt-total.yaml",
            public / "agent/aeep-receipt-check.agent.md",
            grader_spec,
            FIXTURE / "offline-grader-result.json",
        ]
    }
    archive = ARCHIVE | {
        "version": "0.40.16",
        "revision": "d63b702609c4300a2ca07be2bdb0adb9834725e5",
    }
    operations = sum(stage["operations"] for stage in STAGES.values())
    seconds = sum(stage["reserved_seconds"] for stage in STAGES.values())
    review = {
        "schema_version": "aeep.operator.waza-ollama.v1",
        "implementation_source": source,
        "expires_at": expires.isoformat(),
        "purpose": "One Waza engineering task and protected offline grade through a local model.",
        "work": str(work),
        "database": database,
        "grant_baseline": baseline,
        "waza_revision": pinned["source_revision"],
        "waza": str(waza),
        "copilot": str(copilot),
        "copilot_version": "1.0.85",
        "model": MODEL,
        "model_license": "Apache-2.0",
        "archive": archive,
        "model_assets": model_assets,
        "model_manifest": str(manifest),
        "allowed_download_hosts": [
            "github.com",
            "release-assets.githubusercontent.com",
            "registry.ollama.ai",
            "dd20bb891979d25aebc8bec07b2b3bbc.r2.cloudflarestorage.com",
        ],
        "maximum_download_response_bytes": archive["size"]
        + sum(item["size"] for item in model_assets),
        "maximum_archive_expanded_bytes": GIB,
        "minimum_host_free_bytes": 50 * GIB,
        "start_free_bytes": 55 * GIB,
        "pins": pins,
        "profiles": {k: str(v) for k, v in profiles.items()},
        "ports": {"gateway": PORT, "ollama": ENGINE_PORT},
        "max_cash_usd": "0",
        "maximum_additional_operations": operations,
        "maximum_reserved_seconds": seconds,
        "maximum_local_model_turns": 1,
        "maximum_remote_model_turns": 0,
        "stages": STAGES,
        "grant_absolute_limits": {
            "max_model_turns": baseline["state"][2] + 1,
            "max_operations": baseline["state"][1] + operations,
            "max_elapsed_seconds": max(
                baseline["effective_limits"]["max_elapsed_seconds"], baseline["state"][3] + seconds
            ),
            "max_cash_usd": "0",
        },
        "commands": {
            "waza_live": [
                str(waza),
                "--no-update-check",
                "run",
                str(public_spec),
                "--task",
                "receipt-total",
                "--trials",
                "1",
                "--no-cache",
                "--skip-graders",
                "--output",
                str(live / "run.json"),
            ],
            "waza_grade": [
                str(waza),
                "--no-update-check",
                "grade",
                str(grader_spec),
                "--task",
                "receipt-total",
                "--results",
                str(grader / "minimal-result.json"),
                "--workspace",
                str(grader),
                "--output",
                str(grader / "graded.json"),
            ],
            "serve": "one signed archive Ollama executable, argv [executable, serve]",
        },
        "retention": "Keep approved archive, runtime, model blobs, exact receipt hashes and minimized measurements. Remove only owned scratch after verified process stop.",
        "boundaries": [
            "Public HTTPS artifact acquisition before any third-party process. Download by exact byte size and SHA-256.",
            "Separate private homes and explicit environments. No credential paths, GitHub sign-in or provider tokens.",
            "Waza can connect only to the reviewed local gateway. Ollama can use loopback TCP for its child runners. Non-loopback traffic is denied. The grader has no network.",
            "One local completion request through a nonce-bound loopback gateway with explicit model, output limit, provider usage and reply-hash capture.",
            "Apple sandbox bind rules permit wildcard socket creation. The pinned Ollama command sets its API and child runner to literal loopback, and the driver inspects their actual listeners before accepting the inference.",
            "Protected grader and answer unavailable to Waza inference. The original offline text grader receives the one verified Waza reply.",
            "At most one setup attempt and one inference followed by at most one offline grade. No retry, fallback or alternative model.",
            "No Docker changes, global install, provider disclosure, paid usage, activation, comparison or release.",
        ],
    }
    return write(work / "operation-review.json", review)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    print(prepare(args.work.resolve()))
