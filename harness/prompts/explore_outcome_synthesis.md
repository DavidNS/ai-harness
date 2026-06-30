# Explore Outcome Synthesis Phase Prompt v1

Use only the supplied required inputs and the `explore_outcome_synthesis.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "kind": "explore_outcome_synthesis",
  "status": "ready_for_purpose",
  "normalized_request": {"summary": "User request summary."},
  "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
  "entries": [
    {
      "id": "entry-1",
      "classification": "improvement",
      "title": "Bounded title",
      "problem": "Problem or request part PURPOSE must handle.",
      "evidence_refs": [],
      "constraints": [],
      "unknowns": []
    }
  ]
}

Allowed bundle statuses: ready_for_purpose, needs_clarification, problem_gathering_info. Allowed classifications: improvement, limitation, bullshit.
Do not include `evidence` or `exploration_map`; the controller owns those structures and will inject them into the final `explore_outcome_bundle`.
Use only evidence IDs supplied in `evidence` when filling `entries[].evidence_refs`. If uncertain, leave `evidence_refs` empty; the controller will repair missing refs.
If request_profile.ambiguity is blocked_by_product_decision or the request cannot be bounded, return status needs_clarification, include clarification_questions, and entries must be empty.
If supplied inputs describe operational blockers, return problem_gathering_info with operational_blockers.
Otherwise classify each coherent request part as improvement, limitation, or bullshit.
