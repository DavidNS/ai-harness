from __future__ import annotations

import json
from typing import Any


def _normalize_option(selected_option: str) -> str:
    return {
        "analysis": "explorer",
        "easy_implementation": "sdd_low",
        "full_implementation": "sdd_high",
    }.get(selected_option, selected_option)


def _answer(run_id: str, decision_id: str, selected_option: str, request: str, orchestrator: Any):
    selected_option = _normalize_option(selected_option)
    return orchestrator.run(
        request,
        resume_run_id=run_id,
        decision_answer=json.dumps({
            "schema_version": 1,
            "kind": "decision_answer",
            "decision_id": decision_id,
            "answer": f"Use {selected_option}.",
            "selected_option": selected_option,
        }),
    )


def run_with_flow(orchestrator: Any, request: str, selected_option: str):
    waiting = orchestrator.run(request)
    if waiting.outcome != "waiting_for_user":
        raise AssertionError(f"expected flow selection, got {waiting.outcome}")
    assert waiting.control is not None
    current_request = waiting.control["request"]
    if current_request.get("origin_phase") == "ROUTING":
        waiting = _answer(waiting.run_id, waiting.control["decision_id"], "code", request, orchestrator)
        if waiting.outcome != "waiting_for_user":
            raise AssertionError(f"expected flow selection, got {waiting.outcome}")
        assert waiting.control is not None
        current_request = waiting.control["request"]
    if current_request.get("origin_phase") != "SELECTING_STRATEGY":
        raise AssertionError(f"expected flow decision, got {current_request.get('origin_phase')}")
    return _answer(waiting.run_id, waiting.control["decision_id"], selected_option, request, orchestrator)


def run_with_route(orchestrator: Any, request: str, selected_option: str):
    waiting = orchestrator.run(request)
    if waiting.outcome != "waiting_for_user":
        if selected_option == "non_code" and waiting.outcome == "non-code stub":
            return waiting
        raise AssertionError(f"expected routing selection, got {waiting.outcome}")
    assert waiting.control is not None
    route_request = waiting.control["request"]
    if route_request.get("origin_phase") != "ROUTING":
        raise AssertionError(f"expected routing decision, got {route_request.get('origin_phase')}")
    return _answer(waiting.run_id, waiting.control["decision_id"], selected_option, request, orchestrator)
