"""Bounded local Codex metrics relay; positive observations never prove completeness.

This stdlib-only module is also copied into the immutable worker image. It sends
sanitized snapshots over the existing stdio transport, never raw OTLP payloads.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import TCPServer
from typing import Any

NOTIFICATION = 'aeep/catalogMetrics'
WORKER_PATH = '/opt/aeep/codex_metrics.py'
MAX_BODY = 1_048_576
MAX_BATCHES = 128
MAX_POINTS = 256
NAMES = {'codex.skill.injected', 'codex.thread.skills.enabled_total',
         'codex.thread.skills.kept_total', 'codex.thread.skills.truncated'}


def strict_json(data: bytes) -> Any:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate key')
            result[key] = value
        return result

    def invalid(_value: str) -> None:
        raise ValueError('nonfinite value')
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def snapshot(scope: str) -> dict[str, Any]:
    return {'schema_version': 'codex.catalog-metrics.v1', 'scope': scope,
            'batches': 0, 'rejected_batches': 0, 'overflow': False,
            'collector_closed': False, 'delivery_complete': False, 'observations': []}


def validate_snapshot(value: Any, scope: str) -> dict[str, Any]:
    """Validate the worker envelope again at the coordinator trust boundary."""
    if (not isinstance(value, dict) or set(value) != set(snapshot(scope))
            or value['schema_version'] != 'codex.catalog-metrics.v1' or value['scope'] != scope
            or value['delivery_complete'] is not False
            or any(type(value[k]) is not bool for k in ('overflow', 'collector_closed'))
            or any(type(value[k]) is not int or not 0 <= value[k] <= MAX_BATCHES for k in ('batches', 'rejected_batches'))
            or not isinstance(value['observations'], list) or len(value['observations']) > MAX_POINTS):
        raise ValueError('invalid catalog metrics snapshot')
    allowed = {'name', 'skill_digest', 'status', 'invoke_type', 'catalog_surface', 'value', 'count'}
    for point in value['observations']:
        if not isinstance(point, dict) or set(point) - allowed or point.get('name') not in NAMES:
            raise ValueError('invalid catalog metric')
        if (set(point) & {'value', 'count'} != {'value', 'count'}
                or type(point['count']) is not int or not 1 <= point['count'] <= 1_000_000
                or type(point['value']) not in (int, float) or not 0 <= point['value'] <= 1_000_000):
            raise ValueError('invalid catalog metric measurement')
        if point['name'] == 'codex.skill.injected':
            if (set(point) != {'name', 'skill_digest', 'status', 'invoke_type', 'value', 'count'}
                    or not isinstance(point['skill_digest'], str) or not re.fullmatch('[a-f0-9]{64}', point['skill_digest'])
                    or point['status'] not in ('ok', 'error') or point['invoke_type'] not in ('explicit', 'implicit', 'unknown')):
                raise ValueError('invalid skill injection observation')
        elif set(point) != {'name', 'catalog_surface', 'value', 'count'} or point['catalog_surface'] not in ('host_world_state', 'thread_context'):
            raise ValueError('invalid catalog surface')
    return value


class Metrics:
    def __init__(self, scope: str) -> None:
        if not re.fullmatch(r'aeep-metrics-[a-f0-9]{32}', scope):
            raise ValueError('invalid metric scope')
        self.value = snapshot(scope)
        self.bytes_received = 0

    def accept(self, body: bytes) -> None:
        self.bytes_received += len(body)
        if len(body) > MAX_BODY or self.bytes_received > 8 * MAX_BODY or self.value['batches'] >= MAX_BATCHES:
            self.value['overflow'] = True
            raise ValueError('catalog metrics bound exceeded')
        data = strict_json(body)
        points = []
        for resource in data['resourceMetrics']:
            for scope in resource['scopeMetrics']:
                for metric in scope['metrics']:
                    if metric.get('name') not in NAMES:
                        continue
                    for kind in ('sum', 'histogram', 'gauge'):
                        for point in metric.get(kind, {}).get('dataPoints', []):
                            attributes = {}
                            for attribute in point.get('attributes', []):
                                key = attribute['key']
                                if key in attributes:
                                    raise ValueError('duplicate metric attribute')
                                attributes[key] = attribute['value'].get('stringValue')
                            if attributes.get('service_name') != self.value['scope']:
                                continue
                            raw_count = point.get('count', 1)
                            if type(raw_count) not in (int, str) or not re.fullmatch(r'[0-9]{1,7}', str(raw_count)):
                                raise ValueError('invalid metric count')
                            count = int(raw_count)
                            number = point.get('sum') if kind == 'histogram' else point.get('asInt', point.get('asDouble'))
                            if type(number) is str and re.fullmatch(r'[0-9]{1,7}', number):
                                number = int(number)
                            safe = {'name': metric['name'], 'value': number, 'count': count}
                            if metric['name'] == 'codex.skill.injected':
                                skill = attributes.get('skill')
                                if not isinstance(skill, str) or not 0 < len(skill.encode()) <= 512:
                                    raise ValueError('invalid skill identity')
                                safe.update(skill_digest=hashlib.sha256(skill.encode()).hexdigest(),
                                    status=attributes.get('status'), invoke_type=attributes.get('invoke_type', 'unknown'))
                            else:
                                safe['catalog_surface'] = attributes.get('catalog_surface')
                            check = snapshot(self.value['scope'])
                            check['observations'] = [safe]
                            validate_snapshot(check, self.value['scope'])
                            if safe not in points and safe not in self.value['observations']:
                                points.append(safe)
                            if len(points) + len(self.value['observations']) > MAX_POINTS:
                                self.value['overflow'] = True
                                raise ValueError('too many catalog observations')
        self.value['observations'].extend(points)
        self.value['batches'] += 1


def relay(argv: list[str], scope: str) -> int:
    """Supervise one fresh host and export only the bounded, content-free snapshot."""
    if not hasattr(os, "killpg") or not hasattr(signal, "SIGKILL"):
        raise ValueError("catalog metrics relay requires a POSIX host")
    killpg, sigkill = os.killpg, signal.SIGKILL
    metrics = Metrics(scope)
    output_lock = threading.Lock()

    def emit() -> None:
        wire = json.dumps({'method': NOTIFICATION, 'params': metrics.value}, allow_nan=False).encode() + b'\n'
        with output_lock:
            sys.stdout.buffer.write(wire)
            sys.stdout.buffer.flush()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format: str, *args: Any) -> None:
            pass

        def setup(self) -> None:
            super().setup()
            self.connection.settimeout(2)

        def do_POST(self) -> None:
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if (self.path != '/v1/metrics' or len(lengths) != 1 or not lengths[0].isascii()
                        or not lengths[0].isdigit() or not 0 < int(lengths[0]) <= MAX_BODY
                        or self.headers.get('Transfer-Encoding') is not None
                        or self.headers.get('Content-Encoding') is not None
                        or self.headers.get_content_type() != 'application/json'):
                    raise ValueError('invalid metric request')
                body = self.rfile.read(int(lengths[0]))
                if len(body) != int(lengths[0]):
                    raise ValueError('incomplete metric request')
                metrics.accept(body)
                emit()
            except (ValueError, TypeError, KeyError, AttributeError, RecursionError, OSError):
                metrics.value['rejected_batches'] = min(MAX_BATCHES, metrics.value['rejected_batches'] + 1)
                self.send_error(400, 'invalid metrics')
                return
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{}')

    class LoopbackServer(HTTPServer):
        def server_bind(self) -> None:
            # This collector uses a literal loopback address; reverse DNS is unnecessary
            # and can block startup on hosts without a working resolver.
            TCPServer.server_bind(self)
            self.server_name = 'localhost'
            self.server_port = self.server_address[1]

    server = LoopbackServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .05}, daemon=True)
    thread.start()
    endpoint = f'http://127.0.0.1:{server.server_port}/v1/metrics'
    options = ['analytics.enabled=true', 'otel.exporter="none"', 'otel.trace_exporter="none"',
               'otel.log_user_prompt=false', 'otel.metrics_exporter={otlp-http={endpoint=' + json.dumps(endpoint) + ',protocol="json"}}']
    process = None
    try:
        # The immutable worker config is already in argv and cannot override
        # these final telemetry settings. Task input remains on the original pipe.
        command = [*argv, *(part for option in options for part in ('-c', option))]
        environment = dict(os.environ, NO_PROXY='127.0.0.1', OTEL_METRIC_EXPORT_INTERVAL='1000', OTEL_METRIC_EXPORT_TIMEOUT='1000')
        process = subprocess.Popen(command, stdin=sys.stdin.buffer, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                   env=environment, start_new_session=True)
        def stop(_signum: int, _frame: Any) -> None:
            if process is not None and process.poll() is None:
                killpg(process.pid, signal.SIGTERM)
        signal.signal(signal.SIGTERM, stop)
        signal.signal(signal.SIGINT, stop)
        assert process.stdout is not None
        while line := process.stdout.readline(16_777_217):
            if len(line) > 16_777_216 or not line.endswith(b'\n'):
                raise ValueError('oversized host frame')
            message = strict_json(line)
            if not isinstance(message, dict) or message.get('method') == NOTIFICATION:
                raise ValueError('invalid host frame')
            with output_lock:
                sys.stdout.buffer.write(line)
                sys.stdout.buffer.flush()
        code = process.wait()
    finally:
        if process is not None and process.poll() is None:
            killpg(process.pid, sigkill)
            process.wait()
        server.shutdown()
        thread.join(timeout=3)
        server.server_close()
        metrics.value['collector_closed'] = True
        emit()
    return code if code >= 0 else 128 - code
