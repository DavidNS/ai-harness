# Stage 2: Domain Model For Runs, Phases, And Decisions

Goal: move core lifecycle concepts into v2 domain code.

## Actions

- Define v2 domain objects for:
  - run identity;
  - run status;
  - phase name;
  - strategy;
  - lifecycle graph;
  - pending decision;
  - task summary;
  - error record.
- Keep the first graph bundle-oriented:
  - `EXPLORE_BUNDLE`;
  - `PROPOSAL_BUNDLE`;
  - `SPEC_BUNDLE`;
  - `DESIGN_BUNDLE`;
  - `TASKS_BUNDLE`;
  - `TDD_BUNDLE`;
  - terminal states.
- Implement fail-closed transition validation.
- Keep phase internals out of the domain model. Domain code should know phase
  identity and legal transitions, not prompt files or provider calls.

## Checkpoint

- Unit tests cover valid transitions, invalid transitions, terminal states, and
  waiting-for-user state invariants.
- Domain tests run without importing adapters, frontends, hosts, or v1
  orchestrator modules.

## Exit Criteria

- v2 can represent a real SDD run state independently of v1 `RunState`.

## Agent Handoff

Do not port provider, prompt, artifact, or storage behavior in this stage. The
output is pure domain behavior plus tests.
