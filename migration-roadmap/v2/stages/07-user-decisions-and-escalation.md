# Stage 7: User Decisions And Escalation

Goal: make blocked runs and phase escalation first-class backend behavior.

## Actions

- Implement decision request creation as an application event and persisted
  state change.
- Implement decision answer submission through `SubmitUserDecision`.
- Implement targetless escalation issues and an application-owned escalation
  policy.
- Invalidate later phase artifacts and task state through backend logic, not
  frontend logic.
- Keep all decision option validation in backend/application/domain code.
- Ensure decision effects describe escalation categories, not lifecycle target
  phases.

## Checkpoint

- Tests cover:
  - waiting run requires one pending decision;
  - answer id must match pending decision;
  - invalid option fails closed;
  - escalating answer raises an issue and policy resolves it;
  - policy rejects or fails invalid rewind resolutions;
  - later artifacts are invalidated when escalation rewinds state.

## Exit Criteria

- CLI v2 can display a decision request and submit an answer without reading
  raw artifact internals.

## Agent Handoff

Decision handling is backend behavior. Frontends render prompts and submit
answers; they do not decide valid targets, options, or artifact invalidation.

Do not put `target_phase` on pending decisions or decision effects. A decision
can produce an escalation category. The orchestrator/application policy is the
only authority that can translate that category into a rewind, a user question,
a phase failure, or a continue action.

This stage should also decide whether retry/retry-phase belongs with escalation
or with phase failure handling, then add it to the public command contract only
with fail-closed backend semantics.
