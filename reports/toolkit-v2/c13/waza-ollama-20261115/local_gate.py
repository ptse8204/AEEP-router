"""Bound one local OpenAI-compatible request. Keep prompts and replies transient."""

import hashlib
import hmac
import json
import threading
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 49152
MAX_REPLY = 262144
MAX_OUTPUT_TOKENS = 128


def pack(value):
    return json.dumps(value, allow_nan=False, separators=(",", ":")).encode()


def read_usage(body, streaming, model):
    if streaming:
        rows = [
            line.removeprefix(b"data:").strip()
            for line in body.splitlines()
            if line.startswith(b"data:")
        ]
        if not rows or rows[-1] != b"[DONE]":
            raise ValueError("completion did not terminate")
        records = [json.loads(row) for row in rows[:-1]]
    else:
        records = [json.loads(body)]
    if any(row.get("model") != model for row in records):
        raise ValueError("local model identity changed")
    usage = [row["usage"] for row in records if row.get("usage") is not None]
    if len(usage) != 1 or not isinstance(usage[0], dict):
        raise ValueError("expected exactly one provider usage record")
    raw = usage[0]
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        if type(raw.get(key)) is not int or raw[key] < 1:
            raise ValueError("provider token usage unavailable")
    if raw["total_tokens"] != raw["prompt_tokens"] + raw["completion_tokens"]:
        raise ValueError("provider total token usage differs")
    if raw["completion_tokens"] > MAX_OUTPUT_TOKENS:
        raise ValueError("provider exceeded reviewed output limit")
    retained = {key: raw[key] for key in ("prompt_tokens", "completion_tokens", "total_tokens")}
    details = raw.get("prompt_tokens_details") or {}
    cached = details.get("cached_tokens")
    if cached is not None:
        if type(cached) is not int or not 0 <= cached <= raw["prompt_tokens"]:
            raise ValueError("provider cache token usage differs")
        retained["cached_prompt_tokens"] = cached
    return retained


def reply_digest(body, streaming):
    if streaming:
        records = [
            json.loads(fragment)
            for line in body.splitlines()
            if line.startswith(b"data:")
            if (fragment := line.removeprefix(b"data:").strip()) != b"[DONE]"
        ]
    else:
        records = [json.loads(body)]
    chunks = []
    stop = False
    for record in records:
        choices = record.get("choices") or []
        if len(choices) > 1:
            raise ValueError("unexpected completion alternatives")
        for choice in choices:
            message = choice["delta" if streaming else "message"]
            if message.get("tool_calls") or message.get("function_call"):
                raise ValueError("unreviewed tool activity")
            if (text := message.get("content")) is not None:
                if not isinstance(text, str):
                    raise ValueError("unreviewed response content")
                chunks.append(text)
            if choice.get("finish_reason") == "stop":
                stop = True
    reply = "".join(chunks).strip()
    if not stop or not reply or len(reply.encode()) > 4096:
        raise ValueError("bounded completion was not observed")
    return hashlib.sha256(reply.encode()).hexdigest()


def bounded_payload(payload, model, task_prompt):
    if not isinstance(payload, dict) or payload.get("model") != model:
        raise ValueError("unreviewed model")
    if payload.get("tools") or payload.get("functions") or payload.get("n", 1) != 1:
        raise ValueError("unreviewed tools or choice count")
    messages = payload["messages"]
    if not isinstance(messages, list) or not messages:
        raise ValueError("missing messages")
    users = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in {
            "system",
            "developer",
            "user",
        }:
            raise ValueError("unreviewed conversation role")
        content = message.get("content")
        if isinstance(content, list):
            if not all(
                isinstance(part, dict)
                and part.get("type") == "text"
                and isinstance(part.get("text"), str)
                for part in content
            ):
                raise ValueError("unreviewed attached data")
            content = "\n".join(part["text"] for part in content)
        if not isinstance(content, str):
            raise ValueError("unreviewed message content")
        if message["role"] == "user":
            users.append(content)
    if len(users) != 1 or task_prompt not in users[0]:
        raise ValueError("request does not bind the reviewed task")
    if type(payload.get("stream", False)) is not bool:
        raise ValueError("invalid stream flag")
    # Include only documented Ollama completion fields. Preserve message text.
    request = {
        "model": model,
        "messages": messages,
        "n": 1,
        "stream": payload.get("stream", False),
        "max_tokens": MAX_OUTPUT_TOKENS,
        "temperature": 0,
    }
    if request["stream"]:
        request["stream_options"] = {"include_usage": True}
    return request


class Gate(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, port, upstream, model, task_prompt, nonce):
        self.upstream, self.model, self.task_prompt = upstream, model, task_prompt
        self.authorization = "Bearer " + nonce
        self.lock = threading.Lock()
        self.forwarded = 0
        self.rejected = 0
        self.usage = None
        self.normalized_reply_sha256 = None
        super().__init__(("127.0.0.1", port), Handler)

    def facts(self):
        with self.lock:
            return {
                "forwarded": self.forwarded,
                "rejected": self.rejected,
                "usage": self.usage,
                "normalized_reply_sha256": self.normalized_reply_sha256,
            }


class Handler(BaseHTTPRequestHandler):
    def setup(self):
        self.request.settimeout(125)
        super().setup()

    def log_message(self, *_):
        pass

    def finish_request_bytes(self, status, data, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def deny(self, status=400):
        with self.server.lock:
            self.server.rejected += 1
        self.finish_request_bytes(
            status, pack({"error": {"message": "Local review rejected request"}})
        )

    def do_GET(self):
        if self.path != "/v1/models":
            self.deny(404)
            return
        self.finish_request_bytes(
            200,
            pack(
                {
                    "object": "list",
                    "data": [{"id": self.server.model, "object": "model", "owned_by": "ollama"}],
                }
            ),
        )

    def do_POST(self):
        if not hmac.compare_digest(
            self.headers.get("Authorization", "").encode(), self.server.authorization.encode()
        ):
            # Another local caller must not consume or contaminate this attempt.
            self.finish_request_bytes(401, pack({"error": {"message": "Local requester rejected"}}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.path != "/v1/chat/completions" or not 0 < length <= MAX_BODY:
                raise ValueError("unreviewed endpoint or request size")
            request = bounded_payload(
                json.loads(self.rfile.read(length)), self.server.model, self.server.task_prompt
            )
        except (ValueError, TypeError, KeyError):
            self.deny()
            return
        with self.server.lock:
            exceeded = self.server.forwarded != 0
            if not exceeded:
                self.server.forwarded = 1
        if exceeded:
            self.deny(429)
            return
        upstream = HTTPConnection("127.0.0.1", self.server.upstream, timeout=110)
        try:
            upstream.request("POST", self.path, pack(request), {"Content-Type": "application/json"})
            response = upstream.getresponse()
            body = response.read(MAX_REPLY + 1)
            if response.status != 200 or len(body) > MAX_REPLY:
                raise ValueError("local backend failed")
            observed = read_usage(body, request["stream"], self.server.model)
            reply_sha256 = reply_digest(body, request["stream"])
            with self.server.lock:
                self.server.usage = observed
                self.server.normalized_reply_sha256 = reply_sha256
            content_type = "text/event-stream" if request["stream"] else "application/json"
        except (OSError, ValueError, KeyError, TypeError):
            self.deny(502)
            return
        finally:
            upstream.close()
        self.finish_request_bytes(200, body, content_type)
