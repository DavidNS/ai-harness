# Stage 12: UI Frontend

Goal: build a visual frontend over the daemon without duplicating backend logic.

## Actions

- Treat UI as a frontend peer to CLI.
- UI sends commands and queries to the daemon.
- UI renders state, progress, logs, decisions, and results.
- UI submits user decisions back through backend commands.
- UI does not call adapters or inspect runtime files directly.

## Checkpoint

- UI can observe a run, show phase progress, display a decision request, submit
  an answer, and show completion.
- UI behavior is backed by daemon/API tests and frontend state tests.

## Exit Criteria

- CLI and UI expose the same backend behavior through different presentation
  surfaces.

## Agent Handoff

The UI should be a presentation surface. Any backend behavior needed by the UI
should appear as commands, queries, or events.
