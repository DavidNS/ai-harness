# Explore Triage Phase Prompt v1

Use only the supplied required inputs and the `explore_triage.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_triage",
  "complexity": "local_change",
  "ambiguity": "clear",
  "novelty": "known_repo_pattern",
  "risk": "low",
  "evidence_depth": "standard",
  "rationale": "Why this depth is enough."
}

Allowed complexity values: typo, local_change, multi_file, cross_cutting, architecture, migration.
Allowed ambiguity values: clear, partial, high, blocked_by_product_decision.
Allowed novelty values: known_repo_pattern, low, medium, high, uncertain_feasibility.
Allowed risk values: low, medium, high, critical. Evidence depth: light, standard, deep.
