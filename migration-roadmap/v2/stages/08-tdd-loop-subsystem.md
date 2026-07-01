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
- Escalation from the loop must be descriptive, not imperative. The TDD loop may
  raise categories such as `TASK_PLAN_GAP`, `DESIGN_GAP`,
  `IMPLEMENTATION_BLOCKED`, or `VALIDATION_BLOCKED`, but it must not choose the
  lifecycle phase to resume.
- Keep task state changes authoritative in the backend.
- Keep shell/tool execution behind `ToolRunnerPort`.

## Implementation Notes

- Repository mutation remains opt-in: `BundleRuntimeConfig.allow_repository_mutation`
  defaults to disabled for normal in-process/CLI composition. Without explicit
  permission, `TDD_BUNDLE` raises `VALIDATION_BLOCKED`.
- CLI opt-in is explicit through `--allow-repository-mutation` and
  `--working-directory PATH`; callers must choose the workspace that TDD may
  mutate.
- TDD worker capability manifests use repository-wide write (`**`) because the
  current CLI provider can only project repo-wide read/write modes. Backend
  safety is enforced after each attempt with snapshot, diff, `touched_paths`,
  rollback, and escalation.

## Scope Boundary

Stage 8 migrates the TDD subsystem boundary and backend behavior. It does not
try to solve real-provider security or real-provider E2E validation.

In scope for Stage 8:

- `TDD_BUNDLE` runs through backend/application code instead of a placeholder;
- repository mutation is explicitly opt-in and tied to a chosen working
  directory;
- TDD workers may receive repo-wide write capability because the current CLI
  provider can only project repo-wide read/write modes;
- backend code captures snapshots, observes diffs, validates `touched_paths`,
  rolls back failed attempts, records evidence artifacts, and escalates by
  category;
- tests use fake/scripted providers and fixture repositories only.

Out of scope for Stage 8 and for migration acceptance:

- granular write permissions per task/path for Codex or Claude;
- OS sandboxing, provider credential isolation, or production security policy;
- automated E2E tests that execute real Codex or Claude CLIs;
- proving that real providers respect `touched_paths` before backend diff
  validation;
- replacing the repo-wide write projection with a patch protocol or dynamic
  capability projection.

## Checkpoint

- Unit tests cover task state transitions and review verdict handling.
- Integration tests use a fixture repository and fake provider.
- Rollback is tested after failed implementation or failed validation.
- The loop never bypasses state/artifact ports for authoritative data.
- Escalation tests assert that TDD raises an `EscalationIssue` and the
  application policy resolves the transition.

## Exit Criteria

- v2 can run `TDD_BUNDLE` end-to-end in a controlled fixture repository.

## Agent Handoff

Treat this as a subsystem migration. Do not mix repository mutation, command
execution, and task state directly into the main lifecycle service.

Do not let TDD decide whether a failure belongs to SPEC, DESIGN, TASKS, user
input, or phase failure. TDD owns evidence and rollback for its attempt; the
orchestrator/application policy owns lifecycle recovery.
