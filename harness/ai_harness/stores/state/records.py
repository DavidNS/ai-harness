"""Artifact-backed state control record helpers."""

from __future__ import annotations

from typing import Protocol

from ...models import RunState, utc_now


class ControlArtifactStore(Protocol):
    def exists(self, name: str) -> bool: ...

    def read_json(self, name: str) -> object: ...

    def checksum(self, name: str) -> str: ...


def artifact_metadata(artifacts: ControlArtifactStore, name: str, phase: str) -> dict[str, str]:
    return {"path": name, "phase": phase, "checksum": artifacts.checksum(name), "timestamp": utc_now()}


def next_control_id(state: RunState, prefix: str, folder: str) -> str:
    used: set[str] = set()
    for name in state.artifacts:
        parts = name.split("/")
        if len(parts) >= 2 and parts[0] == folder:
            used.add(parts[1].split(".", 1)[0])
    index = 1
    while f"{prefix}{index}" in used:
        index += 1
    return f"{prefix}{index}"


def next_decision_id(state: RunState) -> str:
    return next_control_id(state, "D", "decisions")


def decision_history(state: RunState, artifacts: ControlArtifactStore) -> list[dict[str, object]]:
    decision_ids = sorted(
        {
            parts[1]
            for name in state.artifacts
            for parts in [name.split("/")]
            if len(parts) == 3 and parts[0] == "decisions"
        }
    )
    history: list[dict[str, object]] = []
    for decision_id in decision_ids:
        request_name = f"decisions/{decision_id}/request.json"
        if not artifacts.exists(request_name):
            continue
        item: dict[str, object] = {"decision_id": decision_id, "request": artifacts.read_json(request_name)}
        answer_name = f"decisions/{decision_id}/answer.json"
        if artifacts.exists(answer_name):
            item["answer"] = artifacts.read_json(answer_name)
        history.append(item)
    return history


def escalation_history(state: RunState, artifacts: ControlArtifactStore) -> list[dict[str, object]]:
    escalation_ids = sorted(
        {
            parts[1]
            for name in state.artifacts
            for parts in [name.split("/")]
            if len(parts) == 2 and parts[0] == "escalations" and parts[1].endswith(".json")
        }
    )
    history: list[dict[str, object]] = []
    for escalation_file in escalation_ids:
        name = f"escalations/{escalation_file}"
        if not artifacts.exists(name):
            continue
        history.append({"escalation_id": escalation_file[:-5], "escalation": artifacts.read_json(name)})
    return history
