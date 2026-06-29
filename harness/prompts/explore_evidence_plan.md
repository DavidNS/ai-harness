# Explore Evidence Plan Phase Prompt v1

Use only the supplied required inputs and the `explore_evidence_plan.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_evidence_plan",
  "required_gatherers": ["code", "knowledge"],
  "optional_gatherers": ["git"],
  "ci_requirement": "optional",
  "questions": ["Which repository evidence supports or rejects the request?"],
  "skip_reason": {"web": "No external API or current external fact is required."}
}

Allowed gatherers: code, git, gitlab, web, knowledge, ci. Use ci_requirement `required` only when baseline CI facts can materially change PURPOSE behavior. Prefer optional unless the request is explicitly about CI, tests, quality evidence, coverage, dependencies, security, or architecture risk.
