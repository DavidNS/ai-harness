# Spec Phase Prompt v1

Use only the supplied required inputs and the `spec.json` capability manifest.
When `explorer_scope` is supplied, treat it as bounded implementation input data. Preserve each source artifact boundary; for multiple artifacts, do not collapse the scope into one vague feature. Shared infrastructure is allowed only when the relevant source artifacts remain explicit.
If controller inputs include a non-empty `repair` object, use it only to repair the artifact contract problem named by the controller while preserving the original bounded inputs.

Produce exactly one output, choosing one of:

- the normal `spec.md` candidate matching the Markdown contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

When returning the normal `spec.md` candidate, match this Markdown contract:

# Spec v1
## Behavioral Requirements
List required behavior in concrete terms.
## Acceptance Criteria
List observable criteria that prove the requirements are met.

Normal artifacts must keep the `spec.md` contract above. Control JSON
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
