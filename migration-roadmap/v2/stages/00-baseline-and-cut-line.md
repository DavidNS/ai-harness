# Stage 0: Baseline And Cut Line

Goal: define what v1 behavior matters before building v2.

## Actions

- Record the v1 commands and capabilities that v2 must eventually replace:
  - start run;
  - resume run;
  - answer waiting decision;
  - show status;
  - show runs;
  - archive run;
  - select route;
  - select flow;
  - run a single bundle from a previous run;
  - install CI templates;
  - install recommended packages.
- Mark the current argv contract as a reference, not as the target v2 API.
- Keep the existing tests as the baseline until v2 has equivalent coverage.
- Document current high-risk behavior:
  - `.ai-harness/artifacts` layout;
  - `state.json` shape;
  - resume validation;
  - pending decision artifacts;
  - provider command projection;
  - TDD snapshot and rollback behavior.

## Checkpoint

- v1 architecture checker has no blocking errors.
- Existing unit tests that cover CLI/backend argv and CLI/MVU separation pass.
- A short "v1 behavior baseline" section exists in this stage or a companion
  document.

## Exit Criteria

- The team agrees that v2 may break v1 internals and argv details as long as the
  important capabilities are rebuilt and tested.

## Agent Handoff

Read [../00-context-and-rules.md](../00-context-and-rules.md) first. Do not
start creating `harness_v2/` until the baseline behaviors and high-risk v1
contracts are written down.
