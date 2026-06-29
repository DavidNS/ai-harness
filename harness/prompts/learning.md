# Learning Phase Prompt v1

Use only the supplied required inputs and the `learning.json` capability
manifest. Produce exactly one output, choosing one of:

- the normal JSON learning proposal object matching the contract below;
- a structured `decision_request` control JSON object when a user decision is required before a valid artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or discovered constraint requires an earlier phase to rerun.

When returning the normal learning proposal, return one JSON object with:

- `schema_version`: exactly `1`;
- `phase`: exactly `learning`;
- `proposal_manifest`: an object with `schema_version`, `proposal_id`, `summary`, and `source_artifacts`;
- `proposed_claims`: a nonempty array of claim objects;
- `proposed_relations`: an optional array of relation objects.

Each proposed claim must include `id`, `domain`, `subjects`, `files`, `symbols`,
`claim_type`, `text`, `status`, `evidence`, `valid_from`, `valid_until`, and
`last_verified`. Supported statuses are `active`, `deprecated`, `superseded`,
`conflicted`, `unverified`, and `stale`. Claims with no repository evidence must use `unverified`. Active claims must include at least one repository-backed evidence item with `type` set to `code`, `test`, `documentation`, or `decision` and `file` set to a repository-relative path. Run artifacts, URLs, and manual evidence may explain discovery context, but they are not sufficient for active claims. Evidence objects must include `type` and one of `artifact`, `file`, or `url`; include `symbol`, `commit`, `line_start`, and `line_end` when available.

`learning_context.repository_snapshot` is bounded repository data supplied for evidence selection. Treat harness artifacts as discovery context, not repository knowledge. Propose durable facts about repository files, symbols, APIs, behaviors, constraints, dependencies, conventions, or documented decisions; do not summarize the run, task execution, phase completion, prompt behavior, review approval, or persistence events unless a repository file proves that behavior.

Return only JSON, not a code fence. Do not return Markdown for the normal
learning artifact.

Control JSON objects must be the entire response, not fenced, and not combined
with artifact content. A control JSON object must include a `schema_version` of
`1`, `kind`, and `origin_phase` matching this active worker-backed phase. A
`decision_request` also includes `reason`, `question`, `context`, optional
`options`, and an `allows_freeform` flag. A `phase_escalation` also includes
`target_phase` and `reason`.

Do not claim controller execution, test success, review approval, persistence,
phase completion, controller state mutation, or permission escalation. Do not
mutate controller state or persistence yourself; the controller validates,
records, pauses, escalates, advances, or ends the run. Stop after returning the
single artifact candidate or control JSON object.
