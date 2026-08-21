"""Run the deterministic quote, execution, usage, and reconciliation loop."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

import httpx

from aeep.market_server import example_quote_request


def main() -> None:
    token = os.getenv("AEEP_REFERENCE_MARKET_TOKEN")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    text = "x" * 14_336
    request = example_quote_request(now=datetime.now(UTC), input_bytes=len(text.encode()))
    with httpx.Client(base_url="http://127.0.0.1:8787", headers=headers, timeout=5) as client:
        quote = _json(client.post("/v1/quotes", content=request.model_dump_json()))
        execution = _json(
            client.post(
                "/v1/execute",
                json={
                    "quote_id": quote["quote_id"],
                    "prepared_id": "prepared-reference-1",
                    "action_id": request.action_id,
                    "attempt_id": "attempt-reference-1",
                    "text": text,
                },
            )
        )
        usage = execution["usage_statement"]
        reconciliation = _json(
            client.post(
                "/v1/reconciliations",
                json={
                    "settlement_id": "settlement-reference-1",
                    "usage_statement_id": usage["usage_statement_id"],
                    "billed_amount": usage["provider_calculated_amount"],
                    "task_valid": True,
                    "billing_record_reference": "local-demo-record-1",
                },
            )
        )
    print(
        {
            "expected": quote["expected_amount"],
            "maximum": quote["maximum_amount"],
            "actual": usage["provider_calculated_amount"],
            "reconciliation": reconciliation["status"],
            "output": execution["output"],
        }
    )


def _json(response: httpx.Response) -> dict[str, Any]:
    response.raise_for_status()
    data = response.json()
    if not isinstance(data, dict):
        raise ValueError("reference service returned a non-object response")
    return data


if __name__ == "__main__":
    main()
