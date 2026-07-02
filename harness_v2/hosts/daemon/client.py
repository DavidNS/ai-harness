"""HTTP client for the v2 daemon host contract."""

from __future__ import annotations

import json
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from harness_v2.backend.application.contracts import (
    Command,
    CommandExecutionResult,
    InvalidRunStateError,
    Query,
    QueryResult,
    RunNotFoundError,
)
from harness_v2.hosts.daemon.codec import decode_event, decode_result, encode_envelope


class DaemonClientError(RuntimeError):
    pass


class DaemonClient:
    def __init__(self, base_url: str = "http://127.0.0.1:8765", *, timeout: float = 30.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout

    def execute(self, command: Command) -> CommandExecutionResult:
        response = self._post("/v1/commands", encode_envelope(command))
        result = response.get("result")
        return decode_result(result)  # type: ignore[return-value]

    def query(self, query: Query) -> QueryResult:
        response = self._post("/v1/queries", encode_envelope(query))
        result = response.get("result")
        return decode_result(result)  # type: ignore[return-value]

    def events_after(self, event_id: int, *, timeout: float = 0.0) -> tuple[tuple[int, object], ...]:
        query = urlencode({"after": event_id, "timeout": timeout})
        with urlopen(f"{self._base_url}/v1/events?{query}", timeout=self._timeout) as response:
            content = response.read().decode("utf-8")
        events = []
        for line in content.splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            event_id_value = payload.pop("id")
            events.append((int(event_id_value), decode_event(payload)))
        return tuple(events)

    def _post(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        request = Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self._timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as decode_exc:
                raise DaemonClientError(str(exc)) from decode_exc
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else str(exc)
            error_type = error.get("type") if isinstance(error, dict) else ""
            if error_type == "RunNotFoundError":
                raise RunNotFoundError(str(message)) from exc
            if error_type == "InvalidRunStateError":
                raise InvalidRunStateError(str(message)) from exc
            if error_type == "BadRequest":
                raise ValueError(str(message)) from exc
            raise DaemonClientError(str(message)) from exc
        response_payload = json.loads(raw)
        if not isinstance(response_payload, dict) or response_payload.get("ok") is not True:
            raise DaemonClientError("daemon returned an invalid response")
        return response_payload
