"""In-memory daemon event log fed through the backend event sink port."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Condition
from time import monotonic

from harness_v2.backend.application.contracts import Event
from harness_v2.backend.ports.event_sink import EventSinkPort


@dataclass(frozen=True, slots=True)
class LoggedEvent:
    event_id: int
    event: Event


class DaemonEventLog(EventSinkPort):
    def __init__(self) -> None:
        self._condition = Condition()
        self._events: list[LoggedEvent] = []
        self._next_id = 1

    def emit(self, event: object) -> None:
        with self._condition:
            logged = LoggedEvent(self._next_id, event)  # type: ignore[arg-type]
            self._next_id += 1
            self._events.append(logged)
            self._condition.notify_all()

    def events_after(self, event_id: int, *, timeout: float = 0.0) -> tuple[LoggedEvent, ...]:
        deadline = monotonic() + max(0.0, timeout)
        with self._condition:
            while True:
                events = tuple(event for event in self._events if event.event_id > event_id)
                if events or timeout <= 0:
                    return events
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return ()
                self._condition.wait(remaining)
