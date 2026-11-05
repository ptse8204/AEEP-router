"""Bounded, one-origin Maven Central acquisition for the private resolver."""
import http.server
import json
import re
import socket
import threading
import urllib.error
import urllib.request

ORIGIN = 'https://repo.maven.apache.org'
MAX_FILE = 24 * 1024**2
MAX_TOTAL = 128 * 1024**2
MAX_REQUESTS = 1600
PATH = re.compile(r'/maven2/(?:[A-Za-z0-9_][A-Za-z0-9_.+-]*/)+[A-Za-z0-9_][A-Za-z0-9_.+-]*')
LOCK = threading.Lock()
COUNTS = {'requests': 0, 'fetched_bytes': 0}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('unexpected Maven Central redirect')


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.serve_artifact()

    def do_HEAD(self):
        self.serve_artifact()

    def serve_artifact(self):
        if self.client_address[0] != '172.30.249.3' or not PATH.fullmatch(self.path):
            self.send_error(403)
            return
        if 'SNAPSHOT' in self.path or any(x in ('.', '..') for x in self.path.split('/')):
            self.send_error(403)
            return
        with LOCK:
            if COUNTS['requests'] >= MAX_REQUESTS or COUNTS['fetched_bytes'] >= MAX_TOTAL:
                print(json.dumps({'limit': 'review_ceiling', **COUNTS}), flush=True)
                self.send_error(429)
                return
            COUNTS['requests'] += 1
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        try:
            request = urllib.request.Request(ORIGIN+self.path, method=self.command)
            with opener.open(request, timeout=20) as response:
                raw = response.read(MAX_FILE + 1) if self.command == 'GET' else b''
                length = int(response.headers.get('Content-Length', len(raw)))
            if len(raw) > MAX_FILE or length > MAX_FILE:
                self.send_error(413)
                return
            with LOCK:
                if COUNTS['fetched_bytes'] + len(raw) > MAX_TOTAL:
                    print(json.dumps({'limit': 'review_bytes', **COUNTS}), flush=True)
                    self.send_error(429)
                    return
                COUNTS['fetched_bytes'] += len(raw)
            self.send_response(200)
            self.send_header('Content-Length', str(length))
            self.end_headers()
            if self.command == 'GET':
                self.wfile.write(raw)
        except urllib.error.HTTPError as error:
            if error.code == 429:
                print(json.dumps({'limit': 'upstream_429', **COUNTS}), flush=True)
            self.send_error(error.code if error.code in (404, 429) else 502)
        except (ValueError, OSError):
            self.send_error(502)

    def log_message(self, format, *args):
        return


class Server(http.server.ThreadingHTTPServer):
    daemon_threads = True


with Server(('172.30.249.2', 8765), Handler) as server:
    print(json.dumps({'ready': True, 'registry': ORIGIN, 'maximum_bytes': MAX_TOTAL}), flush=True)
    server.serve_forever()
