# Design Phase Prompt v1

Use only the supplied required inputs and the `design.json` capability manifest. Inputs include `explore_bundle_view` and `purpose/bundle.json`.
When `explorer_scope` is supplied, treat it as bounded implementation input data. Preserve each source artifact boundary; for multiple artifacts, do not collapse the scope into one vague feature. Shared infrastructure is allowed only when the relevant source artifacts remain explicit.
If controller inputs include a non-empty `repair` object, use it only to repair the artifact contract problem named by the controller while preserving the original bounded inputs.

Produce exactly one output, choosing one of:

- the normal `design.md` candidate matching the Markdown contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

Use `explore_bundle_view` as evidence input. If it includes `exploration_map`, use its surfaces, behaviors, constraints, risks, unknowns, candidate_work_shapes, verification_surfaces, and `handoff_notes.design` to choose and justify the design boundaries. Candidate work shapes are not Explorer decisions; DESIGN must make the technical choice while preserving `purpose/bundle.json.implementation_mode`, preserve observed invariants, and explain the verification plan from the evidence.

When returning the normal `design.md` candidate, match this Markdown contract:

# Design v1
## Boundaries
Describe implementation boundaries and ownership.
## Invariants
List invariants the implementation must preserve.
## Implementation Approach
Describe the technical approach.
## Unit Test Design
Describe focused unit coverage, or state why none applies.
## Integration Test Design
Describe integration coverage, or state why none applies.
## End-to-End Test Design
Describe end-to-end coverage, or state why none applies.

Normal artifacts must keep the `design.md` contract above. Control JSON
objects must be the entire response, not fenced, and not combined with artifact
content. A control JSON object must include a `schema_version` of `1`, `kind`,
and `origin_phase` matching this active worker-backed phase. A
`decision_request` also includes `reason`, `question`,
`context`, optional `options`, and an `allows_freeform` flag. A
`phase_escalation` also includes `target_phase` and `reason`.

Do not claim controller execution, test success, review approval, persistence,
phase completion, controller state mutation, or permission escalation. Do not
mutate controller state or persistence yourself; the controller validates,
records, pauses, escalates, advances, or ends the run. Stop after returning the
single artifact candidate or control JSON object.
