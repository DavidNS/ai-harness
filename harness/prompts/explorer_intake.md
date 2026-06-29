# Explorer Intake Phase Prompt v1

Use only the supplied required inputs and the `explorer_intake.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explorer_intake",
  "strategic_framing": {
    "mode": "specific",
    "value_targets": ["artifact quality"],
    "needs_user_direction": false,
    "rationale": "The request names a bounded implementation surface."
  },
  "claims": [
    {"id": "C1", "class": "repository-factual", "text": "Claim to resolve.", "evidence_targets": ["tests", "source"]}
  ],
  "synthesis_notes": []
}
`strategic_framing` is optional for backward compatibility. Include it when the request is vague, strategic, or needs value framing before normal viability checks. Use `mode` `specific` for bounded artifact/bug/surface requests, `strategic` for broad improvement requests with clear value targets, and `needs_user_direction` when the value target is not clear enough to choose a direction. Value targets should name user-visible or controller-visible outcomes such as artifact quality, fewer unnecessary pauses, stronger duplicate detection, less prompt obedience, better implementation readiness, or stronger evidence.

Claim class must be one of repository-factual, duplicate-check, product-tradeoff, artifact-synthesis.

Return only the required artifact or permitted control JSON. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
