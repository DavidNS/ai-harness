# Explorer Decision Phase Prompt v1

Use only the supplied required inputs, including any none-of-above refinement context, and the `explorer_decision.json` capability manifest.

Return either a decision_request control JSON when a product decision is required, or JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explorer_decision",
  "outcome": "new_improvement",
  "rationale": "Evidence-backed reason.",
  "evidence": ["concrete evidence reference"],
  "selected_direction": "D1",
  "value_hypothesis": "Why this direction should produce useful downstream value.",
  "behavioral_delta": "Concrete behavior, gate, route, review, or user workflow that changes.",
  "rejected_alternatives": [
    {"id": "D2", "reason": "Lower impact or weaker evidence."}
  ],
  "counterevidence": ["Evidence that weakens the chosen direction, or none found."],
  "falsifying_conditions": ["Condition that would make this decision wrong."],
  "minimum_verification": "Smallest verification that proves the behavioral delta exists.",
  "target": {"path": "docs/explorer/improvements/example/improvement.md", "checksum": "..."}
}
Outcome must be one of new_improvement, split_bundle, update_existing, duplicate_noop, existing_functionality, limitation, not_worth_it, needs_user_decision, escalate_discovery. Do not ask factual questions discovery can answer.

The value fields are optional for backward compatibility with existing staged documents. Include them whenever discovery produced candidate directions or critic findings. Metadata-only or prose-only decisions are acceptable only when they feed an explicit downstream behavior, gate, route, review, or user workflow. Use `not_worth_it`, `limitation`, `duplicate_noop`, `update_existing`, or `existing_functionality` when the value case is weaker than an existing or lower-cost route.

Return only the required artifact or permitted control JSON. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
