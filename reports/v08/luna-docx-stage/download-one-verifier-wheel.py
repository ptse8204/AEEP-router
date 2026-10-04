"""Single-wheel downloader; parent enforces a hard subprocess timeout."""
from __future__ import annotations

import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def main() -> None:
    if len(sys.argv) != 5:
        raise RuntimeError("expected pinned URL, destination, byte limit, and SHA-256")
    url, destination_arg, size_arg, expected_sha = sys.argv[1:]
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "files.pythonhosted.org":
        raise RuntimeError("wheel URL outside pinned PyPI host")
    destination = Path(destination_arg).resolve()
    if destination.parent.name != "wheels" or len(expected_sha) != 64 or not expected_sha.isascii():
        raise RuntimeError("destination or digest is outside the fixed wheel stage")
    expected_size = int(size_arg)
    digest = hashlib.sha256()
    size = 0
    opener = urllib.request.build_opener(NoRedirect())
    with opener.open(url, timeout=2) as response, destination.open("xb") as target:
        final = urllib.parse.urlparse(response.geturl())
        if final.scheme != "https" or final.hostname != "files.pythonhosted.org":
            raise RuntimeError("wheel redirected outside pinned PyPI host")
        while chunk := response.read(16 * 1024):
            size += len(chunk)
            if size > expected_size:
                raise RuntimeError("wheel exceeded pinned size; preserve partial file")
            target.write(chunk)
            digest.update(chunk)
    if size != expected_size or digest.hexdigest() != expected_sha:
        raise RuntimeError("wheel byte count or SHA-256 mismatch; preserve partial file")
    print(json.dumps({"filename": destination.name, "bytes": size, "sha256": digest.hexdigest()}))


if __name__ == "__main__":
    main()
