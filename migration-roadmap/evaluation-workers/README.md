# Evaluation Workers

This folder contains focused worker prompts for evaluating the migration against
the target architecture.

Use `migration-roadmap/evaluation-criteria.md` as the canonical source. These
worker files split that source into smaller review missions so each worker can
produce a sharper report.

Recommended execution order:

1. `01-boundaries.md`
2. `02-lifecycle.md`
3. `03-knowledge-release.md`
4. `04-contracts-hosts.md`
5. `05-migration-risk-tests.md`

Default review scope:

- `harness_v2/`
- `test_v2/`
- architecture or migration support changes related to the v2 work

All workers must:

- read `ARCHITECTURE.md`;
- read `migration-roadmap/frontend-backend-hexagonal-boundaries.md`;
- read `migration-roadmap/evaluation-criteria.md`;
- review only architecture-relevant issues;
- report concrete file and line references when possible;
- avoid naming/style preferences unless they affect architectural clarity;
- use the shared report format below.

Shared report format:

```text
Reviewed scope:
- <files or directories>

Overall assessment:
- <aligned | partially aligned | misaligned>

Criteria results:
- <criterion number>: <pass | partial | fail | not_applicable> - <short reason>

Findings:
- [<severity>] <criterion number> <file:line or symbol>
  <concrete issue>
  Impact: <why it matters architecturally>
  Suggested correction: <smallest reasonable fix>

Open questions:
- <question or none>

Migration debt accepted:
- <debt item or none>
```
