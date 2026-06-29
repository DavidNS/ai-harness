# Explore Phase Prompt v1

Use only the supplied required inputs and the `explore.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "kind": "explore_outcome_bundle",
  "status": "ready_for_purpose",
  "normalized_request": {"summary": "User request summary."},
  "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
  "evidence": [],
  "entries": [
    {"id": "entry-1", "classification": "improvement", "title": "Bounded title", "problem": "Problem PURPOSE must handle.", "evidence_refs": [], "constraints": [], "unknowns": []}
  ]
}

EXPLORE classifies evidence for PURPOSE. Do not choose implementation approaches, architecture, tasks, or code changes.
