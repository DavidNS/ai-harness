# Test Phase Prompt v1

Use only the supplied required inputs and the `test.json` capability manifest.
If controller inputs include a non-empty `repair` object, use it only to repair the artifact contract problem named by the controller while preserving the original bounded inputs.

Produce exactly one output, choosing one of:

- the normal `tests.md` candidate matching the Markdown contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

When returning the normal `tests.md` candidate, match this Markdown contract:

# Tests v1
## Commands
List the controller-supplied or executed test commands and evidence.
## Results
Describe test results and remaining verification gaps.

Normal artifacts must keep the `tests.md` contract above. Control JSON
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
