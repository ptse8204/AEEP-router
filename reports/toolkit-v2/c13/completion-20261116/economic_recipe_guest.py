"""Adapter from the ordinary contained grader envelope to the protected verifier."""

import base64
import binascii
import hashlib
import json
import os
import sys
import tempfile
from decimal import Decimal
from pathlib import Path


def packet_digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def grade(request, binding, verifier, observe):
    if (
        not isinstance(request, dict)
        or set(request) != {"examples"}
        or not isinstance(request["examples"], list)
        or len(request["examples"]) != 1
    ):
        raise ValueError("expected one reviewed case")
    example = request["examples"][0]
    if (
        not isinstance(example, dict)
        or set(example) != {"input", "output", "expected"}
        or packet_digest(example["input"]) != binding["input_digest"]
        or example["expected"] != {"task_archive_sha256": binding["archive_sha256"]}
    ):
        raise ValueError("protected grader input changed")
    output = example["output"]
    invalid = {"valid": [False], "failure_codes": ["output_contract"]}
    if not isinstance(output, dict) or set(output) != {"answer_b64"}:
        return invalid
    encoded = output["answer_b64"]
    if type(encoded) is not str or len(encoded) > 172:
        return invalid
    try:
        answer = base64.b64decode(encoded, validate=True)
        answer.decode("ascii")
    except (ValueError, binascii.Error):
        return invalid
    if not 0 < len(answer) <= 128:
        return invalid
    result = observe(verifier, answer, Decimal(binding["expected"]))
    if result["protocol_verified"] is not True:
        raise ValueError("protected verifier did not complete all reviewed assertions")
    valid = result["protected_grade"] == 1
    if valid:
        code = None
    elif result["upstream_valid"]:
        code = "precision_rejected"
    else:
        code = "upstream_rejected"
    return {"valid": [valid], "failure_codes": [code]}


def dispatch(binding, verifier_bytes, observe):
    if (
        (os.geteuid(), os.getegid()) != (65534, 65534)
        or sys.version_info[:3] != (3, 13, 15)
        or os.path.exists("/root/answer.txt")
        or hashlib.sha256(verifier_bytes).hexdigest() != binding["verifier_sha256"]
    ):
        raise ValueError("protected economic runtime or verifier changed")
    with tempfile.TemporaryDirectory(prefix="economic-verifier-", dir="/tmp") as scratch:
        verifier = Path(scratch) / "upstream_test.py"
        verifier.write_bytes(verifier_bytes)
        print(json.dumps(grade(json.loads(sys.stdin.buffer.read(750_001)), binding, verifier, observe)))
