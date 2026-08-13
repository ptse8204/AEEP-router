from __future__ import annotations

import json
import sys

from .tools import text_stats


def main() -> None:
    text = sys.argv[1] if len(sys.argv) > 1 else sys.stdin.read()
    print(json.dumps(text_stats(text), separators=(",", ":")))


if __name__ == "__main__":
    main()
