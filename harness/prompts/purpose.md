# Purpose Phase Prompt v1

Use only the supplied required inputs and the `purpose.json` capability manifest. The EXPLORE input is `explore/outcome_bundle.json`.
When `explorer_scope` is supplied, treat it as bounded implementation input data. Preserve each source artifact boundary; for multiple artifacts, do not collapse the scope into one vague feature. Shared infrastructure is allowed only when the relevant source artifacts remain explicit.
If controller inputs include a non-empty `repair` object, use it only to repair the artifact contract problem named by the controller while preserving the original bounded inputs.

Produce exactly one output, choosing one of:

- the normal `purpose.md` candidate matching the Markdown contract below;
- a structured `decision_request` control JSON object when user clarification or a user-facing decision is required before a valid purpose artifact can be produced;
- a structured `phase_escalation` control JSON object when an answer or counter-argument requires EXPLORE to rerun.

Use the EXPLORE outcome bundle this way:
- status `needs_clarification`: ask the most important clarification as a decision_request.
- status `problem_gathering_info`: explain the failed evidence source in a decision_request or escalate to EXPLORE if the answer can unblock evidence gathering.
- classification `improvement`: produce bounded purpose content.
- classification `limitation`: explain the blocker and ask whether to stop or reframe.
- classification `bullshit`: challenge the premise and allow counter-argument or rephrase.
- mixed entries: decide whether PURPOSE can sequence them or must ask a priority/splitting question.
- `exploration_map.handoff_notes.purpose`: use these as unresolved purpose-level questions or scope risks.
- `exploration_map.candidate_work_shapes`: treat these as neutral evidence groupings, not decisions. Use them only to frame scope options when a purpose-level choice is needed.
- `exploration_map.surfaces`, `behaviors`, `constraints`, `risks`, `unknowns`, and `verification_surfaces`: use these to keep the problem and scope evidence-backed.

When returning the normal `purpose.md` candidate, match this Markdown contract:

# Purpose v1
## Problem
Describe the problem to solve.
## Scope
Define the bounded implementation scope.
## Approach
Summarize the proposed approach.
## Exclusions
List explicit non-goals.
## Acceptance Outline
List observable acceptance expectations.

Normal artifacts must keep the `purpose.md` contract above. Control JSON objects must be the entire response, not fenced, and not combined with artifact content. A control JSON object must include a `schema_version` of `1`, `kind`, and `origin_phase` matching this active worker-backed phase. A `decision_request` also includes `reason`, `question`, `context`, optional `options`, and an `allows_freeform` flag. A `phase_escalation` also includes `target_phase` and `reason`.

Do not claim controller execution, test success, review approval, persistence, phase completion, controller state mutation, or permission escalation. Do not mutate controller state or persistence yourself; the controller validates, records, pauses, escalates, advances, or ends the run. Stop after returning the single artifact candidate or control JSON object.
