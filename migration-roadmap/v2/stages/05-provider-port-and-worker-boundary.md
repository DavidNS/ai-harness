# Stage 5: Provider Port And Worker Boundary

Goal: execute bounded AI worker tasks behind a provider port.

## Actions

- Define `ModelProviderPort` with a narrow operation for running one bounded
  prompt/task.
- Define explicit provider request data:
  - prompt text;
  - working directory;
  - model selection;
  - permission/capability projection;
  - timeout and truncation policy.
- Port a fake provider adapter first.
- Port local/scripted provider behavior next for deterministic tests.
- Port Codex and Claude CLI adapters after fake/scripted behavior is stable.
- Keep prompt assembly separate from provider process execution.
- Keep control-output parsing separate from provider invocation.

## Checkpoint

- Fake provider tests cover success, failure, timeout, and malformed output.
- Integration tests prove one phase can request a worker task and store the
  result through ports.
- Provider adapters never use shell string execution.

## Exit Criteria

- v2 can run a bounded worker task without coupling application services to a
  concrete provider.

## Agent Handoff

Do not copy the v1 provider gateway as-is. The provider adapter should run one
bounded request; orchestration, prompt assembly, and output validation stay
outside the concrete process adapter.
