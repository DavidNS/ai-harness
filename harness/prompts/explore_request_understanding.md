# Explore Request Understanding Phase Prompt v1

Use only the supplied required inputs and the `explore_request_understanding.json` capability manifest.

Return JSON only with this shape:
{
  "schema_version": 1,
  "phase": "explore_request_understanding",
  "intent": "feature_or_bug_or_refactor",
  "summary": "One sentence summary of what the user asks for.",
  "mentioned_surfaces": ["paths, APIs, phases, workflows, or systems named by the request"],
  "explicit_constraints": ["constraints stated by the user"],
  "unclear_parts": [],
  "request_type": "bug|feature|refactor|documentation|research|product_idea|cleanup|typo|unknown"
}

Avoid repository analysis beyond making the request understandable enough for triage. Do not choose an implementation approach.
