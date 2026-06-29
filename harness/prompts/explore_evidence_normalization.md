# Explore Evidence Normalization Phase Prompt v1

Use only the supplied required inputs and the `explore_evidence_normalization.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_evidence_normalization",
  "evidence": [
    {
      "id": "E1",
      "claim": "Normalized evidence claim.",
      "status": "supported",
      "confidence": "high",
      "sources": [{"type": "file", "path": "relative/path.py", "description": "Source reference"}]
    }
  ]
}

Carry operational blockers as blocked evidence only when they are facts PURPOSE must see. Do not make implementation recommendations.
