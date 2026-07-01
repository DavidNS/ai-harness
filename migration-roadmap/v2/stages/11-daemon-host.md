# Stage 11: Daemon Host

Goal: expose the stable backend through a local host for rich interactive use.

## Actions

- Add daemon only after the in-process host is stable.
- The daemon should:
  - accept commands;
  - serve queries;
  - stream events;
  - start, resume, cancel, and inspect runs;
  - route decisions into blocked runs;
  - expose health/status;
  - enforce local process and permission boundaries.
- The daemon must not:
  - decide phase semantics;
  - implement SDD rules directly;
  - contain UI presentation state;
  - call storage, git, model, CI, or tools outside backend ports.

## Checkpoint

- The same backend command/query tests can run against in-process and daemon
  hosts.
- CLI v2 can choose in-process or daemon-backed execution.
- Event streaming is covered with deterministic tests.

## Exit Criteria

- Daemon is a host for the backend, not a second backend.

## Agent Handoff

If daemon code starts containing lifecycle rules, move those rules back into
backend application services.
