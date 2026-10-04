"""Stage the exact pinned upstream verifier and fixed public literal input."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
CONTEXT = OUT / "upstream-verifier-context"
VERIFIER = CONTEXT / "verifier"
INPUT = CONTEXT / "input"
PIN = "9a1f4dd5f7659f75707435da3ce854b6e48321d1"
RAW = f"https://raw.githubusercontent.com/benchflow-ai/skillsbench/{PIN}/"
FIXTURE = ROOT / "integrations/assessment-runtime/skillsbench-offer-letter-fixtures.json"
EMPLOYEE = ROOT / "reports/v08/skillsbench-offer-letter-pinned/employee_data.json"
EXPECTED = {
    "fixture_sha256": "f856e8ec8c7c79cebdbc55f590ac14016ee77b2c2462abe2f2d08988aa2494d4",
    "artifact_sha256": "e5ba556c1b7ef19620b8b3963710714218d0eb21b61ec0ba4964a35be60c42c7",
    "artifact_bytes": 39173,
    "employee_sha256": "64dcb6aad2423051a638efefc85d1b47d306718e462342281553bf00082870c0",
    "employee_bytes": 774,
    "verifier_sha256": "913b9a3ebe579aed9c8f876dededea4d6a957eca9fbd0d9e8f043719cfb8cf05",
    "verifier_bytes": 4397,
    "license_sha256": "c71d239df91726fc519c6eb72d318ec65820627232b2f796219e87dcf35d0ab4",
    "license_bytes": 11357,
}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def bounded_get(url: str, maximum: int) -> bytes:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "raw.githubusercontent.com":
        raise RuntimeError("source URL is outside the pinned GitHub raw host")
    with urllib.request.urlopen(url, timeout=15) as response:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "raw.githubusercontent.com":
            raise RuntimeError("source redirected outside the pinned GitHub raw host")
        content = response.read(maximum + 1)
    if len(content) > maximum:
        raise RuntimeError("pinned source exceeded its byte limit")
    return content


def put_exact(path: Path, content: bytes, mode: int) -> None:
    with path.open("xb") as stream:
        stream.write(content)
    os.chmod(path, mode)


def main() -> None:
    if CONTEXT.exists():
        raise RuntimeError("preserving prior verifier staging; no overwrite or replay")
    fixture_bytes = FIXTURE.read_bytes()
    employee_bytes = EMPLOYEE.read_bytes()
    if sha(fixture_bytes) != EXPECTED["fixture_sha256"]:
        raise RuntimeError("fixed fixture source digest mismatch")
    if sha(employee_bytes) != EXPECTED["employee_sha256"] or len(employee_bytes) != EXPECTED["employee_bytes"]:
        raise RuntimeError("pinned employee-data digest mismatch")
    fixture = json.loads(fixture_bytes)
    selected = fixture["fixtures"][0]
    if selected.get("variation") != "relocation_yes":
        raise RuntimeError("fixed public literal fixture index changed")
    artifact = base64.b64decode(selected["document_b64"], validate=True)
    if len(artifact) != EXPECTED["artifact_bytes"] or sha(artifact) != EXPECTED["artifact_sha256"]:
        raise RuntimeError("fixed public literal artifact digest mismatch")
    if json.loads(fixture["employee_data_json"]) != json.loads(employee_bytes):
        raise RuntimeError("pinned employee data differs from fixed fixture")

    verifier = bounded_get(RAW + "tasks/offer-letter-generator/verifier/test_outputs.py", 16_384)
    license_text = bounded_get(RAW + "LICENSE", 20_000)
    if len(verifier) != EXPECTED["verifier_bytes"] or sha(verifier) != EXPECTED["verifier_sha256"]:
        raise RuntimeError("upstream verifier pin mismatch")
    if len(license_text) != EXPECTED["license_bytes"] or sha(license_text) != EXPECTED["license_sha256"]:
        raise RuntimeError("upstream repository license pin mismatch")

    VERIFIER.mkdir(parents=True, mode=0o755)
    INPUT.mkdir(mode=0o755)
    put_exact(VERIFIER / "test_outputs.py", verifier, 0o444)
    put_exact(VERIFIER / "LICENSE", license_text, 0o444)
    put_exact(INPUT / "offer_letter_filled.docx", artifact, 0o444)
    put_exact(INPUT / "employee_data.json", employee_bytes, 0o444)
    os.chmod(VERIFIER, 0o555)
    os.chmod(INPUT, 0o555)
    os.chmod(CONTEXT, 0o555)
    manifest = {
        "schema_version": "assessment.skillsbench-docx-verifier-stage.v1",
        "status": "staged_readonly_no_execution",
        "upstream": {
            "repository": "benchflow-ai/skillsbench",
            "commit": PIN,
            "verifier_path": "tasks/offer-letter-generator/verifier/test_outputs.py",
            "verifier_sha256": sha(verifier),
            "license": "Apache-2.0",
            "license_path": "LICENSE",
            "license_sha256": sha(license_text),
        },
        "fixture": {
            "source": "integrations/assessment-runtime/skillsbench-offer-letter-fixtures.json",
            "source_sha256": sha(fixture_bytes),
            "index": 0,
            "variation": "relocation_yes",
            "artifact_bytes": len(artifact),
            "artifact_sha256": sha(artifact),
            "employee_data_bytes": len(employee_bytes),
            "employee_data_sha256": sha(employee_bytes),
        },
        "staged_paths": {
            "verifier_dir": str(VERIFIER),
            "input_dir": str(INPUT),
        },
        "mode": "directories 0555; files 0444",
        "container_execution": False,
        "assessment_grant_mutation": False,
        "model_or_authentication_access": False,
    }
    manifest_path = OUT / "upstream-verifier-stage.json"
    with manifest_path.open("x", encoding="utf-8") as stream:
        json.dump(manifest, stream, indent=2)
        stream.write("\n")
    print(json.dumps({
        "status": manifest["status"],
        "verifier_sha256": sha(verifier),
        "license_sha256": sha(license_text),
        "artifact_sha256": sha(artifact),
        "employee_data_sha256": sha(employee_bytes),
        "manifest_sha256": sha(manifest_path.read_bytes()),
    }))


if __name__ == "__main__":
    main()
