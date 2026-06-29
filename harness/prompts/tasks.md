# Tasks Phase Prompt v1

Use only the supplied required inputs and the `tasks.json` capability manifest.
When `explorer_scope` is supplied, treat it as bounded implementation input data. Preserve each source artifact boundary; for multiple artifacts, do not collapse the scope into one vague feature. Shared infrastructure is allowed only when the relevant source artifacts remain explicit.
If controller inputs include a non-empty `repair` object, use it only to repair the artifact contract problem named by the controller while preserving the original bounded inputs.
If controller inputs include non-empty `escalation_history`, treat it as controller feedback from later phases. Regenerate tasks to address the recorded cause, such as expanding `touched_paths`, splitting an oversized task, or correcting dependencies when a later phase reports that the current task plan cannot be implemented as scoped.

Produce exactly one output, choosing one of:

- the normal `tasks.json` candidate matching the JSON contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

When returning the normal `tasks.json` candidate, return one JSON object with:

- `schema_version`: exactly `1`.
- `phase`: exactly `tasks`.
- `tasks`: a nonempty array.
- optional `deferrals`: an array of objects with `source_artifact` and nonempty `reason`.

Each task object must include `id`, `title`, `depends_on`, `acceptance_criteria`, `touched_paths`, `focused_tests`, `broader_tests`, and `status`. For full SDD, each task must include `source_artifacts`, a nonempty list of paths from `explorer_scope`. If a source artifact is intentionally out of scope for this run, add a top-level `deferrals` entry with `source_artifact` and `reason`; do not omit it silently. `status` must be `pending`. `focused_tests` must be nonempty. `focused_tests` and `broader_tests` must contain command argument-vector arrays, never shell strings.

Normal artifacts must keep the `tasks.json` contract above. Control JSON
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
