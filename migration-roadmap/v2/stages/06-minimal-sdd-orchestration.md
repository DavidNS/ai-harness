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

## Agent Handoff

Port one bundle at a time. A partial SDD implementation is acceptable if each
ported bundle is complete, tested, and resumable.
