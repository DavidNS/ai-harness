# Stage 7: User Decisions And Escalation

Goal: make blocked runs and phase escalation first-class backend behavior.

## Actions

- Implement decision request creation as an application event and persisted
  state change.
- Implement decision answer submission through `SubmitUserDecision`.
- Implement escalation to an earlier valid phase.
- Invalidate later phase artifacts and task state through backend logic, not
  frontend logic.
- Keep all decision option validation in backend/application/domain code.

## Checkpoint

- Tests cover:
  - waiting run requires one pending decision;
  - answer id must match pending decision;
  - invalid option fails closed;
  - answer resumes at the expected target phase;
  - escalation cannot target a future phase;
  - later artifacts are invalidated when escalation rewinds state.

## Exit Criteria

- CLI v2 can display a decision request and submit an answer without reading
  raw artifact internals.

## Agent Handoff

Decision handling is backend behavior. Frontends render prompts and submit
answers; they do not decide valid targets, options, or artifact invalidation.

This stage should also decide whether retry/retry-phase belongs with escalation
or with phase failure handling, then add it to the public command contract only
with fail-closed backend semantics.
