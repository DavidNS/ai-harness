"""JSON codec for daemon command, query, event, and result DTOs."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from harness_v2.backend.application.contracts import (
    CancelRun,
    CiTemplatesInstalled,
    Command,
    CommandExecutionResult,
    CommandResult,
    ErrorView,
    EscalationRaised,
    EscalationResolved,
    Event,
    GetAvailableActions,
    GetAvailableActionsResult,
    GetKnowledgePatch,
    GetKnowledgePatchResult,
    GetRun,
    GetRunResult,
    GetRunState,
    GetRunStateResult,
    InstallCiTemplates,
    InstallCiTemplatesResult,
    KnowledgePatchCreated,
    KnowledgePatchRejected,
    KnowledgePatchView,
    ListKnowledgePatches,
    ListKnowledgePatchesResult,
    ListRuns,
    ListRunsResult,
    PendingDecisionView,
    BundleCompleted,
    BundleFailed,
    BundleRetryStarted,
    BundleStarted,
    StepCompleted,
    StepFailed,
    StepStarted,
    Query,
    QueryResult,
    RejectKnowledgePatch,
    RejectKnowledgePatchResult,
    ResumeRun,
    RetryBundle,
    RetryStep,
    RunCancelled,
    RunCompleted,
    RunResumed,
    RunStarted,
    RunSummaryView,
    RunView,
    StartRun,
    SubmitUserDecision,
    TaskSummaryView,
    StepView,
    TestsFinished,
    TestsStarted,
    UserDecisionReceived,
    UserDecisionRequested,
)

_COMMAND_CLASSES = (StartRun, ResumeRun, RetryStep, RetryBundle, CancelRun, InstallCiTemplates, SubmitUserDecision, RejectKnowledgePatch)
_QUERY_CLASSES = (GetRun, ListRuns, GetRunState, GetAvailableActions, ListKnowledgePatches, GetKnowledgePatch)
_EVENT_CLASSES = (
    RunStarted,
    BundleStarted,
    BundleCompleted,
    BundleFailed,
    BundleRetryStarted,
    StepStarted,
    StepCompleted,
    StepFailed,
    KnowledgePatchCreated,
    KnowledgePatchRejected,
    TestsStarted,
    TestsFinished,
    EscalationRaised,
    EscalationResolved,
    UserDecisionRequested,
    UserDecisionReceived,
    RunResumed,
    RunCompleted,
    RunCancelled,
    CiTemplatesInstalled,
)
_RESULT_CLASSES = (
    CommandResult,
    GetRunResult,
    ListRunsResult,
    GetRunStateResult,
    GetAvailableActionsResult,
    GetKnowledgePatchResult,
    ListKnowledgePatchesResult,
    RejectKnowledgePatchResult,
    InstallCiTemplatesResult,
)
_VIEW_CLASSES = (PendingDecisionView, TaskSummaryView, StepView, ErrorView, RunView, RunSummaryView, KnowledgePatchView)

_TYPES = {cls.__name__: cls for cls in (*_COMMAND_CLASSES, *_QUERY_CLASSES, *_EVENT_CLASSES, *_RESULT_CLASSES, *_VIEW_CLASSES)}
_COMMAND_TYPES = {cls.__name__: cls for cls in _COMMAND_CLASSES}
_QUERY_TYPES = {cls.__name__: cls for cls in _QUERY_CLASSES}
_EVENT_TYPES = {cls.__name__: cls for cls in _EVENT_CLASSES}
_RESULT_TYPES = {cls.__name__: cls for cls in _RESULT_CLASSES}


class CodecError(ValueError):
    """Raised when a daemon JSON envelope cannot be decoded."""


def encode_envelope(value: object) -> dict[str, object]:
    if not is_dataclass(value):
        raise CodecError(f"cannot encode {type(value).__name__}")
    return {"type": type(value).__name__, "payload": _encode_payload(value)}


def decode_command(envelope: object) -> Command:
    return _decode_envelope(envelope, _COMMAND_TYPES)  # type: ignore[return-value]


def decode_query(envelope: object) -> Query:
    return _decode_envelope(envelope, _QUERY_TYPES)  # type: ignore[return-value]


def decode_result(envelope: object) -> CommandExecutionResult | QueryResult:
    return _decode_envelope(envelope, _RESULT_TYPES)  # type: ignore[return-value]


def decode_event(envelope: object) -> Event:
    return _decode_envelope(envelope, _EVENT_TYPES)  # type: ignore[return-value]


def _encode_payload(value: object) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field in fields(value):
        payload[field.name] = _encode_value(getattr(value, field.name))
    return payload


def _encode_value(value: object) -> object:
    if is_dataclass(value):
        return encode_envelope(value)
    if isinstance(value, tuple | list):
        return [_encode_value(item) for item in value]
    return value


def _decode_envelope(envelope: object, allowed: dict[str, type[object]]) -> object:
    if not isinstance(envelope, dict):
        raise CodecError("envelope must be an object")
    type_name = envelope.get("type")
    payload = envelope.get("payload")
    if not isinstance(type_name, str) or not type_name:
        raise CodecError("envelope.type is required")
    if type_name not in allowed:
        raise CodecError(f"unsupported type: {type_name}")
    if not isinstance(payload, dict):
        raise CodecError("envelope.payload must be an object")
    return _construct(allowed[type_name], payload)


def _construct(cls: type[object], payload: dict[str, object]) -> object:
    names = {field.name for field in fields(cls)}
    unexpected = sorted(set(payload) - names)
    if unexpected:
        raise CodecError(f"{cls.__name__} has unsupported fields: {', '.join(unexpected)}")
    values: dict[str, Any] = {}
    for field in fields(cls):
        if field.name in payload:
            values[field.name] = _decode_value(payload[field.name])
    try:
        return cls(**values)
    except (TypeError, ValueError) as exc:
        raise CodecError(str(exc)) from exc


def _decode_value(value: object) -> object:
    if isinstance(value, dict) and "type" in value and "payload" in value:
        return _decode_envelope(value, _TYPES)
    if isinstance(value, list):
        return tuple(_decode_value(item) for item in value)
    return value
