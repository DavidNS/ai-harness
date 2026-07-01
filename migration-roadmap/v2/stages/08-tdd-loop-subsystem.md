# Stage 8: TDD Loop Subsystem

Goal: migrate the TDD loop without mixing repo mutation, task state, command
execution, rollback, and review into one unbounded service.

## Actions

- Define ports for:
  - repository snapshot;
  - repository rollback;
  - command execution;
  - file operations required by the loop;
  - test result reporting.
- Model the loop as:
  - create failing test;
  - implement code;
  - run tests;
  - review;
  - iterate or escalate.
- Keep task state changes authoritative in the backend.
- Keep shell/tool execution behind `ToolRunnerPort`.

## Checkpoint

- Unit tests cover task state transitions and review verdict handling.
- Integration tests use a fixture repository and fake provider.
- Rollback is tested after failed implementation or failed validation.
- The loop never bypasses state/artifact ports for authoritative data.

## Exit Criteria

- v2 can run `TDD_BUNDLE` end-to-end in a controlled fixture repository.

## Agent Handoff

Treat this as a subsystem migration. Do not mix repository mutation, command
execution, and task state directly into the main lifecycle service.
