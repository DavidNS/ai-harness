"""ExplorerDecisionReader — read-only queries over explorer decision state.

Single responsibility: answer questions about the current explorer run's decision
history and decision artifact without triggering side effects.

Previously the decision-query cluster on ExplorerFlowMixin.
"""
from __future__ import annotations

from ..phases import get_phase
from ..stores.artifact import ArtifactStore
from ..stores.state import StateStore


class ExplorerDecisionReader:
    """Read-only queries over explorer decision history and artifact.

    Cheap to instantiate — all methods are pure reads with no side effects.
    """

    def __init__(self, state: StateStore, artifacts: ArtifactStore) -> None:
        self._state = state
        self._artifacts = artifacts
        self._decision_artifact = get_phase("explorer_decision").artifact

    def none_of_above_count(self) -> int:
        """Count how many times the user chose 'none of the above' in EXPLORER_DECISION."""
        count = 0
        for item in self._state.decision_history():
            request = item.get("request")
            answer = item.get("answer")
            if not isinstance(request, dict) or request.get("origin_phase") != "EXPLORER_DECISION":
                continue
            if not isinstance(answer, dict):
                continue
            if answer.get("selected_option") == "none_of_above":
                count += 1
        return count

    def refinement_escalation_count(self) -> int:
        """Count EXPLORER_DECISION → EXPLORER_DISCOVERY escalations for none_of_above."""
        count = 0
        for name in self._artifacts.list():
            if not name.startswith("escalations/") or not name.endswith(".json"):
                continue
            try:
                payload = self._artifacts.read_json(name)
            except Exception:
                continue
            if (
                payload.get("origin_phase") == "EXPLORER_DECISION"
                and payload.get("target_phase") == "EXPLORER_DISCOVERY"
                and "none_of_above" in str(payload.get("reason", ""))
            ):
                count += 1
        return count

    def latest_none_of_above_refinement(self) -> dict[str, object]:
        """Return the most recent none_of_above decision refinement, or an empty dict."""
        for item in reversed(self._state.decision_history()):
            request = item.get("request")
            answer = item.get("answer")
            if not isinstance(request, dict) or request.get("origin_phase") != "EXPLORER_DECISION":
                continue
            if not isinstance(answer, dict) or answer.get("selected_option") != "none_of_above":
                continue
            return {
                "selected_option": "none_of_above",
                "answer": str(answer.get("answer", "")).strip(),
                "decision_id": item.get("decision_id"),
                "request_context": request.get("context", []),
                "options": request.get("options", []),
            }
        return {}

    def decision_outcome(self) -> str:
        """Return the outcome field from the explorer_decision artifact, or ''."""
        try:
            return str(self._artifacts.read_json(self._decision_artifact).get("outcome", ""))
        except Exception:
            return ""

    def split_bundle_rationale(self) -> str | None:
        """Return the rationale if outcome is split_bundle, else None."""
        try:
            decision = self._artifacts.read_json(self._decision_artifact)
        except Exception:
            return None
        if str(decision.get("outcome", "")) != "split_bundle":
            return None
        rationale = str(decision.get("rationale", "")).strip()
        return rationale or None
