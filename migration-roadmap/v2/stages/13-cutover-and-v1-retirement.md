# Stage 13: Cutover And v1 Retirement

Goal: make v2 the real harness.

## Actions

- Replace root wrappers with v2 entrypoints.
- Decide whether v1 is archived, moved, or removed.
- Move or integrate `test_v2/` into the main test configuration.
- Update architecture checker to enforce v2 boundaries.
- Update install/uninstall/doctor scripts for v2.
- Update README and architecture docs to describe the new implementation.

## Checkpoint

- v2 unit, integration, and acceptance tests pass.
- v2 architecture checker passes.
- Smoke tests cover:
  - start;
  - resume;
  - decision answer;
  - list runs;
  - one full SDD flow with fake/scripted provider;
  - one TDD flow with fixture repository;
  - knowledge patch creation;
  - git/CI adapter smoke path.

## Exit Criteria

- v1 is no longer required for normal usage.

## Agent Handoff

Do not remove or archive v1 until v2 has demonstrated the required product
capabilities through tests and smoke flows.
