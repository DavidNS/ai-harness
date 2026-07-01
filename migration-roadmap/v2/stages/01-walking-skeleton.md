# Stage 1: v2 Walking Skeleton

Goal: create the smallest executable v2 path with correct boundaries.

## Actions

- Create `harness_v2/` and `test_v2/`.
- Define backend command DTOs:
  - `StartRun`;
  - `ResumeRun`;
  - `CancelRun`;
  - `SubmitUserDecision`.
- Define backend query DTOs:
  - `GetRun`;
  - `ListRuns`;
  - `GetRunState`;
  - `GetAvailableActions`.
- Define event DTOs:
  - `RunStarted`;
  - `PhaseStarted`;
  - `PhaseCompleted`;
  - `PhaseFailed`;
  - `UserDecisionRequested`;
  - `UserDecisionReceived`;
  - `RunCompleted`;
  - `RunCancelled`.
- Implement a minimal `InProcessHost` that accepts a `StartRun` command.
- Implement a fake in-memory backend service that creates a run, emits events,
  and completes without invoking providers, git, CI, or filesystem side effects.
- Add a minimal CLI v2 entrypoint only after the in-process host works in tests.

## Checkpoint

- `test_v2/unit` proves DTO validation and event creation.
- `test_v2/integration` proves `InProcessHost -> application service -> events`.
- CLI v2 can start a simulated run and print a useful result.

## Exit Criteria

- The v2 skeleton demonstrates the intended dependency direction without
  importing v1 orchestrator code.

## Agent Handoff

This stage should produce the first real v2 files. Keep behavior fake and
in-memory until the boundary shape is proven.
