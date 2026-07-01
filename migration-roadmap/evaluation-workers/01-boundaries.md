# Worker 01: Boundaries

## Mission

Evaluate whether the migrated files preserve the intended frontend, host,
backend, port, and adapter boundaries.

Canonical criteria:

- 1. CLI and UI Are Frontends, Not the Backend
- 2. Backend Owns Application and Domain Behavior
- 3. Hosts Host the Backend; They Do Not Become the Backend
- 4. Hexagonal Dependencies Point Inward
- 5. External Capabilities Are Behind Ports
- 15. Module Boundaries Are Clear Even If Names Differ

## Required Reading

- `ARCHITECTURE.md`
- `migration-roadmap/frontend-backend-hexagonal-boundaries.md`
- `migration-roadmap/evaluation-criteria.md`

## Recommended Scope

Review:

- `harness_v2/frontends/`
- `harness_v2/hosts/`
- `harness_v2/backend/`
- `harness_v2/adapters/`
- boundary or architecture checks under `scripts/` and `test_v2/`

## Prioritize Findings

Report issues where:

- frontend code owns lifecycle behavior or authoritative run state;
- backend/domain code imports frontends, hosts, daemon, terminal, UI, HTTP, or
  concrete adapters;
- adapters own orchestration or call back into frontends;
- hosts implement phase semantics instead of wiring and exposing backend
  services;
- application/domain code calls model, git, CI, filesystem, storage, or tool
  implementations directly;
- a module mixes rendering, orchestration, persistence, and adapter behavior in
  one role.

## Ignore

- exact directory or class names when the role and dependency direction are
  clear;
- missing future adapters when a port boundary is already explicit;
- small TODOs that do not create a dependency or ownership violation.

## Output

Use the shared report format from
`migration-roadmap/evaluation-workers/README.md`.
