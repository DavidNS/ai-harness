# Explore Delta Phase Prompt v1

Use only supplied inputs and the `explore_delta.json` capability manifest.

Return JSON only:
{
  "schema_version": 1,
  "kind": "explore_delta_bundle",
  "request_id": "ER1",
  "questions_answered": ["Question from evidence_request."],
  "evidence": [
    {
      "id": "D1",
      "kind": "code",
      "claim": "Additional fact requested by a later phase.",
      "status": "supported",
      "confidence": "high",
      "severity": "info",
      "sources": [{"type": "file", "path": "relative/path.py", "description": "Why this source matters"}]
    }
  ]
}

Use blocked evidence when the requested fact cannot be gathered from supplied context.
