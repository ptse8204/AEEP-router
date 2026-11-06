"""Carry only the reviewed local Langfuse health, export and trace readback."""

from __future__ import annotations

import base64
import binascii
import hmac
import json
import re
import subprocess
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from urllib.parse import urlencode

HEALTH = '/api/public/health'
EXPORT = '/api/public/otel/v1/traces'
OBSERVATIONS = '/api/public/v2/observations'
REQUEST_LIMIT = 65536
REPLY_LIMIT = 65536

# Node uses direct loopback HTTP in the selected container. Stdin is transient.
NODE = r"""
const http = require('node:http');
const fs = require('node:fs');
const value = JSON.parse(fs.readFileSync(0, 'utf8'));
const data = Buffer.from(value.body, 'base64');
const headers = {accept:'application/json'};
if (value.authorization) headers.authorization = value.authorization;
if (value.method === 'POST') {
  headers['content-length'] = String(data.length);
  headers['content-type'] = 'application/json';
  headers['x-langfuse-ingestion-version'] = '4';
}
const request = http.request({hostname:'127.0.0.1', port:3000, path:value.path,
  method:value.method, headers, timeout:3000, agent:false}, reply => {
  const chunks = [];
  let size = 0;
  reply.on('data', chunk => {
    size += chunk.length;
    if (size > 65536) reply.destroy(new Error('size'));
    else chunks.push(chunk);
  });
  reply.on('end', () => process.stdout.write(JSON.stringify({
    status:reply.statusCode, body:Buffer.concat(chunks).toString('base64')
  })));
  reply.on('error', () => {process.exitCode = 1;});
});
request.on('timeout', () => request.destroy());
request.on('error', () => {process.exitCode = 1;});
request.end(data);
"""


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def observations(trace):
    if not re.fullmatch('[0-9a-f]{32}', trace):
        raise ValueError('Trace identity must be exact')
    return OBSERVATIONS + '?' + urlencode({
        'traceId': trace, 'fields': 'core,metadata', 'expandMetadata': 'attributes', 'limit': 10,
    })


def docker_transport(argv, container_id, env):
    if not re.fullmatch('[0-9a-f]{64}', container_id):
        raise ValueError('Immutable container ID required')
    fixed = [*argv, 'exec', '-i', container_id, 'node', '-e', NODE]

    def send(method, path, authorization, body):
        message = json.dumps({'method': method, 'path': path, 'authorization': authorization,
                              'body': base64.b64encode(body).decode('ascii')}).encode()
        finished = subprocess.run(fixed, input=message, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, timeout=4, env=env, check=True)
        if len(finished.stdout) > 90_000:
            raise ValueError('Container reply exceeds the carrier envelope')
        value = json.loads(finished.stdout)
        result = base64.b64decode(value['body'], validate=True)
        status = value['status']
        if type(status) is not int or not 200 <= status <= 599 or len(result) > REPLY_LIMIT:
            raise ValueError('Invalid container reply')
        return status, result
    return send


class Scope:
    def __init__(self, send):
        self.send = send
        self.authorization = None
        self.expected = None
        self.readback = None
        self.post_dispatched = False
        self.counts = {'health': 0, 'export': 0, 'readback': 0}

    def permit(self, authorization, payload, trace):
        if self.expected is not None or self.post_dispatched or not authorization.startswith('Basic '):
            raise ValueError('The exact receipt scope can be bound once')
        self.authorization = authorization
        self.expected = canonical(payload)
        self.readback = observations(trace)

    def route(self, method, path, headers, body):
        authorization = headers.get('Authorization', '')
        authenticated = self.authorization is not None and hmac.compare_digest(authorization.encode('utf-8'), self.authorization.encode('utf-8'))
        if method == 'GET' and path == HEALTH and not authorization and not body:
            label, limit = 'health', 20
        elif method == 'POST' and path == EXPORT and authenticated and not self.post_dispatched:
            if (headers.get('Content-Type') != 'application/json'
                    or headers.get('x-langfuse-ingestion-version') != '4'
                    or canonical(json.loads(body)) != self.expected):
                return 403, b'{}'
            body = self.expected
            self.post_dispatched = True
            label, limit = 'export', 1
        elif method == 'GET' and path == self.readback and authenticated and self.post_dispatched and not body:
            label, limit = 'readback', 8
        else:
            return 403, b'{}'
        if self.counts[label] >= limit:
            return 429, b'{}'
        self.counts[label] += 1
        status, reply = self.send(method, path, authorization, body)
        # Do not relay redirect headers or redirects to any other endpoint.
        return (status, reply) if not 300 <= status < 400 else (502, b'{}')


@contextmanager
def listen(port, scope):
    class Handler(BaseHTTPRequestHandler):
        def setup(self):
            super().setup()
            self.connection.settimeout(3)

        def serve(self):
            try:
                lengths = self.headers.get_all('Content-Length', [])
                if (self.headers.get('Transfer-Encoding') is not None or len(lengths) > 1
                        or len(self.headers.get_all('Authorization', [])) > 1):
                    raise ValueError('Unsupported request framing')
                size = int(lengths[0]) if lengths else 0
                if not 0 <= size <= REQUEST_LIMIT or (self.command == 'GET' and size):
                    raise ValueError('Request exceeds the carrier envelope')
                body = self.rfile.read(size)
                if len(body) != size:
                    raise ValueError('Incomplete request')
                status, reply = scope.route(self.command, self.path, self.headers, body)
            except (OSError, subprocess.SubprocessError, ValueError, KeyError, binascii.Error):
                status, reply = 502, b'{}'
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        do_GET = serve
        do_POST = serve

        def log_message(self, _format, *_args):
            pass

    with HTTPServer(('127.0.0.1', port), Handler) as server:
        thread = Thread(target=server.serve_forever, kwargs={'poll_interval': 0.1}, daemon=True)
        thread.start()
        try:
            yield server.server_address[1]
        finally:
            server.shutdown()
            thread.join()
