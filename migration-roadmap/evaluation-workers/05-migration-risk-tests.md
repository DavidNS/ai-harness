# Worker 05: Migration Risk and Tests

## Mission

Evaluate whether the migration follows the intended extraction sequence and
whether tests protect the architectural boundaries that matter.

Canonical criteria:

- 14. Migration Follows the Clean Extraction Sequence
- supporting evidence from criteria 1-15 when tests or migration risk are
  affected

## Required Reading

- `ARCHITECTURE.md`
- `migration-roadmap/frontend-backend-hexagonal-boundaries.md`
- `migration-roadmap/evaluation-criteria.md`
- `migration-roadmap/v2/README.md`
- relevant `migration-roadmap/v2/stages/` files for the reviewed slice

## Recommended Scope

Review:

- `harness_v2/`
- `test_v2/`
- `scripts/check_architecture.py`
- `tests/unit/test_architecture_contracts.py`
- migration roadmap documents that describe the current v2 stage

## Prioritize Findings

Report issues where:

- new code wraps CLI-coupled behavior in a daemon before extracting backend
  services;
- migration adds direct CLI calls to adapters instead of introducing ports;
- UI, daemon, or tests duplicate lifecycle behavior instead of exercising the
  backend;
- compatibility layers are not clearly marked and look like permanent
  architecture;
- tests do not catch critical boundary violations such as backend-to-frontend
  imports, domain-to-adapter imports, or frontend direct adapter calls;
- tests only verify happy-path behavior while missing architectural contract
  protections.

## Ignore

- incomplete product behavior that is intentionally outside the current v2
  stage;
- tests that are narrow but correctly protect the current migration slice;
- temporary scaffolding that is explicitly documented and does not invert the
  target dependency direction.

## Output

Use the shared report format from
`migration-roadmap/evaluation-workers/README.md`.
