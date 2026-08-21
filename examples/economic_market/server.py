"""Run the local-only AEEP economic evidence reference service."""

from __future__ import annotations

import argparse
import os

from aeep.market_server import ReferenceMarket, create_app, reference_executor_spec


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--token-env", default="AEEP_REFERENCE_MARKET_TOKEN")
    parser.add_argument(
        "--unsafe-allow-unauthenticated-evidence",
        action="store_true",
        help="test-only: allow unauthenticated usage/reconciliation ingestion",
    )
    args = parser.parse_args()
    token = os.getenv(args.token_env)
    if args.host not in {"127.0.0.1", "localhost", "::1"} and not token:
        parser.error(f"non-loopback binding requires a bearer token in {args.token_env}")
    try:
        import uvicorn
    except ImportError as exc:
        parser.error("install the http-server optional dependency")
        raise AssertionError("unreachable") from exc
    display_host = f"[{args.host}]" if ":" in args.host else args.host
    executor_spec = reference_executor_spec(
        base_url=f"http://{display_host}:{args.port}",
        auth_token_env=args.token_env if token else None,
    )
    uvicorn.run(
        create_app(
            ReferenceMarket(executor_spec=executor_spec),
            bearer_token=token,
            allow_unauthenticated_evidence=args.unsafe_allow_unauthenticated_evidence,
        ),
        host=args.host,
        port=args.port,
        log_level="info",
    )


if __name__ == "__main__":
    main()
