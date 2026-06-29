"""Controller-mediated mutating actions with durable idempotency."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from .capabilities import CapabilityError, CapabilityPolicy


class ActionExecutor(Protocol):
    def __call__(self, server: str, tool: str, arguments: Mapping[str, object]) -> Mapping[str, object]: ...


PostconditionVerifier = Callable[[str, Mapping[str, object], Mapping[str, object]], bool]


@dataclass(frozen=True, slots=True)
class ActionRequest:
    server: str
    tool: str
    arguments: Mapping[str, object]
    idempotency_key: str
    postconditions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.server or not self.tool:
            raise CapabilityError("action server and tool are required")
        if not self.idempotency_key or len(self.idempotency_key) > 200:
            raise CapabilityError("a bounded idempotency key is required")


@dataclass(frozen=True, slots=True)
class ActionEvidence:
    server: str
    tool: str
    idempotency_key: str
    result: Mapping[str, object]
    postconditions: tuple[str, ...]
    replayed: bool = False


class ActionMediator:
    """Execute declared mutations once and persist only verified successes."""

    def __init__(
        self,
        policy: CapabilityPolicy,
        evidence_directory: Path,
        executor: ActionExecutor,
        verifier: PostconditionVerifier,
    ) -> None:
        self.policy = policy
        self.directory = Path(evidence_directory).resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.executor = executor
        self.verifier = verifier

    def execute(self, request: ActionRequest) -> ActionEvidence:
        self.policy.authorize_tool(request.server, request.tool, "mutate", request.arguments)
        undeclared = set(request.postconditions) - set(self.policy.manifest.postconditions)
        if undeclared:
            raise CapabilityError(f"undeclared postconditions: {sorted(undeclared)}")
        if set(request.postconditions) != set(self.policy.manifest.postconditions):
            raise CapabilityError("all declared postconditions are required")

        fingerprint = self._fingerprint(request)
        path = self.directory / f"{hashlib.sha256(request.idempotency_key.encode()).hexdigest()}.json"
        if path.exists():
            stored = json.loads(path.read_text(encoding="utf-8"))
            if stored.get("fingerprint") != fingerprint:
                raise CapabilityError("idempotency key was reused for a different action")
            return ActionEvidence(
                request.server,
                request.tool,
                request.idempotency_key,
                stored["result"],
                tuple(stored["postconditions"]),
                replayed=True,
            )

        result = self.executor(request.server, request.tool, request.arguments)
        if not isinstance(result, Mapping):
            raise CapabilityError("action executor must return an object")
        for condition in request.postconditions:
            if not self.verifier(condition, request.arguments, result):
                raise CapabilityError(f"action postcondition failed: {condition}")

        payload = {
            "schema_version": 1,
            "fingerprint": fingerprint,
            "server": request.server,
            "tool": request.tool,
            "idempotency_key": request.idempotency_key,
            "arguments": dict(request.arguments),
            "result": dict(result),
            "postconditions": list(request.postconditions),
        }
        self._atomic_json(path, payload)
        return ActionEvidence(
            request.server, request.tool, request.idempotency_key, dict(result), request.postconditions
        )

    @staticmethod
    def _fingerprint(request: ActionRequest) -> str:
        value = json.dumps(
            {"server": request.server, "tool": request.tool, "arguments": request.arguments},
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        return hashlib.sha256(value).hexdigest()

    @staticmethod
    def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
        data = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
