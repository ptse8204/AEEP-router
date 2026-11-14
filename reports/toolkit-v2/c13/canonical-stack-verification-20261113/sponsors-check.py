"""Actual offline Sponsors checks with the preserved public funding declaration."""

import contextlib
import hashlib
import io
import json
import sys
import tempfile
from pathlib import Path

PUBLISHER = "DietrichGebert"
URL = f"https://github.com/sponsors/{PUBLISHER}"
REVISION = "1d95ff7d39de12d87014ea40d4e22201bddc501b"


def evaluate(arguments):
    from aeep_toolkit.cli import main

    rendered = io.StringIO()
    with contextlib.redirect_stdout(rendered), contextlib.redirect_stderr(io.StringIO()):
        try:
            code = main(arguments)
        except SystemExit as stopped:
            return stopped.code, None
    return code, json.loads(rendered.getvalue())["document"]


def run(check, source, source_revision, public_files):
    with tempfile.TemporaryDirectory() as staging:
        root = Path(staging).resolve()
        for name, value in public_files.items():
            assert name in {"no-observations.json", "sponsors-review.json", "FUNDING.yml"}
            (root / name).write_bytes(bytes.fromhex(value))
        digest = hashlib.sha256((root / "sponsors-review.json").read_bytes()).hexdigest()
        args = ["export-preview", "--evidence", str(root / "no-observations.json"),
                "--sponsors-review", str(root / "sponsors-review.json"), "--reviewed-digest", digest]
        code, document = evaluate([*args, "--disclose-source"])
        assert code == 0 and document
        assertion = document["developer"]["assertion"]
        assert document["developer"]["status"] == "reviewed_source_declaration"
        assert document["outcome"] == "NOT_ASSESSED" and not document["publication_performed"]
        assert assertion["assertion_ref"] == digest and assertion["identity"] == PUBLISHER
        assert assertion["source"]["revision"] == REVISION and assertion["support_url"] == URL
        observed = {"component": "github-sponsors", "check": check, "implementation_source": source,
                    "source_revision": source_revision, "mode": "upstream_functional"}
        if check == "source_attribution":
            (root / "FUNDING.yml").write_text("github: OtherPublicAccount\n")
            assert evaluate([*args, "--disclose-source"])[0] == 2
            return observed | {"funding_drift_rejected": True, "funding_source_revision": REVISION}
        if check != "authorized_link":
            raise ValueError("unknown check")
        assert evaluate(args)[0] == 2
        assert evaluate([*args[:-1], "0" * 64, "--disclose-source"])[0] == 2
        return observed | {"explicit_source_disclosure_required": True, "support_url": URL}


if __name__ == "__main__":
    sys.path.insert(0, sys.argv[2])
    print(json.dumps(run(*json.loads(sys.argv[1]))))
