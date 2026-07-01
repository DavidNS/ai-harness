# Worker 03: Knowledge and Release

## Mission

Evaluate whether the migrated files preserve the target knowledge lifecycle and
release lifecycle.

Canonical criteria:

- 9. Learning Produces Knowledge Patches, Not Direct Truth Mutation
- 10. Knowledge Is Regenerative
- 11. Release Lifecycle Uses Trunk-Based Flow and CI Artifacts

## Required Reading

- `ARCHITECTURE.md`
- `migration-roadmap/frontend-backend-hexagonal-boundaries.md`
- `migration-roadmap/evaluation-criteria.md`

## Recommended Scope

Review:

- `harness_v2/backend/domain/knowledge` or equivalent knowledge modules;
- `harness_v2/backend/application/` knowledge and release services;
- `harness_v2/backend/ports/` knowledge, git, and CI ports;
- `harness_v2/adapters/` storage, git, CI, and filesystem modules;
- knowledge/release tests under `test_v2/`.

## Prioritize Findings

Report issues where:

- knowledge extraction writes learned facts directly into accepted source of
  truth files;
- knowledge patches are transient logs instead of permanent candidate
  artifacts;
- promotion from knowledge patch to source of truth is implicit, or missing from
  a slice that claims to implement promotion;
- local agents DB or human knowledge files are treated as authoritative truth
  instead of generated views;
- CI artifacts, feature branches, merge requests, or main-branch artifact
  refresh are implemented outside backend ports or ignored by design.

## Ignore

- absent full knowledge implementation when the reviewed slice does not touch
  knowledge or release behavior;
- absent KP-to-SOT, SOT-to-local-agents-DB, or SOT-to-human-knowledge-file
  workflows when reviewing the v2 Stage 9 candidate-patch slice;
- placeholder ports that are intentionally empty but preserve the boundary;
- release workflow gaps documented as future stages, unless new code actively
  contradicts the target flow.

## Output

Use the shared report format from
`migration-roadmap/evaluation-workers/README.md`.
