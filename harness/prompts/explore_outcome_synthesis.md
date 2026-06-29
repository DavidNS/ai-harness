# Explore Outcome Synthesis Phase Prompt v1

Use only the supplied required inputs and the `explore_outcome_synthesis.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "kind": "explore_outcome_bundle",
  "status": "ready_for_purpose",
  "normalized_request": {"summary": "User request summary."},
  "triage": {"complexity": "local_change", "ambiguity": "clear", "risk": "low", "evidence_depth": "standard"},
  "evidence": [],
  "exploration_map": {
    "schema_version": 1,
    "kind": "exploration_map",
    "surfaces": [],
    "behaviors": [],
    "constraints": [],
    "risks": [],
    "unknowns": [],
    "candidate_work_shapes": [],
    "verification_surfaces": [],
    "handoff_notes": {"purpose": [], "design": [], "tasks": []}
  },
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
If clarification_gate.status is needs_clarification, return status needs_clarification, include clarification_questions, and entries must be empty.
If ci_barrier has required unavailable CI evidence or evidence_collection has operational blockers, return problem_gathering_info with operational_blockers.
Otherwise classify each coherent request part as improvement, limitation, or bullshit.
Preserve or refine the supplied exploration_map as a decision-neutral evidence map. It may name candidate work shapes, verification surfaces, risks, constraints, and unknowns, but it must not choose an implementation approach or declare refactoring, security work, performance work, or any other work type as required.
