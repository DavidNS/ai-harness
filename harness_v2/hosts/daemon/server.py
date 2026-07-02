"""HTTP daemon host for the v2 backend contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from harness_v2.backend.application.contracts import InvalidRunStateError, RunNotFoundError
from harness_v2.hosts.daemon.codec import CodecError, decode_command, decode_query, encode_envelope
from harness_v2.hosts.daemon.event_log import DaemonEventLog
from harness_v2.hosts.in_process.host import InProcessHost


@dataclass(frozen=True, slots=True)
class DaemonConfig:
    state_root: Path
    working_directory: Path | None = None
    allow_repository_mutation: bool = False
    branch_mode: str = "current"
    github_ci_mode: str = "baseline"
    host: str = "127.0.0.1"
    port: int = 8765


class DaemonApplication:
    def __init__(self, config: DaemonConfig) -> None:
        self.events = DaemonEventLog()
        self.host = InProcessHost(
            state_root=config.state_root,
            event_sink=self.events,
            working_directory=config.working_directory,
            allow_repository_mutation=config.allow_repository_mutation,
            branch_mode=config.branch_mode,
            github_ci_mode=config.github_ci_mode,
        )

    def execute_payload(self, payload: object) -> dict[str, object]:
        result = self.host.execute(decode_command(payload))
        return {"ok": True, "result": encode_envelope(result)}

    def query_payload(self, payload: object) -> dict[str, object]:
        result = self.host.query(decode_query(payload))
        return {"ok": True, "result": encode_envelope(result)}

    def event_payloads_after(self, event_id: int, *, timeout: float) -> list[dict[str, object]]:
        return [
            {"id": logged.event_id, **encode_envelope(logged.event)}
            for logged in self.events.events_after(event_id, timeout=timeout)
        ]


class DaemonHttpServer(ThreadingHTTPServer):
    def __init__(self, config: DaemonConfig) -> None:
        self.app = DaemonApplication(config)
        super().__init__((config.host, config.port), _handler(self.app))


def serve(config: DaemonConfig) -> None:
    server = DaemonHttpServer(config)
    try:
        server.serve_forever()
    finally:
        server.server_close()


def _handler(app: DaemonApplication) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "AIHarnessV2Daemon/0.1"

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/health":
                self._send_json(HTTPStatus.OK, {"status": "ok"})
                return
            if parsed.path == "/v1/events":
                params = parse_qs(parsed.query)
                try:
                    after = _int_param(params, "after", 0)
                    timeout = _float_param(params, "timeout", 0.0)
                except ValueError as exc:
                    self._send_error(HTTPStatus.BAD_REQUEST, "BadRequest", str(exc))
                    return
                events = app.event_payloads_after(after, timeout=min(max(timeout, 0.0), 30.0))
                self._send_ndjson(HTTPStatus.OK, events)
                return
            self._send_error(HTTPStatus.NOT_FOUND, "NotFound", "unknown endpoint")

        def do_POST(self) -> None:
            parsed = urlparse(self.path)
            try:
                payload = self._read_json()
                if parsed.path == "/v1/commands":
                    self._send_json(HTTPStatus.OK, app.execute_payload(payload))
                    return
                if parsed.path == "/v1/queries":
                    self._send_json(HTTPStatus.OK, app.query_payload(payload))
                    return
                self._send_error(HTTPStatus.NOT_FOUND, "NotFound", "unknown endpoint")
            except CodecError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "BadRequest", str(exc))
            except RunNotFoundError as exc:
                self._send_error(HTTPStatus.NOT_FOUND, "RunNotFoundError", str(exc))
            except InvalidRunStateError as exc:
                self._send_error(HTTPStatus.CONFLICT, "InvalidRunStateError", str(exc))
            except ValueError as exc:
                self._send_error(HTTPStatus.BAD_REQUEST, "BadRequest", str(exc))

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _read_json(self) -> object:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("invalid Content-Length") from exc
            if length <= 0:
                raise ValueError("request body is required")
            body = self.rfile.read(length)
            try:
                return json.loads(body.decode("utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("request body must be JSON") from exc

        def _send_json(self, status: HTTPStatus, payload: dict[str, object]) -> None:
            content = (json.dumps(payload, sort_keys=True) + "\n").encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_ndjson(self, status: HTTPStatus, payloads: list[dict[str, object]]) -> None:
            content = "".join(json.dumps(payload, sort_keys=True) + "\n" for payload in payloads).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _send_error(self, status: HTTPStatus, error_type: str, message: str) -> None:
            self._send_json(status, {"ok": False, "error": {"type": error_type, "message": message}})

    return Handler


def _int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    values = params.get(name)
    if not values:
        return default
    return int(values[0])


def _float_param(params: dict[str, list[str]], name: str, default: float) -> float:
    values = params.get(name)
    if not values:
        return default
    return float(values[0])
