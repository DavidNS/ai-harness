# Explore Clarification Gate Phase Prompt v1

Use only the supplied required inputs and the `explore_clarification_gate.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_clarification_gate",
  "status": "continue",
  "clarification_questions": [],
  "rationale": "Why EXPLORE can or cannot plan evidence collection."
}

Use `needs_clarification` only when the request is too vague to decide what evidence to collect. Do not ask approach, tradeoff, or product-direction questions here.
