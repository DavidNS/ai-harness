# Worker 04: Contracts and Hosts

## Mission

Evaluate whether commands, queries, events, and host behavior form a shared
contract for CLI, UI, daemon, in-process execution, and tests.

Canonical criteria:

- 3. Hosts Host the Backend; They Do Not Become the Backend
- 12. Commands, Queries, and Events Are Explicit

## Required Reading

- `ARCHITECTURE.md`
- `migration-roadmap/frontend-backend-hexagonal-boundaries.md`
- `migration-roadmap/evaluation-criteria.md`

## Recommended Scope

Review:

- `harness_v2/backend/application/contracts.py` or equivalent contract modules;
- `harness_v2/backend/application/` use cases;
- `harness_v2/hosts/in_process/`;
- `harness_v2/hosts/daemon/`;
- `harness_v2/frontends/`;
- contract and host tests under `test_v2/`.

## Prioritize Findings

Report issues where:

- user intent is represented as ad hoc method calls instead of commands;
- read-only inspection mutates state or is not modeled as queries;
- progress and state changes are terminal text only instead of events;
- CLI and UI cannot share the same command/query/event contract;
- daemon or in-process hosts implement divergent lifecycle behavior;
- resume, cancel, retry, or user decision submission cannot be represented in
  the contract.

## Ignore

- missing daemon implementation when the in-process host and shared contract are
  explicit;
- missing UI rendering when UI can still consume the same contract later;
- exact event or command names if the concepts are represented clearly.

## Output

Use the shared report format from
`migration-roadmap/evaluation-workers/README.md`.
