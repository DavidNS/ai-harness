# Explore Request Profile Phase Prompt v1

Use only supplied inputs and the `explore_request_profile.json` capability manifest.

Return JSON only:
{
  "schema_version": 1,
  "phase": "explore_request_profile",
  "summary": "Short user request summary.",
  "request_type": "feature|bug|refactor|documentation|cleanup|typo|research|unknown",
  "complexity": "local_change",
  "ambiguity": "clear",
  "risk": "low",
  "evidence_depth": "standard",
  "request_parts": ["Bounded request part."],
  "constraints": ["Explicit user constraint."],
  "evidence_questions": ["Question EXPLORE evidence must answer."],
  "gatherers": ["code", "knowledge", "ci"],
  "clarification_questions": []
}

Allowed complexity: typo, local_change, multi_file, cross_cutting, architecture, migration.
Allowed ambiguity: clear, partial, high, blocked_by_product_decision.
Allowed risk: low, medium, high, critical.
Allowed evidence_depth: light, standard, deep.
Allowed gatherers: code, git, gitlab, knowledge, ci. Do not use web in this iteration; if external facts would be required, include an evidence question and leave it to downstream blocked evidence.
