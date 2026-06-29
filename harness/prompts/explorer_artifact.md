# Explorer Artifact Phase Prompt v1

Use only the supplied required inputs and the `explorer_artifact.json` capability manifest.

Return exactly one artifact candidate using one of these accepted envelopes:
- Compact improvement Markdown starting with `# Improvement: <title>` and containing exactly one each of `## Status`, `## Problem`, `## Evidence`, `## Desired Behavior`, `## Implementation Notes`, and `## Acceptance Criteria`.
- `# Limitation v1` Markdown.
- `# Existing Functionality v1` Markdown.
- Legacy `# Improvement Analysis v1` Markdown for compatibility.
- `explorer_bundle` JSON.
Do not use a plain descriptive heading such as `# Slash Command Autocomplete`; for a new improvement, use `# Improvement: Slash Command Autocomplete`. The artifact must follow the decision outcome and must not choose a different outcome. If repair is supplied, revise only the rejected artifact issue.

When the decision includes value fields, preserve the selected direction, value hypothesis, behavioral delta, rejected alternatives, counterevidence or falsifying conditions, and minimum verification in the artifact content where the artifact shape allows it. Do not resurrect a direction rejected by discovery critic findings or decision rationale.

Return only the required artifact or permitted control JSON. Do not wrap it in a code fence. Do not claim controller execution, persistence, publication, phase completion, or permission escalation.
