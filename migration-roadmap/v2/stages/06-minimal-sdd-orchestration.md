# Stage 6: Minimal SDD Orchestration

Goal: rebuild the SDD lifecycle as application orchestration over ports.

## Actions

- Implement `EXPLORE_BUNDLE` first.
- Add bundles one at a time:
  - `PROPOSAL_BUNDLE`;
  - `SPEC_BUNDLE`;
  - `DESIGN_BUNDLE`;
  - `TASKS_BUNDLE`;
  - `TDD_BUNDLE`.
- For each bundle define:
  - inputs;
  - worker task boundaries;
  - output artifacts;
  - validation rules;
  - possible events;
  - possible user-decision requests;
  - failure behavior.
- Keep bundle internals behind application services. Frontends should only see
  commands, queries, state, and events.

## Checkpoint

For each bundle:

- Unit tests cover validation and transition behavior.
- Integration tests run the bundle with fake provider output.
- Artifacts are recorded through the artifact port.
- Resume from before and after the bundle is covered.

## Exit Criteria

- v2 can run a complete SDD lifecycle with fake/scripted providers.

## Stage 6 Deferred Behavior

- `TDD_BUNDLE` may be a tested placeholder that marks fake/scripted tasks
  complete only to prove lifecycle wiring. The real create-test, implement, run,
  review, rollback, and iterate loop belongs to Stage 8.
- Retry/retry-phase and escalation are intentionally outside the Stage 6 public
  command contract. Stage 7 owns target phase semantics and invalidation of
  later artifacts/state. Stage 6 must fail closed instead of inventing ad hoc
  backwards transitions.
- The Stage 6 SDD graph is explicitly "SDD without knowledge phases". Knowledge
  extraction, patch creation, review, and promotion are Stage 9 concerns and
  must not be implemented through placeholder worker calls in this stage.

## Agent Handoff

Port one bundle at a time. A partial SDD implementation is acceptable if each
ported bundle is complete, tested, and resumable.

When a bundle blocks for user input, create the waiting state and emit
`UserDecisionRequested` from backend orchestration/application services; do not
add a frontend command that fabricates decision requests.
