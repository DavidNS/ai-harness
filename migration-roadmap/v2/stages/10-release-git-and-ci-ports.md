# Stage 10: Release, Git, And CI Ports

Goal: isolate release lifecycle side effects.

## Actions

- Define `GitPort`.
- Define `CIPort`.
- Move branch behavior behind `GitPort`.
- Move CI template installation and CI signal collection behind `CIPort`.
- Keep GitHub/GitLab specifics in adapters.
- Make CI artifacts available to `EXPLORE` through backend ports, not direct
  frontend access.

## Checkpoint

- Fake git/CI adapters cover branch modes and CI signal ingestion.
- Real git adapter smoke tests are controlled and do not mutate user branches
  unexpectedly.
- CI install commands remain explicit and testable.

## Exit Criteria

- v2 can connect local SDD work to trunk-based release flow through ports.

## Agent Handoff

Git and CI are release lifecycle adapters. Do not let SDD phases or frontends
shell out to git or CI tools directly.
