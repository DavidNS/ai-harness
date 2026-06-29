# Implement Phase Prompt v1

Use only the supplied required inputs and the `implement.json` capability manifest.
Make the requested repository changes for the supplied task only when the task can
proceed within the manifest. Produce exactly one output, choosing one of:

- the normal `implementation.md` candidate matching the Markdown contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid implementation artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

When returning the normal `implementation.md` candidate, match this Markdown contract:

# Implementation v1
## Changes
Describe the repository changes made for the task.
## Evidence
Describe evidence the controller can verify, or say that controller tests must verify it.

Normal artifacts must keep the existing `implementation.md` contract. Control JSON
objects must be the entire response, not fenced, and not combined with artifact
content. A control JSON object must include a `schema_version` of `1`, `kind`,
and `origin_phase` matching this active worker-backed phase. A
`decision_request` also includes `reason`, `question`,
`context`, optional `options`, and an `allows_freeform` flag. A
`phase_escalation` also includes `target_phase` and `reason`.

Return only one artifact candidate or control JSON object. Do not wrap it in a
code fence. Do not claim controller execution, test success, review approval,
persistence, phase completion, controller state mutation, or permission
escalation. Do not mutate controller state or persistence yourself; the
controller validates, records, pauses, escalates, advances, or ends the run. Stop
when the single output is complete.
