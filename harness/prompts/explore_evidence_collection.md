# Explore Evidence Collection Phase Prompt v1

Use only the supplied required inputs and the `explore_evidence_collection.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_evidence_collection",
  "evidence": [
    {
      "id": "R1",
      "claim": "Concrete fact supported or rejected by repository/knowledge evidence.",
      "status": "supported",
      "confidence": "high",
      "sources": [{"type": "file", "path": "relative/path.py", "description": "Why this source matters"}]
    }
  ],
  "blockers": []
}

Allowed evidence statuses: supported, contradicted, partially_supported, unresolved, not_applicable, blocked. Use blockers only for operational failures collecting planned evidence.
Collect evidence that helps later phases understand what exists before deciding what to do: relevant implementation/test/documentation/CI surfaces, observed behaviors, hard constraints, risk signals, unresolved unknowns, and likely verification surfaces. Keep claims factual and repository-backed; do not recommend a solution.
