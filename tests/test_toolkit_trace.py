"""OTLP serialization of synthetic receipts, with no exporter or destination."""
import json
import socket
import subprocess
from datetime import UTC, datetime, timedelta

import pytest

from aeep.models import ExecutionReceipt
from aeep.telemetry import receipt_otlp_preview
from aeep_toolkit.cli import main


def receipt():
    start = datetime(2026, 1, 1, 0, 0, 0, 123456, tzinfo=UTC)
    return ExecutionReceipt(decision_id='PRIVATE_DECISION', action_id='PRIVATE_ACTION', capability='private.capability',
        executor_id='PRIVATE_EXECUTOR', executor_kind='command', status='success', started_at=start,
        ended_at=start+timedelta(microseconds=3), execution_success=True, estimated={},
        actual_resources={'latency_ms': 0.003}, metadata={'input': 'PRIVATE_PROMPT', 'secret': 'PRIVATE_KEY'})


def test_preview_minimizes_attributes_preserves_unknowns_and_exact_times(tmp_path, monkeypatch, capsys):
    record = receipt()
    def forbidden(*args, **kwargs):
        pytest.fail('trace preview attempted export or execution')
    monkeypatch.setattr(socket.socket, 'connect', forbidden)
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    result = receipt_otlp_preview(record)
    span = result['payload']['resourceSpans'][0]['scopeSpans'][0]['spans'][0]
    assert int(span['endTimeUnixNano'])-int(span['startTimeUnixNano']) == 3000
    attrs = {a['key']: a['value'] for a in span['attributes']}
    assert attrs['aeep.evidence.trust']['stringValue'] == 'supplied_unverified'
    assert attrs['aeep.resource.local.latency_ms']['doubleValue'] == 0.003
    assert 'aeep.resource.tokens' not in attrs
    assert 'PRIVATE_' not in json.dumps(result) and 'private.capability' not in json.dumps(result)
    assert result['export_performed'] is False and result['destination'] is None
    path = tmp_path/'receipt.json'
    path.write_text(record.model_dump_json())
    assert main(['trace-preview', '--receipt', str(path)]) == 0
    assert json.loads(capsys.readouterr().out) == result
    assert list(tmp_path.iterdir()) == [path]


def test_trace_rejects_naive_or_reversed_timestamps():
    for start, end in [(datetime(2026, 1, 1), datetime(2026, 1, 2)),
                       (datetime(2026, 1, 2, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))]:
        with pytest.raises(ValueError):
            receipt_otlp_preview(receipt().model_copy(update={'started_at': start, 'ended_at': end}))
