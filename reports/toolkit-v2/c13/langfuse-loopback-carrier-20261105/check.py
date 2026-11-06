"""Exercise first-party relay rules using synthetic requests and no Docker."""

import http.client
import json

from relay import EXPORT, HEALTH, Scope, listen, observations


def verify():
    auth = 'Basic synthetic-only'
    trace = 'a' * 32
    exact = {'resourceSpans': [{'synthetic': True}]}
    requests = []

    def fake(method, path, authorization, body):
        requests.append((method, path, authorization, body))
        return (200, b'{}')

    scope = Scope(fake)
    with listen(0, scope) as port:
        def call(method, path, value=None, token=None, **overrides):
            headers = {'Content-Type': 'application/json', 'x-langfuse-ingestion-version': '4'}
            if token is not None:
                headers['Authorization'] = token
            headers.update(overrides)
            client = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
            try:
                client.request(method, path, body=json.dumps(value) if value is not None else None,
                               headers=headers)
                reply = client.getresponse()
                reply.read()
                return reply.status
            finally:
                client.close()

        assert call('GET', HEALTH) == 200
        assert call('GET', HEALTH, token=auth) == 403
        assert call('GET', '/api/public/../../') == 403
        assert call('GET', 'http://localhost' + HEALTH) == 403
        assert call('POST', EXPORT, exact, auth) == 403
        scope.permit(auth, exact, trace)
        assert call('GET', observations(trace), token=auth) == 403
        assert call('POST', EXPORT, exact, 'Basic wrong') == 403
        assert call('POST', EXPORT, {'prompt': 'forbidden'}, auth) == 403
        assert call('POST', EXPORT, exact, auth, **{'Transfer-Encoding': 'chunked'}) == 502
        assert call('POST', EXPORT, exact, auth) == 200
        assert call('POST', EXPORT, exact, auth) == 403
        assert call('GET', observations('b' * 32), token=auth) == 403
        assert call('GET', observations(trace), token=auth) == 200
        assert len(requests) == 3
    print(json.dumps({'synthetic_only': True, 'controls_passed': 13, 'forwarded': scope.counts,
                      'docker_started': False, 'ingestion_verified': False}))


if __name__ == '__main__':
    verify()
