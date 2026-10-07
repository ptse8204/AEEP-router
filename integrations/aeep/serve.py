"""Start the operator-installed runtime; never install packages during MCP startup."""

import os
import sys
from pathlib import Path


def main() -> None:
    runtime = Path.home() / ".local/share/aeep/venv/bin/python"
    manifest = Path.home() / ".config/aeep/config.yaml"
    if not runtime.is_file() or not manifest.is_file():
        sys.exit("AEEP setup is incomplete. Follow README.md: Install in Codex.")
    args = [str(runtime), "-m", "aeep", "serve", "--transport", "stdio",
            "--profile", "legacy", "--manifest", str(manifest)]
    discovery = manifest.parent / "discovery.json"
    if discovery.is_file():
        args.extend(["--discovery-config", str(discovery)])
    os.execv(str(runtime), args)


if __name__ == "__main__":
    main()
