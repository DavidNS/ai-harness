# Stage 0: Baseline And Cut Line

Goal: define what v1 behavior matters before building v2.

Baseline companion: [00-v1-behavior-baseline.md](00-v1-behavior-baseline.md).

Stage 0 is documentation-only. Do not create `harness_v2/` or `test_v2/` until
the v1 behavior baseline and high-risk contracts are accepted.

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
- Treat v1 argv details, wrapper flags, compatibility spellings, and exact exit
  codes as reference-only unless a later v2 stage explicitly promotes them into
  the v2 command/query contract.

## Checkpoint

- v1 architecture checker has no blocking errors.
- Existing unit tests that cover CLI/backend argv and CLI/MVU separation pass.
- A short "v1 behavior baseline" section exists in this stage or a companion
  document.

Current baseline verification:

```bash
python3 -B scripts/check_architecture.py --summary
python3 -B -m unittest tests.unit.test_architecture_contracts tests.unit.test_backend_client tests.unit.test_console_runtime_primitives tests.unit.test_state_store tests.unit.test_runtime_lock tests.integration.test_launcher tests.integration.test_decision_gates
```

The architecture checker is expected to pass with existing warnings; warnings
are not treated as Stage 0 blockers unless they become errors.

## Exit Criteria

- The team agrees that v2 may break v1 internals and argv details as long as the
  important capabilities are rebuilt and tested.

## Agent Handoff

Read [../00-context-and-rules.md](../00-context-and-rules.md) first. Do not
start creating `harness_v2/` until the baseline behaviors and high-risk v1
contracts are written down.
